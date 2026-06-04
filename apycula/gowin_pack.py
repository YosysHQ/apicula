import argparse
import importlib.resources
import itertools
import json
import re

from apycula import attrids
from apycula import bitmatrix
from apycula import bslib
from apycula import chipdb
from apycula.chipdb import add_attr_val, get_shortval_fuses, get_longval_fuses, \
                           get_bank_fuses, get_bank_io_fuses, get_long_fuses, load_chipdb, Tile, Coord
from collections.abc import Iterator
from dataclasses import dataclass
from types import FunctionType

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
class AttrVal:
    attr: str
    val: str

    # debug
    def __repr__(self):
        return f'attr:{self.attr}, val:{self.val}'

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
    idx_str: str
    idx_int: int # to avoid having to convert to a number every time it's needed
    cell: CellDesc

    def __init__(self, x: int, y: int, idx: str, cell: CellDesc):
        object.__setattr__(self, 'x', x)
        object.__setattr__(self, 'y', y)
        object.__setattr__(self, 'cell', cell)
        object.__setattr__(self, 'idx_str', idx)
        try:
            object.__setattr__(self, 'idx_int', int(idx))
        except ValueError:
            object.__setattr__(self, 'idx_int', -1)

    def is_diff_io(self) -> bool:
        return 'DIFF' in self.cell.parms

    # debug
    def __repr__(self):
        return f'x:{self.x}, y:{self.y}, idx_str:{self.idx_str}, idx_int:{self.idx_int}, cell:{self.cell}'

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
@dataclass(frozen = True)
class IoCfg:
    """ Alternate IO configurations """
    x: int
    y: int
    idx_str: str
    cfgs: set[str]

    # debug
    def __repr__(self):
        return f'x:{self.x}, y:{self.y}, idx_str:{self.idx_str}, cfgs:{self.cfgs}'

################################################################
@dataclass(frozen = True)
class IoDiffCfg:
    """ Differential IO configuration """
    positive: bool
    true_lvds: bool

    # debug
    def __repr__(self):
        return f'positive:{self.positive}, true_lvds:{self.true_lvds}'

################################################################
def _convert_legacy_io_cell_attr(attr: str, val: str) -> tuple[str, str]:
    """ Convert legacy '&IO_TYPE=LVCMOS33' style attributes to name-value pairs """
    if attr[0] != '&':
        return (attr, val)
    name_val = attr.split('=')
    return (name_val[0][1:], name_val[1])

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
        return self.fill_cell_desc(name, self.get_cell_data(name))

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

    def io_loc_from_str_to_xyidx(self, io_loc: str) -> tuple[int, int, str]:
        side = io_loc[2]
        num = io_loc[3:-1]
        idx_str = io_loc[-1]
        if side == 'T':
            row = 0
            col = int(num) - 1
        elif side == 'B':
            row = self.rows - 1
            col = int(num) - 1
        elif side == 'L':
            row = int(num) - 1
            col = 0
        elif side == 'R':
            row = int(num) - 1
            col = self.cols - 1
        return (col, row, idx_str)

    def get_ttyp(self, x: int, y: int) -> int:
        return self.db.grid[y][x]

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

    def get_lut_data(self, x: int, y: int, idx: int) -> dict[int, set[Coord]]:
        """ Return LUT encoding """
        return self.get_tiledata(x, y).bels[f'LUT{idx}'].flags

    def get_alu_modes(self, x: int, y: int, idx: int) -> dict[int, set[Coord]]:
        return self.get_tiledata(x, y).bels[f'ALU{idx}'].modes

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

    def get_slice_attr_val(self, attrval: AttrVal, av: set[tuple[int, int]]):
        add_attr_val(self.db, 'SLICE', av, attrids.cls_attrids[attrval.attr], attrids.cls_attrvals[attrval.val])

    def get_slice_fuses(self, x: int, y: int, idx: int, av: set[tuple[int, int]]) -> set[Coord]:
        return get_shortval_fuses(self.db, self.db.grid[y][x], av, f'CLS{idx}')

    def get_gsr_attr_val(self, attrval: AttrVal, av: set[tuple[int, int]]):
        add_attr_val(self.db, 'GSR', av, attrids.gsr_attrids[attrval.attr], attrids.gsr_attrvals[attrval.val])

    def get_gsr_fuses(self, x: int, y: int, av: set[tuple[int, int]]) -> set[Coord]:
        return get_shortval_fuses(self.db, self.db.grid[y][x], av, 'GSR')

    def get_cfg_attr_val(self, attrval: AttrVal, av: set[tuple[int, int]]):
        add_attr_val(self.db, 'CFG', av, attrids.cfg_attrids[attrval.attr], attrids.cfg_attrvals[attrval.val])

    def get_cfg_fuses(self, x: int, y: int, av: set[tuple[int, int]]) -> set[Coord]:
        return get_shortval_fuses(self.db, self.db.grid[y][x], av, 'CFG')

    def get_bank_attr_val(self, attrval: AttrVal, av: set[tuple[int, int]]):
        add_attr_val(self.db, 'IOB', av, attrids.iob_attrids[attrval.attr], attrids.iob_attrvals[attrval.val])

    def get_bank_fuses(self, x: int, y: int, av: set[tuple[int, int]], bank_idx: int) -> set[Coord]:
        return get_bank_fuses(self.db, self.db.grid[y][x], av, 'BANK', bank_idx)

    def get_bank_io_fuses(self, x: int, y: int, av: set[tuple[int, int]]) -> set[Coord]:
        """ XXX Prior to the 5A series, I/O could not be located in the same
        cell as bank control bits, but this has changed in the 5A
        series. The feature remains for now, but further research is needed on
        the coexistence of banks and I/O. """
        return get_bank_io_fuses(self.db, self.db.grid[y][x], av)

    def get_iob_attr_val(self, attrval: AttrVal, av: set[tuple[int, int]]):
        add_attr_val(self.db, 'IOB', av, attrids.iob_attrids[attrval.attr], attrids.iob_attrvals[attrval.val])

    def get_io_diff_cfg(self, x: int, y: int, idx_str: str) -> IoDiffCfg:
        bel = self.get_tiledata(x, y).bels[f'IOB{idx_str}']
        if not bel.is_diff:
            return None
        return IoDiffCfg(bool(bel.is_diff_p), bool(bel.is_true_lvds))

    def get_iob_fuses(self, x: int, y: int, av: set[tuple[int, int]], idx_str: str) -> set[Coord]:
        return get_longval_fuses(self.db, self.db.grid[y][x], av, f'IOB{idx_str}')

    def get_io_cfgs(self) -> Iterator[IoCfg]:
        """ Alternate IO configuration iterator """
        for loc, cfgs in self.db.io_cfg.items():
            x, y, idx_str = self.io_loc_from_str_to_xyidx(loc)
            yield IoCfg(x, y, idx_str, cfgs)

    def get_loc_bank(self, x: int, y: int) -> int:
        """ Bank for IO location  """
        try:
            return chipdb.loc2bank(self.db, y, x)
        except KeyError:
            return -1

    def get_bank_x_y(self, bank_idx: int) -> tuple[int, int]:
        """ Get x and y of the bank cell """
        # swap row, col to x, y
        tile = self.db.bank_tiles[bank_idx]
        return (tile[1], tile[0])

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
class UsedSlices:
    """ Tracking used slices for processing at the final stage.
        Slice or two LUTs and two DFFs have fuses that are set if some
        attribute is not specified, making it difficult to obtain the fuse bits
        immediately — you have to assemble the complete slices and only then
        request the fuse bits once all the necessary attributes are set.  """
    def __init__(self):
        # {(x, y, slice_idx): (has_dff0, has_dff1, [AttrVal])}
        # We use a simple tuple as the key for performance reasons—LUTs and
        # DFFs make up the bulk of the design, so the dictionary will be large
        # and the key needs to be simple.
        self.backet = {}

    def add_slice_attrs(self, x: int, y: int, idx: int, has_dff_0: bool, has_dff_1: bool, attr_vals: list[AttrVal]):
        """ Set slice attributes """
        has_dff0, has_dff1, sl_attrvals = self.backet.setdefault((x, y, idx), (False, False, []))
        sl_attrvals += attr_vals
        self.backet[x, y, idx] = (has_dff0 or has_dff_0, has_dff1 or has_dff_1, sl_attrvals)

    def enumerate(self):
        for x_y_idx, attr_vals in self.backet.items():
            yield (x_y_idx, attr_vals)

    # debug
    def __repr__(self):
        return f'backet:{self.backet}'

################################################################
class BankDesc:
    """ IO bank """
    _vcc_ios = {'LVCMOS10': '1.0', 'LVCMOS12': '1.2', 'LVCMOS15': '1.5', 'LVCMOS18': '1.8', 'LVCMOS25': '2.5',
                'LVCMOS33': '3.3', 'LVDS25': '2.5', 'LVCMOS33D': '3.3', 'LVCMOS_D': '3.3', 'MIPI': '1.2',
                'SSTL15': '1.5', 'SSTL18_I': '1.8', 'SSTL18_II': '1.8', 'SSTL25_I': '2.5', 'SSTL25_II': '2.5',
                'SSTL33_I': '3.3', 'SSTL33_II': '3.3', 'SSTL15D': '1.5', 'SSTL18D_I': '1.8', 'SSTL18D_II': '1.8',
                'SSTL25D_I': '2.5', 'SSTL25D_II': '2.5', 'SSTL33D_I': '3.3', 'SSTL33D_II': '3.3'}

    def __init__(self):
        self.x, self.y = None, None
        # Bank has regular output bels such as OBUF, IOBUF etc (not LVDS)
        self.has_outputs = False
        self.attrs = {}
        self.bels = []
        # For diagnostic messages, we record the I/O pin that caused a voltage to be applied to the bank.
        # { attr: bel }
        self.set_attr_bels = {}

    @property
    def is_used(self) -> bool:
        return bool(self.bels)

    @property
    def io_type(self) -> str:
        return self.attrs.get("IO_TYPE")

    @property
    def bank_vccio(self) -> str:
        return self.attrs.get("BANK_VCCIO")

    def set_x_y(self, x: int, y: int):
        """ Set bank cell location """
        self.x = x
        self.y = y

    def set_attr(self, attr: str, val: str):
        self.attrs[attr] = val

    def set_bank_vccio_by_io_type(self, io_type: str):
        self.attrs['BANK_VCCIO'] = self._vcc_ios[io_type]

    def check_or_set_attr(self, bel: BelDesc, attr: str):
        """ Set bank attr or check for conflict """
        new_val = bel.cell.attrs.get(attr)
        if new_val:
            if not self.set_attr_bels.get(attr):
                self.set_attr_bels[attr] = bel
                self.attrs[attr] = new_val
            else:
                cur_val = self.attrs.get(attr)
                if new_val and new_val != cur_val:
                    set_bel = self.set_attr_bels[attr]
                    raise Exception(f"{attr} conflict: X{bel.x}Y{bel.y}/IOB{bel.idx_str} ({bel.cell.name}) is trying to set {new_val} but X{set_bel.x}Y{set_bel.y}/IOB{set_bel.idx_str} ({set_bel.cell.name}) already set {cur_val}")

    def check_for_vccio_conflict(self, default_io_type: str):
        """ This function is called after all I/Os have been added to the bank. It checks for conflicts between the IO_TYPE and BANK_VCC_IO attributes. If IO_TYPE has not been specified, the default value is used.
        """
        io_type_bel = self.set_attr_bels.get('IO_TYPE')
        if io_type_bel:
            io_type = self.io_type
        else:
            io_type = default_io_type
        if self.bank_vccio:
            if self._vcc_ios[io_type] != self.bank_vccio:
                set_bel = self.set_attr_bels['BANK_VCCIO']
                if io_type_bel:
                    raise Exception(f"IO_TYPE and BANK_VCCIO conflict: X{io_type_bel.x}Y{io_type_bel.y}/IOB{io_type_bel.idx_str} ({io_type_bel.cell.name}) is trying to set {io_type} but X{set_bel.x}Y{set_bel.y}/IOB{set_bel.idx_str} ({set_bel.cell.name}) already set {self.bank_vccio}")
                else:
                    raise Exception(f"Default IO_TYPE ({io_type}) and BANK_VCCIO conflict: X{set_bel.x}Y{set_bel.y}/IOB{set_bel.idx_str} ({set_bel.cell.name}) set {self.bank_vccio}")

    def add_io_bel(self, bel: BelDesc):
        """ Add IO to the bank """
        self.bels.append(bel)
        if not bel.is_diff_io():
            self.check_or_set_attr(bel, 'IO_TYPE')
        if 'IS_OUTPUT' in bel.cell.parms:
            self.check_or_set_attr(bel, 'BANK_VCCIO')
            self.has_outputs = True

    def get_attrs(self) -> Iterator[AttrVal]:
        for attr, val in self.attrs.items():
            yield AttrVal(attr, val)

    def is_io_bel_used(self, x: int, y: int, idx_str: str) -> bool:
        used = False
        for bel in self.bels:
            if x == bel.x and y == bel.y and idx_str == bel.idx_str:
                used = True
                break
        return used

    # debug
    def __repr__(self):
        return f'x:{self.x}, y:{self.y}, attrs:{self.attrs}, set_attr_bels:{self.set_attr_bels}, bels:{self.bels}'

################################################################
class Device:
    """ Base chip. The fuses for a specific chip are set in a class that inherits from this one. """
    def __init__(self, cli_args: CliArgs, pnr: Netlist):
        device_name = cli_args.get_device()
        if not device_name:
            device_name = pnr.get_device()
        self.chipdb = ChipDB(device_name)
        self.used_slices = UsedSlices()
        # default slice attributes
        self.default_slice_attrvals = {}
        for name, attrval in zip(
                ["no_dff", "no_dff", "no_dff", "no_dff", "no_dff0", "no_dff1"],
                [AttrVal('LSRONMUX', '0'), AttrVal('CLKMUX_1', '1'),
                 AttrVal('REG0_REGSET', 'RESET'), AttrVal('REG1_REGSET', 'RESET'),
                 AttrVal('REG0_REGSET', 'RESET'), AttrVal('REG1_REGSET', 'RESET'),
                 ]):
            av = self.default_slice_attrvals.setdefault(name, set())
            self.chipdb.get_slice_attr_val(attrval, av)

        # default SSRAM slice attributes
        self.default_ssram_slice_attrvals = set()
        for attrval in [AttrVal('REG0_REGSET', 'UNKNOWN'), AttrVal('REG1_REGSET', 'UNKNOWN')]:
            self.chipdb.get_slice_attr_val(attrval, self.default_ssram_slice_attrvals)
        # MODE=SSRAM for quick test
        av = set()
        self.chipdb.get_slice_attr_val(AttrVal('MODE', 'SSRAM'), av)
        self.mode_eq_ssram = next(iter(av)) if av else None

        # IO init
        self.io_banks = None # This is a list, but None ensures that subclasses must initialize the IO banks.
        self.default_ibuf_attrs = [('PADDI', 'PADDI'), ('HYSTERESIS', 'NONE'), ('PULLMODE', 'UP'), ('SLEWRATE', 'SLOW'),
                 ('DRIVE', '0'), ('CLAMP', 'OFF'), ('OPENDRAIN', 'OFF'), ('DIFFRESISTOR', 'OFF'),
                 ('VREF', 'OFF'), ('LVDS_OUT', 'OFF')]
        self.default_obuf_attrs = [('ODMUX_1', '1'), ('PULLMODE', 'UP'), ('SLEWRATE', 'FAST'),
                 ('DRIVE', '8'), ('HYSTERESIS', 'NONE'), ('CLAMP', 'OFF'),
                 ('SINGLERESISTOR', 'OFF'), ('LVDS_OUT', 'OFF'), ('DDR_DYNTERM', 'NA'),
                 ('TO', 'INV'), ('OPENDRAIN', 'OFF')]
        self.default_tbuf_attrs = [('ODMUX_1', 'UNKNOWN'), ('PULLMODE', 'UP'), ('SLEWRATE', 'FAST'),
                 ('DRIVE', '8'), ('HYSTERESIS', 'NONE'), ('CLAMP', 'OFF'),
                 ('SINGLERESISTOR', 'OFF'), ('LVDS_OUT', 'OFF'), ('DDR_DYNTERM', 'NA'),
                 ('TO', 'INV'), ('PERSISTENT', 'OFF'), ('ODMUX', 'TRIMUX'), ('OPENDRAIN', 'OFF')]
        self.default_iobuf_attrs = [('ODMUX_1', 'UNKNOWN'), ('PULLMODE', 'UP'), ('SLEWRATE', 'FAST'),
                 ('DRIVE', '8'), ('HYSTERESIS', 'NONE'), ('CLAMP', 'OFF'), ('DIFFRESISTOR', 'OFF'),
                 ('SINGLERESISTOR', 'OFF'), ('LVDS_OUT', 'OFF'), ('DDR_DYNTERM', 'NA'),
                 ('TO', 'INV'), ('PERSISTENT', 'OFF'), ('ODMUX', 'TRIMUX'), ('PADDI', 'PADDI'), ('OPENDRAIN', 'OFF')]
        self.default_elvds_ibuf_attrs = [('PADDI', 'PADDI'), ('HYSTERESIS', 'NA'),
                 ('SLEWRATE', 'SLOW'), ('ODMUX_1', 'UNKNOWN'),
                 ('DRIVE', '0'), ('CLAMP', 'OFF'), ('OPENDRAIN', 'OFF'), ('DIFFRESISTOR', 'OFF'),
                 ('VREF', 'OFF'), ('LVDS_OUT', 'OFF')]
        self.default_elvds_obuf_attrs = [('ODMUX_1', '0'), ('PULLMODE', 'NONE'), ('SLEWRATE', 'FAST'),
                 ('DRIVE', '8'), ('HYSTERESIS', 'NA'), ('CLAMP', 'OFF'),
                 ('SINGLERESISTOR', 'OFF'), ('LVDS_OUT', 'OFF'), ('DDR_DYNTERM', 'NA'),
                 ('TO', 'INV'), ('PERSISTENT', 'OFF'), ('ODMUX', 'TRIMUX'), ('TRIMUX_PADDT', '1'),
                 ('OPENDRAIN', 'OFF')]
        self.default_elvds_tbuf_attrs = [('ODMUX_1', 'UNKNOWN'), ('PULLMODE', 'NONE'), ('SLEWRATE', 'FAST'),
                 ('DRIVE', 'UNKNOWN'), ('HYSTERESIS', 'NA'), ('CLAMP', 'OFF'), ('DIFFRESISTOR', 'OFF'),
                 ('SINGLERESISTOR', 'OFF'), ('LVDS_OUT', 'OFF'), ('DDR_DYNTERM', 'NA'),
                 ('TO', 'INV'), ('PERSISTENT', 'OFF'), ('ODMUX', 'TRIMUX'), ('TRIMUX_PADDT', '0'),
                 ('OPENDRAIN', 'OFF')]
        self.default_tlvds_ibuf_attrs = [('PADDI', 'PADDI'), ('HYSTERESIS', 'NA'),
                 ('SLEWRATE', 'SLOW'), ('ODMUX_1', 'UNKNOWN'), ('PULLMODE', 'NONE'),
                 ('DRIVE', '0'), ('CLAMP', 'OFF'), ('OPENDRAIN', 'OFF'), ('DIFFRESISTOR', 'OFF'),
                 ('VREF', 'OFF'), ('LVDS_OUT', 'OFF')]
        self.io_type_alias = {
                frozenset({"BLVDS25E"}): "BLVDS_E",
                frozenset({"LVTTL33"}): "LVCMOS33",
                frozenset({"LVCMOS12D", "LVCMOS15D", "LVCMOS18D", "LVCMOS25D", "LVCMOS33D", }): "LVCMOS_D",
                frozenset({"HSTL15", "HSTL18_I", "HSTL18_II"}): "HSTL",
                frozenset({"SSTL15", "SSTL18_I", "SSTL18_II", "SSTL25_I", "SSTL25_II", "SSTL33_I", "SSTL33_II"}): "SSTL",
                frozenset({"MLVDS25E"}): "MLVDS_E",
                frozenset({"SSTL15D", "SSTL18D_I", "SSTL18D_II", "SSTL25D_I", "SSTL25D_II", "SSTL33D_I", "SSTL33D_II"}): "SSTL_D",
                frozenset({"HSTL15D", "HSTL18D_I", "HSTL18D_II"}): "HSTL_D",
                frozenset({"RSDS"}): "RSDS25",
                frozenset({"RSDS25E"}): "RSDS_E",
                }

    def get_io_type_alias(self, io_type: str) -> str:
        for k, v in self.io_type_alias.items():
            if io_type in k:
                io_type = v
                break
        return io_type

    def normalize_io_cell_attr(self, cell: CellDesc) -> CellDesc:
        """ Modify IO attrs """
        refine_attrs = {'SLEW_RATE': 'SLEWRATE', 'PULL_MODE': 'PULLMODE', 'OPEN_DRAIN': 'OPENDRAIN'}
        new_attrs = {}
        for attr, val in cell.attrs.items():
            new_attr, new_val = _convert_legacy_io_cell_attr(attr, val)
            new_name = refine_attrs.get(new_attr, new_attr)
            new_attrs[new_name] = new_val

        new_io_type = new_attrs.get('IO_TYPE')
        if new_io_type:
            new_attrs['IO_TYPE'] = self.get_io_type_alias(new_io_type)

        # change type for differential IO
        new_typ = cell.typ
        diff_type = cell.parms.get('DIFF_TYPE')
        if diff_type:
            new_typ = diff_type
        return CellDesc(cell.name, new_typ, cell.parms, new_attrs)

    def normalize_io_bel_attr(self, bel: BelDesc) -> BelDesc:
        """ Modify IO attrs """
        return BelDesc(bel.x, bel.y, bel.idx_str, self.normalize_io_cell_attr(bel.cell))

    def set_io_bel_flags(self, bel: BelDesc, flags_dict: dict[str, any]) -> BelDesc:
        """ Set flags like 'is Output' """
        cell = bel.cell
        new_parms = cell.parms.copy()
        new_parms.update(flags_dict)
        return BelDesc(bel.x, bel.y, bel.idx_str, CellDesc(cell.name, cell.typ, new_parms, cell.attrs))

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

    def get_bel_bank(self, bel: BelDesc) -> int:
        """ Get bank for IO bel """
        bank = self.chipdb.get_loc_bank(bel.x, bel.y)
        if bank < 0:
            raise Exception(f"IO bel {bel} is not allowed for a given package.")
        return bank

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

    def mod_bels(self, bels: Iterator[BelDesc]) -> Iterator[BelDesc]:
        """ Add/Remove/Modify bels """
        yield from bels

    # The `get_xxx_fuses` methods are responsible for packing specific cell types.
    # They are invoked by retrieving a class attribute formed by combining the
    # type name with prefixi and suffix.
    # For diagnostic purposes, the base implementation should include handlers
    # for all cell types, even if they consist solely of outputting an error
    # message.
    # It’s not always possible to generate the necessary fuses right
    # away — sometimes you need to process the entire design while collecting
    # certain data. That’s why, in these methods, we generate what we can, and
    # handle the rest in the `get_final_fuses()` method, which is called last.
    def error_not_supported_cell_type(self, bel: BelDesc):
        #raise Exception(f"Not supported cell type '{bel.cell.typ}'. Cell '{bel.cell.name}'.")
        print(f"Not supported cell type '{bel.cell.typ}'. Cell '{bel.cell.name}'.")
        return []

    #========== LUTs
    def get_slice_fuses(self, x: int, y: int, idx: int, has_dff_0: bool, has_dff_1: bool, attr_vals: list[AttrVal]) -> list[CellFuseBits]:
        """ Add default attributes """
        av =  set()
        for attrval in attr_vals:
            self.chipdb.get_slice_attr_val(attrval, av)

        # defaults
        if self.mode_eq_ssram in av:
            av.update(self.default_ssram_slice_attrvals)
        elif not (has_dff_0 or has_dff_1):
            av.update(self.default_slice_attrvals['no_dff'])
        else:
            if not has_dff_0:
                av.update(self.default_slice_attrvals['no_dff0'])
            if not has_dff_1:
                av.update(self.default_slice_attrvals['no_dff1'])

        fuses = []
        bits = self.chipdb.get_slice_fuses(x, y, idx, av)
        if bits:
            fuses.append(CellFuseBits(x, y, bits))
        return fuses

    def get_final_slice_fuses(self) -> list[CellFuseBits]:
        """ Fuses for LUT-DFF combinations that were not detected """
        attr_vals = []
        fuses = []
        for x_y_idx, dffs_attr_vals in self.used_slices.enumerate():
            x, y, idx = x_y_idx
            has_dff_0, has_dff_1, attr_vals = dffs_attr_vals
            fuses += self.get_slice_fuses(x, y, idx, has_dff_0, has_dff_1, attr_vals)
        return fuses

    def get_LUT4_fuses(self, bel: BelDesc) -> list[CellFuseBits]:
        init = str(bel.cell.parms['INIT'])
        if len(init) > 16:
            init = init[-16:]
        else:
            init = init*(16//len(init))

        fuses = []
        bits = set()
        lutmap = self.chipdb.get_lut_data(bel.x, bel.y, bel.idx_int)
        for bitnum, lutbit in enumerate(init[::-1]):
            if lutbit == '0':
                bits.update(lutmap[bitnum])
        fuses.append(CellFuseBits(bel.x, bel.y, bits))
        if bel.idx_int < 6:
            self.used_slices.add_slice_attrs(bel.x, bel.y, bel.idx_int // 2, False, False, [])
        return fuses

    def get_LUT1_fuses(self, bel: BelDesc) -> list[CellFuseBits]:
        return self.get_LUT4_fuses(bel)

    def get_LUT2_fuses(self, bel: BelDesc) -> list[CellFuseBits]:
        return self.get_LUT4_fuses(bel)

    def get_LUT3_fuses(self, bel: BelDesc) -> list[CellFuseBits]:
        return self.get_LUT4_fuses(bel)

    #========== DFFs
    def get_common_ff_fuses(self, bel: BelDesc, attr_vals: list[AttrVal]) -> list[CellFuseBits]:
        attr_vals.append(AttrVal('REGMODE', 'LATCH' if int(bel.cell.attrs.get('LATCH', '0')) else 'FF'))
        self.used_slices.add_slice_attrs(bel.x, bel.y, bel.idx_int // 2, bel.idx_int % 2 == 0, bel.idx_int % 2 == 1, attr_vals)
        return []

    def get_DFF_fuses(self, bel: BelDesc) -> list[CellFuseBits]:
        attr_vals = [AttrVal('CEMUX_1', '1'), # CE port is connected to VCC
                     AttrVal(f'REG{bel.idx_int % 2}_REGSET', 'RESET'), # RESET
                     AttrVal('CLKMUX_CLK', 'SIG') # CLOCK
                     ]
        return self.get_common_ff_fuses(bel, attr_vals)

    def get_DFFN_fuses(self, bel: BelDesc) -> list[CellFuseBits]:
        attr_vals = [AttrVal('CEMUX_1', '1'), # CE port is connected to VCC
                     AttrVal(f'REG{bel.idx_int % 2}_REGSET', 'RESET'), # RESET
                     AttrVal('CLKMUX_CLK', 'INV') # CLOCK
                     ]
        return self.get_common_ff_fuses(bel, attr_vals)

    def get_DFFE_fuses(self, bel: BelDesc) -> list[CellFuseBits]:
        attr_vals = [AttrVal('CEMUX_1', 'UNKNOWN'), AttrVal('CEMUX_CE', 'SIG'), # CE port is used
                     AttrVal(f'REG{bel.idx_int % 2}_REGSET', 'RESET'), # RESET
                     AttrVal('CLKMUX_CLK', 'SIG') # CLOCK
                     ]
        return self.get_common_ff_fuses(bel, attr_vals)

    def get_DFFNE_fuses(self, bel: BelDesc) -> list[CellFuseBits]:
        attr_vals = [AttrVal('CEMUX_1', 'UNKNOWN'), AttrVal('CEMUX_CE', 'SIG'), # CE port is used
                     AttrVal(f'REG{bel.idx_int % 2}_REGSET', 'RESET'), # RESET
                     AttrVal('CLKMUX_CLK', 'INV') # CLOCK
                     ]
        return self.get_common_ff_fuses(bel, attr_vals)

    def get_DFFR_fuses(self, bel: BelDesc) -> list[CellFuseBits]:
        attr_vals = [AttrVal('CEMUX_1', '1'), # CE port is connected to VCC
                     AttrVal(f'REG{bel.idx_int % 2}_REGSET', 'RESET'), AttrVal('LSRONMUX', 'LSRMUX'), # RESET
                     AttrVal('CLKMUX_CLK', 'SIG') # CLOCK
                     ]
        return self.get_common_ff_fuses(bel, attr_vals)

    def get_DFFNR_fuses(self, bel: BelDesc) -> list[CellFuseBits]:
        attr_vals = [AttrVal('CEMUX_1', '1'), # CE port is connected to VCC
                     AttrVal(f'REG{bel.idx_int % 2}_REGSET', 'RESET'), AttrVal('LSRONMUX', 'LSRMUX'), # RESET
                     AttrVal('CLKMUX_CLK', 'INV') # CLOCK
                     ]
        return self.get_common_ff_fuses(bel, attr_vals)

    def get_DFFRE_fuses(self, bel: BelDesc) -> list[CellFuseBits]:
        attr_vals = [AttrVal('CEMUX_1', 'UNKNOWN'), AttrVal('CEMUX_CE', 'SIG'), # CE port is used
                     AttrVal(f'REG{bel.idx_int % 2}_REGSET', 'RESET'), AttrVal('LSRONMUX', 'LSRMUX'), # RESET
                     AttrVal('CLKMUX_CLK', 'SIG') # CLOCK
                     ]
        return self.get_common_ff_fuses(bel, attr_vals)

    def get_DFFNRE_fuses(self, bel: BelDesc) -> list[CellFuseBits]:
        attr_vals = [AttrVal('CEMUX_1', 'UNKNOWN'), AttrVal('CEMUX_CE', 'SIG'), # CE port is used
                     AttrVal(f'REG{bel.idx_int % 2}_REGSET', 'RESET'), AttrVal('LSRONMUX', 'LSRMUX'), # RESET
                     AttrVal('CLKMUX_CLK', 'INV') # CLOCK
                     ]
        return self.get_common_ff_fuses(bel, attr_vals)

    def get_DFFS_fuses(self, bel: BelDesc) -> list[CellFuseBits]:
        attr_vals = [AttrVal('CEMUX_1', '1'), # CE port is connected to VCC
                     AttrVal(f'REG{bel.idx_int % 2}_REGSET', 'SET'), AttrVal('LSRONMUX', 'LSRMUX'), # RESET
                     AttrVal('CLKMUX_CLK', 'SIG') # CLOCK
                     ]
        return self.get_common_ff_fuses(bel, attr_vals)

    def get_DFFNS_fuses(self, bel: BelDesc) -> list[CellFuseBits]:
        attr_vals = [AttrVal('CEMUX_1', '1'), # CE port is connected to VCC
                     AttrVal(f'REG{bel.idx_int % 2}_REGSET', 'SET'), AttrVal('LSRONMUX', 'LSRMUX'), # RESET
                     AttrVal('CLKMUX_CLK', 'INV') # CLOCK
                     ]
        return self.get_common_ff_fuses(bel, attr_vals)

    def get_DFFSE_fuses(self, bel: BelDesc) -> list[CellFuseBits]:
        attr_vals = [AttrVal('CEMUX_1', 'UNKNOWN'), AttrVal('CEMUX_CE', 'SIG'), # CE port is used
                     AttrVal(f'REG{bel.idx_int % 2}_REGSET', 'SET'), AttrVal('LSRONMUX', 'LSRMUX'), # RESET
                     AttrVal('CLKMUX_CLK', 'SIG') # CLOCK
                     ]
        return self.get_common_ff_fuses(bel, attr_vals)

    def get_DFFNSE_fuses(self, bel: BelDesc) -> list[CellFuseBits]:
        attr_vals = [AttrVal('CEMUX_1', 'UNKNOWN'), AttrVal('CEMUX_CE', 'SIG'), # CE port is used
                     AttrVal(f'REG{bel.idx_int % 2}_REGSET', 'SET'), AttrVal('LSRONMUX', 'LSRMUX'), # RESET
                     AttrVal('CLKMUX_CLK', 'INV') # CLOCK
                     ]
        return self.get_common_ff_fuses(bel, attr_vals)

    def get_DFFC_fuses(self, bel: BelDesc) -> list[CellFuseBits]:
        attr_vals = [AttrVal('CEMUX_1', '1'), # CE port is connected to VCC
                     AttrVal(f'REG{bel.idx_int % 2}_REGSET', 'RESET'), AttrVal('LSRONMUX', 'LSRMUX'), # RESET
                     AttrVal('SRMODE', 'ASYNC'),
                     AttrVal('CLKMUX_CLK', 'SIG') # CLOCK
                     ]
        return self.get_common_ff_fuses(bel, attr_vals)

    def get_DFFNC_fuses(self, bel: BelDesc) -> list[CellFuseBits]:
        attr_vals = [AttrVal('CEMUX_1', '1'), # CE port is connected to VCC
                     AttrVal(f'REG{bel.idx_int % 2}_REGSET', 'RESET'), AttrVal('LSRONMUX', 'LSRMUX'), # RESET
                     AttrVal('SRMODE', 'ASYNC'),
                     AttrVal('CLKMUX_CLK', 'INV') # CLOCK
                     ]
        return self.get_common_ff_fuses(bel, attr_vals)

    def get_DFFCE_fuses(self, bel: BelDesc) -> list[CellFuseBits]:
        attr_vals = [AttrVal('CEMUX_1', 'UNKNOWN'), AttrVal('CEMUX_CE', 'SIG'), # CE port is used
                     AttrVal(f'REG{bel.idx_int % 2}_REGSET', 'RESET'), AttrVal('LSRONMUX', 'LSRMUX'), # RESET
                     AttrVal('SRMODE', 'ASYNC'),
                     AttrVal('CLKMUX_CLK', 'SIG') # CLOCK
                     ]
        return self.get_common_ff_fuses(bel, attr_vals)

    def get_DFFNCE_fuses(self, bel: BelDesc) -> list[CellFuseBits]:
        attr_vals = [AttrVal('CEMUX_1', 'UNKNOWN'), AttrVal('CEMUX_CE', 'SIG'), # CE port is used
                     AttrVal(f'REG{bel.idx_int % 2}_REGSET', 'RESET'), AttrVal('LSRONMUX', 'LSRMUX'), # RESET
                     AttrVal('SRMODE', 'ASYNC'),
                     AttrVal('CLKMUX_CLK', 'INV') # CLOCK
                     ]
        return self.get_common_ff_fuses(bel, attr_vals)

    def get_DFFP_fuses(self, bel: BelDesc) -> list[CellFuseBits]:
        attr_vals = [AttrVal('CEMUX_1', '1'), # CE port is connected to VCC
                     AttrVal(f'REG{bel.idx_int % 2}_REGSET', 'SET'), AttrVal('LSRONMUX', 'LSRMUX'), # RESET
                     AttrVal('SRMODE', 'ASYNC'),
                     AttrVal('CLKMUX_CLK', 'SIG') # CLOCK
                     ]
        return self.get_common_ff_fuses(bel, attr_vals)

    def get_DFFNP_fuses(self, bel: BelDesc) -> list[CellFuseBits]:
        attr_vals = [AttrVal('CEMUX_1', '1'), # CE port is connected to VCC
                     AttrVal(f'REG{bel.idx_int % 2}_REGSET', 'SET'), AttrVal('LSRONMUX', 'LSRMUX'), # RESET
                     AttrVal('SRMODE', 'ASYNC'),
                     AttrVal('CLKMUX_CLK', 'INV') # CLOCK
                     ]
        return self.get_common_ff_fuses(bel, attr_vals)

    def get_DFFPE_fuses(self, bel: BelDesc) -> list[CellFuseBits]:
        attr_vals = [AttrVal('CEMUX_1', 'UNKNOWN'), AttrVal('CEMUX_CE', 'SIG'), # CE port is used
                     AttrVal(f'REG{bel.idx_int % 2}_REGSET', 'SET'), AttrVal('LSRONMUX', 'LSRMUX'), # RESET
                     AttrVal('SRMODE', 'ASYNC'),
                     AttrVal('CLKMUX_CLK', 'SIG') # CLOCK
                     ]
        return self.get_common_ff_fuses(bel, attr_vals)

    def get_DFFNPE_fuses(self, bel: BelDesc) -> list[CellFuseBits]:
        attr_vals = [AttrVal('CEMUX_1', 'UNKNOWN'), AttrVal('CEMUX_CE', 'SIG'), # CE port is used
                     AttrVal(f'REG{bel.idx_int % 2}_REGSET', 'SET'), AttrVal('LSRONMUX', 'LSRMUX'), # RESET
                     AttrVal('SRMODE', 'ASYNC'),
                     AttrVal('CLKMUX_CLK', 'INV') # CLOCK
                     ]
        return self.get_common_ff_fuses(bel, attr_vals)

    #========== ALU
    def get_ALU_fuses(self, bel: BelDesc) -> list[CellFuseBits]:
        fuses = []
        init = bel.cell.parms.get('RAW_ALU_LUT')
        if init:
            if len(init) > 16:
                init = init[-16:]
            else:
                init = init*(16//len(init))

            lutmap = self.chipdb.get_lut_data(bel.x, bel.y, bel.idx_int)
            bits = set()
            for bitnum, lutbit in enumerate(init[::-1]):
                if lutbit == '0':
                    bits.update(lutmap[bitnum])
            fuses.append(CellFuseBits(bel.x, bel.y, bits))
        else:
            mode = str(bel.cell.parms['ALU_MODE'])
            alu_modes = self.chipdb.get_alu_modes(bel.x, bel.y, bel.idx_int)
            bits = alu_modes.get(mode)
            if not bits:
                bits = alu_modes[str(int(mode, 2))]
            if bits:
                fuses.append(CellFuseBits(bel.x, bel.y, bits))

        self.used_slices.add_slice_attrs(bel.x, bel.y, bel.idx_int // 2, False, False, [AttrVal('MODE', 'ALU')])
        return fuses

    #========== Misc
    def get_BUFG_fuses(self, bel: BelDesc) -> list[CellFuseBits]:
        return self.error_not_supported_cell_type(bel)

    def get_BANDGAP_fuses(self, bel: BelDesc) -> list[CellFuseBits]:
        return self.error_not_supported_cell_type(bel)

    def get_GSR_fuses(self, bel: BelDesc) -> list[CellFuseBits]:
        """ Global Set/Reset """
        return self.error_not_supported_cell_type(bel)

    #========== IO
    def get_default_io_type(self) -> str:
        """ Default IO_TYPE """
        return "LVCMOS12"

    def get_default_elvds_io_type(self) -> str:
        """ Default IO_TYPE """
        return "LVCMOS_D"

    def get_default_tlvds_io_type(self) -> str:
        """ Default IO_TYPE """
        return "LVDS25"


    def get_default_unused_io_type(self) -> str:
        """ Default IO_TYPE for unused IO """
        return "LVCMOS18"

    def get_unused_io_attrvals(self) -> list[AttrVal]:
        """ Attributes for unused IO """
        return []

    def get_unused_io_fuses(self) -> list[CellFuseBits]:
        """ Set attributes for unused banks and return fuses for all unused IOs """
        for bank_desc in self.io_banks:
            if not bank_desc.is_used:
                bank_desc.set_attr("IO_TYPE", self.get_default_unused_io_type())
                bank_desc.set_bank_vccio_by_io_type(self.get_default_unused_io_type())

        fuses = []
        unused_io_attrvals = self.get_unused_io_attrvals()
        for io_cfg in self.chipdb.get_io_cfgs():
            bank_desc = self.io_banks[self.chipdb.get_loc_bank(io_cfg.x, io_cfg.y)]
            # skip used IO
            if bank_desc.is_io_bel_used(io_cfg.x, io_cfg.y, io_cfg.idx_str):
                continue
            av = set()
            for attrval in unused_io_attrvals:
                self.chipdb.get_io_attr_val(attrval, av)
            self.chipdb.get_iob_attr_val(AttrVal("IO_TYPE", bank_desc.io_type), av)
            self.chipdb.get_iob_attr_val(AttrVal("BANK_VCCIO", bank_desc.bank_vccio), av)
            bits = self.chipdb.get_iob_fuses(io_cfg.x, io_cfg.y, av, io_cfg.idx_str)
            if bits:
                fuses.append(CellFuseBits(io_cfg.x, io_cfg.y, bits))
        return fuses

    def get_io_bank_fuses(self) -> list[CellFuseBits]:
        fuses = self.get_unused_io_fuses()

        # Bank fuses
        for bank, bank_desc in enumerate(self.io_banks):
            av = set()
            for attrval in bank_desc.get_attrs():
                self.chipdb.get_bank_attr_val(attrval, av)
            bits = self.chipdb.get_bank_fuses(bank_desc.x, bank_desc.y, av, bank)
            bits.update(self.chipdb.get_bank_io_fuses(bank_desc.x, bank_desc.y, av))
            if bits:
                fuses.append(CellFuseBits(bank_desc.x, bank_desc.y, bits))
        return fuses

    def check_io_banks(self):
        """ Check BANK IO_TYPE and VCCIO """
        for bank_desc in self.io_banks:
            if bank_desc.is_used:
               bank_desc.check_for_vccio_conflict(self.get_default_io_type())
               if not bank_desc.io_type:
                   default_io_type = self.get_default_io_type()
                   bank_desc.set_attr("IO_TYPE", default_io_type)
               if bank_desc.has_outputs:
                   bank_desc.set_bank_vccio_by_io_type(bank_desc.io_type)
               else:
                   bank_desc.set_bank_vccio_by_io_type(self.get_default_io_type())

    def add_io_to_bank(self, bel: BelDesc):
        self.io_banks[self.get_bel_bank(bel)].add_io_bel(bel)

    # Second pass IO functions
    def set_input_resistor(self, val: str, bel: BelDesc, av: set[int]):
        """ Set additional atribute for input resistor """
        if val != 'OFF' and bel.cell.typ in {'IBUF', 'IOBUF', 'TLVDS_IBUF', 'TLVDS_IOBUF', 'ELVDS_IBUF', 'ELVDS_IOBUF'}:
            self.chipdb.get_iob_attr_val(AttrVal('DDR_DYNTERM', 'ON'), av)

    def set_io_attrvals(self, bel: BelDesc, default_attrs: list[tuple[str, str]]) -> set[int]:
        av = set()
        for attr, val in default_attrs:
            override_val = bel.cell.attrs.get(attr)
            if override_val:
                val = override_val
            # Check for input resistor
            if attr == 'SINGLERESISTOR':
                self.set_input_resistor(val, bel, av)
            self.chipdb.get_iob_attr_val(AttrVal(attr, val), av)
        return av

    def process_OBUF(self, bank_desc: BankDesc, bel: BelDesc) -> list[CellFuseBits]:
        av = self.set_io_attrvals(bel, self.default_obuf_attrs)
        fuses = []
        self.chipdb.get_iob_attr_val(AttrVal("IO_TYPE", bank_desc.io_type), av)
        self.chipdb.get_iob_attr_val(AttrVal("BANK_VCCIO", bank_desc.bank_vccio), av)
        bits = self.chipdb.get_iob_fuses(bel.x, bel.y, av, bel.idx_str)
        if bits:
            fuses.append(CellFuseBits(bel.x, bel.y, bits))
        return fuses

    def process_IBUF(self, bank_desc: BankDesc, bel: BelDesc) -> list[CellFuseBits]:
        av = self.set_io_attrvals(bel, self.default_ibuf_attrs)
        fuses = []
        self.chipdb.get_iob_attr_val(AttrVal("IO_TYPE", bank_desc.io_type), av)
        self.chipdb.get_iob_attr_val(AttrVal("BANK_VCCIO", bank_desc.bank_vccio), av)
        bits = self.chipdb.get_iob_fuses(bel.x, bel.y, av, bel.idx_str)
        if bits:
            fuses.append(CellFuseBits(bel.x, bel.y, bits))
        return fuses

    def process_TBUF(self, bank_desc: BankDesc, bel: BelDesc) -> list[CellFuseBits]:
        av = self.set_io_attrvals(bel, self.default_tbuf_attrs)
        fuses = []
        self.chipdb.get_iob_attr_val(AttrVal("IO_TYPE", bank_desc.io_type), av)
        self.chipdb.get_iob_attr_val(AttrVal("BANK_VCCIO", bank_desc.bank_vccio), av)
        bits = self.chipdb.get_iob_fuses(bel.x, bel.y, av, bel.idx_str)
        if bits:
            fuses.append(CellFuseBits(bel.x, bel.y, bits))
        return fuses

    # Differential IO functions
    def check_elvds_placement(self, bel: BelDesc):
        """ Check Emulation vs True LVDS, postive vs negative pins etc """
        io_diff_cfg = self.chipdb.get_io_diff_cfg(bel.x, bel.y, bel.idx_str)
        if not io_diff_cfg:
            raise Exception(f"X{bel.x}Y{bel.y}/IOB{bel.idx_str} ({bel.cell.name}) cannot be placed - location is not a LVDS pin")
        if io_diff_cfg.true_lvds:
            raise Exception(f"X{bel.x}Y{bel.y}/IOB{bel.idx_str} ({bel.cell.name}) cannot be placed - location is a True LVDS pin")
        if io_diff_cfg.positive != (bel.cell.parms.get('DIFF') == 'P'):
            raise Exception(f"X{bel.x}Y{bel.y}/IOB{bel.idx_str} ({bel.cell.name}) cannot be placed - pin P must be IOBA, pin N must be IOBB")

    def check_tlvds_placement(self, bel: BelDesc):
        """ Check Emulation vs True LVDS, postive vs negative pins etc """
        io_diff_cfg = self.chipdb.get_io_diff_cfg(bel.x, bel.y, bel.idx_str)
        if not io_diff_cfg:
            raise Exception(f"X{bel.x}Y{bel.y}/IOB{bel.idx_str} ({bel.cell.name}) cannot be placed - location is not a LVDS pin")
        if not io_diff_cfg.true_lvds:
            raise Exception(f"X{bel.x}Y{bel.y}/IOB{bel.idx_str} ({bel.cell.name}) cannot be placed - location is a Emulated LVDS pin")
        if io_diff_cfg.positive != (bel.cell.parms.get('DIFF') == 'P'):
            raise Exception(f"X{bel.x}Y{bel.y}/IOB{bel.idx_str} ({bel.cell.name}) cannot be placed - pin P must be IOBA, pin N must be IOBB")

    def process_TLVDS_IBUF(self, bank_desc: BankDesc, bel: BelDesc) -> list[CellFuseBits]:
        self.check_tlvds_placement(bel)

        av = self.set_io_attrvals(bel, self.default_tlvds_ibuf_attrs)
        fuses = []
        io_type = bel.cell.attrs.get('IO_TYPE')
        if io_type:
            self.chipdb.get_iob_attr_val(AttrVal("IO_TYPE", io_type), av)
        else:
            self.chipdb.get_iob_attr_val(AttrVal("IO_TYPE", self.get_default_tlvds_io_type()), av)

        bits = self.chipdb.get_iob_fuses(bel.x, bel.y, av, bel.idx_str)
        if bits:
            fuses.append(CellFuseBits(bel.x, bel.y, bits))
        return fuses

    def process_ELVDS_IBUF(self, bank_desc: BankDesc, bel: BelDesc) -> list[CellFuseBits]:
        self.check_elvds_placement(bel)

        av = self.set_io_attrvals(bel, self.default_elvds_ibuf_attrs)
        fuses = []
        io_type = bel.cell.attrs.get('IO_TYPE')
        if io_type:
            self.chipdb.get_iob_attr_val(AttrVal("IO_TYPE", io_type), av)
        else:
            self.chipdb.get_iob_attr_val(AttrVal("IO_TYPE", self.get_default_elvds_io_type()), av)
        # A vs B pullup
        if bel.idx_str == 'A':
            self.chipdb.get_iob_attr_val(AttrVal("PULLMODE", "UP"), av)
        else:
            self.chipdb.get_iob_attr_val(AttrVal("PULLMODE", "NONE"), av)

        bits = self.chipdb.get_iob_fuses(bel.x, bel.y, av, bel.idx_str)
        if bits:
            fuses.append(CellFuseBits(bel.x, bel.y, bits))
        return fuses

    def process_ELVDS_OBUF(self, bank_desc: BankDesc, bel: BelDesc) -> list[CellFuseBits]:
        self.check_elvds_placement(bel)

        av = self.set_io_attrvals(bel, self.default_elvds_obuf_attrs)
        fuses = []
        io_type = bel.cell.attrs.get('IO_TYPE')
        if io_type:
            self.chipdb.get_iob_attr_val(AttrVal("IO_TYPE", io_type), av)
        else:
            self.chipdb.get_iob_attr_val(AttrVal("IO_TYPE", self.get_default_elvds_io_type()), av)
        self.chipdb.get_iob_attr_val(AttrVal("BANK_VCCIO", bank_desc.bank_vccio), av)
        bits = self.chipdb.get_iob_fuses(bel.x, bel.y, av, bel.idx_str)
        if bits:
            fuses.append(CellFuseBits(bel.x, bel.y, bits))
        return fuses

    def process_ELVDS_TBUF(self, bank_desc: BankDesc, bel: BelDesc) -> list[CellFuseBits]:
        self.check_elvds_placement(bel)

        av = self.set_io_attrvals(bel, self.default_elvds_tbuf_attrs)
        fuses = []
        io_type = bel.cell.attrs.get('IO_TYPE')
        if io_type:
            self.chipdb.get_iob_attr_val(AttrVal("IO_TYPE", io_type), av)
        else:
            self.chipdb.get_iob_attr_val(AttrVal("IO_TYPE", self.get_default_elvds_io_type()), av)
        self.chipdb.get_iob_attr_val(AttrVal("BANK_VCCIO", bank_desc.bank_vccio), av)
        bits = self.chipdb.get_iob_fuses(bel.x, bel.y, av, bel.idx_str)
        if bits:
            fuses.append(CellFuseBits(bel.x, bel.y, bits))
        return fuses

    def get_io_fuses(self) -> list[CellFuseBits]:
        """ Second IO pass """
        fuses = []
        for bank_desc in self.io_banks:
            if bank_desc.is_used:
                for bel in bank_desc.bels:
                    fuses += getattr(self, f'process_{bel.cell.typ}')(bank_desc, bel)
        return fuses

    def common_io_handler(self, bel: BelDesc):
        mod_bel = self.normalize_io_bel_attr(bel)
        self.add_io_to_bank(mod_bel)

    # These are general functions; the fuses for I/O cannot be determined until
    # data on all of them has been collected. Therefore, the fuses will
    # actually be configured by the process_XXX functions.
    def get_OBUF_fuses(self, bel: BelDesc) -> list[CellFuseBits]:
        self.common_io_handler(self.set_io_bel_flags(bel, {'IS_OUTPUT': 1}))
        return []

    def get_IBUF_fuses(self, bel: BelDesc) -> list[CellFuseBits]:
        self.common_io_handler(bel)
        return []

    def get_TBUF_fuses(self, bel: BelDesc) -> list[CellFuseBits]:
        self.common_io_handler(bel)
        return []

    def get_IOBUF_fuses(self, bel: BelDesc) -> list[CellFuseBits]:
        self.common_io_handler(self.set_io_bel_flags(bel, {'IS_OUTPUT': 1}))
        return []

    #========== Finalize
    def get_final_fuses(self) -> list[CellFuseBits]:
        """ Delayed fuse generation """
        fuses = self.get_final_slice_fuses()

        # finalize IO
        self.check_io_banks()

        fuses += self.get_io_bank_fuses()
        fuses += self.get_io_fuses()
        return fuses

    # debug
    def __repr__(self):
        return f'db:{self.chipdb},\ndefault_slice_attrvals:{self.default_slice_attrvals},\ndefault_ssram_slice_attrvals:{self.default_ssram_slice_attrvals},\nmode_eq_ssram:{self.mode_eq_ssram}, \nio_banks:[{len(self.io_banks)}]{self.io_banks}'

################################################################
class GW1N(Device):
    """ GW1N series """
    def __init__(self, cli_args: CliArgs, pnr: Netlist):
        super().__init__(cli_args, pnr)

    #========== Misc
    def get_GSR_fuses(self, bel: BelDesc) -> list[CellFuseBits]:
        """ Global Set/Reset """
        gsr_attr_vals = [AttrVal('GSRMODE', 'ACTIVE_LOW')]
        cfg_attr_vals = [AttrVal('GSR', 'USED'), AttrVal('GOE', 'F0'), AttrVal('GSR', 'F0'),
                         AttrVal('DONE', 'F0'), AttrVal('GWD', 'F0')]

        # The configuration fuses are described in the ['shortval'][60] table, global set/reset is
        # described in the ['shortval'][20] table. Look for cells with type with these tables
        gsr_types = [50, 83]
        cfg_types = [50, 51]
        fuses = []
        for x, y in itertools.product(range(self.chipdb.cols), range(self.chipdb.rows)):
            ttyp = self.chipdb.get_ttyp(x, y)
            bits = set()
            if ttyp in gsr_types:
                av = set()
                for attrval in gsr_attr_vals:
                    self.chipdb.get_gsr_attr_val(attrval, av)
                bits = self.chipdb.get_gsr_fuses(x, y, av)
            if ttyp in cfg_types:
                av = set()
                for attrval in cfg_attr_vals:
                    self.chipdb.get_cfg_attr_val(attrval, av)
                bits.update(self.chipdb.get_cfg_fuses(x, y, av))
            if bits:
                fuses.append(CellFuseBits(x, y, bits))
        return fuses

    # debug
    def __repr__(self):
        return super().__repr__() + ""

################################################################
class GW1N_1(GW1N):
    """ GW1N-1 chip. Tangnano board """
    def __init__(self, cli_args: CliArgs, pnr: Netlist):
        super().__init__(cli_args, pnr)
        self.io_banks = [BankDesc() for _ in range(4)]
        for bank_idx, bank_desc in enumerate(self.io_banks):
            x, y = self.chipdb.get_bank_x_y(bank_idx)
            bank_desc.set_x_y(x, y)

    #========== IO
    def process_ELVDS_IOBUF(self, bank_desc: BankDesc, bel: BelDesc) -> list[CellFuseBits]:
        raise Exception("The GW1N-1 does not support ELVDS IOBUF")

    # debug
    def __repr__(self):
        return super().__repr__() + ""

################################################################
class GW1NZ_1(GW1N):
    """ GW1NZ-1 chip. Tangnano1k board """
    def __init__(self, cli_args: CliArgs, pnr: Netlist):
        super().__init__(cli_args, pnr)
        self.io_banks = [BankDesc() for _ in range(2)]
        for bank_idx, bank_desc in enumerate(self.io_banks):
            x, y = self.chipdb.get_bank_x_y(bank_idx)
            bank_desc.set_x_y(x, y)

    #========== Misc
    def get_BANDGAP_fuses(self, bel: BelDesc) -> list[CellFuseBits]:
        return []

    #========== IO
    def process_ELVDS_IBUF(self, bank_desc: BankDesc, bel: BelDesc) -> list[CellFuseBits]:
        raise Exception("The GW1NZ-1 does not support ELVDS IBUF")

    def process_ELVDS_IOBUF(self, bank_desc: BankDesc, bel: BelDesc) -> list[CellFuseBits]:
        raise Exception("The GW1NZ-1 does not support ELVDS IOBUF")

    # debug
    def __repr__(self):
        return super().__repr__() + ""

################################################################
class GW1N_9C(GW1N):
    """ GW1N-9C chip. Tangnano9k board """
    def __init__(self, cli_args: CliArgs, pnr: Netlist):
        super().__init__(cli_args, pnr)
        self.io_banks = [BankDesc() for _ in range(4)]
        for bank_idx, bank_desc in enumerate(self.io_banks):
            x, y = self.chipdb.get_bank_x_y(bank_idx)
            bank_desc.set_x_y(x, y)

    # debug
    def __repr__(self):
        return super().__repr__() + ""


################################################################
class GW2A(Device):
    """ GW2A series """
    def __init__(self, cli_args: CliArgs, pnr: Netlist):
        super().__init__(cli_args, pnr)

    # debug
    def __repr__(self):
        return super().__repr__() + ""

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
        for bel in self.device.mod_bels(self.pnr.get_bels()):
            self.fuses += getattr(self.device, f'get_{bel.cell.typ}_fuses')(bel)

    def set_const_fuses(self):
        """ Set fuses that must always be in place """
        self.fuses += self.device.get_all_cons_fuses()

    def get_fuses(self) -> list[CellFuseBits]:
        """ Return generated fuses """
        self.fuses += self.device.get_final_fuses()
        return self.fuses

    # debug
    def __repr__(self):
        return f'device:{self.device}, pnr:{self.pnr}'

################################################################
def create_device(cli_args: CliArgs, pnr: Netlist) -> Device:
    return {
            'GW1N-1' : GW1N_1(cli_args, pnr),
            'GW1NZ-1': GW1NZ_1(cli_args, pnr),
            'GW1N-9C': GW1N_9C(cli_args, pnr),
    } [cli_args.get_device()]

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
    import ipdb; ipdb.set_trace()
    pack.place()

    fuses = pack.get_fuses()
    output.set_fuses(fuses)
    import ipdb; ipdb.set_trace()
    output.write()


if __name__ == '__main__':
    main()

# vim: set et sw=4 ts=4:
