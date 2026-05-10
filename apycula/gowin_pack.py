import argparse
import importlib.resources
import json
import re

from apycula.chipdb import add_attr_val, get_shortval_fuses, get_longval_fuses, get_bank_fuses, get_bank_io_fuses, get_long_fuses, load_chipdb
from collections.abc import Iterator
from dataclasses import dataclass

################################################################
class CliArgs:
    """ Parses the command line. """
    def __init__(self):
        parser = argparse.ArgumentParser(description='Pack Gowin bitstream')
        parser.add_argument('netlist')
        parser.add_argument('-d', '--device', default = None)
        parser.add_argument('-o', '--output', default='pack.fs')
        parser.add_argument('-c', '--compress', action='store_true')
        parser.add_argument('-s', '--cst', default = None)
        parser.add_argument('--jtag_as_gpio', action = 'store_true')
        parser.add_argument('--sspi_as_gpio', action = 'store_true')
        parser.add_argument('--mspi_as_gpio', action = 'store_true')
        parser.add_argument('--ready_as_gpio', action = 'store_true')
        parser.add_argument('--done_as_gpio', action = 'store_true')
        parser.add_argument('--reconfign_as_gpio', action = 'store_true')
        parser.add_argument('--cpu_as_gpio', action = 'store_true')
        parser.add_argument('--i2c_as_gpio', action = 'store_true')

        self.args = parser.parse_args()

        # For tool integration it is allowed to pass a full part number
        self.device = self.args.device
        if self.args.device:
            m = re.match("(GW..)(S|Z)?[A-Z]*-(LV|UV|UX)([0-9]{1,2})C?([A-Z]{2}[0-9]+P?)(C[0-9]/I[0-9])", self.args.device)
            if m:
                series = m.group(1)
                mods = m.group(2) or ""
                num = m.group(4)
                self.device = f"{series}{mods}-{num}"

    def get_netlist_filename(self) -> str:
        return self.args.netlist

    def get_device(self) -> str:
        """ Parsed chip name """
        return self.device

    # debug
    def __repr__(self):
        return f'args:{self.args}, device:{self.device}'

################################################################
@dataclass(frozen = True)
class PipDesc:
    x: int
    y: int
    src: str
    dest: str

################################################################
class Netlist:
    """ P&R json file """
    def __init__(self, cli_args: CliArgs):
        with open(cli_args.get_netlist_filename()) as f:
            self.in_file = json.load(f)
        # find top module
        assert len(self.in_file['modules']) == 1
        self.top_module_name = next(iter(self.in_file['modules']))

        # check for used chipdb
        cli_device = cli_args.get_device()
        pnr_device = self.get_device()
        if cli_device and cli_device != pnr_device:
            raise Exception(f"The netlist was generated for chip {pnr_device}, but chip {cli_device} is specified in the command line.")

    def get_device(self) -> str:
        """ The chip specified in the netlist """
        return self.in_file['modules'][self.top_module_name]['settings']['packer.chipdb']

    def get_pips(self) -> Iterator[PipDesc]:
        """ Pips generator """
        pipre = re.compile(r"X(\d+)Y(\d+)/([\w_]+)/([\w_]+)")
        for net in self.in_file['modules'][self.top_module_name]['netnames'].values():
            routing = net['attributes']['ROUTING']
            pips = routing.split(';')[1::3]
            for pip in pips:
                res = pipre.fullmatch(pip) # ignore alias
                if res:
                    col, row, dest, src = res.groups()
                    yield PipDesc(row, col, src, dest)
                elif pip and "DUMMY" not in pip:
                    raise Exception("Invalid pip:", pip)

    # debug
    def __repr__(self):
        return f'in_file:{self.in_file}, top_module_name:{self.top_module_name}'

################################################################
class ChipDB:
    """ Chip database interface """
    def __init__(self, device_name: str):
        self.device_name = device_name
        with importlib.resources.path('apycula', f'{self.device_name}.msgpack.xz') as path:
            self.db = load_chipdb(path)

    # debug
    def __repr__(self):
        return f'db name:{self.device_name}'

################################################################
class Device:
    """ Base chip """
    def __init__(self, cli_args: CliArgs, pnr: Netlist):
        device_name = cli_args.get_device()
        if not device_name:
            device_name = pnr.get_device()
        self.chipdb = ChipDB(device_name)

    def get_pip_fuses(self, pips: list[PipDesc]):
        for pip in pips:
            print(pip.x, pip.y, pip.src, pip.dest)

    # debug
    def __repr__(self):
        return f'db:{self.chipdb}'

################################################################
class Pack:
    """ The packing process """
    def __init__(self, cli_args: CliArgs, pnr: Netlist, device: Device):
        self.device = device
        self.pnr = pnr

    def route(self):
        """ Set fuses for all pips """
        fuses = self.device.get_pip_fuses(self.pnr.get_pips())

    # debug
    def __repr__(self):
        return f'device:{self.device}, pnr:{self.pnr}'

################################################################
def create_device(cli_args: CliArgs, pnr: Netlist) -> Device:
    return Device(cli_args, pnr)

def main():
    cli_args = CliArgs()
    pnr = Netlist(cli_args)
    device = create_device(cli_args, pnr)

    pack = Pack(cli_args, pnr, device)
    pack.route()

    import ipdb; ipdb.set_trace()

if __name__ == '__main__':
    main()

# vim: set et sw=4 ts=4:
