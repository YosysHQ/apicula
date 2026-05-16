import argparse
import importlib.resources
import itertools
import json
import re

from apycula import bitmatrix
from apycula import bslib
from apycula import chipdb
from apycula.chipdb import add_attr_val, get_shortval_fuses, get_longval_fuses, \
                           get_bank_fuses, get_bank_io_fuses, get_long_fuses, load_chipdb, Tile, Coord
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

    def get_compress(self) -> bool:
        return self.args.compress

    def get_output_filename(self) -> str:
        return self.args.output

    # debug
    def __repr__(self):
        return f'args:{self.args}, device:{self.device}'

################################################################
@dataclass(frozen = True)
class PipDesc:
    """ One PIP  """
    x: int
    y: int
    src: str
    dest: str

    # debug
    def __repr__(self):
        return f'x:{self.x}, y:{self.y}, src:{self.src}, dest:{self.dest}'

################################################################
@dataclass(frozen = True)
class WireDesc:
    """ One wire """
    x: int
    y: int
    name: str

    # debug
    def __repr__(self):
        return f'x:{self.x}, y:{self.y}, name:{self.name}'

################################################################
@dataclass(frozen = True)
class CellDesc:
    """ One Cell """
    name: str
    typ: str
    parms: dict[str, str]
    attrs: dict[str, str]

    # debug
    def __repr__(self):
        return f'name:{self.name}, typ:{self.typ}, parms:{self.parms}, attrs:{self.attrs}'

################################################################
@dataclass(frozen = True)
class BelDesc:
    """ One Bel """
    x: int
    y: int
    idx: str
    cell: CellDesc

    # debug
    def __repr__(self):
        return f'x:{self.x}, y:{self.y}, idx:{self.idx}, cell:{self.cell}'

################################################################
@dataclass(frozen = True)
class CellFuseBits:
    """ Bits to set in one cell """
    x: int
    y: int
    bits: list[Coord]

    def __init__(self, x: int, y: int, bits: set[Coord]):
        object.__setattr__(self, 'x', x)
        object.__setattr__(self, 'y', y)
        object.__setattr__(self, 'bits', list(bits))

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

    def get_cell_data(self, name: str) -> dict:
        """ Return cell data values """
        return self.in_file['modules'][self.top_module_name]['cells'][name]

    def fill_cell_desc(self, name: str, cell_data: dict) -> CellDesc:
        """ Fill cell description """
        return CellDesc(name, cell_data['type'], cell_data['parameters'], cell_data['attributes'])

    def get_cell(self, name: str) -> CellDesc:
        """ Get cell desc by name """
        return self.fill_cell_desc(name, self.et_cell_data(name))

    def get_pips(self) -> Iterator[PipDesc]:
        """ Pip generator """
        pipre = re.compile(r"X(\d+)Y(\d+)/([\w_]+)/([\w_]+)")
        for net in self.in_file['modules'][self.top_module_name]['netnames'].values():
            routing = net['attributes']['ROUTING']
            pips = routing.split(';')[1::3]
            for pip in pips:
                res = pipre.fullmatch(pip) # ignore alias
                if res:
                    col, row, dest, src = res.groups()
                    # nextpnr creates the passtrough LUTs by itself, so skip such pips
                    if dest.startswith('XD') and src.startswith('F'):
                        continue
                    yield PipDesc(int(col), int(row), src, dest)
                elif pip and "DUMMY" not in pip:
                    raise Exception("Invalid pip:", pip)

    def is_gnd_vcc_bel(self, bel_attr: str) -> bool:
        return bel_attr in {"VCC", "GND"} or bel_attr[-4:] in {"/GND", "/VCC"}

    def get_bels(self) -> Iterator[BelDesc]:
        """ Bel generator """
        # differencial IOs do not define the IOSTD for the bank; they merely modify it.
        # Therefore, we will postpone their generation until after normal IOs, once the standard has been clarified.
        yield_later = []

        belre = re.compile(r"X(\d+)Y(\d+)/(?:GSR|LUT|DFF|IOB|MUX|ALU|ODDR|OSC[ZFHWOA]?|BUF[GS]|RAM16SDP4|RAM16SDP2|RAM16SDP1|PLL|IOLOGIC|CLKDIV2|CLKDIV|BSRAM|ALU|MULTALU18X18|MULTALU27X18|MULTALU36X18|MULTADDALU18X18|MULTADDALU12X12|MULT36X36|MULT18X18|MULT12X12|MULT9X9|PADD18|PADD9|BANDGAP|DQCE|DCS|USERFLASH|EMCU|DHCEN|MIPI_OBUF|MIPI_IBUF|DLLDLY|PINCFG|PLLA|ADC)(\w*)")
        for cell_name, cell_data in self.in_file['modules'][self.top_module_name]['cells'].items():
            cell = self.fill_cell_desc(cell_name, cell_data)
            bel_attr = cell.attrs.get('NEXTPNR_BEL')
            if not bel_attr or self.is_gnd_vcc_bel(bel_attr):
                continue
            bel_groups = belre.match(bel_attr)
            if not bel_groups:
                raise Exception(f"Unknown bel:{bel_attr} for cell {cell.name}")
            col, row, idx = bel_groups.groups()
            x = int(col)
            y = int(row)
            bel = BelDesc(x, y, idx, cell)
            if 'DIFF' in cell.attrs:
                yield_later.append(bel)
            else:
                yield bel

        for bel in yield_later:
            yield bel

    def get_wires_to_isolate(self) -> Iterator[WireDesc]:
        """ Generate segment wires to isolate """
        wire_re = re.compile(r"X(\d+)Y(\d+)/([\w]+)")
        for net in self.in_file['modules'][self.top_module_name]['netnames'].values():
            val = net['attributes'].get('SEG_WIRES_TO_ISOLATE')
            if not val:
                continue
            wires = val.split(';')
            for wire_ex in wires:
                if not wire_ex:
                    continue
                res = wire_re.fullmatch(wire_ex)
                if res:
                    col, row, wire = res.groups()
                    yield WireDesc(int(col), int(row), wire)
                else:
                    raise Exception(f"Invalid isolated wire:{wire_ex}")

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

    def get_hdr(self):
        """ Bitstream header """
        return self.db.cmd_hdr

    def get_ftr(self):
        """ Bitstream footer """
        return self.db.cmd_ftr

    def create_main_tilemap(self) -> dict:
        """ Return chip tilemap """
        return chipdb.tile_bitmap(self.db, bitmatrix.zeros(self.db.height, self.db.width), empty=True)

    def fuse_bitmap(self, tilemap) -> dict:
        """ Tilemap -> Bitmap """
        return chipdb.fuse_bitmap(self.db, tilemap)

    def get_tiledata(self, x: int, y: int) -> Tile:
        """ Get one cell description """
        return self.db[y, x]

    def get_clock_pips(self, tiledata: Tile) -> dict[str, dict[str, set[Coord]]]:
        return tiledata.clock_pips

    def get_pips(self, tiledata: Tile) -> dict[str, dict[str, set[Coord]]]:
        return tiledata.pips

    def get_alonenode(self, tiledata: Tile) -> dict[str, list[tuple[set[str], set[Coord]]]]:
        return tiledata.alonenode

    def get_alonenode6(self, tiledata: Tile) -> dict[str, list[tuple[set[str], set[Coord]]]]:
        return tiledata.alonenode_6

    def get_const_fuses(self, x: int, y: int) -> set[Coord]:
        return self.db.const.get(self.db.grid[y][x], set())

    @property
    def rows(self):
        return self.db.rows

    @property
    def cols(self):
        return self.db.cols

    # debug
    def __repr__(self):
        return f'db name:{self.device_name}, rows:{self.rows}, cols:{self.cols}'

################################################################
class Device:
    """ Base chip. The fuses for a specific chip are set in a class that inherits from this one. """
    def __init__(self, cli_args: CliArgs, pnr: Netlist):
        device_name = cli_args.get_device()
        if not device_name:
            device_name = pnr.get_device()
        self.chipdb = ChipDB(device_name)

    def get_hdr(self):
        """ Bitstream header """
        return self.chipdb.get_hdr()

    def get_ftr(self):
        """ Bitstream footer """
        return self.chipdb.get_ftr()

    def create_main_tilemap(self) -> dict:
        """ Return chip tilemap """
        return self.chipdb.create_main_tilemap()

    def fuse_bitmap(self, tilemap) -> dict:
        """ Tilemap -> Bitmap """
        return self.chipdb.fuse_bitmap(tilemap)

    def is_clock_pip(self, tiledata: Tile, src: str, dest: str) -> bool:
        return dest in self.chipdb.get_clock_pips(tiledata)

    def is_hclk_pip(self, tiledata: Tile, src: str, dest: str) -> bool:
        return dest in {'FCLKA', 'FCLKB'}

    def get_simple_pip_fuses(self, tiledata: Tile, src: str, dest: str) -> set[Coord]:
        """ Return fuses for the simple PIP """
        return self.chipdb.get_pips(tiledata)[dest][src]

    def get_simple_clock_pip_fuses(self, tiledata: Tile, src: str, dest: str) -> set[Coord]:
        """ Return fuses for the simple clock PIP """
        return self.chipdb.get_clock_pips(tiledata)[dest][src]

    def get_alonenode_fuses(self, tiledata: Tile, src: str, dest: str) -> set[Coord]:
        """ Return fuses if pip's dest is not connected to srcs listen in the alonenode table """
        fuses = set()
        alonenode = self.chipdb.get_alonenode(tiledata)
        for srcs_bits in alonenode.get(dest, []):
            srcs, bits = srcs_bits
            if src not in srcs:
                fuses |= bits
        return fuses

    def get_all_pips_fuses(self, pips: Iterator[PipDesc]) -> list[CellFuseBits]:
        """ Return fuses for all PIPs """
        fuses = []
        for pip in pips:
            tiledata = self.chipdb.get_tiledata(pip.x, pip.y)
            if self.is_hclk_pip(tiledata, pip.src, pip.dest):
                continue
            if self.is_clock_pip(tiledata, pip.src, pip.dest):
                bits = self.get_simple_clock_pip_fuses(tiledata, pip.src, pip.dest)
                if bits:
                    fuses.append(CellFuseBits(pip.x, pip.y, bits))
            else:
                bits = self.get_simple_pip_fuses(tiledata, pip.src, pip.dest)
                bits |= self.get_alonenode_fuses(tiledata, pip.src, pip.dest)
                if bits:
                    fuses.append(CellFuseBits(pip.x, pip.y, bits))
        return fuses

    def get_isolated_wires(self, wires: Iterator[WireDesc]) -> list[CellFuseBits]:
        """ Return fuses for all isolated wires """
        fuses = []
        for wire in wires:
            tiledata = self.chipdb.get_tiledata(wire.x, wire.y)
            alonenode6 = self.chipdb.get_alonenode6(tiledata)
            if wire.name not in alonenode6:
                raise Exception(f"Wire X{wire.x}Y{wire.y}/{wire.name} is not in alonenode fuse table")
            if len(alonenode6[wire.name]) != 1:
                raise Exception(f"Incorrect alonenode fuse table for X{wire.x}Y{wire.y}/{wire.name}")
            bits = alonenode6[wire.name][0][1]
            if bits:
                fuses.append(CellFuseBits(wire.x, wire.y, bits))
        return fuses

    def get_all_cons_fuses(self) -> list[CellFuseBits]:
        """ Always set fuses """
        fuses = []
        for x, y in itertools.product(range(self.chipdb.cols), range(self.chipdb.rows)):
            bits = self.chipdb.get_const_fuses(x, y)
            if bits:
                fuses.append(CellFuseBits(x, y, bits))
        return fuses

    # debug
    def __repr__(self):
        return f'db:{self.chipdb}'

################################################################
class Bitstream:
    """ Output bitstream. Base class """
    def __init__(self, cli_args: CliArgs, device: Device):
        self.output_name = cli_args.get_output_filename()
        self.compress = cli_args.get_compress()
        self.device = device
        self.main_tilemap = device.create_main_tilemap()
        self.header = device.get_hdr()
        self.footer = device.get_ftr()
        self.init_bsram = False

    def set_fuses(self, fuses: list[CellFuseBits]):
        """ Set bits in all cells """
        for cell in fuses:
            tile = self.main_tilemap[cell.y, cell.x]
            for row, col in cell.bits:
                tile[row][col] = 1

    def fill_header_footer(self, bs):
        """
        Generate fs header and footer
        Currently limited to checksum with
        CRC_check and security_bit_enable set
        """
        # configuration data checksum is computed on all
        # data in 16bit format
        bs = bitmatrix.fliplr(bs)
        bs = bitmatrix.packbits(bs)

        res = int(bitmatrix.bsum(bs[0::2]) * pow(2,8) + bitmatrix.bsum(bs[1::2]))
        checksum = res & 0xffff
        # set the checksum
        self.footer[1] = bytearray.fromhex(f"{0x0A << 56 | checksum:016x}")

    def write(self):
        """ Write bitsream to file """
        main_map = self.device.fuse_bitmap(self.main_tilemap)
        self.fill_header_footer(main_map)

        bslib.write_bitstream(self.output_name, main_map, self.header, self.footer, self.compress, extra_slots = {})

    # debug
    def __repr__(self):
        return f'output_name:{self.output_name}, compress:{self.compress}, init_bsram:{self.init_bsram}, header:{self.header}, footer:{self.footer}'

################################################################
class Pack:
    """ The packing process """
    def __init__(self, cli_args: CliArgs, pnr: Netlist, device: Device):
        self.device = device
        self.pnr = pnr
        self.fuses = []

    def route(self):
        """ Set fuses for all pips """
        self.fuses += self.device.get_all_pips_fuses(self.pnr.get_pips())
        # isolate segment wires used
        self.fuses += self.device.get_isolated_wires(self.pnr.get_wires_to_isolate())

    def place(self):
        """ Set fuses for Bels """
        for bel in self.pnr.get_bels():
            print(bel)

    def set_const_fuses(self):
        """ Set fuses that must always be in place """
        self.fuses += self.device.get_all_cons_fuses()

    def get_fuses(self) -> list[CellFuseBits]:
        """ Return generated fuses """
        return self.fuses

    # debug
    def __repr__(self):
        return f'device:{self.device}, pnr:{self.pnr}'

################################################################
def create_device(cli_args: CliArgs, pnr: Netlist) -> Device:
    return Device(cli_args, pnr)

def create_output_bitstream(cli_args: CliArgs, device: Device) -> Bitstream:
    return Bitstream(cli_args, device)

def main():
    cli_args = CliArgs()
    pnr = Netlist(cli_args)
    device = create_device(cli_args, pnr)
    output = create_output_bitstream(cli_args, device)

    pack = Pack(cli_args, pnr, device)
    pack.route()
    pack.set_const_fuses()
    pack.place()

    fuses = pack.get_fuses()
    output.set_fuses(fuses)
    import ipdb; ipdb.set_trace()
    output.write()


if __name__ == '__main__':
    main()

# vim: set et sw=4 ts=4:
