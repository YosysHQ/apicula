import argparse
import bisect
import importlib.resources
import itertools
import json
import math
import re

from apycula import attrids
from apycula import bitmatrix
from apycula import bslib
from apycula import chipdb
from apycula import wirenames as wnames
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
        parser.add_argument(
            '--multiboot_address',
            type=lambda value: int(value, 0),
            default=None,
            help='SPI flash address of the next bitstream for multiboot'
        )

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

    def get_multiboot_addr(self) -> int:
        address = self.args.multiboot_address
        if not address:
            return 0
        if not 0 <= address <= 0xffffffff:
            raise ValueError('Multiboot address must fit in 32 bits')
        if address % 0x1000 != 0:
            raise ValueError('Multiboot address must be 4KiB aligned')
        return address

    # debug
    def __repr__(self):
        return f'args:{self.args}, device:{self.device}'

################################################################
@dataclass(frozen = True)
class AttrVal:
    attr: str
    val: any

    # debug
    def __repr__(self):
        return f'|AttrVal| attr:{self.attr}=val:{self.val}'

################################################################
@dataclass(frozen = True)
class PipDesc:
    """ One PIP  """
    x: int
    y: int
    src: str
    dest: str

    # common field
    pipre = re.compile(r"X(\d+)Y(\d+)/([\w_]+)/([\w_]+)")

    # debug
    def __repr__(self):
        return f'|PipDesc| x:{self.x}, y:{self.y}, src:{self.src}, dest:{self.dest}'

################################################################
@dataclass(frozen = True)
class WireDesc:
    """ One wire """
    x: int
    y: int
    name: str

    # debug
    def __repr__(self):
        return f'|WireDesc| x:{self.x}, y:{self.y}, name:{self.name}'

################################################################
@dataclass(frozen = True)
class CellDesc:
    """ One Cell """
    name: str
    typ: str
    parms: dict[str, str]
    attrs: dict[str, str]
    connections: dict[str, list[int]]

    # debug
    def __repr__(self):
        return f'|CellDesc| name:{self.name}, typ:{self.typ}, parms:{self.parms}, attrs:{self.attrs}'

################################################################
IO_BEL_NET_VCC = 1
IO_BEL_NET_GND = 2
IO_BEL_NET_NET = 3

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

    # debug
    def __repr__(self):
        return f'|BelDesc| x:{self.x}, y:{self.y}, idx_str:{self.idx_str}, idx_int:{self.idx_int}, cell:{self.cell}'

@dataclass(frozen = True)
class IoBelDesc(BelDesc):
    """ Io bel """
    flags: dict[str, any]

    def __init__(self, x: int, y: int, idx: str, cell: CellDesc, flags = {}):
        super().__init__(x, y, idx, cell)
        object.__setattr__(self, 'flags', flags)

    def is_mipi_in(self) -> bool:
        return 'MIPI_IBUF' in self.cell.parms

    def is_mipi_out(self) -> bool:
        return 'MIPI_OBUF' in self.cell.parms

    def is_mipi_aux(self) -> bool:
        return 'IS_MIPI_AUX' in self.flags

    def is_mipi(self) -> bool:
        return self.is_mipi_in() or self.is_mipi_out() or self.is_mipi_aux()

    def is_diff_io(self) -> bool:
        return 'DIFF' in self.cell.parms or self.is_mipi()

    def is_i3c_io(self) -> bool:
        return 'I3C_IOBUF' in self.cell.parms

    def is_true_lvds_output(self) -> bool:
        diff_type = self.cell.parms.get('DIFF_TYPE', '')
        return diff_type in {'TLVDS_OBUF', 'TLVDS_TBUF', 'TLVDS_IOBUF'}

    def get_iob_pin_net(self, pin: str) -> int: # IO_BEL_NET_ constants or None
        """ Returns the network type the given pin is connected to. """
        net = self.cell.parms.get(f'NET_{pin}')
        if net:
            return {'VCC': IO_BEL_NET_VCC, 'GND': IO_BEL_NET_GND, 'NET': IO_BEL_NET_NET}[net]
        return None

    # debug
    def __repr__(self):
        return '|IoBelDesc ' + super().__repr__() + f"| flags:{self.flags}"

@dataclass(frozen = True)
class IologicBelDesc(BelDesc):
    """ Iologic bel """
    fclk: str
    main_cell_outmode: str
    main_cell_inmode: str

    def __init__(self, x: int, y: int, idx: str, cell: CellDesc, fclk: str, main_cell_outmode: str, main_cell_inmode: str):
        super().__init__(x, y, idx, cell)
        object.__setattr__(self, 'fclk', fclk)
        object.__setattr__(self, 'main_cell_outmode', main_cell_outmode)
        object.__setattr__(self, 'main_cell_inmode', main_cell_inmode)

    # debug
    def __repr__(self):
        return '|IologicBelDesc ' + super().__repr__() + f"| fclk:{self.fclk}, main_cell_outmode:{self.main_cell_outmode}, main_cell_inmode:{self.main_cell_inmode}"

@dataclass(frozen = True)
class BsramBelDesc(BelDesc):
    """ BSRAM bel """

    def __init__(self, x: int, y: int, idx: str, cell: CellDesc, flags = {}):
        super().__init__(x, y, idx, cell)

    def __lt__(self, other) -> bool:
        """ for bisect.insort """
        if self.x < other.x:
            return True
        return self.x == other.x and self.y < other.y

    def __gt__(self, other) -> bool:
        """ for bisect.insort """
        if self.x > other.x:
            return True
        return self.x == other.x and self.y > other.y

    # debug
    def __repr__(self):
        return '|BsramBelDesc ' + super().__repr__() + "|"

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

    # debug
    def __repr__(self):
        return '|CellFuseBits|' + f" x:{self.x}, y:{self.y}, bits:{self.bits}"

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
        return f'|IoCfg| x:{self.x}, y:{self.y}, idx_str:{self.idx_str}, cfgs:{self.cfgs}'

################################################################
@dataclass(frozen = True)
class IoDiffCfg:
    """ Differential IO configuration """
    positive: bool
    true_lvds: bool

    # debug
    def __repr__(self):
        return f'|IoDiffCfg| positive:{self.positive}, true_lvds:{self.true_lvds}'

################################################################
@dataclass(frozen = True)
class DspIndices:
    """ Block coordinates inside the DSP """
    def __init__(self, mac: int, idx: int):
        object.__setattr__(self, 'mac', mac)
        object.__setattr__(self, 'idx', idx)
        object.__setattr__(self, 'is_even', idx & 1)
        object.__setattr__(self, 'pair_idx', idx // 2)

    # debug
    def __repr__(self):
        return f'|DspIndices| max:{self.mac}, idx:{self.idx}, is_even:{self.is_even}, pair_idx:{self.pair_idx}'

################################################################
@dataclass(frozen = True)
class AdcIo:
    """ ADC input pin """
    x: int
    y: int
    bus: str

    # debug
    def __repr__(self):
        return f'|AdcIo| x:{self.x}, y:{self.y}, bus:{self.bus}'

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
        # must have GND and VCC networks
        self.gnd_net_bits = self.in_file['modules'][self.top_module_name]['netnames']['$PACKER_GND']['bits']
        self.vcc_net_bits = self.in_file['modules'][self.top_module_name]['netnames']['$PACKER_VCC']['bits']

    def get_net_by_bits(self, net_bits: [int]):
        """ Returns net description """
        nets = self.in_file['modules'][self.top_module_name]['netnames']
        for net_name in nets:
            net = nets[net_name]
            for bits in net_bits:
                if bits in net['bits']:
                    return net
        return None

    def is_vcc_net(self, wire: int):
        """ wire - integer id from json """
        return wire in self.vcc_net_bits

    def is_gnd_net(self, wire: int):
        """ wire - integer id from json """
        return wire in self.gnd_net_bits

    def is_constant_net(self, wire: int):
        """ wire - integer id from json """
        return self.is_gnd_net(wire) or self.is_vcc_net(wire)

    def get_device(self) -> str:
        """ The chip specified in the netlist """
        return self.in_file['modules'][self.top_module_name]['settings']['packer.chipdb']

    def get_raw_cell_data(self, name: str) -> dict:
        """ Return cell data values wo modifications (uppercase for exampe) """
        return self.in_file['modules'][self.top_module_name]['cells'][name]

    def fill_cell_desc(self, name: str, cell_data: dict) -> CellDesc:
        """ Fill cell description """
        # uppercase for all cell parameters
        u_params = {k.upper(): v.upper() for k, v in cell_data['parameters'].items()}
        return CellDesc(name, cell_data['type'], u_params, cell_data['attributes'], cell_data['connections'])

    def get_cell(self, name: str) -> CellDesc:
        """ Get cell desc by name """
        return self.fill_cell_desc(name, self.get_raw_cell_data(name))

    def get_pips(self) -> Iterator[PipDesc]:
        """ Pip generator """
        for net in self.in_file['modules'][self.top_module_name]['netnames'].values():
            routing = net['attributes']['ROUTING']
            pips = routing.split(';')[1::3]
            for pip in pips:
                res = PipDesc.pipre.fullmatch(pip)
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
            if not bel_attr or self.is_gnd_vcc_bel(bel_attr) or cell.typ in {'OSER16', 'IDES16'}:
                continue
            bel_groups = belre.match(bel_attr)
            if not bel_groups:
                raise Exception(f"Unknown bel:{bel_attr} for cell {cell.name}")
            col, row, idx = bel_groups.groups()
            x = int(col)
            y = int(row)
            if cell.typ == 'IOB':
                bel = IoBelDesc(x, y, idx, cell)
            elif cell.typ in {'IOLOGIC', 'IOLOGICI', 'IOLOGICO', 'IOLOGIC_DUMMY', 'ODDR', 'ODDRC', 'OSER4',
                   'OSER8', 'OSER10', 'OVIDEO', 'IDDR', 'IDDRC', 'IDES4', 'IDES8', 'IDES10', 'IVIDEO',
                   'IOLOGICI_EMPTY', 'IOLOGICO_EMPTY'}:
                if idx[-1] in 'IO':
                    idx = idx[:-1]
                bel = IologicBelDesc(x, y, idx, cell, 'UNKNOWN', None, None)
            else:
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
        return f'|Netlist| in_file:{self.in_file}, top_module_name:{self.top_module_name}'

################################################################
class ChipDB:
    """ Chip database interface """
    def __init__(self, device_name: str):
        self.device_name = device_name
        with importlib.resources.path('apycula', f'{self.device_name}.msgpack.xz') as path:
            self.db = load_chipdb(path)
        self.simplio_rows = sorted(list(self.db.simplio_rows))

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
        return chipdb.tile_bitmap(self.db, bitmatrix.zeros(self.db.height, self.db.width), empty = True)

    def create_main_tilemap_holes(self, calc_size_func) -> dict:
        """ Return chip tilemap """
        return chipdb.tile_bitmap_holes(self.db, bitmatrix.zeros(self.db.height, self.db.width), empty = True, calc_size_func = calc_size_func)

    def fuse_bitmap(self, tilemap, calc_size_func = None) -> dict:
        """ Tilemap -> Bitmap """
        return chipdb.fuse_bitmap(self.db, tilemap)

    def fuse_bitmap_holes(self, tilemap, calc_size_func) -> dict:
        """ Tilemap -> Bitmap """
        return chipdb.fuse_bitmap_holes(self.db, tilemap, calc_size_func)

    def get_tiledata(self, x: int, y: int) -> Tile:
        """ Get one cell description """
        return self.db[y, x]

    def get_lut_data(self, x: int, y: int, idx: int) -> dict[int, set[Coord]]:
        """ Return LUT encoding """
        return self.get_tiledata(x, y).bels[f'LUT{idx}'].flags

    def get_iob_fuse_cell_offset(self, x: int, y: int, idx_str: str) -> Coord:
        """ Return IOB fuse cell """
        return self.get_tiledata(x, y).bels[f'IOB{idx_str}'].fuse_cell_offset

    def get_alu_modes(self, x: int, y: int, idx: int) -> dict[int, set[Coord]]:
        return self.get_tiledata(x, y).bels[f'ALU{idx}'].modes

    def get_clock_pips(self, tiledata: Tile) -> dict[str, dict[str, set[Coord]]]:
        return tiledata.clock_pips

    def get_hclk_pips_by_xy(self, x: int, y: int) -> dict[str, dict[str, set[Coord]]]:
        return self.db.hclk_pips.get((y, x), {})

    def get_hclk_pips(self) -> dict[tuple[int, int], dict[str, dict[str, set[Coord]]]]:
        return self.db.hclk_pips

    def get_pips(self, tiledata: Tile) -> dict[str, dict[str, set[Coord]]]:
        return tiledata.pips

    def get_alonenode(self, tiledata: Tile) -> dict[str, list[tuple[set[str], set[Coord]]]]:
        return tiledata.alonenode

    def get_alonenode6(self, tiledata: Tile) -> dict[str, list[tuple[set[str], set[Coord]]]]:
        return tiledata.alonenode_6

    def get_dhcen_wire_side(self, x: int, y: int, idx_int) -> tuple[str, str]:
        _, wire, _, side = self.db.extra_func[y, x]['dhcen'][idx_int]['pip']
        return (wire, side)

    def get_dcs_spine(self, x: int, y: int, idx_int) -> str:
        return self.db.extra_func[y, x]['dcs'][idx_int]['clkout']

    def get_slot_idx(self, x: int, y: int, kind: str) -> int:
        return self.db.extra_func[y, x][kind]['slot_idx']

    def get_adc_bus(self, x: int, y: int) -> str:
        return self.db.extra_func[y, x]['adcio']['bus']

    def get_const_fuses(self, x: int, y: int) -> set[Coord]:
        return self.db.const.get(self.get_ttyp(x, y), set())

    def get_slice_attr_val(self, attrval: AttrVal, av: set[tuple[int, int]]):
        add_attr_val(self.db, 'SLICE', av, attrids.cls_attrids[attrval.attr], attrids.cls_attrvals[attrval.val])

    def get_slice_fuses(self, x: int, y: int, idx: int, av: set[tuple[int, int]]) -> set[Coord]:
        return get_shortval_fuses(self.db, self.get_ttyp(x, y), av, f'CLS{idx}')

    def get_gsr_attr_val(self, attrval: AttrVal, av: set[tuple[int, int]]):
        add_attr_val(self.db, 'GSR', av, attrids.gsr_attrids[attrval.attr], attrids.gsr_attrvals[attrval.val])

    def get_gsr_fuses(self, x: int, y: int, av: set[tuple[int, int]]) -> set[Coord]:
        return get_shortval_fuses(self.db, self.get_ttyp(x, y), av, 'GSR')

    def get_cfg_attr_val(self, attrval: AttrVal, av: set[tuple[int, int]]):
        add_attr_val(self.db, 'CFG', av, attrids.cfg_attrids[attrval.attr], attrids.cfg_attrvals[attrval.val])

    def get_cfg_fuses(self, x: int, y: int, av: set[tuple[int, int]]) -> set[Coord]:
        return get_shortval_fuses(self.db, self.get_ttyp(x, y), av, 'CFG')

    def get_bank_attr_val(self, attrval: AttrVal, av: set[tuple[int, int]]):
        add_attr_val(self.db, 'IOB', av, attrids.iob_attrids[attrval.attr], attrids.iob_attrvals[attrval.val])

    def get_bank_fuses(self, x: int, y: int, av: set[tuple[int, int]], bank_idx: int) -> set[Coord]:
        return get_bank_fuses(self.db, self.get_ttyp(x, y), av, 'BANK', bank_idx)

    def get_bank_io_fuses(self, x: int, y: int, av: set[tuple[int, int]]) -> set[Coord]:
        """ XXX Prior to the 5A series, I/O could not be located in the same
        cell as bank control bits, but this has changed in the 5A
        series. The feature remains for now, but further research is needed on
        the coexistence of banks and I/O. """
        return get_bank_io_fuses(self.db, self.get_ttyp(x, y), av)

    def get_iob_attr_val(self, attrval: AttrVal, av: set[tuple[int, int]]):
        add_attr_val(self.db, 'IOB', av, attrids.iob_attrids[attrval.attr], attrids.iob_attrvals[attrval.val])

    def get_io_diff_cfg(self, x: int, y: int, idx_str: str) -> IoDiffCfg:
        bel = self.get_tiledata(x, y).bels[f'IOB{idx_str}']
        if (not bel.is_diff) or bel.simplified_iob:
            return None
        return IoDiffCfg(bool(bel.is_diff_p), bool(bel.is_true_lvds))

    def get_iob_fuses(self, x: int, y: int, av: set[tuple[int, int]], idx_str: str) -> set[Coord]:
        return get_longval_fuses(self.db, self.get_ttyp(x, y), av, f'IOB{idx_str}')

    def get_iologic_attr_val(self, attrval: AttrVal, av: set[tuple[int, int]]):
        add_attr_val(self.db, 'IOLOGIC', av, attrids.iologic_attrids[attrval.attr], attrids.iologic_attrvals[attrval.val])

    def get_iologic_fuses(self, x: int, y: int, av: set[tuple[int, int]], idx_str: str) -> set[Coord]:
        return get_shortval_fuses(self.db, self.get_ttyp(x, y), av, f'IOLOGIC{idx_str}')

    def get_osc_attr_val(self, attrval: AttrVal, av: set[tuple[int, int]]):
        val = attrval.val
        if isinstance(val, str):
            val = attrids.osc_attrvals[val]
        add_attr_val(self.db, 'OSC', av, attrids.osc_attrids[attrval.attr], val)

    def get_osc_fuses(self, x: int, y: int, av: set[tuple[int, int]]) -> set[Coord]:
        return get_shortval_fuses(self.db, self.get_ttyp(x, y), av, f'OSC')

    def get_hclk_attr_val(self, attrval: AttrVal, av: set[tuple[int, int]]):
        val = attrval.val
        if isinstance(val, str):
            val = attrids.hclk_attrvals[val]
        add_attr_val(self.db, 'HCLK', av, attrids.hclk_attrids[attrval.attr], val)

    def get_hclk_fuses(self, x: int, y: int, av: set[tuple[int, int]]) -> set[Coord]:
        return get_shortval_fuses(self.db, self.get_ttyp(x, y), av, f'HCLK')

    def get_pll_attr_val(self, attrval: AttrVal, av: set[tuple[int, int]]):
        val = attrval.val
        if isinstance(val, str):
            val = attrids.pll_attrvals[val]
        add_attr_val(self.db, 'PLL', av, attrids.pll_attrids[attrval.attr], val)

    def get_pll_fuses(self, x: int, y: int, av: set[tuple[int, int]]) -> set[Coord]:
        ttyp = self.get_ttyp(x, y)
        if 'PLL' in self.db.shortval[ttyp]:
            return get_shortval_fuses(self.db, ttyp, av, f'PLL')
        return []

    def get_dcs_attr_val(self, attrval: AttrVal, av: set[tuple[int, int]]):
        add_attr_val(self.db, 'DCS', av, attrids.dcs_attrids[attrval.attr], attrids.dcs_attrvals[attrval.val])

    def get_dcs_fuses(self, x: int, y: int, av: set[tuple[int, int]], dcs_str: str) -> set[Coord]:
        ttyp = self.get_ttyp(x, y)
        lf = self.db.longfuses.get(ttyp, None)
        if lf and dcs_str in lf:
            return get_long_fuses(self.db, ttyp, av, dcs_str)
        return set()

    def get_dhcen_attr_val(self, attrval: AttrVal, av: set[tuple[int, int]]):
        add_attr_val(self.db, 'HCLK', av, attrids.hclk_attrids[attrval.attr], attrids.hclk_attrvals[attrval.val])

    def get_dhcen_fuses(self, x: int, y: int, av: set[tuple[int, int]]) -> set[Coord]:
        ttyp = self.get_ttyp(x, y)
        if 'HCLK' in self.db.shortval[ttyp]:
            return get_shortval_fuses(self.db, ttyp, av, f'HCLK')
        return []

    def get_bsram_attr_val(self, attrval: AttrVal, av: set[tuple[int, int]]):
        val = attrval.val
        if isinstance(val, str):
            val = attrids.bsram_attrvals[val]
        add_attr_val(self.db, 'BSRAM', av, attrids.bsram_attrids[attrval.attr], val)

    def get_bsram_fuses(self, x: int, y: int, av: set[tuple[int, int]], bsram_type: str) -> set[Coord]:
        ttyp = self.get_ttyp(x, y)
        table_name = f'BSRAM_{bsram_type}'
        if table_name in self.db.shortval[ttyp]:
            return get_shortval_fuses(self.db, ttyp, av, table_name)
        return []

    def get_io_cfgs(self) -> Iterator[IoCfg]:
        """ Alternate IO configuration iterator """
        for loc, cfgs in self.db.io_cfg.items():
            x, y, idx_str = self.io_loc_from_str_to_xyidx(loc)
            yield IoCfg(x, y, idx_str, cfgs)

    def get_dsp_attr_val(self, attrval: AttrVal, av: set[tuple[int, int]]):
        val = attrval.val
        if isinstance(val, str):
            val = attrids.dsp_attrvals[val]
        add_attr_val(self.db, 'DSP', av, attrids.dsp_attrids[attrval.attr], val)

    def get_dsp_fuses(self, x: int, y: int, av: set[tuple[int, int]], idx_str: str) -> set[Coord]:
        ttyp = self.get_ttyp(x, y)
        table_name = f'DSP{idx_str[-2]}'
        if table_name in self.db.shortval[ttyp]:
            return get_shortval_fuses(self.db, ttyp, av, table_name)
        return []

    def get_adc_attr_val(self, attrval: AttrVal, av: set[tuple[int, int]]):
        val = attrval.val
        if isinstance(val, str):
            val = attrids.adc_attrvals[val]
        add_attr_val(self.db, 'ADC', av, attrids.adc_attrids[attrval.attr], val)

    def get_adc_fuses(self, x: int, y: int, av: set[tuple[int, int]]) -> set[Coord]:
        ttyp = self.get_ttyp(x, y)
        table_name = 'ADC'
        if table_name in self.db.shortval[ttyp]:
            return get_shortval_fuses(self.db, ttyp, av, table_name)
        return []

    def get_dsp5_attr_val(self, attrval: AttrVal, av: set[tuple[int, int]]):
        val = attrval.val
        if isinstance(val, str):
            val = attrids.dsp_5a_attrvals[val]
        add_attr_val(self.db, '5A_DSP', av, attrids.dsp_5a_attrids[attrval.attr], val)

    def get_dsp5_fuses(self, x: int, y: int, av: set[tuple[int, int]]) -> set[Coord]:
        ttyp = self.get_ttyp(x, y)
        table_name = '5A_DSP'
        if table_name in self.db.shortval[ttyp]:
            return get_shortval_fuses(self.db, ttyp, av, table_name)
        return []

    def get_spine_enable_fuses(self, x: int, y: int, table_name: str) -> set[Coord]:
        ttyp = self.get_ttyp(x, y)
        tab = self.db.shortval[ttyp].get(table_name, None)
        if tab and (1, 0) in tab:
            return tab[(1, 0)]
        return set()

    def get_pll_slot_fuses(self, av: set[tuple[int, int]]) -> set[Coord]:
        return get_shortval_fuses(self.db, 1024, av, 'PLL')

    def get_adc_slot_fuses(self, av: set[tuple[int, int]]) -> set[Coord]:
        return get_shortval_fuses(self.db, 1026, av, 'ADC')

    def get_banks(self) -> Iterator[dict[int, tuple[int, int]]]:
        """ returns bank_idx:(col, row) """
        for idx, row_col in self.db.bank_tiles.items():
            yield idx, (row_col[1], row_col[0])

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

    @property
    def width(self):
        return self.db.width

    @property
    def height(self):
        return self.db.height

    @property
    def empty_x(self):
        return self.db.empty_cell_col

    @property
    def empty_y(self):
        return self.db.empty_cell_row

    def rev_logicinfo(self, table: str):
        return self.db.rev_logicinfo(table)

    # debug
    def __repr__(self):
        return f'|ChipDB| db name:{self.device_name}, rows:{self.rows}, cols:{self.cols}, simplio_rows:{self.simplio_rows}'

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
        return f'|UsedSlices| backet:{self.backet}'

################################################################
class BankDesc:
    """ IO bank """
    _vcc_ios = {'LVCMOS10': '1.0', 'LVCMOS12': '1.2', 'LVCMOS15': '1.5', 'LVCMOS18': '1.8', 'LVCMOS25': '2.5',
                'LVCMOS33': '3.3', 'LVDS25': '2.5', 'LVDS25E': '2.5', 'LVCMOS33D': '3.3', 'LVCMOS_D': '3.3', 'MIPI': '1.2',
                'SSTL15': '1.5', 'SSTL18_I': '1.8', 'SSTL18_II': '1.8', 'SSTL25_I': '2.5', 'SSTL25_II': '2.5',
                'SSTL33_I': '3.3', 'SSTL33_II': '3.3', 'SSTL15D': '1.5', 'SSTL18D_I': '1.8', 'SSTL18D_II': '1.8',
                'SSTL25D_I': '2.5', 'SSTL25D_II': '2.5', 'SSTL33D_I': '3.3', 'SSTL33D_II': '3.3', 'MIPI': '2.5'}

    def __init__(self, x: int, y: int):
        self.x, self.y = x, y
        # Bank has output bels such as OBUF, IOBUF etc
        self.has_outputs = False
        self.has_lvds_outputs = False
        self.has_true_lvds_outputs = False
        # if have LVDS outputs when BANK_VCCIO must be >= this
        self.lvds_BANK_VCCIO = None
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

    @property
    def bank_pull_strength(self) -> str:
        return self.attrs.get("PULL_STRENGTH")

    def set_x_y(self, x: int, y: int):
        """ Set bank cell location """
        self.x = x
        self.y = y

    def set_attr(self, attr: str, val: str):
        self.attrs[attr] = val

    def set_bank_vccio_by_io_type(self, io_type: str):
        self.attrs['BANK_VCCIO'] = self._vcc_ios[io_type]

    def check_or_set_attr(self, bel: IoBelDesc, attr: str):
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
            set_bel = self.set_attr_bels['BANK_VCCIO']
            if self._vcc_ios[io_type] != self.bank_vccio:
                if io_type_bel:
                    raise Exception(f"IO_TYPE and BANK_VCCIO conflict: X{io_type_bel.x}Y{io_type_bel.y}/IOB{io_type_bel.idx_str} ({io_type_bel.cell.name}) is trying to set {io_type} but X{set_bel.x}Y{set_bel.y}/IOB{set_bel.idx_str} ({set_bel.cell.name}) already set {self.bank_vccio}")
                else:
                    raise Exception(f"Default IO_TYPE ({io_type}) and BANK_VCCIO conflict: X{set_bel.x}Y{set_bel.y}/IOB{set_bel.idx_str} ({set_bel.cell.name}) set {self.bank_vccio}")
            if self.has_lvds_outputs:
                if float(self.bank_vccio) < float(self.lvds_BANK_VCCIO):
                    raise Exception(f"BANK_VCCIO conflict: X{set_bel.x}Y{set_bel.y}/IOB{set_bel.idx_str} ({set_bel.cell.name}) set {self.bank_vccio} but LVDS set {self.lvds_BANK_VCCIO}")
        elif self.has_lvds_outputs:
            self.attrs['BANK_VCCIO'] = self.lvds_BANK_VCCIO;

    def add_io_bel(self, device, bel: IoBelDesc):
        """ Add IO to the bank """
        self.bels.append(bel)
        self.check_or_set_attr(bel, 'PULL_STRENGTH')
        if not bel.is_diff_io():
            self.check_or_set_attr(bel, 'IO_TYPE')
            if 'IS_OUTPUT' in bel.flags:
                self.check_or_set_attr(bel, 'BANK_VCCIO')
                self.has_outputs = True
        else: # LVDS
            if 'IS_OUTPUT' in bel.flags:
                if 'IO_TYPE' not in bel.cell.attrs:
                    if bel.is_mipi:
                        io_type = device.get_mipi_io_type()
                    else:
                        raise Exception(f"LVDS bel X{bel.x}Y{bel.y}/IOB{bel.idx_str} must have IO_TYPE.")
                else:
                    io_type = bel.cell.attrs['IO_TYPE']
                self.lvds_BANK_VCCIO = self._vcc_ios[io_type]
                self.has_lvds_outputs = True
                if bel.is_true_lvds_output():
                    self.has_true_lvds_outputs = True

    def get_attrs(self) -> Iterator[AttrVal]:
        for attr, val in self.attrs.items():
            yield AttrVal(attr, val)

    def get_bel_by_xy(self, x: int, y: int, idx_str: str) -> IoBelDesc:
        ret_bel = None
        for bel in self.bels:
            if x == bel.x and y == bel.y and idx_str == bel.idx_str:
                ret_bel = bel
                break
        return ret_bel

    # debug
    def __repr__(self):
        return f'|BankDesc| x:{self.x}, y:{self.y}, attrs:{self.attrs}, has_outputs:{self.has_outputs}, has_lvds_outputs:{self.has_lvds_outputs}, lvds_BANK_VCCIO:{self.lvds_BANK_VCCIO}, set_attr_bels:{self.set_attr_bels}, bels:{self.bels}'

################################################################
class Device:
    """ Base chip. The fuses for a specific chip are set in a class that inherits from this one. """
    def __init__(self, cli_args: CliArgs, pnr: Netlist):
        self.cli_args = cli_args
        self.device_name = cli_args.get_device()
        if not self.device_name:
            self.device_name = pnr.get_device()

        wnames.select_wires(self.device_name)

        # We need access to the design because sometimes the fuses of one cell
        # depend on the parameters of another cell.
        self.pnr = pnr

        self.chipdb = ChipDB(self.device_name)
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
        self.io_banks = dict()
        for bank_idx, x_y in self.chipdb.get_banks():
            x, y = x_y
            self.io_banks[bank_idx] = BankDesc(x, y)

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
        self.default_iobuf_attrs = [('PULLMODE', 'UP'), ('SLEWRATE', 'FAST'),
                 ('DRIVE', '8'), ('HYSTERESIS', 'NONE'), ('CLAMP', 'OFF'), ('DIFFRESISTOR', 'OFF'),
                 ('SINGLERESISTOR', 'OFF'), ('LVDS_OUT', 'OFF'), ('DDR_DYNTERM', 'NA'),
                 ('PERSISTENT', 'OFF'), ('ODMUX', 'TRIMUX'), ('PADDI', 'PADDI'), ('OPENDRAIN', 'OFF')]
        self.default_elvds_ibuf_attrs = [('PADDI', 'PADDI'), ('HYSTERESIS', 'NA'),
                 ('SLEWRATE', 'SLOW'), ('ODMUX_1', 'UNKNOWN'),
                 ('DRIVE', '0'), ('CLAMP', 'OFF'), ('OPENDRAIN', 'OFF'), ('DIFFRESISTOR', 'OFF'),
                 ('VREF', 'OFF'), ('LVDS_OUT', 'OFF')]
        self.default_elvds_obuf_attrs = [('ODMUX_1', '0'), ('PULLMODE', 'NONE'), ('SLEWRATE', 'FAST'),
                 ('DRIVE', '8'), ('HYSTERESIS', 'NA'), ('CLAMP', 'OFF'),
                 ('SINGLERESISTOR', 'OFF'), ('LVDS_OUT', 'OFF'), ('DDR_DYNTERM', 'NA'),
                 ('TO', 'INV'), ('PERSISTENT', 'OFF'), ('ODMUX', 'TRIMUX'),
                 ('OPENDRAIN', 'OFF')]
        self.default_elvds_tbuf_attrs = [('ODMUX_1', 'UNKNOWN'), ('PULLMODE', 'NONE'), ('SLEWRATE', 'FAST'),
                 ('DRIVE', 'UNKNOWN'), ('HYSTERESIS', 'NA'), ('CLAMP', 'OFF'), ('DIFFRESISTOR', 'OFF'),
                 ('SINGLERESISTOR', 'OFF'), ('LVDS_OUT', 'OFF'), ('DDR_DYNTERM', 'NA'),
                 ('TO', 'INV'), ('PERSISTENT', 'OFF'), ('ODMUX', 'TRIMUX'),
                 ('OPENDRAIN', 'OFF')]
        self.default_elvds_iobuf_attrs = [('SLEWRATE', 'FAST'),
                 ('DRIVE', 'UNKNOWN'), ('HYSTERESIS', 'NA'), ('CLAMP', 'OFF'), ('DIFFRESISTOR', 'OFF'),
                 ('SINGLERESISTOR', 'OFF'), ('LVDS_OUT', 'OFF'), ('DDR_DYNTERM', 'NA'),
                 ('PERSISTENT', 'OFF'), ('ODMUX', 'TRIMUX'), ('PADDI', 'PADDI'),
                 ('OPENDRAIN', 'OFF')]
        self.default_tlvds_ibuf_attrs = [('PADDI', 'PADDI'), ('HYSTERESIS', 'NA'),
                 ('SLEWRATE', 'SLOW'), ('ODMUX_1', 'UNKNOWN'), ('PULLMODE', 'NONE'),
                 ('DRIVE', '0'), ('CLAMP', 'OFF'), ('OPENDRAIN', 'OFF'), ('DIFFRESISTOR', 'OFF'),
                 ('VREF', 'OFF'), ('LVDS_OUT', 'OFF')]
        self.default_tlvds_tbuf_attrs = [('ODMUX_1', 'UNKNOWN'), ('PULLMODE', 'NONE'), ('SLEWRATE', 'FAST'),
                 ('DRIVE', '0'), ('HYSTERESIS', 'NA'), ('CLAMP', 'OFF'), ('DIFFRESISTOR', 'OFF'),
                 ('SINGLERESISTOR', 'OFF'), ('DDR_DYNTERM', 'NA'),
                 ('TO', 'INV'), ('PERSISTENT', 'OFF'), ('ODMUX', 'TRIMUX'), ('TRIMUX_PADDT', '0'),
                 ('OPENDRAIN', 'OFF')]
        self.default_tlvds_obuf_attrs = [('ODMUX_1', 'UNKNOWN'), ('PULLMODE', 'NONE'), ('SLEWRATE', 'FAST'),
                 ('DRIVE', '0'), ('HYSTERESIS', 'NA'), ('CLAMP', 'OFF'), ('DIFFRESISTOR', 'OFF'),
                 ('SINGLERESISTOR', 'OFF'), ('DDR_DYNTERM', 'NA'),
                 ('TO', 'INV'), ('PERSISTENT', 'OFF'), ('ODMUX', 'TRIMUX'),
                 ('OPENDRAIN', 'OFF')]
        self.default_tlvds_iobuf_attrs = [('PULLMODE', 'NONE'), ('SLEWRATE', 'FAST'),
                 ('DRIVE', '0'), ('HYSTERESIS', 'NA'), ('CLAMP', 'OFF'), ('DIFFRESISTOR', 'OFF'),
                 ('SINGLERESISTOR', 'OFF'), ('DDR_DYNTERM', 'NA'),
                 ('PERSISTENT', 'OFF'), ('ODMUX', 'TRIMUX'), ('PADDI', 'PADDI'),
                 ('OPENDRAIN', 'OFF')]
        self.default_mipi_tlvds_tbuf_attrs = [('ODMUX_1', 'UNKNOWN'), ('PULLMODE', 'NONE'), ('SLEWRATE', 'FAST'),
                 ('HYSTERESIS', 'NA'), ('CLAMP', 'OFF'), ('DIFFRESISTOR', 'OFF'),
                 ('SINGLERESISTOR', 'OFF'), ('DDR_DYNTERM', 'NA'), ('MIPI', 'ENABLE'), ('IO_TYPE', 'MIPI'),
                 ('LPRX_A1', 'ENABLE'), ('LVDS_ON', 'ENABLE'), ('IOBUF_MIPI_LP', 'ENABLE'),
                 ('TO', 'INV'), ('PERSISTENT', 'OFF'), ('OPENDRAIN', 'OFF'), ('ODMUX', 'TRIMUX')]
        self.default_i3c_iobuf_attrs = [('PULLMODE', 'NONE'), ('SLEWRATE', 'FAST'),
                 ('DRIVE', '8'), ('HYSTERESIS', 'NONE'), ('CLAMP', 'OFF'), ('DIFFRESISTOR', 'NA'),
                 ('SINGLERESISTOR', 'NA'), ('LVDS_OUT', 'OFF'), ('DDR_DYNTERM', 'NA'), ('OD', 'ENABLE'),
                 ('PERSISTENT', 'OFF'), ('ODMUX', 'TRIMUX'), ('PADDI', 'PADDI'), ('OPENDRAIN', 'OFF')]
        self.default_mipi_iobuf_attrs = [('PULLMODE', 'NONE'), ('SLEWRATE', 'SLOW'),
                 ('DRIVE', '8'), ('HYSTERESIS', 'NONE'), ('CLAMP', 'OFF'), ('DIFFRESISTOR', 'OFF'),
                 ('SINGLERESISTOR', 'OFF'), ('LVDS_OUT', 'OFF'), ('DDR_DYNTERM', 'NA'),
                 ('PERSISTENT', 'OFF'), ('ODMUX', 'TRIMUX'), ('PADDI', 'PADDI'), ('OPENDRAIN', 'OFF'),
                 ('LPRX_A1', 'ENABLE')]
        self.default_mipi_aux_ibuf_a_attrs = [('IO_TYPE', 'LVDS25'), ('LPRX_A2', 'ENABLE'), ('ODMUX', 'TRIMUX'),
                ('OPENDRAIN', 'OFF'), ('DIFFRESISTOR', 'OFF'), ('BANK_VCCIO', '2.5')]
        self.default_mipi_aux_ibuf_b_attrs = [('IO_TYPE', 'LVDS25'), ('BANK_VCCIO', '2.5')]

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
        # aux tables for DSP fuse generation
        self._ABLH = [('A', 'L'), ('A', 'H'), ('B', 'L'), ('B', 'H')]
        self._01LH = [(0, 'L'), (1, 'H')]
        # DCSs
        self.dcs_spine2quadrant_idx = {
                'SPINE6'  : ('1', 'DCS6'),
                'SPINE7'  : ('1', 'DCS7'),
                'SPINE14' : ('2', 'DCS6'),
                'SPINE15' : ('2', 'DCS7'),
                'SPINE22' : ('3', 'DCS6'),
                'SPINE23' : ('3', 'DCS7'),
                'SPINE30' : ('4', 'DCS6'),
                'SPINE31' : ('4', 'DCS7'),
                }

        # BSRAM bels with INIT info
        self.bsram_bels_with_init = []

    def get_mipi_io_type(self) -> str:
        return 'LVDS25'

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
        return CellDesc(cell.name, new_typ, cell.parms, new_attrs, cell.connections)

    def normalize_io_bel_attr(self, bel: IoBelDesc) -> IoBelDesc:
        """ Modify IO attrs """
        mod_cell = self.normalize_io_cell_attr(bel.cell)
        io_type = mod_cell.attrs.get('IO_TYPE', None)
        mod_bel = IoBelDesc(bel.x, bel.y, bel.idx_str, mod_cell, bel.flags)
        return mod_bel

    def set_io_bel_flags(self, bel: IoBelDesc, flags_dict: dict[str, any]) -> IoBelDesc:
        """ Set flags like 'is Output' """
        flags = bel.flags
        flags.update(flags_dict)
        return IoBelDesc(bel.x, bel.y, bel.idx_str, bel.cell, flags)

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

    def get_extra_slots(self) -> dict[int, any]:
        raise Exception("get_extra_slots is not implemented.")

    def get_bel_bank(self, bel: BelDesc) -> int:
        """ Get bank for IO bel """
        bank = self.chipdb.get_loc_bank(bel.x, bel.y)
        if bank < 0:
            raise Exception(f"IO bel {bel} is not allowed for a given package.")
        return bank

    def is_clock_pip(self, tiledata: Tile, src: str, dest: str) -> bool:
        return dest in self.chipdb.get_clock_pips(tiledata)

    def is_hclk_pip(self, x: int, y: int, src: str, dest: str) -> bool:
        hclk_pips = self.chipdb.get_hclk_pips_by_xy(x, y)
        return dest in hclk_pips and src in hclk_pips[dest]

    def get_hclk_pip_fuses(self, x: int, y: int, src: str, dest: str) -> set[Coord]:
        return self.chipdb.get_hclk_pips_by_xy(x, y)[dest][src]

    def get_simple_pip_fuses(self, tiledata: Tile, src: str, dest: str) -> set[Coord]:
        """ Return fuses for the simple PIP """
        return self.chipdb.get_pips(tiledata)[dest][src]

    def get_simple_clock_pip_fuses(self, tiledata: Tile, src: str, dest: str) -> set[Coord]:
        """ Return fuses for the simple clock PIP """
        dest_rec = self.chipdb.get_clock_pips(tiledata).get(dest, None)
        if dest_rec:
            return dest_rec.get(src, set())
        return set()

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
        raise Exception(f"Not supported cell type '{bel.cell.typ}'. Cell '{bel.cell.name}'.")

    def error_not_implemented_method(self, method_name: str):
        raise Exception(f"Not implemented method '{method_name}'.")

    #==============================
    #========== PIPs
    #==============================
    def get_inter_hclk_fuses(self, x: int, y: int, src: str, dest: str) -> list[CellFuseBits]:
        if dest in {'HCLK_BANK_OUT0', 'HCLK_BANK_OUT1'}:
            print('inter_hclk', x, y, src, dest)
            raise Exception("HCLK")
        elif dest.startswith('HCLK_TO_IHCLK'):
            print(f"Add IHCLK {sec}->{dest}")
            raise Exception("HCLK")
        return []

    def get_alonenode_fuses(self, tiledata: Tile, src: str, dest: str) -> set[Coord]:
        """ Return fuses if pip's dest is not connected to srcs listen in the alonenode table """
        fuses = set()
        alonenode = self.chipdb.get_alonenode(tiledata)
        for srcs_bits in alonenode.get(dest, []):
            srcs, bits = srcs_bits
            if src not in srcs:
                fuses |= bits
        return fuses

    def get_all_hclk_pip_fuses(self, x: int, y: int, src: str, dest: str) -> list[CellFuseBits]:
        """ Depending on the chip series, fuses can be either in one cell or in several. """
        self.error_not_implemented_method("get_all_hclk_pip_fuses")

    def get_all_pips_fuses(self, pips: Iterator[PipDesc]) -> list[CellFuseBits]:
        """ Return fuses for all PIPs """
        fuses = []
        for pip in pips:
            tiledata = self.chipdb.get_tiledata(pip.x, pip.y)
            if self.is_hclk_pip(pip.x, pip.y, pip.src, pip.dest):
                fuses += self.get_all_hclk_pip_fuses(pip.x, pip.y, pip.src, pip.dest)
            elif self.is_clock_pip(tiledata, pip.src, pip.dest):
                bits = self.get_simple_clock_pip_fuses(tiledata, pip.src, pip.dest)
                if bits:
                    fuses.append(CellFuseBits(pip.x, pip.y, bits))
            else:
                bits = self.get_simple_pip_fuses(tiledata, pip.src, pip.dest)
                bits |= self.get_alonenode_fuses(tiledata, pip.src, pip.dest)
                if bits:
                    fuses.append(CellFuseBits(pip.x, pip.y, bits))
        return fuses

    def get_isolated_wire_fuses(self, wires: Iterator[WireDesc]) -> list[CellFuseBits]:
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

    #==============================
    #========== LUTs
    #==============================
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
        if bits:
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

    def get_MUX2_LUT5_fuses(self, bel: BelDesc) -> list[CellFuseBits]:
        return []

    def get_MUX2_LUT6_fuses(self, bel: BelDesc) -> list[CellFuseBits]:
        return []

    def get_MUX2_LUT7_fuses(self, bel: BelDesc) -> list[CellFuseBits]:
        return []

    def get_MUX2_LUT8_fuses(self, bel: BelDesc) -> list[CellFuseBits]:
        return []

    def get_RAM16SDP4_fuses(self, bel: BelDesc) -> list[CellFuseBits]:
        av = set()

        fuses = []
        for i in range(4):
            init = str(bel.cell.parms[f'INIT_{i}'])
            if len(init) > 16:
                init = init[-16:]
            else:
                init = init*(16//len(init))

            bits = set()
            lutmap = self.chipdb.get_lut_data(bel.x, bel.y, i)
            for bitnum, lutbit in enumerate(init[::-1]):
                if lutbit == '0':
                    bits.update(lutmap[bitnum])

            if bits:
                fuses.append(CellFuseBits(bel.x, bel.y, bits))

            self.used_slices.add_slice_attrs(bel.x, bel.y, i, False, False, [AttrVal('MODE', 'SSRAM')])

        self.used_slices.add_slice_attrs(bel.x, bel.y, 2, False, False, [AttrVal('LSRONMUX', 'LSRMUX'), AttrVal('LSR_MUX_LSR', 'INV'), AttrVal('CLKMUX_1', 'UNKNOWN'), AttrVal('CLKMUX_CLK', 'SIG')])
        return fuses

    #==============================
    #========== DFFs
    #==============================
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

    #==============================
    #========== ALU
    #==============================
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

    #==============================
    #========== Oscillators
    #==============================
    def set_osc_attrvals(self, bel: BelDesc, attr_vals: list[AttrVal]) -> set[int]:
        av = set()
        for attr_val in attr_vals:
            self.chipdb.get_osc_attr_val(attr_val, av)
        return av

    def get_OSC_fuses(self, bel: BelDesc) -> list[CellFuseBits]:
        attr_vals = []
        cell_parms = bel.cell.parms

        val = int(cell_parms.get('FREQ_DIV', bin(100)), 2) # default division coefficient 100
        if val % 2 == 1:
            raise Exception(f"Divisor of the cell '{bel.cell.name}' (OSC) must be even")

        attr_vals.append(AttrVal('MCLKCIB', val))
        attr_vals.append(AttrVal('MCLKCIB_EN', 'ENABLE'))
        attr_vals.append(AttrVal('NORMAL', 'ENABLE'))

        av = self.set_osc_attrvals(bel, attr_vals)

        fuses = []
        bits = self.chipdb.get_osc_fuses(bel.x, bel.y, av)
        if bits:
            fuses.append(CellFuseBits(bel.x, bel.y, bits))
        return fuses

    def get_OSCA_fuses(self, bel: BelDesc) -> list[CellFuseBits]:
        self.error_not_supported_cell_type(bel)

    def get_OSCF_fuses(self, bel: BelDesc) -> list[CellFuseBits]:
        self.error_not_supported_cell_type(bel)

    def get_OSCH_fuses(self, bel: BelDesc) -> list[CellFuseBits]:
        self.error_not_supported_cell_type(bel)

    def get_OSCO_fuses(self, bel: BelDesc) -> list[CellFuseBits]:
        self.error_not_supported_cell_type(bel)

    def get_OSCW_fuses(self, bel: BelDesc) -> list[CellFuseBits]:
        self.error_not_supported_cell_type(bel)

    def get_OSCZ_fuses(self, bel: BelDesc) -> list[CellFuseBits]:
        self.error_not_supported_cell_type(bel)

    #==============================
    #========== Misc
    #==============================
    def get_DUMMY_CELL_fuses(self, bel: BelDesc) -> list[CellFuseBits]:
        return []

    def get_BUFG_fuses(self, bel: BelDesc) -> list[CellFuseBits]:
        """ Logic -> clock gate """
        self.error_not_supported_cell_type(bel)

    def get_BANDGAP_fuses(self, bel: BelDesc) -> list[CellFuseBits]:
        self.error_not_supported_cell_type(bel)

    def get_GSR_fuses(self, bel: BelDesc) -> list[CellFuseBits]:
        """ Global Set/Reset """
        self.error_not_supported_cell_type(bel)

    def get_FLASH64KZ_fuses(self, bel: BelDesc) -> list[CellFuseBits]:
        self.error_not_supported_cell_type(bel)

    def get_FLASH256K_fuses(self, bel: BelDesc) -> list[CellFuseBits]:
        self.error_not_supported_cell_type(bel)

    def get_FLASH608K_fuses(self, bel: BelDesc) -> list[CellFuseBits]:
        self.error_not_supported_cell_type(bel)

    def get_EMCU_fuses(self, bel: BelDesc) -> list[CellFuseBits]:
        self.error_not_supported_cell_type(bel)

    def get_cfgs_types(self) -> set[int]:
        self.error_not_implemented_method('get_cfg_types')

    def get_pins_attr_vals(self) -> list[AttrVal]:
        self.error_not_implemented_method('get_pins_attr_vals')

    def get_dualpin_fuses(self) -> list[CellFuseBits]:
        """ Dual purpose pins """
        pins_attr_vals = self.get_pins_attr_vals()
        av = set()
        for attrval in pins_attr_vals:
            self.chipdb.get_cfg_attr_val(attrval, av)

        cfg_types = self.get_cfg_types()

        fuses = []
        for x, y in itertools.product(range(self.chipdb.cols), range(self.chipdb.rows)):
            ttyp = self.chipdb.get_ttyp(x, y)
            bits = set()
            if ttyp in cfg_types:
                bits = self.chipdb.get_cfg_fuses(x, y, av)
                if bits:
                    fuses.append(CellFuseBits(x, y, bits))
        return fuses

    def get_work_in_progress_fuses(self) -> list[CellFuseBits]:
        """ Setting bits whose purpose is unclear or roughly clear, but the
        mechanism hasn't been fully developed. For example, if a chip doesn't
        yet support segment wires in nextpnr, the ends of segments still need
        to be insulated. """
        return []

    #==============================
    #========== IO
    #==============================
    def get_default_pull_strength(self) -> str:
        self.error_not_implemented_method('get_default_pull_strength')

    def get_default_io_type(self) -> str:
        """ Default IO_TYPE """
        return "LVCMOS12"

    def get_default_elvds_io_type(self) -> str:
        """ Default IO_TYPE """
        return "LVDS25E"

    def get_default_tlvds_io_type(self) -> str:
        """ Default IO_TYPE """
        return "LVDS25"

    def get_default_unused_io_type(self) -> str:
        """ Default IO_TYPE for unused IO """
        return "LVCMOS18"

    def get_unused_io_attrvals(self, io_cfg: IoCfg, bank: BankDesc) -> list[AttrVal]:
        """ Attributes for unused IO """
        return []

    def get_iob_fuses(self, x: int, y: int, idx_str: str, av: set[int]) -> list[CellFuseBits]:
        """ In the 5A series, A and B blocks have fuses in different cells. To
        avoid repeating common code, we're moving the actual fuse generation to
        an auxiliary method. """
        self.error_not_implemented_method('get_iob_fuses')

    def do_not_touch_io(self, x: int, y: int, idx_str: str) -> bool:
        """ Do not set fuses for this IO """
        return False

    def get_unused_io_fuses(self) -> list[CellFuseBits]:
        """ Set attributes for unused banks and return fuses for all unused IOs """
        for bank_desc in self.io_banks.values():
            if not bank_desc.is_used:
                bank_desc.set_attr("IO_TYPE", self.get_default_unused_io_type())
                bank_desc.set_bank_vccio_by_io_type(self.get_default_unused_io_type())

        fuses = []
        for io_cfg in self.chipdb.get_io_cfgs():
            bank_idx = self.chipdb.get_loc_bank(io_cfg.x, io_cfg.y)
            if bank_idx == -1:
                continue
            bank_desc = self.io_banks[bank_idx]
            # skip used IO
            io_bel = bank_desc.get_bel_by_xy(io_cfg.x, io_cfg.y, io_cfg.idx_str)
            if io_bel:
                continue

            # skip reserved IO - for exavple used ADC inputs (device specific)
            if self.do_not_touch_io(io_cfg.x, io_cfg.y, io_cfg.idx_str):
                #print('reserved:', io_cfg.x, io_cfg.y, io_cfg.idx_str)
                continue

            #print('unused:', io_cfg.x, io_cfg.y, io_cfg.idx_str)
            av = set()
            for attrval in self.get_unused_io_attrvals(io_cfg, bank_desc):
                #print(attrval)
                self.chipdb.get_iob_attr_val(attrval, av)
            #print(bank_desc.io_type, bank_desc.bank_vccio)
            self.chipdb.get_iob_attr_val(AttrVal("IO_TYPE", bank_desc.io_type), av)
            self.chipdb.get_iob_attr_val(AttrVal("BANK_VCCIO", bank_desc.bank_vccio), av)
            fuses += self.get_iob_fuses(io_cfg.x, io_cfg.y, io_cfg.idx_str, av)
        return fuses

    def get_io_bank_fuses(self) -> list[CellFuseBits]:
        fuses = self.get_unused_io_fuses()

        # Bank fuses
        for bank, bank_desc in self.io_banks.items():
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
        for bank_desc in self.io_banks.values():
            if bank_desc.is_used:
                bank_desc.check_for_vccio_conflict(self.get_default_io_type())
                # set True Lvds output flag
                if bank_desc.has_true_lvds_outputs:
                    bank_desc.set_attr("LVDS_OUT", "ON")
                    default_io_type = self.get_default_tlvds_io_type()
                    bank_desc.set_attr("IO_TYPE", default_io_type)
                if not bank_desc.bank_pull_strength:
                    default_pull_strength = self.get_default_pull_strength()
                    bank_desc.set_attr("PULL_STRENGTH", default_pull_strength)
                if not bank_desc.io_type:
                    # BANK_VCCIO wasn't set
                    default_io_type = self.get_default_io_type()
                    bank_desc.set_attr("IO_TYPE", default_io_type)
                if not bank_desc.bank_vccio:
                    # BANK_VCCIO may be set without IO_TYPE - in case of LVDS for example
                    if bank_desc.has_outputs:
                        bank_desc.set_bank_vccio_by_io_type(bank_desc.io_type)
                    else:
                        bank_desc.set_bank_vccio_by_io_type(self.get_default_io_type())

    def add_io_to_bank(self, bel: IoBelDesc):
        self.io_banks[self.get_bel_bank(bel)].add_io_bel(self, bel)

    # Second pass IO functions
    def set_input_resistor(self, val: str, bel: IoBelDesc, av: set[int]):
        """ Set additional atribute for input resistor """
        if val != 'OFF' and bel.cell.typ in {'IBUF', 'IOBUF', 'TLVDS_IBUF', 'TLVDS_IOBUF', 'ELVDS_IBUF', 'ELVDS_IOBUF'}:
            self.chipdb.get_iob_attr_val(AttrVal('DDR_DYNTERM', 'ON'), av)

    def set_io_attrvals(self, bel: IoBelDesc, default_attrs: list[tuple[str, str]], defaults_only = False) -> set[int]:
        """ Set IO attributes in addition to those specified in default. Or use only default. """
        lvds = bel.cell.typ[1:].startswith('LVDS')
        av = set()
        for attr, val in default_attrs:
            if defaults_only:
                self.chipdb.get_iob_attr_val(AttrVal(attr, val), av)
                continue
            override_val = bel.cell.attrs.get(attr)
            if override_val:
                val = override_val
            # Check for input resistor
            if attr == 'SINGLERESISTOR':
                self.set_input_resistor(val, bel, av)
            self.chipdb.get_iob_attr_val(AttrVal(attr, val), av)
        return av

    def set_iobuf_attrs(self, bel: IoBelDesc, av: set[int]):
        """ Set attributes depending on the OEN pin source """
        net = bel.get_iob_pin_net('OEN')
        if net:
            if net == IO_BEL_NET_GND:
                self.chipdb.get_iob_attr_val(AttrVal("TRIMUX_PADDT", "SIG"), av)
                self.chipdb.get_iob_attr_val(AttrVal("ODMUX_1", "UNKNOWN"), av)
            elif net == IO_BEL_NET_VCC:
                self.chipdb.get_iob_attr_val(AttrVal("TRIMUX_PADDT", "SIG"), av)
                self.chipdb.get_iob_attr_val(AttrVal("ODMUX_1", "0"), av)
            else:
                self.chipdb.get_iob_attr_val(AttrVal("TRIMUX_PADDT", "SIG"), av)
                self.chipdb.get_iob_attr_val(AttrVal("ODMUX_1", "UNKNOWN"), av)
                self.chipdb.get_iob_attr_val(AttrVal("TO", "SIG"), av)
        else:
            self.chipdb.get_iob_attr_val(AttrVal("ODMUX_1", "1"), av)

    def process_OBUF(self, bank_desc: BankDesc, bel: IoBelDesc) -> list[CellFuseBits]:
        av = self.set_io_attrvals(bel, self.default_obuf_attrs)
        fuses = []
        self.chipdb.get_iob_attr_val(AttrVal("IO_TYPE", bank_desc.io_type), av)
        self.chipdb.get_iob_attr_val(AttrVal("BANK_VCCIO", bank_desc.bank_vccio), av)
        fuses += self.get_iob_fuses(bel.x, bel.y, bel.idx_str, av)
        return fuses

    def process_IBUF(self, bank_desc: BankDesc, bel: IoBelDesc) -> list[CellFuseBits]:
        av = self.set_io_attrvals(bel, self.default_ibuf_attrs)
        fuses = []
        self.chipdb.get_iob_attr_val(AttrVal("IO_TYPE", bank_desc.io_type), av)
        self.chipdb.get_iob_attr_val(AttrVal("BANK_VCCIO", bank_desc.bank_vccio), av)
        fuses += self.get_iob_fuses(bel.x, bel.y, bel.idx_str, av)
        return fuses

    def process_TBUF(self, bank_desc: BankDesc, bel: IoBelDesc) -> list[CellFuseBits]:
        av = self.set_io_attrvals(bel, self.default_tbuf_attrs)
        fuses = []
        self.chipdb.get_iob_attr_val(AttrVal("IO_TYPE", bank_desc.io_type), av)
        self.chipdb.get_iob_attr_val(AttrVal("BANK_VCCIO", bank_desc.bank_vccio), av)
        fuses += self.get_iob_fuses(bel.x, bel.y, bel.idx_str, av)
        return fuses

    def process_IOBUF(self, bank_desc: BankDesc, bel: IoBelDesc) -> list[CellFuseBits]:
        if bel.is_i3c_io():
            av = self.set_io_attrvals(bel, self.default_i3c_iobuf_attrs, defaults_only = True)
            self.chipdb.get_iob_attr_val(AttrVal("IO_TYPE", bank_desc.io_type), av)
        elif bel.is_mipi_in():
            if bel.idx_str == 'A':
                av = self.set_io_attrvals(bel, self.default_mipi_iobuf_attrs, defaults_only = True)
                self.chipdb.get_iob_attr_val(AttrVal("IO_TYPE", "LVDS25"), av)
            else:
                av = self.set_io_attrvals(bel, self.default_mipi_iobuf_attrs, defaults_only = True)
        else:
            av = self.set_io_attrvals(bel, self.default_iobuf_attrs)
            self.chipdb.get_iob_attr_val(AttrVal("IO_TYPE", bank_desc.io_type), av)
        fuses = []
        self.chipdb.get_iob_attr_val(AttrVal("BANK_VCCIO", bank_desc.bank_vccio), av)
        self.set_iobuf_attrs(bel, av)

        fuses += self.get_iob_fuses(bel.x, bel.y, bel.idx_str, av)
        return fuses

    # Differential IO functions
    def check_elvds_placement(self, bel: IoBelDesc):
        """ Check Emulation vs True LVDS, postive vs negative pins etc """
        io_diff_cfg = self.chipdb.get_io_diff_cfg(bel.x, bel.y, bel.idx_str)
        if not io_diff_cfg:
            raise Exception(f"X{bel.x}Y{bel.y}/IOB{bel.idx_str} ({bel.cell.name}) cannot be placed - location is not a LVDS pin")
        if io_diff_cfg.true_lvds:
            raise Exception(f"X{bel.x}Y{bel.y}/IOB{bel.idx_str} ({bel.cell.name}) cannot be placed - location is a True LVDS pin")
        if io_diff_cfg.positive != (bel.cell.parms.get('DIFF') == 'P'):
            raise Exception(f"X{bel.x}Y{bel.y}/IOB{bel.idx_str} ({bel.cell.name}) cannot be placed - pin P must be IOBA, pin N must be IOBB")

    def check_tlvds_placement(self, bel: IoBelDesc):
        """ Check Emulation vs True LVDS, postive vs negative pins etc """
        io_diff_cfg = self.chipdb.get_io_diff_cfg(bel.x, bel.y, bel.idx_str)
        if not io_diff_cfg:
            raise Exception(f"X{bel.x}Y{bel.y}/IOB{bel.idx_str} ({bel.cell.name}) cannot be placed - location is not a LVDS pin")
        if not io_diff_cfg.true_lvds:
            raise Exception(f"X{bel.x}Y{bel.y}/IOB{bel.idx_str} ({bel.cell.name}) cannot be placed - location is a Emulated LVDS pin")
        if io_diff_cfg.positive != (bel.cell.parms.get('DIFF') == 'P'):
            raise Exception(f"X{bel.x}Y{bel.y}/IOB{bel.idx_str} ({bel.cell.name}) cannot be placed - pin P must be IOBA, pin N must be IOBB")

    def process_TLVDS_IBUF(self, bank_desc: BankDesc, bel: IoBelDesc) -> list[CellFuseBits]:
        self.check_tlvds_placement(bel)

        av = self.set_io_attrvals(bel, self.default_tlvds_ibuf_attrs)
        fuses = []
        io_type = bel.cell.attrs.get('IO_TYPE')
        if io_type:
            self.chipdb.get_iob_attr_val(AttrVal("IO_TYPE", io_type), av)
        else:
            self.chipdb.get_iob_attr_val(AttrVal("IO_TYPE", self.get_default_tlvds_io_type()), av)

        fuses += self.get_iob_fuses(bel.x, bel.y, bel.idx_str, av)
        return fuses

    def process_TLVDS_TBUF(self, bank_desc: BankDesc, bel: IoBelDesc) -> list[CellFuseBits]:
        self.check_tlvds_placement(bel)

        if bel.is_mipi_out():
            av = self.set_io_attrvals(bel, self.default_mipi_tlvds_tbuf_attrs, defaults_only = True)
        else:
            av = self.set_io_attrvals(bel, self.default_tlvds_tbuf_attrs)
        fuses = []
        io_type = bel.cell.attrs.get('IO_TYPE')
        if io_type:
            self.chipdb.get_iob_attr_val(AttrVal("IO_TYPE", io_type), av)
        else:
            self.chipdb.get_iob_attr_val(AttrVal("IO_TYPE", self.get_default_tlvds_io_type()), av)
        if bel.idx_str == 'A':
            self.chipdb.get_iob_attr_val(AttrVal("LVDS_OUT", "ON"), av)
        self.chipdb.get_iob_attr_val(AttrVal("BANK_VCCIO", bank_desc.bank_vccio), av)
        fuses += self.get_iob_fuses(bel.x, bel.y, bel.idx_str, av)
        return fuses

    def process_TLVDS_OBUF(self, bank_desc: BankDesc, bel: IoBelDesc) -> list[CellFuseBits]:
        self.check_tlvds_placement(bel)

        av = self.set_io_attrvals(bel, self.default_tlvds_obuf_attrs)
        fuses = []
        io_type = bel.cell.attrs.get('IO_TYPE')
        if io_type:
            self.chipdb.get_iob_attr_val(AttrVal("IO_TYPE", io_type), av)
        else:
            self.chipdb.get_iob_attr_val(AttrVal("IO_TYPE", self.get_default_tlvds_io_type()), av)
        if bel.idx_str == 'A':
            self.chipdb.get_iob_attr_val(AttrVal("LVDS_OUT", "ON"), av)
        self.chipdb.get_iob_attr_val(AttrVal("BANK_VCCIO", bank_desc.bank_vccio), av)
        fuses += self.get_iob_fuses(bel.x, bel.y, bel.idx_str, av)
        return fuses

    def process_TLVDS_IOBUF(self, bank_desc: BankDesc, bel: IoBelDesc) -> list[CellFuseBits]:
        self.check_tlvds_placement(bel)

        av = self.set_io_attrvals(bel, self.default_tlvds_iobuf_attrs)
        fuses = []
        io_type = bel.cell.attrs.get('IO_TYPE')
        if io_type:
            self.chipdb.get_iob_attr_val(AttrVal("IO_TYPE", io_type), av)
        else:
            self.chipdb.get_iob_attr_val(AttrVal("IO_TYPE", self.get_default_tlvds_io_type()), av)
        if bel.idx_str == 'A':
            self.chipdb.get_iob_attr_val(AttrVal("LVDS_OUT", "ON"), av)
        self.chipdb.get_iob_attr_val(AttrVal("BANK_VCCIO", bank_desc.bank_vccio), av)
        self.set_iobuf_attrs(bel, av)

        fuses += self.get_iob_fuses(bel.x, bel.y, bel.idx_str, av)
        return fuses

    def process_ELVDS_IBUF(self, bank_desc: BankDesc, bel: IoBelDesc) -> list[CellFuseBits]:
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

        fuses += self.get_iob_fuses(bel.x, bel.y, bel.idx_str, av)
        return fuses

    def process_ELVDS_OBUF(self, bank_desc: BankDesc, bel: IoBelDesc) -> list[CellFuseBits]:
        self.check_elvds_placement(bel)

        av = self.set_io_attrvals(bel, self.default_elvds_obuf_attrs)
        fuses = []
        io_type = bel.cell.attrs.get('IO_TYPE')
        if io_type:
            self.chipdb.get_iob_attr_val(AttrVal("IO_TYPE", io_type), av)
        else:
            self.chipdb.get_iob_attr_val(AttrVal("IO_TYPE", self.get_default_elvds_io_type()), av)
        self.chipdb.get_iob_attr_val(AttrVal("BANK_VCCIO", bank_desc.bank_vccio), av)
        fuses += self.get_iob_fuses(bel.x, bel.y, bel.idx_str, av)
        return fuses

    def process_ELVDS_TBUF(self, bank_desc: BankDesc, bel: IoBelDesc) -> list[CellFuseBits]:
        self.check_elvds_placement(bel)

        av = self.set_io_attrvals(bel, self.default_elvds_tbuf_attrs)
        fuses = []
        io_type = bel.cell.attrs.get('IO_TYPE')
        if io_type:
            self.chipdb.get_iob_attr_val(AttrVal("IO_TYPE", io_type), av)
        else:
            self.chipdb.get_iob_attr_val(AttrVal("IO_TYPE", self.get_default_elvds_io_type()), av)
        self.chipdb.get_iob_attr_val(AttrVal("BANK_VCCIO", bank_desc.bank_vccio), av)
        fuses += self.get_iob_fuses(bel.x, bel.y, bel.idx_str, av)
        return fuses

    def process_ELVDS_IOBUF(self, bank_desc: BankDesc, bel: IoBelDesc) -> list[CellFuseBits]:
        self.check_elvds_placement(bel)

        av = self.set_io_attrvals(bel, self.default_elvds_iobuf_attrs)
        fuses = []
        io_type = bel.cell.attrs.get('IO_TYPE')
        if io_type:
            self.chipdb.get_iob_attr_val(AttrVal("IO_TYPE", io_type), av)
        else:
            self.chipdb.get_iob_attr_val(AttrVal("IO_TYPE", self.get_default_elvds_io_type()), av)
        self.chipdb.get_iob_attr_val(AttrVal("BANK_VCCIO", bank_desc.bank_vccio), av)
        self.set_iobuf_attrs(bel, av)

        fuses += self.get_iob_fuses(bel.x, bel.y, bel.idx_str, av)
        return fuses

    def process_MIPI_IBUF(self, bank_desc: BankDesc, bel: IoBelDesc) -> list[CellFuseBits]:
        if bel.idx_str == 'A':
            av = self.set_io_attrvals(bel, self.default_mipi_aux_ibuf_a_attrs)
        else:
            av = self.set_io_attrvals(bel, self.default_mipi_aux_ibuf_b_attrs)

        fuses = self.get_iob_fuses(bel.x, bel.y, bel.idx_str, av)
        return fuses

    def get_io_fuses(self) -> list[CellFuseBits]:
        """ Second IO pass """
        fuses = []
        for bank_desc in self.io_banks.values():
            if bank_desc.is_used:
                for bel in bank_desc.bels:
                    fuses += getattr(self, f'process_{bel.cell.typ}')(bank_desc, bel)
        return fuses

    def make_IoBelDesc(self, bel: BelDesc, flags = {}) -> IoBelDesc:
        return IoBelDesc(bel.x, bel.y, bel.idx_str, bel.cell, flags)

    def common_io_handler(self, bel: IoBelDesc):
        mod_bel = self.normalize_io_bel_attr(bel)
        self.add_io_to_bank(mod_bel)

    # These are general functions; the fuses for I/O cannot be determined until
    # data on all of them has been collected. Therefore, the fuses will
    # actually be configured by the process_XXX functions.
    def get_OBUF_fuses(self, bel: BelDesc) -> list[CellFuseBits]:
        self.common_io_handler(self.set_io_bel_flags(self.make_IoBelDesc(bel), {'IS_OUTPUT': 1}))
        return []

    def get_IBUF_fuses(self, bel: BelDesc) -> list[CellFuseBits]:
        self.common_io_handler(self.make_IoBelDesc(bel))
        return []

    def get_TBUF_fuses(self, bel: BelDesc) -> list[CellFuseBits]:
        self.common_io_handler(self.set_io_bel_flags(self.make_IoBelDesc(bel), {'IS_OUTPUT': 1}))
        return []

    def get_IOBUF_fuses(self, bel: BelDesc) -> list[CellFuseBits]:
        self.common_io_handler(self.set_io_bel_flags(self.make_IoBelDesc(bel), {'IS_OUTPUT': 1}))
        return []

    def get_MIPI_OBUF_fuses(self, bel: BelDesc) -> list[CellFuseBits]:
        return []

    def get_MIPI_IBUF_fuses(self, bel: BelDesc) -> list[CellFuseBits]:
        # add aux IBUFs
        aux_bel = BelDesc(bel.x + 1, bel.y, 'A', bel.cell)
        self.common_io_handler(self.set_io_bel_flags(self.make_IoBelDesc(aux_bel), {'IS_MIPI_AUX': 1}))
        aux_bel = BelDesc(bel.x + 1, bel.y, 'B', bel.cell)
        self.common_io_handler(self.set_io_bel_flags(self.make_IoBelDesc(aux_bel), {'IS_MIPI_AUX': 1}))
        return []

    def get_PINCFG_fuses(self, bel: BelDesc) -> list[CellFuseBits]:
        self.error_not_supported_cell_type(bel)

    #==============================
    #========== Iologic
    #==============================
    def set_iologic_bel_fclk(self, bel: IologicBelDesc) -> IologicBelDesc:
        """ HCLK and clock spines have same numbers in the tables """
        if bel.cell.typ == 'IOLOGIC_DUMMY':
            cell = self.pnr.get_cell(bel.cell.attrs['MAIN_CELL'])
        else:
            cell = bel.cell
        fclk = {'HCLK_OUT0': 'SPINE10', 'HCLK_OUT1': 'SPINE11', 'HCLK_OUT2': 'SPINE12',
                'HCLK_OUT3': 'SPINE13'}.get(cell.attrs['IOLOGIC_FCLK'], 'UNKNOWN')
        main_cell_outmode = cell.parms.get('OUTMODE')
        main_cell_inmode = cell.parms.get('INMODE')
        return IologicBelDesc(bel.x, bel.y, bel.idx_str, bel.cell, fclk, main_cell_outmode, main_cell_inmode)

    def handle_iodelay(self, bel: IologicBelDesc) -> list[AttrVal]:
        """ Iodelay is a part of iologic """
        attr_vals = []
        iodelay = bel.cell.attrs.get('IODELAY')
        if iodelay == 'IN':
            attr_vals.append(AttrVal("INDEL", "ENABLE"))
        elif iodelay == 'OUT':
            attr_vals.append(AttrVal("OUTDEL", "ENABLE"))
        else:
            return attr_vals
        attr_vals.append(AttrVal("CLKOMUX", "ENABLE"))
        attr_vals.append(AttrVal("IMARG", "ENABLE"))
        attr_vals.append(AttrVal("INDEL_0", "ENABLE"))
        attr_vals.append(AttrVal("INDEL_1", "ENABLE"))

        c_static_delay = bel.cell.parms.get('C_STATIC_DELAY')
        if c_static_delay:
            for i in range(1, 8):
                if c_static_delay[-i] == '1':
                    attr_vals.append(AttrVal(f"DELAY_DEL{i - 1}", "1"))
        return attr_vals

    def common_iologic_handler(self, bel: IologicBelDesc) -> list[AttrVal]:
        attr_vals = []
        cell_parms = bel.cell.parms
        val = cell_parms.get('TXCLK_POL', '0')
        if int(val) == 0:
            attr_vals.append(AttrVal('TSHX', 'SIG'))
        else:
            attr_vals.append(AttrVal('TSHX', 'INV'))
        val = cell_parms.get('HWL', 'FALSE')
        if val == 'TRUE':
            attr_vals.append(AttrVal('UPDATE', 'SAME'))
        val = cell_parms.get('GSREN', 'FALSE')
        if val == 'TRUE':
            attr_vals.append(AttrVal('GSR', 'ENGSR'))
        else:
            attr_vals.append(AttrVal('GSR', 'DISGSR'))
        return attr_vals + self.handle_iodelay(bel)

    def get_out_iologic_attrs(self, bel: IologicBelDesc) -> list[AttrVal]:
        """ OUT iologic attrs """
        attr_vals = []
        cell_parms = bel.cell.parms

        val = cell_parms.get('UPDATE', None)
        if val:
            attr_vals.append(AttrVal('UPDATE', val))

        if cell_parms['OUTMODE'] == 'ODDRX8' or cell_parms['OUTMODE'] == 'DDRENABLE16':
            attr_vals.append(AttrVal('LSROMUX_0', '0'))
        elif cell_parms['OUTMODE'] != 'ODDRX1' or bel.cell.typ == 'ODDRC':
            attr_vals.append(AttrVal('LSROMUX_0', '1'))
        else:
            attr_vals.append(AttrVal('LSROMUX_0', '0'))

        if cell_parms['OUTMODE'] == 'DDRENABLE16':
            attr_vals.append(AttrVal('OUTMODE', 'DDRENABLE'))
            attr_vals.append(AttrVal('ISI', 'ENABLE'))
        elif cell_parms['OUTMODE'] == 'DDRENABLE':
            attr_vals.append(AttrVal('OUTMODE', 'DDRENABLE'))
            attr_vals.append(AttrVal('ISI', 'ENABLE'))
        else:
            attr_vals.append(AttrVal('OUTMODE', cell_parms['OUTMODE']))

        attr_vals.append(AttrVal('LSRIMUX_0', '0'))
        attr_vals.append(AttrVal('CLKOMUX', 'ENABLE'))

        # out fclk
        if cell_parms['OUTMODE'] != 'ODDRX1':
            attr_vals.append(AttrVal('CLKODDRMUX_WRCLK', 'ECLK0'))
        if bel.fclk in {'SPINE12', 'SPINE13'}:
            attr_vals.append(AttrVal('CLKODDRMUX_ECLK', 'ECLK1'))
        elif bel.fclk in {'SPINE10', 'SPINE11'}:
            attr_vals.append(AttrVal('CLKODDRMUX_ECLK', 'ECLK0'))
        else:
            attr_vals.append(AttrVal('CLKODDRMUX_ECLK', 'UNKNOWN'))
        return attr_vals

    def get_in_iologic_attrs(self, bel: IologicBelDesc) -> list[AttrVal]:
        """ IN iologic attrs """
        attr_vals = []
        cell_parms = bel.cell.parms

        if bel.cell.typ not in {'IDDR', 'IDDRC'}:
            attr_vals.append(AttrVal('CLKIMUX_1', '1'))
            attr_vals.append(AttrVal('LSRIMUX_0', '1'))
            if cell_parms['INMODE'] == 'IDDRX8' or cell_parms['INMODE'] == 'DDRENABLE16':
                attr_vals.append(AttrVal('LSRIMUX_0', '0'))
            if cell_parms['INMODE'] == 'DDRENABLE16':
                attr_vals.append(AttrVal('INMODE', 'DDRENABLE'))
                attr_vals.append(AttrVal('ISI', 'ENABLE'))
            elif cell_parms['INMODE'] == 'DDRENABLE':
                attr_vals.append(AttrVal('ISI', 'ENABLE'))
            else:
                attr_vals.append(AttrVal('INMODE', cell_parms['INMODE']))
        elif bel.cell.typ == 'IDDR':
            attr_vals.append(AttrVal('LSRIMUX_0', '0'))
            attr_vals.append(AttrVal('INMODE', cell_parms['INMODE']))
        else:
            attr_vals.append(AttrVal('LSRIMUX_0', 'UNKNOWN'))
            attr_vals.append(AttrVal('LSRMUX_LSR', 'SIG'))
            attr_vals.append(AttrVal('INMODE', cell_parms['INMODE']))

        attr_vals.append(AttrVal('LSROMUX_0', '0'))
        attr_vals.append(AttrVal('CLKIMUX', 'ENABLE'))

        # in fclk
        if bel.fclk in {'SPINE12', 'SPINE13'}:
            attr_vals.append(AttrVal('CLKIDDRMUX_ECLK', 'ECLK1'))
        elif bel.fclk in {'SPINE10', 'SPINE11'}:
            attr_vals.append(AttrVal('CLKIDDRMUX_ECLK', 'ECLK0'))
        return attr_vals

    def set_iologic_attrvals(self, bel: IologicBelDesc, attr_vals: list[AttrVal]) -> set[int]:
        av = set()
        for attr_val in attr_vals:
            self.chipdb.get_iologic_attr_val(attr_val, av)
        return av

    def make_IologicBelDesc(self, bel: BelDesc) -> IologicBelDesc:
        return IologicBelDesc(bel.x, bel.y, bel.idx_str, bel.cell, bel.fclk, bel.main_cell_outmode, bel.main_cell_inmode)

    def common_out_iologic_handler(self, bel: IologicBelDesc) -> list[CellFuseBits]:
        iol_bel = self.make_IologicBelDesc(bel)
        iol_bel = self.set_iologic_bel_fclk(iol_bel)
        attr_vals = self.common_iologic_handler(iol_bel)
        attr_vals += self.get_out_iologic_attrs(iol_bel)

        av = self.set_iologic_attrvals(iol_bel, attr_vals)
        fuses = []
        bits = self.chipdb.get_iologic_fuses(iol_bel.x, iol_bel.y, av, iol_bel.idx_str)
        if bits:
            fuses.append(CellFuseBits(iol_bel.x, iol_bel.y, bits))
        return fuses

    def common_in_iologic_handler(self, bel: IologicBelDesc) -> list[CellFuseBits]:
        iol_bel = self.make_IologicBelDesc(bel)
        iol_bel = self.set_iologic_bel_fclk(iol_bel)
        attr_vals = self.common_iologic_handler(iol_bel)
        attr_vals += self.get_in_iologic_attrs(iol_bel)

        av = self.set_iologic_attrvals(iol_bel, attr_vals)
        fuses = []
        bits = self.chipdb.get_iologic_fuses(iol_bel.x, iol_bel.y, av, iol_bel.idx_str)
        if bits:
            fuses.append(CellFuseBits(iol_bel.x, iol_bel.y, bits))
        return fuses


    def get_ODDR_fuses(self, bel: BelDesc) -> list[CellFuseBits]:
        iol_bel = self.make_IologicBelDesc(bel)
        attr_vals = self.common_iologic_handler(iol_bel)
        attr_vals += self.get_out_iologic_attrs(iol_bel)

        av = self.set_iologic_attrvals(iol_bel, attr_vals)
        fuses = []
        bits = self.chipdb.get_iologic_fuses(iol_bel.x, iol_bel.y, av, iol_bel.idx_str)
        if bits:
            fuses.append(CellFuseBits(iol_bel.x, iol_bel.y, bits))
        return fuses

    def get_ODDRC_fuses(self, bel: BelDesc) -> list[CellFuseBits]:
        return self.get_ODDR_fuses(bel)

    def get_OSER4_fuses(self, bel: BelDesc) -> list[CellFuseBits]:
        return self.common_out_iologic_handler(bel)

    def get_OSER8_fuses(self, bel: BelDesc) -> list[CellFuseBits]:
        return self.common_out_iologic_handler(bel)

    def get_OSER10_fuses(self, bel: BelDesc) -> list[CellFuseBits]:
        return self.common_out_iologic_handler(bel)

    def get_OVIDEO_fuses(self, bel: BelDesc) -> list[CellFuseBits]:
        return self.common_out_iologic_handler(bel)

    def get_IDDR_fuses(self, bel: BelDesc) -> list[CellFuseBits]:
        iol_bel = self.make_IologicBelDesc(bel)
        attr_vals = self.common_iologic_handler(iol_bel)
        attr_vals += self.get_in_iologic_attrs(iol_bel)

        av = self.set_iologic_attrvals(iol_bel, attr_vals)
        fuses = []
        bits = self.chipdb.get_iologic_fuses(iol_bel.x, iol_bel.y, av, iol_bel.idx_str)
        if bits:
            fuses.append(CellFuseBits(iol_bel.x, iol_bel.y, bits))
        return fuses

    def get_IDDRC_fuses(self, bel: BelDesc) -> list[CellFuseBits]:
        return self.get_IDDR_fuses(bel)

    def get_IDES4_fuses(self, bel: BelDesc) -> list[CellFuseBits]:
        return self.common_in_iologic_handler(bel)

    def get_IDES8_fuses(self, bel: BelDesc) -> list[CellFuseBits]:
        return self.common_in_iologic_handler(bel)

    def get_IDES10_fuses(self, bel: BelDesc) -> list[CellFuseBits]:
        return self.common_in_iologic_handler(bel)

    def get_IVIDEO_fuses(self, bel: BelDesc) -> list[CellFuseBits]:
        return self.common_in_iologic_handler(bel)

    def get_IOLOGIC_DUMMY_fuses(self, bel: BelDesc) -> list[CellFuseBits]:
        iol_bel = self.make_IologicBelDesc(bel)
        iol_bel = self.set_iologic_bel_fclk(iol_bel)
        attr_vals = self.common_iologic_handler(iol_bel)
        if iol_bel.main_cell_outmode:
            attr_vals += self.get_out_iologic_attrs(iol_bel)
        else:
            attr_vals += self.get_in_iologic_attrs(iol_bel)

        av = self.set_iologic_attrvals(iol_bel, attr_vals)
        fuses = []
        bits = self.chipdb.get_iologic_fuses(iol_bel.x, iol_bel.y, av, iol_bel.idx_str)
        if bits:
            fuses.append(CellFuseBits(iol_bel.x, iol_bel.y, bits))
        return fuses

    def get_IOLOGICI_EMPTY_fuses(self, bel: BelDesc) -> list[CellFuseBits]:
        iol_bel = self.make_IologicBelDesc(bel)
        attr_vals = self.common_iologic_handler(iol_bel)

        av = self.set_iologic_attrvals(iol_bel, attr_vals)
        fuses = []
        bits = self.chipdb.get_iologic_fuses(iol_bel.x, iol_bel.y, av, iol_bel.idx_str)
        if bits:
            fuses.append(CellFuseBits(iol_bel.x, iol_bel.y, bits))
        return fuses

    def get_IOLOGICO_EMPTY_fuses(self, bel: BelDesc) -> list[CellFuseBits]:
        iol_bel = self.make_IologicBelDesc(bel)
        attr_vals = self.common_iologic_handler(iol_bel)


        fuses = []
        bits = self.chipdb.get_iologic_fuses(iol_bel.x, iol_bel.y, av, iol_bel.idx_str)
        if bits:
            fuses.append(CellFuseBits(iol_bel.x, iol_bel.y, bits))
        return fuses

    def get_IOLOGIC_fuses(self, bel: BelDesc) -> list[CellFuseBits]:
        self.error_not_supported_cell_type(bel)

    #==============================
    #========== Clocks
    #==============================
    def get_permitted_pll_freqs(self) -> tuple[float, float, float, float, float]:
        raise Exception("get_permitted_pll_freqs is not implemented.")

    def get_pll_attrvals(self, bel: BelDesc) -> set[int]:
        """ rPLL attributes - the most common type of PLL in the GW1N and GW2A series """
        av = set()
        cell_parms = bel.cell.parms

        # calc pump
        permitted_freqs = self.get_permitted_pll_freqs()

        fclkin = float(cell_parms.get('FCLKIN', '100.00'))
        if fclkin < 3 or fclkin > permitted_freqs[0]:
            raise Exception(f"The {fclkin}MHz frequency is outside the permissible range of 3-{permitted_freqs[0]}MHz.")

        val = cell_parms.get('FBDIV_SEL', '0')
        fbdiv = 1 + int(val, 2)
        self.chipdb.get_pll_attr_val(AttrVal('FDIV', fbdiv), av)

        val = cell_parms.get('IDIV_SEL', '0')
        idiv = 1 + int(val, 2)
        self.chipdb.get_pll_attr_val(AttrVal('IDIV', idiv), av)

        val = cell_parms.get('ODIV_SEL', '1000')
        odiv = int(val, 2)
        self.chipdb.get_pll_attr_val(AttrVal('ODIV', odiv), av)

        dyn_idiv_sel = cell_parms.get('DYN_IDIV_SEL', 'FALSE')
        if dyn_idiv_sel == 'TRUE':
            self.chipdb.get_pll_attr_val(AttrVal('IDIVSEL', 'DYN'), av)
        dyn_fbdiv_sel = cell_parms.get('DYN_FBDIV_SEL', 'FALSE')
        if dyn_fbdiv_sel == 'TRUE':
            self.chipdb.get_pll_attr_val(AttrVal('FDIVSEL', 'DYN'), av)
        dyn_odiv_sel = cell_parms.get('DYN_ODIV_SEL', 'FALSE')
        if dyn_odiv_sel == 'TRUE':
            self.chipdb.get_pll_attr_val(AttrVal('ODIVSEL', 'DYN'), av)

        if not (dyn_idiv_sel or dyn_fbdiv_sel or dyn_odiv_sel):
            # static. We can immediately check the compatibility of the divisors
            clkout = fclkin * fbdiv / idiv
            if clkout <= permitted_freqs[2] or clkout > permitted_freqs[1]:
                raise Exception(f"CLKOUT = FCLKIN*(FBDIV_SEL+1)/(IDIV_SEL+1) = {clkout}MHz not in range {permitted_freqs[2]} - {permitted_freqs[1]}MHz")
            pfd = fclkin / idiv
            if pfd < 3.0 or pfd > permitted_freqs[0]:
                raise Exception(f"PFD = FCLKIN/(IDIV_SEL+1) = {pfd}MHz not in range 3.0 - {permitted_freqs[0]}MHz")
            fvco = odiv * fclkin * fbdiv / idiv
            if fvco < permitted_freqs[4] or  fvco > permitted_freqs[3]:
                raise Exception(f"VCO = FCLKIN*(FBDIV_SEL+1)*ODIV_SEL/(IDIV_SEL+1) = {fvco}MHz not in range {permitted_freqs[4]} - {permitted_freqs[3]}MHz")

        fref = fclkin / idiv
        fvco = (odiv * fbdiv * fclkin) / idiv
        fclkin_idx, icp, r_idx = self.get_pll_pump(fref, fvco)
        self.chipdb.get_pll_attr_val(AttrVal('ICPSEL', int(icp)), av)
        self.chipdb.get_pll_attr_val(AttrVal('LPR', f'R{r_idx}'), av)
        self.chipdb.get_pll_attr_val(AttrVal('FLDCOUNT', fclkin_idx), av)

        # duty cycle
        if cell_parms.get('DYN_DA_EN', 'FALSE') == 'TRUE':
            self.chipdb.get_pll_attr_val(AttrVal('DPSEL', 'DYN'), av)
            self.chipdb.get_pll_attr_val(AttrVal('DUTY', 0), av)
            self.chipdb.get_pll_attr_val(AttrVal('PHASE', 0), av)
            self.chipdb.get_pll_attr_val(AttrVal('PASEL', 'DISABLE'), av)
            # steps in 50ps
            val = int(cell_parms.get('CLKOUT_DLY_STEP', '0'), 2) * 50
            self.chipdb.get_pll_attr_val(AttrVal('OPDLY', val), av)
            # XXX here is unclear according to the documentation only three
            # values are allowed: 0, 1 and 2, but there are 4 fuses (0, 50,
            # 75, 100). Find out what to do with 75
            val = int(cell_parms.get('CLKOUTP_DLY_STEP', '0'), 2) * 50
            self.chipdb.get_pll_attr_val(AttrVal('OSDLY', val), av)
        else:
            self.chipdb.get_pll_attr_val(AttrVal('OSDLY', 'DISABLE'), av)
            self.chipdb.get_pll_attr_val(AttrVal('OPDLY', 'DISABLE'), av)
            phase_val = int(cell_parms.get('PSDA_SEL', '0').strip(), 2)
            self.chipdb.get_pll_attr_val(AttrVal('PHASE', phase_val), av)
            self.chipdb.get_pll_attr_val(AttrVal('PASEL', 0), av)
            duty_val = int(cell_parms.get('DUTYDA_SEL', '1000').strip(), 2)
            # XXX there are fuses for 15 variants (excluding 0) so for now
            # we will implement all of them, including those prohibited by
            # documentation 1 and 15
            if (phase_val + duty_val) < 16:
                duty_val = phase_val + duty_val
            else:
                duty_val = phase_val + duty_val - 16
            self.chipdb.get_pll_attr_val(AttrVal('DUTY', duty_val), av)

        # set other attributes
        val = int(cell_parms.get('DYN_SDIV_SEL', '10'), 2)
        self.chipdb.get_pll_attr_val(AttrVal('SDIV', val), av)
        val = cell_parms.get('CLKOUTD_SRC', 'CLKOUT')
        if val == 'CLKOUTP':
            self.chipdb.get_pll_attr_val(AttrVal('CLKOUTDIVSEL', 'CLKOUTPS'), av)
        val = cell_parms.get('CLKOUTD3_SRC', 'CLKOUT')
        if val == 'CLKOUTP':
            self.chipdb.get_pll_attr_val(AttrVal('CLKOUTDIV3SEL', 'CLKOUTPS'), av)
        val = cell_parms.get('CLKOUT_BYPASS', 'FALSE')
        if val == 'TRUE':
            self.chipdb.get_pll_attr_val(AttrVal('BYPCK', 'BYPASS'), av)
        val = cell_parms.get('CLKOUTP_BYPASS', 'FALSE')
        if val == 'TRUE':
            self.chipdb.get_pll_attr_val(AttrVal('BYPCKPS', 'BYPASS'), av)
        val = cell_parms.get('CLKOUTD_BYPASS', 'FALSE')
        if val == 'TRUE':
            self.chipdb.get_pll_attr_val(AttrVal('BYPCKDIV', 'BYPASS'), av)

        val = cell_parms.get('INSEL', 'CLKIN1')
        self.chipdb.get_pll_attr_val(AttrVal('INSEL', val), av)

        # set internal attrs
        self.chipdb.get_pll_attr_val(AttrVal('FBSEL', 'CLKFB3'), av)
        self.chipdb.get_pll_attr_val(AttrVal('PLOCK', 'ENABLE'), av)
        self.chipdb.get_pll_attr_val(AttrVal('FLOCK', 'ENABLE'), av)
        self.chipdb.get_pll_attr_val(AttrVal('FLTOP', 'ENABLE'), av)
        self.chipdb.get_pll_attr_val(AttrVal('GMCMODE', 15), av)
        self.chipdb.get_pll_attr_val(AttrVal('GMCGAIN', 0), av)
        self.chipdb.get_pll_attr_val(AttrVal('CLKOUTDIV3', 'ENABLE'), av)
        self.chipdb.get_pll_attr_val(AttrVal('CLKOUTDIV', 'ENABLE'), av)
        self.chipdb.get_pll_attr_val(AttrVal('CLKOUTPS', 'ENABLE'), av)
        self.chipdb.get_pll_attr_val(AttrVal('PDN', 'ENABLE'), av)
        self.chipdb.get_pll_attr_val(AttrVal('IRSTEN', 'DISABLE'), av)
        self.chipdb.get_pll_attr_val(AttrVal('SRSTEN', 'DISABLE'), av)
        self.chipdb.get_pll_attr_val(AttrVal('PWDEN', 'ENABLE'), av)
        self.chipdb.get_pll_attr_val(AttrVal('RSTEN', 'ENABLE'), av)
        self.chipdb.get_pll_attr_val(AttrVal('VCOBIAS_EN_D', 'ENABLE'), av)
        self.chipdb.get_pll_attr_val(AttrVal('VCOBIAS_EN_U', 'ENABLE'), av)

        return av

    def get_pll_freq_R(self) -> list[tuple[float, float]]:
        raise Exception("get_pll_freq_R is not implemented.")

    def get_pll_coeffs(self, fvco: float) -> tuple[float, float]:
        raise Exception("get_pll_coeffs is not implemented.")

    def get_pll_pump(self, fref: float, fvco: float) -> tuple[int, int, int]:
        """ input params are calculated as described in GOWIN doc (UG286-1.7E_Gowin Clock User Guide)
         fref = fclkin / idiv
         fvco = (odiv * fdiv * fclkin) / idiv

         returns (fclkin_idx, icp, r_idx)
         fclkin_idx - input frequency range index
         icp - charge current
         r_idx - resistor value index

         There are not many resistors so the whole frequency range is divided into
         30MHz intervals and the number of this interval is one of the fuse sets. But
         the resistor itself is not directly dependent on the input frequency. """

        fclkin_idx = int((fref - 1) // 30)
        if (fclkin_idx == 13 and fref <= 395) or (fclkin_idx == 14 and fref <= 430) or (fclkin_idx == 15 and fref <= 465) or fclkin_idx == 16:
            fclkin_idx = fclkin_idx - 1

        freq_Ri = self.get_pll_freq_R()
        r_vals = [(fr[1], len(freq_Ri) - 1 - idx) for idx, fr in enumerate(freq_Ri) if fr[0] < fref]
        r_vals.reverse()

        # Find the resistor that provides the minimum current through the capacitor
        K1, C1 = self.get_pll_coeffs(fvco)
        Kvco = 1000000.0 * K1
        Ndiv = fvco / fref

        for R1, r_idx in r_vals:
            Ic = (1.8769 / (R1 * R1 * Kvco * C1)) * 4.0 * Ndiv
            if Ic <= 0.00028:
                icp = int(Ic * 100000.0 + 0.5) * 10
                break

        return ((fclkin_idx + 1) * 16, icp, r_idx)

    def common_pll_handler(self, bel: BelDesc) -> list[CellFuseBits]:
        av = self.get_pll_attrvals(bel)

        fuses = []
        bels_x_y = self.get_pll_bels(bel)
        for x_y in bels_x_y:
            x, y = x_y
            bits = self.chipdb.get_pll_fuses(x, y, av)
            if bits:
                fuses.append(CellFuseBits(x, y, bits))
        return fuses

    def get_default_clkdiv_divmode(self) -> str:
        raise Exception("get_default_clkdiv_divmode is not implemented.")

    def get_valid_clkdiv_divmodes(self) -> set[str]:
        raise Exception("get_valid_clkdiv_divmodes is not implemented.")

    def get_clkdiv_bels(self, bel: BelDesc) -> Iterator[tuple[int, int]]:
        """ CLKDIV can occupy several cells """
        yield (bel.x, bel.y)

    def get_clkdiv2_bels(self, bel: BelDesc) -> Iterator[tuple[int, int]]:
        """ CLKDIV2 can occupy several cells """
        yield (bel.x, bel.y)

    def get_clkdiv_divmode(self, bel: BelDesc) -> str:
        def bin_str_to_dec(str_val):
            """ In case the DIV_MODE parameter was not a string, but a binary representation.  """
            bin_pattern = r'^[0,1]+'
            bin_str = re.findall(bin_pattern, str_val)
            if bin_str:
                dec_num = int(bin_str[0], 2)
                return str(dec_num)
            return None

        div_mode = bel.cell.parms.get('DIV_MODE', self.get_default_clkdiv_divmode())
        if div_mode not in self.get_valid_clkdiv_divmodes():
            bin_match = bin_str_to_dec(div_mode)
            if bin_match is None or bin_match not in self.get_valid_clkdiv_divmodes():
                raise Exception(f"Invalid DIV_MODE {bin_match or div_mode} for CLKDIV {bel.cell.name} on device {self.device_name}")
            div_mode = str(bin_match[0])
        return div_mode

    def get_hclk_sections(self, bel: BelDesc) -> tuple[str, str]:
        """ Returns (hclk_idx, section_idx) """
        name_pattern = r'^_HCLK([0,1])_SECT([0,1])$'
        pattern_match = re.findall(name_pattern, bel.idx_str)
        if (not pattern_match):
            import ipdb; ipdb.set_trace()
            raise Exception (f"Unknown HCLK Bel/HCLK Section: {bel.cell.typ}{bel.idx_str}")
        return pattern_match[0]

    def get_dcs_attrvals(self, bel: BelDesc, spine: str) -> set[tuple[int, int]]:
        q, _ = self.dcs_spine2quadrant_idx[spine]
        av = set()
        self.chipdb.get_dcs_attr_val(AttrVal(q, bel.cell.attrs['DCS_MODE']), av)
        return av

    def get_rPLL_fuses(self, bel: BelDesc) -> list[CellFuseBits]:
        self.error_not_supported_cell_type(bel)

    def get_PLLVR_fuses(self, bel: BelDesc) -> list[CellFuseBits]:
        self.error_not_supported_cell_type(bel)

    def get_CLKDIV_fuses(self, bel: BelDesc) -> list[CellFuseBits]:
        hclk_idx, section_idx = self.get_hclk_sections(bel)

        av = set()
        self.chipdb.get_hclk_attr_val(AttrVal(f"HCLKDIV{hclk_idx}_DIV", self.get_clkdiv_divmode(bel)), av)
        if (section_idx == '1'):
            self.chipdb.get_hclk_attr_val(AttrVal(f"HCLKDCS{hclk_idx}_SEL", f"HCLKBK{section_idx}{hclk_idx}"), av)

        fuses = []
        bels_x_y = self.get_clkdiv_bels(bel)
        for x_y in bels_x_y:
            x, y = x_y
            bits = self.chipdb.get_hclk_fuses(x, y, av)
            if bits:
                fuses.append(CellFuseBits(x, y, bits))
        return fuses

    def get_CLKDIV2_fuses(self, bel: BelDesc) -> list[CellFuseBits]:
        hclk_idx, section_idx = self.get_hclk_sections(bel)

        av = set()
        self.chipdb.get_hclk_attr_val(AttrVal(f"BK{section_idx}MUX{hclk_idx}_OUTSEL", "DIV2"), av)

        fuses = []
        bels_x_y = self.get_clkdiv2_bels(bel)
        for x_y in bels_x_y:
            x, y = x_y
            bits = self.chipdb.get_hclk_fuses(x, y, av)
            if bits:
                fuses.append(CellFuseBits(x, y, bits))
        return fuses

    def get_DHCEN_fuses(self, bel: BelDesc) -> list[CellFuseBits]:
        # DHCEN as such is just a control wire and does not have a fuse
        # itself, but HCLK has fuses that allow this control. Here we look
        # for the corresponding HCLK and set its fuses.
        fuses = []
        if 'DHCEN_USED' in bel.cell.attrs:
            wire, side = self.chipdb.get_dhcen_wire_side(bel.x, bel.y, bel.idx_int)

            attrval = {
                'HCLK_IN0': AttrVal('HSB0MUX0_HSTOP', 'HCLKCIBSTOP0'),
                'HCLK_IN1': AttrVal('HSB1MUX0_HSTOP', 'HCLKCIBSTOP2'),
                'HCLK_IN2': AttrVal('HSB0MUX1_HSTOP', 'HCLKCIBSTOP1'),
                'HCLK_IN3': AttrVal('HSB1MUX1_HSTOP', 'HCLKCIBSTOP3'),
                'HCLK_BANK_OUT0': AttrVal('BRGMUX0_BRGSTOP', 'BRGCIBSTOP0'),
                'HCLK_BANK_OUT1': AttrVal('BRGMUX1_BRGSTOP', 'BRGCIBSTOP1'),
            }[wire]
            av = set()
            self.chipdb.get_dhcen_attr_val(attrval, av)

            if side in "TB":
                if side == 'T':
                    y = 0
                else:
                    y = self.chipdb.rows - 1
                for x in range(self.chipdb.cols):
                    bits = self.chipdb.get_dhcen_fuses(x, y, av)
                    if bits:
                        fuses.append(CellFuseBits(x, y, bits))
            else:
                if side == 'L':
                    x = 0
                else:
                    x = self.chipdb.cols - 1
                for y in range(self.chipdb.rows):
                    bits = self.chipdb.get_dhcen_fuses(x, y, av)
                    if bits:
                        fuses.append(CellFuseBits(x, y, bits))
        return fuses

    def get_DQCE_fuses(self, bel: BelDesc) -> list[CellFuseBits]:
        pip = bel.cell.attrs.get('DQCE_PIP', "")
        res = PipDesc.pipre.fullmatch(pip)

        fuses = []
        if res:
            x_s, y_s, dest, src = res.groups()
            x = int(x_s)
            y = int(y_s)
            tiledata = self.chipdb.get_tiledata(x, y)
            bits = self.get_simple_clock_pip_fuses(tiledata, src, dest)
            if bits:
                fuses.append(CellFuseBits(x, y, bits))

        return fuses

    def get_DCS_fuses(self, bel: BelDesc) -> list[CellFuseBits]:
        # DCSs without DCS_MODE are unused
        if 'DCS_MODE' not in bel.cell.attrs:
            return []
        spine = self.chipdb.get_dcs_spine(bel.x, bel.y, bel.idx_int)

        av = self.get_dcs_attrvals(bel, spine)
        _, dcs_str = self.dcs_spine2quadrant_idx[spine]

        fuses = []
        bits = self.chipdb.get_dcs_fuses(bel.x, bel.y, av, dcs_str)
        if bits:
            fuses.append(CellFuseBits(bel.x, bel.y, bits))
        return fuses

    #==============================
    #========== Memory
    #==============================
    def make_BsramBelDesc(self, bel: BelDesc) -> BsramBelDesc:
        return BsramBelDesc(bel.x, bel.y, bel.idx_str, bel.cell)

    def get_bsram_bitwidth(self, width: int, bw = {1: '1', 2: '2', 4: '4', 8: '9', 9: '9', 16: '16', 18: '16', 32: 'X36', 36: 'X36'}) -> str:
        """ default argument trick for spedup """
        return bw[width]

    def is_9bit_bsram(self, bel: BsramBelDesc) -> bool:
        """ 9, 18 or 32 bit bsram """
        return bel.cell.attrs['BSRAM_SUBTYPE'] == 'X9'

    def has_bsram_init_data(self) -> bool:
        """ Were there any bsram with init data """
        return len(self.bsram_bels_with_init) != 0

    def get_bsram_bels_with_init_data(self) -> Iterator[BsramBelDesc]:
        for bel in self.bsram_bels_with_init:
            yield bel

    def get_bsram_cols_iterator(self) -> Iterator[int]:
        def it():
            for bel in self.bsram_bels_with_init:
                yield bel.x
        return it

    def get_bsram_init_map(self):
        """ Returns matrix of bsram init data  """
        def get_bits(init_data, width):
            bit_no = 0
            ptr = -1
            while ptr >= -width:
                if bit_no == 8 or bit_no == 17:
                    if width == 288:
                        yield (init_data[ptr], bit_no, lambda x: x)
                        ptr -= 1
                    else:
                        yield ('0', bit_no, lambda x: x)
                    bit_no = (bit_no + 1) % 18
                else:
                    yield (init_data[ptr], bit_no, lambda x: x + 1)
                    ptr -= 1
                    bit_no = (bit_no + 1) % 18

        # Explanation of what comes from and magic numbers. The process is this: you
        # create a file with one primitive from the BSRAM family. In my case pROM. You
        # give it a completely zero initialization. You generate an image. You specify
        # one single nonzero bit at address 0 in the initialization. You generate an
        # image. You compare. You sweep away garbage like CRC.
        # Repeat 16 times.
        # The 16th bit did not show much, but it allowed us to discover the meaning of
        # the logicinfo table [39] - this is the location of a bit in the chip
        # depending on its location in a 16-bit word.
        # Next, we set the bits at address 2 (the next 16 bits) and compare. The result
        # is unexpected: the bits no longer end up where we expect, but a certain pattern
        # is present - bits 4 and 5 radically change the position of the bits in the
        # chip, we take this into account.
        # We repeat for bits up to the 13th --- since this is the maximum address in one SRAM block.
        # 256 * bsram rows * chip bit width
        bsram_init_map = bitmatrix.zeros(256 * len(self.chipdb.simplio_rows), self.chipdb.width)

        for bel in self.bsram_bels_with_init:
            # 3 BSRAM cells have width 3 * 60
            loc_map = bitmatrix.zeros(256, 3 * 60)
            width = 288 if self.is_9bit_bsram(bel) else 256

            addr = -1
            for init_row in range(0x40):
                row_name = f'INIT_RAM_{init_row:02X}'
                # skip missing init rows
                if row_name not in bel.cell.parms:
                    addr += 0x100
                    continue
                init_data = bel.cell.parms[row_name]
                #print(f'row:{row_name}', init_data)
                for ptr_bit_inc in get_bits(init_data, width):
                    addr = ptr_bit_inc[2](addr)
                    if ptr_bit_inc[0] == '0':
                        continue
                    logic_line = ptr_bit_inc[1] * 4 + (addr >> 12)
                    bit = self.chipdb.rev_logicinfo('BSRAM_INIT')[logic_line][0] - 1
                    quad = {0x30: 0xc0, 0x20: 0x40, 0x10: 0x80, 0x00: 0x00}[addr & 0x30]
                    map_row = quad + ((addr >> 6) & 0x3f)
                    #print(f'map_row:{map_row}, addr: {addr}, bit {ptr_bit_inc[1]}, bit:{bit}')
                    loc_map[255 - map_row][bit] = 1

            # now put one cell init data into global space
            height = 256
            y = 0
            for brow in self.chipdb.simplio_rows:
                if bel.y == brow:
                    break
                y += height
            x = 0
            for jdx in range(bel.x):
                x += self.chipdb.get_tiledata(jdx, 0).width

            for row in loc_map:
                x0 = x
                for val in row:
                    bsram_init_map[y][x0] = val
                    x0 += 1
                y += 1

        return bsram_init_map

    def add_bsram_to_init(self, bel: BsramBelDesc):
        bisect.insort(self.bsram_bels_with_init, bel)

    def get_bsram_bels(self, bel: BsramBelDesc) -> Iterator[tuple[int, int]]:
        """ BSRAM occupy several cells """
        for off in range(3):
            yield (bel.x + off, bel.y)

    def get_bsram_attrvals(self, bel: BsramBelDesc) -> set[int]:
        if 'INIT_RAM_00' in bel.cell.parms:
            self.add_bsram_to_init(bel)

        av = set()
        self.chipdb.get_bsram_attr_val(AttrVal('MODE', 'ENABLE'), av)
        self.chipdb.get_bsram_attr_val(AttrVal('GSR', 'DISABLE'), av)

        val = bel.cell.parms.get('RESET_MODE', 'SYNC')
        if val == 'ASYNC':
            self.chipdb.get_bsram_attr_val(AttrVal('OUTREG_ASYNC', 'RESET'), av)
        return av

    def common_bsram_handler(self, bel: BsramBelDesc, av: set[int]) -> list[CellFuseBits]:
        fuses = []
        bels_x_y = self.get_bsram_bels(bel)
        for x_y in bels_x_y:
            x, y = x_y
            bits = self.chipdb.get_bsram_fuses(x, y, av, bel.cell.typ)
            if bits:
                fuses.append(CellFuseBits(x, y, bits))
        return fuses

    def get_ROM_fuses(self, bel: BelDesc) -> list[CellFuseBits]:
        """ Read Only bsram """
        bsram_bel = self.make_BsramBelDesc(bel)
        av = self.get_bsram_attrvals(bsram_bel)

        # We bring it into line with what is observed in the Gowin images - in the
        # ROM, port A has a signal CE = VCC and inversion is turned on on this pin.
        # We will provide VCC in nextpnr, and enable the inversion here.
        self.chipdb.get_bsram_attr_val(AttrVal('CEMUX_CEA', 'INV'), av)

        # blksel
        val = bsram_bel.cell.parms.get('BLK_SEL', "111")
        for i in range(3):
            if val[-1 - i] == '0':
                self.chipdb.get_bsram_attr_val(AttrVal(f'CSA_{i}', 'SET'), av)
                self.chipdb.get_bsram_attr_val(AttrVal(f'CSB_{i}', 'SET'), av)

        # bit width
        val = int(bsram_bel.cell.parms.get('BIT_WIDTH', bin(36 if self.is_9bit_bsram(bsram_bel) else 32)), 2)
        bw = self.get_bsram_bitwidth(val)
        if val < 32:
            self.chipdb.get_bsram_attr_val(AttrVal('ROMA_DATA_WIDTH', bw), av)
            self.chipdb.get_bsram_attr_val(AttrVal('ROMB_DATA_WIDTH', bw), av)
        else:
            self.chipdb.get_bsram_attr_val(AttrVal('DBLWA', bw), av)
            self.chipdb.get_bsram_attr_val(AttrVal('DBLWB', bw), av)

        # read mode
        val = int(bsram_bel.cell.parms.get('READ_MODE', bin(0)), 2)
        if val == 1:
            self.chipdb.get_bsram_attr_val(AttrVal('ROMA_REGMODE', 'OUTREG'), av)
            self.chipdb.get_bsram_attr_val(AttrVal('ROMB_REGMODE', 'OUTREG'), av)

        # disable byte enables
        self.chipdb.get_bsram_attr_val(AttrVal('ROMA_BEHB', 'DISABLE'), av)
        self.chipdb.get_bsram_attr_val(AttrVal('ROMA_BELB', 'DISABLE'), av)
        self.chipdb.get_bsram_attr_val(AttrVal('ROMB_BEHB', 'DISABLE'), av)
        self.chipdb.get_bsram_attr_val(AttrVal('ROMB_BELB', 'DISABLE'), av)

        return self.common_bsram_handler(bsram_bel, av)

    def get_SDP_fuses(self, bel: BelDesc) -> list[CellFuseBits]:
        """ Semi Dual Port bsram """
        bsram_bel = self.make_BsramBelDesc(bel)
        av = self.get_bsram_attrvals(bsram_bel)

        # blksel
        val = bsram_bel.cell.parms.get('BLK_SEL_0', "000")
        for i in range(3):
            if val[-1 - i] == '0':
                self.chipdb.get_bsram_attr_val(AttrVal(f'CSA_{i}', 'SET'), av)
        val = bsram_bel.cell.parms.get('BLK_SEL_1', "000")
        for i in range(3):
            if val[-1 - i] == '0':
                self.chipdb.get_bsram_attr_val(AttrVal(f'CSB_{i}', 'SET'), av)

        # bit width
        # Port A
        val = int(bsram_bel.cell.parms.get('BIT_WIDTH_0', bin(36 if self.is_9bit_bsram(bsram_bel) else 32)), 2)
        bw = self.get_bsram_bitwidth(val)
        nets = bel.cell.connections
        if val < 32:
            self.chipdb.get_bsram_attr_val(AttrVal('SDPA_DATA_WIDTH', bw), av)
            if val in {16, 18}:
                constant_byte_enable = self.pnr.is_constant_net(nets['ADA0'][0]) and self.pnr.is_constant_net(nets['ADA1'][0])
                if constant_byte_enable:
                    self.chipdb.get_bsram_attr_val(AttrVal('SDPA_BEHB', 'ENABLE'), av)
                    self.chipdb.get_bsram_attr_val(AttrVal('SDPA_BELB', 'ENABLE'), av)
                else:
                    self.chipdb.get_bsram_attr_val(AttrVal('SDPA_BEHB', 'DISABLE'), av)
                    self.chipdb.get_bsram_attr_val(AttrVal('SDPA_BELB', 'DISABLE'), av)
                self.chipdb.get_bsram_attr_val(AttrVal('SDPB_BEHB', 'DISABLE'), av)
                self.chipdb.get_bsram_attr_val(AttrVal('SDPB_BELB', 'DISABLE'), av)
            else:
                self.chipdb.get_bsram_attr_val(AttrVal('SDPA_BEHB', 'DISABLE'), av)
                self.chipdb.get_bsram_attr_val(AttrVal('SDPA_BELB', 'DISABLE'), av)
                self.chipdb.get_bsram_attr_val(AttrVal('SDPB_BEHB', 'DISABLE'), av)
                self.chipdb.get_bsram_attr_val(AttrVal('SDPB_BELB', 'DISABLE'), av)
        else:
            self.chipdb.get_bsram_attr_val(AttrVal('DBLWA', bw), av)
            constant_byte_enable = self.pnr.is_constant_net(nets['ADA0'][0]) and self.pnr.is_constant_net(nets['ADA1'][0]) \
                                   and self.pnr.is_constant_net(nets['ADA2'][0]) and self.pnr.is_constant_net(nets['ADA3'][0])
            if constant_byte_enable:
                self.chipdb.get_bsram_attr_val(AttrVal('SDPA_BEHB', 'ENABLE'), av)
                self.chipdb.get_bsram_attr_val(AttrVal('SDPA_BELB', 'ENABLE'), av)
                self.chipdb.get_bsram_attr_val(AttrVal('SDPB_BEHB', 'ENABLE'), av)
                self.chipdb.get_bsram_attr_val(AttrVal('SDPB_BELB', 'ENABLE'), av)
            else:
                self.chipdb.get_bsram_attr_val(AttrVal('SDPA_BEHB', 'DISABLE'), av)
                self.chipdb.get_bsram_attr_val(AttrVal('SDPA_BELB', 'DISABLE'), av)
                self.chipdb.get_bsram_attr_val(AttrVal('SDPB_BEHB', 'DISABLE'), av)
                self.chipdb.get_bsram_attr_val(AttrVal('SDPB_BELB', 'DISABLE'), av)
        # Port B
        val = int(bsram_bel.cell.parms.get('BIT_WIDTH_1', bin(36 if self.is_9bit_bsram(bsram_bel) else 32)), 2)
        bw = self.get_bsram_bitwidth(val)
        if val < 32:
            self.chipdb.get_bsram_attr_val(AttrVal('SDPB_DATA_WIDTH', bw), av)
        else:
            self.chipdb.get_bsram_attr_val(AttrVal('DBLWB', bw), av)

        # read mode
        val = int(bsram_bel.cell.parms.get('READ_MODE', bin(0)), 2)
        if val == 1:
            self.chipdb.get_bsram_attr_val(AttrVal('SDPA_REGMODE', 'OUTREG'), av)
            self.chipdb.get_bsram_attr_val(AttrVal('SDPB_REGMODE', 'OUTREG'), av)

        return self.common_bsram_handler(bsram_bel, av)

    def get_SP_fuses(self, bel: BelDesc) -> list[CellFuseBits]:
        """ Single Port bsram """
        bsram_bel = self.make_BsramBelDesc(bel)
        av = self.get_bsram_attrvals(bsram_bel)

        # blksel
        val = bsram_bel.cell.parms.get('BLK_SEL', "000")
        for i in range(3):
            if val[-1 - i] == '0':
                self.chipdb.get_bsram_attr_val(AttrVal(f'CSA_{i}', 'SET'), av)
                self.chipdb.get_bsram_attr_val(AttrVal(f'CSB_{i}', 'SET'), av)

        # bit width
        val = int(bsram_bel.cell.parms.get('BIT_WIDTH', bin(36 if self.is_9bit_bsram(bsram_bel) else 32)), 2)
        bw = self.get_bsram_bitwidth(val)
        nets = bel.cell.connections
        if val < 32:
            self.chipdb.get_bsram_attr_val(AttrVal('SPA_DATA_WIDTH', bw), av)
            self.chipdb.get_bsram_attr_val(AttrVal('SPB_DATA_WIDTH', bw), av)
            if val in {16, 18}:
                constant_byte_enable = self.pnr.is_constant_net(nets['AD0'][0]) and self.pnr.is_constant_net(nets['AD1'][0])
                if constant_byte_enable:
                    self.chipdb.get_bsram_attr_val(AttrVal('SPA_BEHB', 'ENABLE'), av)
                    self.chipdb.get_bsram_attr_val(AttrVal('SPA_BELB', 'ENABLE'), av)
                else:
                    self.chipdb.get_bsram_attr_val(AttrVal('SPA_BEHB', 'DISABLE'), av)
                    self.chipdb.get_bsram_attr_val(AttrVal('SPA_BELB', 'DISABLE'), av)
                self.chipdb.get_bsram_attr_val(AttrVal('SPB_BEHB', 'DISABLE'), av)
                self.chipdb.get_bsram_attr_val(AttrVal('SPB_BELB', 'DISABLE'), av)
            else:
                self.chipdb.get_bsram_attr_val(AttrVal('SPA_BEHB', 'DISABLE'), av)
                self.chipdb.get_bsram_attr_val(AttrVal('SPA_BELB', 'DISABLE'), av)
                self.chipdb.get_bsram_attr_val(AttrVal('SPB_BEHB', 'DISABLE'), av)
                self.chipdb.get_bsram_attr_val(AttrVal('SPB_BELB', 'DISABLE'), av)
        else:
            constant_byte_enable = self.pnr.is_constant_net(nets['AD0'][0]) and self.pnr.is_constant_net(nets['AD1'][0]) \
                                   and self.pnr.is_constant_net(nets['AD2'][0]) and self.pnr.is_constant_net(nets['AD3'][0])
            if constant_byte_enable:
                self.chipdb.get_bsram_attr_val(AttrVal('SPA_BEHB', 'ENABLE'), av)
                self.chipdb.get_bsram_attr_val(AttrVal('SPA_BELB', 'ENABLE'), av)
                self.chipdb.get_bsram_attr_val(AttrVal('SPB_BEHB', 'ENABLE'), av)
                self.chipdb.get_bsram_attr_val(AttrVal('SPB_BELB', 'ENABLE'), av)
            else:
                self.chipdb.get_bsram_attr_val(AttrVal('SPA_BEHB', 'DISABLE'), av)
                self.chipdb.get_bsram_attr_val(AttrVal('SPA_BELB', 'DISABLE'), av)
                self.chipdb.get_bsram_attr_val(AttrVal('SPB_BEHB', 'DISABLE'), av)
                self.chipdb.get_bsram_attr_val(AttrVal('SPB_BELB', 'DISABLE'), av)

        # read mode
        val = int(bsram_bel.cell.parms.get('READ_MODE', bin(0)), 2)
        if val == 1:
            self.chipdb.get_bsram_attr_val(AttrVal('SPA_REGMODE', 'OUTREG'), av)
            self.chipdb.get_bsram_attr_val(AttrVal('SPB_REGMODE', 'OUTREG'), av)

        # write mode
        val = int(bsram_bel.cell.parms.get('WRITE_MODE', bin(0)), 2)
        if val == 1:
            self.chipdb.get_bsram_attr_val(AttrVal('SPA_MODE', 'WT'), av)
            self.chipdb.get_bsram_attr_val(AttrVal('SPB_MODE', 'WT'), av)
        elif val == 2:
            self.chipdb.get_bsram_attr_val(AttrVal('SPA_MODE', 'RBW'), av)
            self.chipdb.get_bsram_attr_val(AttrVal('SPB_MODE', 'RBW'), av)

        return self.common_bsram_handler(bsram_bel, av)

    def get_DP_fuses(self, bel: BelDesc) -> list[CellFuseBits]:
        """ Dual Port bsram """
        bsram_bel = self.make_BsramBelDesc(bel)
        av = self.get_bsram_attrvals(bsram_bel)

        # blksel
        val = bsram_bel.cell.parms.get('BLK_SEL_0', "000")
        for i in range(3):
            if val[-1 - i] == '0':
                self.chipdb.get_bsram_attr_val(AttrVal(f'CSA_{i}', 'SET'), av)
        val = bsram_bel.cell.parms.get('BLK_SEL_1', "000")
        for i in range(3):
            if val[-1 - i] == '0':
                self.chipdb.get_bsram_attr_val(AttrVal(f'CSB_{i}', 'SET'), av)

        # bit width
        # Port A
        val = int(bsram_bel.cell.parms.get('BIT_WIDTH_0', bin(36 if self.is_9bit_bsram(bsram_bel) else 32)), 2)
        bw = self.get_bsram_bitwidth(val)
        nets = bel.cell.connections
        if val < 32:
            self.chipdb.get_bsram_attr_val(AttrVal('DPA_DATA_WIDTH', bw), av)
            if val in {16, 18}:
                constant_byte_enable = self.pnr.is_constant_net(nets['ADA0'][0]) and self.pnr.is_constant_net(nets['ADA1'][0])
                if constant_byte_enable:
                    self.chipdb.get_bsram_attr_val(AttrVal('DPA_BEHB', 'ENABLE'), av)
                    self.chipdb.get_bsram_attr_val(AttrVal('DPA_BELB', 'ENABLE'), av)
                else:
                    self.chipdb.get_bsram_attr_val(AttrVal('DPA_BEHB', 'DISABLE'), av)
                    self.chipdb.get_bsram_attr_val(AttrVal('DPA_BELB', 'DISABLE'), av)
            else:
                self.chipdb.get_bsram_attr_val(AttrVal('DPA_BEHB', 'DISABLE'), av)
                self.chipdb.get_bsram_attr_val(AttrVal('DPA_BELB', 'DISABLE'), av)
        else:
            raise Exception(f"Dual Port bsram (%s) not supported bit width %d for port A.", bel.cell.name, val)

        # Port B
        val = int(bsram_bel.cell.parms.get('BIT_WIDTH_1', bin(36 if self.is_9bit_bsram(bsram_bel) else 32)), 2)
        bw = self.get_bsram_bitwidth(val)
        nets = bel.cell.connections
        if val < 32:
            self.chipdb.get_bsram_attr_val(AttrVal('DPB_DATA_WIDTH', bw), av)
            if val in {16, 18}:
                constant_byte_enable = self.pnr.is_constant_net(nets['ADB0'][0]) and self.pnr.is_constant_net(nets['ADB1'][0])
                if constant_byte_enable:
                    self.chipdb.get_bsram_attr_val(AttrVal('DPB_BEHB', 'ENABLE'), av)
                    self.chipdb.get_bsram_attr_val(AttrVal('DPB_BELB', 'ENABLE'), av)
                else:
                    self.chipdb.get_bsram_attr_val(AttrVal('DPB_BEHB', 'DISABLE'), av)
                    self.chipdb.get_bsram_attr_val(AttrVal('DPB_BELB', 'DISABLE'), av)
            else:
                self.chipdb.get_bsram_attr_val(AttrVal('DPB_BEHB', 'DISABLE'), av)
                self.chipdb.get_bsram_attr_val(AttrVal('DPB_BELB', 'DISABLE'), av)
        else:
            raise Exception(f"Dual Port bsram (%s) not supported bit width %d for port B.", bel.cell.name, val)

        # read mode
        val = int(bsram_bel.cell.parms.get('READ_MODE0', bin(0)), 2)
        if val == 1:
            self.chipdb.get_bsram_attr_val(AttrVal('DPA_REGMODE', 'OUTREG'), av)
        val = int(bsram_bel.cell.parms.get('READ_MODE1', bin(0)), 2)
        if val == 1:
            self.chipdb.get_bsram_attr_val(AttrVal('DPB_REGMODE', 'OUTREG'), av)

        # write mode
        val = int(bsram_bel.cell.parms.get('WRITE_MODE', bin(0)), 2)
        if val == 1:
            self.chipdb.get_bsram_attr_val(AttrVal('DPA_MODE', 'WT'), av)
            self.chipdb.get_bsram_attr_val(AttrVal('DPB_MODE', 'WT'), av)

        return self.common_bsram_handler(bsram_bel, av)

    #==============================
    #========== DSP
    #==============================
    def set_bel_idx(self, bel: BelDesc, idx_str: str) -> BelDesc:
        return BelDesc(bel.x, bel.y, idx_str, bel.cell)

    def dsp_mod_bel_idx(self, bel: BelDesc) -> BelDesc:
        return self.set_bel_idx(bel, bel.idx_str[-1] + bel.idx_str[-1])

    def get_dsp_bels(self, bel: BsramBelDesc) -> Iterator[tuple[int, int]]:
        """ DSP occupy several cells """
        for off in range(9):
            yield (bel.x + off, bel.y)

    def common_dsp_handler(self, bel: BelDesc, attr_vals: list[AttrVal]) -> list[CellFuseBits]:
        av =  set()
        for attrval in attr_vals:
            self.chipdb.get_dsp_attr_val(attrval, av)

        fuses = []
        bels_x_y = self.get_dsp_bels(bel)
        for x_y in bels_x_y:
            x, y = x_y
            bits = self.chipdb.get_dsp_fuses(x, y, av, bel.idx_str)
            if bits:
                fuses.append(CellFuseBits(x, y, bits))
        return fuses

    def decode_dsp_indices(self, bel: BelDesc) -> DspIndices:
        idx = int(bel.idx_str[-1])
        return DspIndices(int(bel.idx_str[-2]), idx)

    def set_padd9_attrvals(self, bel: BelDesc, dsp_indices: DspIndices) -> list[AttrVal]:
        """ 9 """
        attr_vals = []
        cell_parms = bel.cell.parms
        cell_attrs = bel.cell.attrs

        pair_idx = dsp_indices.pair_idx
        idx = dsp_indices.idx
        is_even = dsp_indices.is_even

        ce_val = int(cell_attrs.get('CE', '0'), 2)
        clk_val = int(cell_attrs.get('CLK', '0'), 2)
        reset_val = int(cell_attrs.get('RESET', '0'), 2)

        attr_vals.append(AttrVal(f'CINBY_{pair_idx + 7}', "ENABLE"))
        attr_vals.append(AttrVal(f'CINNS_{pair_idx + 7}', "ENABLE"))
        if pair_idx:
            attr_vals.append(AttrVal('CIR_BYPH_1', "1"))
            attr_vals.append(AttrVal('RCISEL_3', "1"))
        else:
            attr_vals.append(AttrVal('CIR_BYPL_0', "1"))
            attr_vals.append(AttrVal('RCISEL_1', "1"))

        if pair_idx == 0:
            attr_vals.append(AttrVal('MATCH', "ENABLE"))
            attr_vals.append(AttrVal('MATCH_SHFEN', "ENABLE"))
            if 'LAST_IN_CHAIN' in cell_attrs:
                attr_vals.append(AttrVal('PRAD_FBB1', "ENABLE"))

        attr_vals.append(AttrVal(f'PRAD_MUXA0EN_{pair_idx}', "ENABLE"))
        attr_vals.append(AttrVal(f'OR2CIB_EN{pair_idx}L_{pair_idx * 2}', "ENABLE"))

        # sel nets
        val = cell_attrs.get('NET_ASEL', "")
        if val != 'GND':
            if val == 'VCC':
                attr_vals.append(AttrVal(f'PRAD_MUXA1_{pair_idx * 2}', "ENABLE"))
            elif val != "":
                attr_vals.append(AttrVal(f'PRAD_MUXA1_{pair_idx * 2}', "ENABLE"))
                attr_vals.append(AttrVal(f'PRAD_MUXA1_{pair_idx * 2 + 1}', "ENABLE"))

        # dsp registers
        sync_padd_reset = cell_parms.get('PADD_RESET_MODE', 'ASYNC') == 'SYNC'
        for r in 'AB':
            val = int(cell_parms.get(f'{r}REG', '0'), 2)
            if val:
                if is_even:
                    attr_vals.append(AttrVal(f'CEHMUX_REG{r}{pair_idx}', ce_val))
                    attr_vals.append(AttrVal(f'CLKHMUX_REG{r}{pair_idx}', clk_val))
                    attr_vals.append(AttrVal(f'RSTHMUX_REG{r}{pair_idx}', reset_val))
                    if sync_padd_reset:
                        attr_vals.append(AttrVal(f'RSTGENHMUX_REG{r}{pair_idx}', 'SYNC'))
                else:
                    attr_vals.append(AttrVal(f'CELMUX_REG{r}{pair_idx}', ce_val))
                    attr_vals.append(AttrVal(f'CLKLMUX_REG{r}{pair_idx}', clk_val))
                    attr_vals.append(AttrVal(f'RSTLMUX_REG{r}{pair_idx}', reset_val))
                    if sync_padd_reset:
                        attr_vals.append(AttrVal(f'RSTGENLMUX_REG{r}{pair_idx}', 'SYNC'))
            else:
                if is_even:
                    attr_vals.append(AttrVal(f'IRNS_PRAD{pair_idx}{r}H_{pair_idx * 4 + 1}', "ENABLE"))
                    attr_vals.append(AttrVal(f'IRBY_PRAD{pair_idx}{r}H_{pair_idx * 4 + 1}', "ENABLE"))
                else:
                    attr_vals.append(AttrVal(f'IRNS_PRAD{pair_idx}{r}L_{pair_idx * 4}', "ENABLE"))
                    attr_vals.append(AttrVal(f'IRBY_PRAD{pair_idx}{r}L_{pair_idx * 4}', "ENABLE"))

        val = int(cell_parms.get('SOREG', '0'), 2)
        if val:
            if is_even:
                attr_vals.append(AttrVal('CEHMUX_REGSD', ce_val))
                attr_vals.append(AttrVal('CLKHMUX_REGSD', clk_val))
                attr_vals.append(AttrVal('RSTHMUX_REGSD', reset_val))
            else:
                attr_vals.append(AttrVal('CELMUX_REGSD', ce_val))
                attr_vals.append(AttrVal('CLKLMUX_REGSD', clk_val))
                attr_vals.append(AttrVal('RSTLMUX_REGSD', reset_val))
            if sync_padd_reset:
                if is_even:
                    attr_vals.append(AttrVal('RSTGENHMUX_REGSD', 'SYNC'))
                else:
                    attr_vals.append(AttrVal('RSTGENLMUX_REGSD', 'SYNC'))
        else:
            if is_even:
                attr_vals.append(AttrVal('IRBY_IRMATCHH_9', "ENABLE"))
                attr_vals.append(AttrVal('IRNS_IRMATCHH_9', "ENABLE"))
            else:
                attr_vals.append(AttrVal('IRBY_IRMATCHL_8', "ENABLE"))
                attr_vals.append(AttrVal('IRNS_IRMATCHL_8', "ENABLE"))

        val = int(cell_parms.get('BSEL_MODE', '0'), 2)
        if val:
            attr_vals.append(AttrVal(f'PRAD_MUXB_{pair_idx * 2 + 1}', "ENABLE"))
        else:
            attr_vals.append(AttrVal(f'PRAD_MUXB_{pair_idx * 2}', "ENABLE"))

        # mult: * C=1
        attr_vals.append(AttrVal(f'AIRMUX0_{pair_idx}', "ENABLE"))
        attr_vals.append(AttrVal(f'BIRMUX0_{pair_idx * 2}', "ENABLE"))
        if is_even:
            attr_vals.append(AttrVal(f'IRBY_IREG{pair_idx}AH_{pair_idx * 4 + 1}', "ENABLE"))
            attr_vals.append(AttrVal(f'IRNS_IREG{pair_idx}AH_{pair_idx * 4 + 1}', "ENABLE"))
            attr_vals.append(AttrVal(f'IRBY_IREG{pair_idx}BH_{pair_idx * 4 + 3}', "ENABLE"))
            attr_vals.append(AttrVal(f'IRNS_IREG{pair_idx}BH_{pair_idx * 4 + 3}', "ENABLE"))
            attr_vals.append(AttrVal(f'CINNS_{pair_idx * 3}', "ENABLE"))
            attr_vals.append(AttrVal(f'CINBY_{pair_idx * 3}', "ENABLE"))
            attr_vals.append(AttrVal(f'CPRNS_{pair_idx * 3}', "ENABLE"))
            attr_vals.append(AttrVal(f'CPRBY_{pair_idx * 3}', "ENABLE"))
            attr_vals.append(AttrVal(f'CINNS_{pair_idx * 3 + 1}', "ENABLE"))
            attr_vals.append(AttrVal(f'CINBY_{pair_idx * 3 + 1}', "ENABLE"))
            attr_vals.append(AttrVal(f'CPRNS_{pair_idx * 3 + 1}', "ENABLE"))
            attr_vals.append(AttrVal(f'CPRBY_{pair_idx * 3 + 1}', "ENABLE"))
            attr_vals.append(AttrVal(f'PPREG{pair_idx}_NSH_{pair_idx * 2 + 1}', "ENABLE"))
            attr_vals.append(AttrVal(f'PPREG{pair_idx}_BYPH_{pair_idx * 2 + 1}', "ENABLE"))
            attr_vals.append(AttrVal(f'OREG{pair_idx}_NSH_{pair_idx * 2 + 1}', "ENABLE"))
            attr_vals.append(AttrVal(f'OREG{pair_idx}_BYPH_{pair_idx * 2 + 1}', "ENABLE"))
            attr_vals.append(AttrVal(f'OR2CIB_EN{pair_idx}H_{pair_idx * 2 + 1}', "ENABLE"))
        else:
            attr_vals.append(AttrVal(f'IRBY_IREG{pair_idx}AL_{pair_idx * 4}', "ENABLE"))
            attr_vals.append(AttrVal(f'IRNS_IREG{pair_idx}AL_{pair_idx * 4}', "ENABLE"))
            attr_vals.append(AttrVal(f'IRBY_IREG{pair_idx}BL_{pair_idx * 4 + 2}', "ENABLE"))
            attr_vals.append(AttrVal(f'IRNS_IREG{pair_idx}BL_{pair_idx * 4 + 2}', "ENABLE"))
            attr_vals.append(AttrVal(f'CINNS_{pair_idx * 3}', "ENABLE"))
            attr_vals.append(AttrVal(f'CINBY_{pair_idx * 3}', "ENABLE"))
            attr_vals.append(AttrVal(f'CPRNS_{pair_idx * 3}', "ENABLE"))
            attr_vals.append(AttrVal(f'CPRBY_{pair_idx * 3}', "ENABLE"))
            attr_vals.append(AttrVal(f'CINNS_{pair_idx * 3 + 1}', "ENABLE"))
            attr_vals.append(AttrVal(f'CINBY_{pair_idx * 3 + 1}', "ENABLE"))
            attr_vals.append(AttrVal(f'CPRNS_{pair_idx * 3 + 1}', "ENABLE"))
            attr_vals.append(AttrVal(f'CPRBY_{pair_idx * 3 + 1}', "ENABLE"))
            attr_vals.append(AttrVal(f'PPREG{pair_idx}_NSL_{pair_idx * 2}', "ENABLE"))
            attr_vals.append(AttrVal(f'PPREG{pair_idx}_BYPL_{pair_idx * 2}', "ENABLE"))
            attr_vals.append(AttrVal(f'OREG{pair_idx}_NSL_{pair_idx * 2}', "ENABLE"))
            attr_vals.append(AttrVal(f'OREG{pair_idx}_BYPL_{pair_idx * 2}', "ENABLE"))
            attr_vals.append(AttrVal(f'OR2CIB_EN{pair_idx}L_{pair_idx * 2}', "ENABLE"))
        return attr_vals

    def set_mult9x9_attrvals(self, bel: BelDesc, dsp_indices: DspIndices) -> list[AttrVal]:
        """ 9x9 """
        attr_vals = []
        cell_parms = bel.cell.parms
        cell_attrs = bel.cell.attrs

        pair_idx = dsp_indices.pair_idx
        idx = dsp_indices.idx
        is_even = dsp_indices.is_even

        ce_val = int(cell_attrs.get('CE', '0'), 2)
        clk_val = int(cell_attrs.get('CLK', '0'), 2)
        reset_val = int(cell_attrs.get('RESET', '0'), 2)

        attr_vals.append(AttrVal(f'IRASHFEN_{pair_idx}', "1"))
        attr_vals.append(AttrVal(f'IRBSHFEN_{pair_idx}', "1"))
        if pair_idx:
            attr_vals.append(AttrVal('MATCH_SHFEN', "ENABLE"))
        if is_even:
            attr_vals.append(AttrVal(f'OR2CIB_EN{pair_idx}H_{idx}', "ENABLE"))
        else:
            attr_vals.append(AttrVal(f'OR2CIB_EN{pair_idx}L_{idx}', "ENABLE"))

        # sel nets
        val = cell_attrs.get('NET_ASEL', '')
        if val != 'GND':
            if val == 'VCC':
                attr_vals.append(AttrVal(f'AIRMUX1_{pair_idx}', "ENABLE"))
            elif val != "":
                attr_vals.append(AttrVal(f'AIRMUX1_SEL_{pair_idx}', "ENABLE"))

        val = cell_attrs.get('NET_BSEL', '')
        if val != 'GND':
            if val == 'VCC':
                attr_vals.append(AttrVal(f'BIRMUX1_{pair_idx * 2}', "ENABLE"))
            elif val != "":
                attr_vals.append(AttrVal(f'BIRMUX0_{pair_idx * 2}', "ENABLE"))
                attr_vals.append(AttrVal(f'BIRMUX0_{pair_idx * 2 + 1}', "ENABLE"))
                attr_vals.append(AttrVal(f'BIRMUX1_{pair_idx * 2}', "ENABLE"))
                attr_vals.append(AttrVal(f'BIRMUX1_{pair_idx * 2 + 1}', "ENABLE"))

        # dsp registers
        sync_mult_reset = cell_parms.get('MULT_RESET_MODE', 'ASYNC') == 'SYNC'
        for r in 'AB':
            val = int(cell_parms.get(f'{r}REG', '0'), 2)
            if val:
                if is_even:
                    attr_vals.append(AttrVal(f'CEHMUX_REGM{r}{pair_idx}', ce_val))
                    attr_vals.append(AttrVal(f'CLKHMUX_REGM{r}{pair_idx}', clk_val))
                    attr_vals.append(AttrVal(f'RSTHMUX_REGM{r}{pair_idx}', reset_val))
                    if sync_mult_reset:
                        attr_vals.append(AttrVal(f'RSTGENHMUX_REGM{r}{pair_idx}', 'SYNC'))
                else:
                    attr_vals.append(AttrVal(f'CELMUX_REGM{r}{pair_idx}', ce_val))
                    attr_vals.append(AttrVal(f'CLKLMUX_REGM{r}{pair_idx}', clk_val))
                    attr_vals.append(AttrVal(f'RSTLMUX_REGM{r}{pair_idx}', reset_val))
                    if sync_mult_reset:
                        attr_vals.append(AttrVal(f'RSTGENLMUX_REGM{r}{pair_idx}', 'SYNC'))
            else:
                if is_even:
                    attr_vals.append(AttrVal(f'IRBY_IREG{pair_idx}{r}H_{pair_idx * 4 + 1}', "ENABLE"))
                    attr_vals.append(AttrVal(f'IRNS_IREG{pair_idx}{r}H_{pair_idx * 4 + 1}', "ENABLE"))
                else:
                    attr_vals.append(AttrVal(f'IRBY_IREG{pair_idx}{r}L_{pair_idx * 4}', "ENABLE"))
                    attr_vals.append(AttrVal(f'IRNS_IREG{pair_idx}{r}L_{pair_idx * 4}', "ENABLE"))

            val = int(cell_parms.get(f'{r}SIGN_REG', '0'), 2)
            if val:
                attr_vals.append(AttrVal(f'CEMUX_{r}SIGN{pair_idx}1', ce_val))
                attr_vals.append(AttrVal(f'CLKMUX_{r}SIGN{pair_idx}1', clk_val))
                attr_vals.append(AttrVal(f'RSTMUX_{r}SIGN{pair_idx}1', reset_val))
                if sync_mult_reset:
                    attr_vals.append(AttrVal(f'RSTGENMUX_{r}SIGN{pair_idx}1', 'SYNC'))

        val = int(cell_parms.get('PIPE_REG', '0'), 2)
        if val:
            attr_vals.append(AttrVal(f'CEMUX_ASIGN{pair_idx}2', ce_val))
            attr_vals.append(AttrVal(f'CLKMUX_ASIGN{pair_idx}2', clk_val))
            attr_vals.append(AttrVal(f'RSTMUX_ASIGN{pair_idx}2', reset_val))
            attr_vals.append(AttrVal(f'CEMUX_BSIGN{pair_idx}2', ce_val))
            attr_vals.append(AttrVal(f'CLKMUX_BSIGN{pair_idx}2', clk_val))
            attr_vals.append(AttrVal(f'RSTMUX_BSIGN{pair_idx}2', reset_val))
            if is_even:
                attr_vals.append(AttrVal(f'CEHMUX_REGP{pair_idx}', ce_val))
                attr_vals.append(AttrVal(f'CLKHMUX_REGP{pair_idx}', clk_val))
                attr_vals.append(AttrVal(f'RSTHMUX_REGP{pair_idx}', reset_val))
            else:
                attr_vals.append(AttrVal(f'CELMUX_REGP{pair_idx}', ce_val))
                attr_vals.append(AttrVal(f'CLKLMUX_REGP{pair_idx}', clk_val))
                attr_vals.append(AttrVal(f'RSTLMUX_REGP{pair_idx}', reset_val))
            if sync_mult_reset:
                attr_vals.append(AttrVal(f'RSTGENMUX_ASIGN{pair_idx}2', 'SYNC'))
                attr_vals.append(AttrVal(f'RSTGENMUX_BSIGN{pair_idx}2', 'SYNC'))
                if is_even:
                    attr_vals.append(AttrVal(f'RSTGENHMUX_REGP{pair_idx}', 'SYNC'))
                else:
                    attr_vals.append(AttrVal(f'RSTGENLMUX_REGP{pair_idx}', 'SYNC'))
        else:
            attr_vals.append(AttrVal(f'CPRNS_{pair_idx * 3}', "ENABLE"))
            attr_vals.append(AttrVal(f'CPRBY_{pair_idx * 3}', "ENABLE"))
            attr_vals.append(AttrVal(f'CPRNS_{pair_idx * 3 + 1}', "ENABLE"))
            attr_vals.append(AttrVal(f'CPRBY_{pair_idx * 3 + 1}', "ENABLE"))
            if is_even:
                attr_vals.append(AttrVal(f'PPREG{pair_idx}_NSH_{idx}', "ENABLE"))
                attr_vals.append(AttrVal(f'PPREG{pair_idx}_BYPH_{idx}', "ENABLE"))
            else:
                attr_vals.append(AttrVal(f'PPREG{pair_idx}_NSL_{idx}', "ENABLE"))
                attr_vals.append(AttrVal(f'PPREG{pair_idx}_BYPL_{idx}', "ENABLE"))

        val = int(cell_parms.get('OUT_REG', '0'), 2)
        if val:
            if is_even:
                attr_vals.append(AttrVal(f'CEHMUX_OREG{pair_idx}', ce_val))
                attr_vals.append(AttrVal(f'CLKHMUX_OREG{pair_idx}', clk_val))
                attr_vals.append(AttrVal(f'RSTHMUX_OREG{pair_idx}', reset_val))
            else:
                attr_vals.append(AttrVal(f'CELMUX_OREG{pair_idx}', ce_val))
                attr_vals.append(AttrVal(f'CLKLMUX_OREG{pair_idx}', clk_val))
                attr_vals.append(AttrVal(f'RSTLMUX_OREG{pair_idx}', reset_val))
            if sync_mult_reset:
                if is_even:
                    attr_vals.append(AttrVal(f'RSTGENHMUX_OREG{pair_idx}', 'SYNC'))
                else:
                    attr_vals.append(AttrVal(f'RSTGENLMUX_OREG{pair_idx}', 'SYNC'))
        else:
            if is_even:
                attr_vals.append(AttrVal(f'OREG{pair_idx}_BYPH_{idx}', "ENABLE"))
                attr_vals.append(AttrVal(f'OREG{pair_idx}_NSH_{idx}', "ENABLE"))
            else:
                attr_vals.append(AttrVal(f'OREG{pair_idx}_BYPL_{idx}', "ENABLE"))
                attr_vals.append(AttrVal(f'OREG{pair_idx}_NSL_{idx}', "ENABLE"))

        val = int(cell_parms.get('SOA_REG', '0'), 2)
        if val:
            if is_even:
                attr_vals.append(AttrVal('CEHMUX_REGSD', ce_val))
                attr_vals.append(AttrVal('CLKHMUX_REGSD', clk_val))
                attr_vals.append(AttrVal('RSTHMUX_REGSD', reset_val))
            else:
                attr_vals.append(AttrVal('CELMUX_REGSD', ce_val))
                attr_vals.append(AttrVal('CLKLMUX_REGSD', clk_val))
                attr_vals.append(AttrVal('RSTLMUX_REGSD', reset_val))
            if sync_mult_reset:
                if is_even:
                    attr_vals.append(AttrVal('RSTGENHMUX_REGSD', 'SYNC'))
                else:
                    attr_vals.append(AttrVal('RSTGENLMUX_REGSD', 'SYNC'))
        else:
            if is_even:
                attr_vals.append(AttrVal('IRBY_IRMATCHH_9', "ENABLE"))
                attr_vals.append(AttrVal('IRNS_IRMATCHH_9', "ENABLE"))
            else:
                attr_vals.append(AttrVal('IRBY_IRMATCHL_8', "ENABLE"))
                attr_vals.append(AttrVal('IRNS_IRMATCHL_8', "ENABLE"))

        return attr_vals

    def set_alu54d_attrvals(self, bel: BelDesc) -> list[AttrVal]:
        """ ALU54D """
        attr_vals = []
        cell_parms = bel.cell.parms
        cell_attrs = bel.cell.attrs

        ce_val = int(cell_attrs.get('CE', '0'), 2)
        clk_val = int(cell_attrs.get('CLK', '0'), 2)
        reset_val = int(cell_attrs.get('RESET', '0'), 2)

        attr_vals.append(AttrVal('ALU_EN', "ENABLE"))
        for i in range(2, 7):
            attr_vals.append(AttrVal(f'CPRNS_{i}', "ENABLE"))
            attr_vals.append(AttrVal(f'CPRBY_{i}', "ENABLE"))
            if i > 4:
                attr_vals.append(AttrVal(f'CINNS_{i}', "ENABLE"))
                attr_vals.append(AttrVal(f'CINBY_{i}', "ENABLE"))

        attr_vals.append(AttrVal("OPCD_3", "1"))
        attr_vals.append(AttrVal("OPCD_9", "1"))
        attr_vals.append(AttrVal('RCISEL_1', "1"))
        attr_vals.append(AttrVal('RCISEL_3', "1"))

        val = int(cell_parms.get('B_ADD_SUB', '0'), 2)
        if val == 1:
            attr_vals.append(AttrVal('OPCD_7', "1"))

        # cascade link
        if "USE_CASCADE_IN" in cell_attrs:
            attr_vals.append(AttrVal('CSGIN_EXT', "ENABLE"))
            attr_vals.append(AttrVal('CSIGN_PRE', "ENABLE"))
        if "USE_CASCADE_OUT" in cell_attrs:
            attr_vals.append(AttrVal('OR2CASCADE_EN', "ENABLE"))


        val = int(cell_parms.get('ALUD_MODE', '0'), 2)
        if val == 2:
            attr_vals.append(AttrVal('OPCD_1', "1"))
            attr_vals.append(AttrVal('OPCD_5', "1"))
        else:
            if val == 0:
                attr_vals.append(AttrVal('OPCD_6', "1"))

                val = int(cell_parms.get('C_ADD_SUB', '0'), 2)
                if val == 1:
                    attr_vals.append(AttrVal('OPCD_8', "1"))
            else:
                attr_vals.append(AttrVal('OPCD_5', "1"))

            val = cell_attrs.get('NET_ACCLOAD', "")
            if val == "GND":
                attr_vals.append(AttrVal('OPCD_0', "1"))
                attr_vals.append(AttrVal('OPCD_1', "1"))
            elif val == "VCC":
                attr_vals.append(AttrVal('OR2CASCADE_EN', "ENABLE"))
            else:
                attr_vals.append(AttrVal('OR2CASCADE_EN', "ENABLE"))
                attr_vals.append(AttrVal('OPCDDYN_0', "ENABLE"))
                attr_vals.append(AttrVal('OPCDDYN_1', "ENABLE"))
                attr_vals.append(AttrVal('OPCDDYN_INV_0', "ENABLE"))
                attr_vals.append(AttrVal('OPCDDYN_INV_1', "ENABLE"))

        # dsp registers
        sync_alu_reset = cell_parms.get('ALU_RESET_MODE', 'ASYNC') == 'SYNC'

        val = int(cell_parms.get('AREG', '0'), 2)
        if val == 0:
            ii = 0
            attr_vals.append(AttrVal('CIR_BYPL_0', "1"))
            for i, h in [(i, h) for i in "AB" for h in "LH"]:
                attr_vals.append(AttrVal(f'IRBY_IREG0{i}{h}_{ii}', "ENABLE"))
                attr_vals.append(AttrVal(f'IRNS_IREG0{i}{h}_{ii}', "ENABLE"))
                ii += 1
        else:
            for i, h in [(i, h) for i in "AB" for h in "LH"]:
                attr_vals.append(AttrVal(f'CE{h}MUX_REGM{i}0', ce_val))
                attr_vals.append(AttrVal(f'CLK{h}MUX_REGM{i}0', clk_val))
                attr_vals.append(AttrVal(f'RST{h}MUX_REGM{i}0', reset_val))
                if sync_alu_reset:
                    attr_vals.append(AttrVal('RSTGENLMUX_REGC0', 'SYNC'))
                    for i, h in [(i, h) for i in "AB" for h in "LH"]:
                        attr_vals.append(AttrVal(f'RSTGEN{h}MUX_REGM{i}0', 'SYNC'))

        val = int(cell_parms.get('BREG', '0'), 2)
        if val == 0:
            ii = 4
            attr_vals.append(AttrVal('CIR_BYPH_1', "1"))
            for i, h in [(i, h) for i in "AB" for h in "LH"]:
                attr_vals.append(AttrVal(f'IRBY_IREG1{i}{h}_{ii}', "ENABLE"))
                attr_vals.append(AttrVal(f'IRNS_IREG1{i}{h}_{ii}', "ENABLE"))
                ii += 1
        else:
            attr_vals.append(AttrVal('CEHMUX_CREG', ce_val))
            attr_vals.append(AttrVal('CLKHMUX_CREG', clk_val))
            attr_vals.append(AttrVal('RSTHMUX_CREG', reset_val))
            for i, h in [(i, h) for i in "AB" for h in "LH"]:
                attr_vals.append(AttrVal(f'CE{h}MUX_REGM{i}1', ce_val))
                attr_vals.append(AttrVal(f'CLK{h}MUX_REGM{i}1', clk_val))
                attr_vals.append(AttrVal(f'RST{h}MUX_REGM{i}1', reset_val))
                if sync_alu_reset:
                    attr_vals.append(AttrVal('RSTGENLMUX_REGC0', 'SYNC'))
                    for i, h in [(i, h) for i in "AB" for h in "LH"]:
                        attr_vals.append(AttrVal(f'RSTGEN{h}MUX_REGM{i}0', 'SYNC'))

        val = int(cell_parms.get('ASIGN_REG', '0'), 2)
        if val == 0:
            attr_vals.append(AttrVal('CINBY_3', "ENABLE"))
            attr_vals.append(AttrVal('CINNS_3', "ENABLE"))
        else:
            attr_vals.append(AttrVal('CEMUX_ASIGN11', ce_val))
            attr_vals.append(AttrVal('CLKMUX_ASIGN11', clk_val))
            attr_vals.append(AttrVal('RSTMUX_ASIGN11', reset_val))

            if sync_alu_reset:
                attr_vals.append(AttrVal('RSTGENMUX_ASIGN11', 'SYNC'))

        val = int(cell_parms.get('BSIGN_REG', '0'), 2)
        if val == 0:
            attr_vals.append(AttrVal('CINBY_4', "ENABLE"))
            attr_vals.append(AttrVal('CINNS_4', "ENABLE"))
        else:
            attr_vals.append(AttrVal('CEMUX_BSIGN11', ce_val))
            attr_vals.append(AttrVal('CLKMUX_BSIGN11', clk_val))
            attr_vals.append(AttrVal('RSTMUX_BSIGN11', reset_val))

            if sync_alu_reset:
                attr_vals.append(AttrVal('RSTGENMUX_BSIGN11', 'SYNC'))

        val = int(cell_parms.get('OUT_REG', '0'), 2)
        ii = 0
        if val == 0:
            for i, h in [(i, h) for i in range(2) for h in "LH"]:
                attr_vals.append(AttrVal(f'OREG{i}_NS{h}_{ii}', "ENABLE"))
                attr_vals.append(AttrVal(f'OREG{i}_BYP{h}_{ii}', "ENABLE"))
                attr_vals.append(AttrVal(f'OR2CIB_EN{i}{h}_{ii}', "ENABLE"))
                ii += 1
        else:
            for i, h in [(i, h) for i in range(2) for h in "LH"]:
                attr_vals.append(AttrVal(f'CE{h}MUX_OREG{i}', ce_val))
                attr_vals.append(AttrVal(f'CLK{h}MUX_OREG{i}', clk_val))
                attr_vals.append(AttrVal(f'RST{h}MUX_OREG{i}', reset_val))
                attr_vals.append(AttrVal(f'OR2CIB_EN{i}{h}_{ii}', "ENABLE"))
                ii += 1
                if sync_alu_reset:
                    attr_vals.append(AttrVal(f'RSTGEN{h}MUX_OREG{i}', 'SYNC'))

        val = int(cell_parms.get('ACCLOAD_REG', '0'), 2)
        if val == 0:
            attr_vals.append(AttrVal('CINBY_2', "ENABLE"))
            attr_vals.append(AttrVal('CINNS_2', "ENABLE"))
        else:
            attr_vals.append(AttrVal('CEMUX_ALUSEL1', ce_val))
            attr_vals.append(AttrVal('CLKMUX_ALUSEL1', clk_val))
            attr_vals.append(AttrVal('RSTMUX_ALUSEL1', reset_val))

            if sync_alu_reset:
                attr_vals.append(AttrVal('RSTGENMUX_ALUSEL1', 'SYNC'))

        return attr_vals

    def set_multalu18x18_attrvals(self, bel: BelDesc) -> list[AttrVal]:
        """ MULTALU18x18 """
        attr_vals = []
        cell_parms = bel.cell.parms
        cell_attrs = bel.cell.attrs

        ce_val = int(cell_attrs.get('CE', '0'), 2)
        clk_val = int(cell_attrs.get('CLK', '0'), 2)
        reset_val = int(cell_attrs.get('RESET', '0'), 2)

        # The mode determines which multiplier is used, and this in turn selects
        # the registers and pins used. We rely on nextpnr so that MULTALU18X18_MODE
        # is from the set {0, 1, 2}
        mode = int(cell_parms.get('MULTALU18X18_MODE', "0"), 2)
        mode_01 = int(mode != 2)
        accload = cell_attrs.get('NET_ACCLOAD', '')

        attr_vals.append(AttrVal("RCISEL_3", "1"))
        if mode_01:
            attr_vals.append(AttrVal("RCISEL_1", "1"))

        attr_vals.append(AttrVal('OR2CIB_EN0L_0', "ENABLE"))
        attr_vals.append(AttrVal('OR2CIB_EN0H_1', "ENABLE"))
        attr_vals.append(AttrVal('OR2CIB_EN1L_2', "ENABLE"))
        attr_vals.append(AttrVal('OR2CIB_EN1H_3', "ENABLE"))

        val = int(cell_parms.get('B_ADD_SUB', '0'), 2)
        if val == 1:
            attr_vals.append(AttrVal('OPCD_7', "1"))

        attr_vals.append(AttrVal('ALU_EN', "ENABLE"))
        attr_vals.append(AttrVal('OPCD_5', "1"))
        attr_vals.append(AttrVal('OPCD_9', "1"))
        for i in {5, 6}:
            attr_vals.append(AttrVal(f'CINBY_{i}', "ENABLE"))
            attr_vals.append(AttrVal(f'CINNS_{i}', "ENABLE"))
            attr_vals.append(AttrVal(f'CPRBY_{i}', "ENABLE"))
            attr_vals.append(AttrVal(f'CPRNS_{i}', "ENABLE"))

        if "USE_CASCADE_IN" in cell_attrs:
            attr_vals.append(AttrVal('CSGIN_EXT', "ENABLE"))
            attr_vals.append(AttrVal('CSIGN_PRE', "ENABLE"))
        if "USE_CASCADE_OUT" in cell_attrs:
            attr_vals.append(AttrVal('OR2CASCADE_EN', "ENABLE"))

        if mode_01:
            attr_vals.append(AttrVal('OPCD_2', "1"))
            if accload == "VCC":
                attr_vals.append(AttrVal('OR2CASCADE_EN', "ENABLE"))
            elif accload == "GND":
                attr_vals.append(AttrVal('OPCD_0', "1"))
                attr_vals.append(AttrVal('OPCD_1', "1"))
            else:
                attr_vals.append(AttrVal('OPCDDYN_0', "ENABLE"))
                attr_vals.append(AttrVal('OPCDDYN_1', "ENABLE"))
                attr_vals.append(AttrVal('OR2CASCADE_EN', "ENABLE"))
                attr_vals.append(AttrVal('OPCDDYN_INV_0', "ENABLE"))
                attr_vals.append(AttrVal('OPCDDYN_INV_1', "ENABLE"))
            if mode == 0:
                attr_vals.append(AttrVal('OPCD_4', "1"))

                val = int(cell_parms.get('C_ADD_SUB', '0'), 2)
                if val == 1:
                    attr_vals.append(AttrVal('OPCD_8', "1"))
        else:
            attr_vals.append(AttrVal('OPCD_0', "1"))
            attr_vals.append(AttrVal('OPCD_3', "1"))

        # dsp registers
        sync_mult_reset = cell_parms.get('MULT_RESET_MODE', 'ASYNC') == 'SYNC'

        val = int(cell_parms.get('AREG', '0'), 2)
        if val == 0:
            for i, h in self._01LH:
                attr_vals.append(AttrVal(f'IRBY_IREG{mode_01}A{h}_{4 * mode_01 + i}', "ENABLE"))
                attr_vals.append(AttrVal(f'IRNS_IREG{mode_01}A{h}_{4 * mode_01 + i}', "ENABLE"))
        else:
            for h in "LH":
                attr_vals.append(AttrVal(f'CE{h}MUX_REGMA{mode_01}', ce_val))
                attr_vals.append(AttrVal(f'CLK{h}MUX_REGMA{mode_01}', clk_val))
                attr_vals.append(AttrVal(f'RST{h}MUX_REGMA{mode_01}', reset_val))

            if sync_mult_reset:
                for h in "LH":
                    attr_vals.append(AttrVal(f'RSTGEN{h}MUX_REGMA{mode_01}', 'SYNC'))

        val = int(cell_parms.get('BREG', '0'), 2)
        if val == 0:
            for i, h in self._01LH:
                attr_vals.append(AttrVal(f'IRBY_IREG{mode_01}B{h}_{4 * mode_01 + 2 + i}', "ENABLE"))
                attr_vals.append(AttrVal(f'IRNS_IREG{mode_01}B{h}_{4 * mode_01 + 2 + i}', "ENABLE"))
        else:
            for h in "LH":
                attr_vals.append(AttrVal(f'CE{h}MUX_REGMB{mode_01}', ce_val))
                attr_vals.append(AttrVal(f'CLK{h}MUX_REGMB{mode_01}', clk_val))
                attr_vals.append(AttrVal(f'RST{h}MUX_REGMB{mode_01}', reset_val))

            if sync_mult_reset:
                for h in "LH":
                    attr_vals.append(AttrVal(f'RSTGEN{h}MUX_REGMB{mode_01}', 'SYNC'))

        val = int(cell_parms.get('CREG', '0'), 2)
        if val == 0:
            for i, h in self._01LH:
                attr_vals.append(AttrVal(f'CIR_BYP{h}_{i}', "1"))
        else:
            for h in "LH":
                attr_vals.append(AttrVal(f'CE{h}MUX_CREG', ce_val))
                attr_vals.append(AttrVal(f'CLK{h}MUX_CREG', clk_val))
                attr_vals.append(AttrVal(f'RST{h}MUX_CREG', reset_val))

            if sync_mult_reset:
                for h in "LH":
                    attr_vals.append(AttrVal(f'RSTGEN{h}MUX_REGC0', 'SYNC'))

        val = int(cell_parms.get('DREG', '0'), 2)
        if val == 0:
            attr_vals.append(AttrVal('CIR_BYPH_1', "1"))
            ii = 4
            for i, h in self._ABLH:
                attr_vals.append(AttrVal(f'IRBY_IREG1{i}{h}_{ii}', "ENABLE"))
                attr_vals.append(AttrVal(f'IRNS_IREG1{i}{h}_{ii}', "ENABLE"))
                ii += 1
        else:
            attr_vals.append(AttrVal('CEHMUX_CREG', ce_val))
            attr_vals.append(AttrVal('CLKHMUX_CREG', clk_val))
            attr_vals.append(AttrVal('RSTHMUX_CREG', reset_val))
            for i, h in self._ABLH:
                attr_vals.append(AttrVal(f'CE{h}MUX_REGM{i}1', ce_val))
                attr_vals.append(AttrVal(f'CLK{h}MUX_REGM{i}1', clk_val))
                attr_vals.append(AttrVal(f'RST{h}MUX_REGM{i}1', reset_val))

            if sync_mult_reset:
                attr_vals.append(AttrVal('RSTGENHMUX_REGC0', 'SYNC'))
                for i, h in self._ABLH:
                    attr_vals.append(AttrVal(f'RSTGEN{h}MUX_REGM{i}1', 'SYNC'))

        val = int(cell_parms.get('ASIGN_REG', '0'), 2)
        if val == 0:
            attr_vals.append(AttrVal(f'CINNS_{3 * mode_01}', "ENABLE"))
            attr_vals.append(AttrVal(f'CINBY_{3 * mode_01}', "ENABLE"))
        else:
            attr_vals.append(AttrVal(f'CEMUX_ASIGN{mode_01}1', ce_val))
            attr_vals.append(AttrVal(f'CLKMUX_ASIGN{mode_01}1', clk_val))
            attr_vals.append(AttrVal(f'RSTMUX_ASIGN{mode_01}1', reset_val))

            if sync_mult_reset:
                attr_vals.append(AttrVal(f'RSTGENMUX_ASIGN{mode_01}1', 'SYNC'))

        val = int(cell_parms.get('BSIGN_REG', '0'), 2)
        if val == 0:
            attr_vals.append(AttrVal(f'CINNS_{1 + 3 * mode_01}', "ENABLE"))
            attr_vals.append(AttrVal(f'CINBY_{1 + 3 * mode_01}', "ENABLE"))
        else:
            attr_vals.append(AttrVal(f'CEMUX_BSIGN{mode_01}1', ce_val))
            attr_vals.append(AttrVal(f'CLKMUX_BSIGN{mode_01}1', clk_val))
            attr_vals.append(AttrVal(f'RSTMUX_BSIGN{mode_01}1', reset_val))

            if sync_mult_reset:
                attr_vals.append(AttrVal(f'RSTGENMUX_BSIGN{mode_01}1', 'SYNC'))

        if not mode_01:
            val = int(cell_parms.get('DSIGN_REG', '0'), 2)
            if val == 0:
                attr_vals.append(AttrVal('CINNS_4', "ENABLE"))
                attr_vals.append(AttrVal('CINBY_4', "ENABLE"))
            else:
                attr_vals.append(AttrVal('CEMUX_BSIGN11', ce_val))
                attr_vals.append(AttrVal('CLKMUX_BSIGN11', clk_val))
                attr_vals.append(AttrVal('RSTMUX_BSIGN11', reset_val))

                if sync_mult_reset:
                    attr_vals.append(AttrVal('RSTGENMUX_BSIGN11', 'SYNC'))

            val = int(cell_parms.get('PIPE_REG', '0'), 2)
            if val == 0:
                attr_vals.append(AttrVal('CPRNS_4', "ENABLE"))
                attr_vals.append(AttrVal('CPRBY_4', "ENABLE"))
            else:
                attr_vals.append(AttrVal('CLK_BSIGN12', clk_val))
                attr_vals.append(AttrVal('RST_BSIGN12', reset_val))

                if sync_mult_reset:
                    attr_vals.append(AttrVal(f'RSTGENMUX_BSIGN12', 'SYNC'))

        val = int(cell_parms.get('PIPE_REG', '0'), 2)
        if val == 0:
            attr_vals.append(AttrVal(f'CPRNS_{3 * mode_01}', "ENABLE"))
            attr_vals.append(AttrVal(f'CPRBY_{3 * mode_01}', "ENABLE"))
            attr_vals.append(AttrVal(f'CPRNS_{1 + 3 * mode_01}', "ENABLE"))
            attr_vals.append(AttrVal(f'CPRBY_{1 + 3 * mode_01}', "ENABLE"))
            for i, h in self._01LH:
                attr_vals.append(AttrVal(f'PPREG{mode_01}_NS{h}_{2 * mode_01 + i}', "ENABLE"))
                attr_vals.append(AttrVal(f'PPREG{mode_01}_BYP{h}_{2 * mode_01 + i}', "ENABLE"))
        else:
            for i in "AB":
                attr_vals.append(AttrVal(f'CEMUX_{i}SIGN{1 - mode_01}2', ce_val))
                attr_vals.append(AttrVal(f'CLKMUX_{i}SIGN{1 - mode_01}2', clk_val))
                attr_vals.append(AttrVal(f'RSTMUX_{i}SIGN{1 - mode_01}2', reset_val))
            for i in "LH":
                attr_vals.append(AttrVal(f'CE{i}MUX_REGP{1 - mode_01}', ce_val))
                attr_vals.append(AttrVal(f'CLK{i}MUX_REGP{1 - mode_01}', clk_val))
                attr_vals.append(AttrVal(f'RST{i}MUX_REGP{1 - mode_01}', reset_val))

            if sync_mult_reset:
                attr_vals.append(AttrVal(f'RSTGENMUX_ASIGN{1 - mode_01}2', 'SYNC'))
                attr_vals.append(AttrVal(f'RSTGENMUX_BSIGN{1 - mode_01}2', 'SYNC'))
                attr_vals.append(AttrVal(f'RSTGENLMUX_REGP{1 - mode_01}', 'SYNC'))
                attr_vals.append(AttrVal(f'RSTGENHMUX_REGP{1 - mode_01}', 'SYNC'))

        val = int(cell_parms.get('OUT_REG', '0'), 2)
        if val == 0:
            for i in range(2):
                attr_vals.append(AttrVal(f'OREG{i}_NSL_{2 * i}', "ENABLE"))
                attr_vals.append(AttrVal(f'OREG{i}_BYPL_{2 * i}', "ENABLE"))
                attr_vals.append(AttrVal(f'OREG{i}_NSH_{2 * i + 1}', "ENABLE"))
                attr_vals.append(AttrVal(f'OREG{i}_BYPH_{2 * i + 1}', "ENABLE"))
        else:
            for i in range(2):
                for h in "LH":
                    attr_vals.append(AttrVal(f'CE{h}MUX_OREG{i}', ce_val))
                    attr_vals.append(AttrVal(f'CLK{h}MUX_OREG{i}', clk_val))
                    attr_vals.append(AttrVal(f'RST{h}MUX_OREG{i}', reset_val))

            if sync_mult_reset:
                for h in "LH":
                    attr_vals.append(AttrVal(f'RSTGEN{h}MUX_OREG0', 'SYNC'))
                    attr_vals.append(AttrVal(f'RSTGEN{h}MUX_OREG1', 'SYNC'))

        val = int(cell_parms.get('ACCLOAD_REG0', '0'), 2)
        if val == 0:
            attr_vals.append(AttrVal('CINNS_2', "ENABLE"))
            attr_vals.append(AttrVal('CINBY_2', "ENABLE"))
        else:
            attr_vals.append(AttrVal('CEMUX_ALUSEL1', ce_val))
            attr_vals.append(AttrVal('CLKMUX_ALUSEL1', clk_val))
            attr_vals.append(AttrVal('RSTMUX_ALUSEL1', reset_val))

            if sync_mult_reset:
                attr_vals.append(AttrVal('RSTGENMUX_ALUSEL1', 'SYNC'))

        val = int(cell_parms.get('ACCLOAD_REG1', '0'), 2)
        if val == 0:
            attr_vals.append(AttrVal('CPRNS_2', "ENABLE"))
            attr_vals.append(AttrVal('CPRBY_2', "ENABLE"))
        else:
            attr_vals.append(AttrVal('CEMUX_ALUSEL2', ce_val))
            attr_vals.append(AttrVal('CLKMUX_ALUSEL2', clk_val))
            attr_vals.append(AttrVal('RSTMUX_ALUSEL2', reset_val))

            if sync_mult_reset:
                attr_vals.append(AttrVal('RSTGENMUX_ALUSEL2', 'SYNC'))

        return attr_vals

    def set_multalu36x18_attrvals(self, bel: BelDesc, dsp_indices: DspIndices) -> list[AttrVal]:
        """ MULTALU36x18 """
        attr_vals = []
        cell_parms = bel.cell.parms
        cell_attrs = bel.cell.attrs
        mac = dsp_indices.mac

        ce_val = int(cell_attrs.get('CE', '0'), 2)
        clk_val = int(cell_attrs.get('CLK', '0'), 2)
        reset_val = int(cell_attrs.get('RESET', '0'), 2)

        mode = int(cell_parms.get('MULTALU36X18_MODE', "0"), 2)
        accload = cell_attrs.get('NET_ACCLOAD', '')

        attr_vals.append(AttrVal("RCISEL_1", "1"))
        attr_vals.append(AttrVal("RCISEL_3", "1"))

        attr_vals.append(AttrVal('OR2CIB_EN0L_0', "ENABLE"))
        attr_vals.append(AttrVal('OR2CIB_EN0H_1', "ENABLE"))
        attr_vals.append(AttrVal('OR2CIB_EN1L_2', "ENABLE"))
        attr_vals.append(AttrVal('OR2CIB_EN1H_3', "ENABLE"))

        attr_vals.append(AttrVal('ALU_EN', "ENABLE"))
        for i in {5, 6}:
            attr_vals.append(AttrVal(f'CINBY_{i}', "ENABLE"))
            attr_vals.append(AttrVal(f'CINNS_{i}', "ENABLE"))
            attr_vals.append(AttrVal(f'CPRBY_{i}', "ENABLE"))
            attr_vals.append(AttrVal(f'CPRNS_{i}', "ENABLE"))

        if "USE_CASCADE_IN" in cell_attrs:
            attr_vals.append(AttrVal('CSGIN_EXT', "ENABLE"))
            attr_vals.append(AttrVal('CSIGN_PRE', "ENABLE"))
        if "USE_CASCADE_OUT" in cell_attrs:
            attr_vals.append(AttrVal('OR2CASCADE_EN', "ENABLE"))

        attr_vals.append(AttrVal('OPCD_0', "1"))
        attr_vals.append(AttrVal('OPCD_9', "1"))
        if mode == 0:
            attr_vals.append(AttrVal('OPCD_4', "1"))
            attr_vals.append(AttrVal('OPCD_5', "1"))
            val = int(cell_parms.get('C_ADD_SUB', '0'), 2)
            if val == 1:
                attr_vals.append(AttrVal('OPCD_8', "1"))
        elif mode == 2:
            attr_vals.append(AttrVal('OPCD_5', "1"))
        else:
            if accload == "VCC":
                attr_vals.append(AttrVal('OPCD_4', "1"))
                attr_vals.append(AttrVal('OPCD_6', "1"))
                attr_vals.append(AttrVal('OR2CASCADE_EN', "ENABLE"))
            elif accload != "GND":
                attr_vals.append(AttrVal('OPCDDYN_4', "ENABLE"))
                attr_vals.append(AttrVal('OPCDDYN_6', "ENABLE"))
                attr_vals.append(AttrVal('OR2CASCADE_EN', "ENABLE"))

        # dsp registers
        sync_mult_reset = cell_parms.get('MULT_RESET_MODE', 'ASYNC') == 'SYNC'

        val = int(cell_parms.get('AREG', '0'), 2)
        if val == 0:
            for k in range(2):
                for i, h in self._01LH:
                    attr_vals.append(AttrVal(f'IRBY_IREG{k}A{h}_{4 * k + i}', "ENABLE"))
                    attr_vals.append(AttrVal(f'IRNS_IREG{k}A{h}_{4 * k + i}', "ENABLE"))
        else:
            for k in range(2):
                for h in "LH":
                    attr_vals.append(AttrVal(f'CE{h}MUX_REGMA{k}', ce_val))
                    attr_vals.append(AttrVal(f'CLK{h}MUX_REGMA{k}', clk_val))
                    attr_vals.append(AttrVal(f'RST{h}MUX_REGMA{k}', reset_val))

            if sync_mult_reset:
                for k in range(2):
                    for h in "LH":
                        attr_vals.append(AttrVal(f'RSTGEN{h}MUX_REGMA{k}', 'SYNC'))

        val = int(cell_parms.get('BREG', '0'), 2)
        if val == 0:
            for k in range(2):
                for i, h in self._01LH:
                    attr_vals.append(AttrVal(f'IRBY_IREG{k}B{h}_{4 * k + 2 + i}', "ENABLE"))
                    attr_vals.append(AttrVal(f'IRNS_IREG{k}B{h}_{4 * k + 2 + i}', "ENABLE"))
        else:
            for k in range(2):
                for h in "LH":
                    attr_vals.append(AttrVal(f'CE{h}MUX_REGMB{k}', ce_val))
                    attr_vals.append(AttrVal(f'CLK{h}MUX_REGMB{k}', clk_val))
                    attr_vals.append(AttrVal(f'RST{h}MUX_REGMB{k}', reset_val))

            if sync_mult_reset:
                for k in range(2):
                    for h in "LH":
                        attr_vals.append(AttrVal(f'RSTGEN{h}MUX_REGMB{k}', 'SYNC'))

        val = int(cell_parms.get('CREG', '0'), 2)
        if val == 0:
            for i, h in self._01LH:
                attr_vals.append(AttrVal(f'CIR_BYP{h}_{i}', "1"))
        else:
            for h in "LH":
                attr_vals.append(AttrVal(f'CE{h}MUX_CREG', ce_val))
                attr_vals.append(AttrVal(f'CLK{h}MUX_CREG', clk_val))
                attr_vals.append(AttrVal(f'RST{h}MUX_CREG', reset_val))

            if sync_mult_reset:
                for h in "LH":
                    attr_vals.append(AttrVal(f'RSTGEN{h}MUX_REGC0', 'SYNC'))

        val = int(cell_parms.get('ASIGN_REG', '0'), 2)
        if val == 0:
            for k in range(2):
                attr_vals.append(AttrVal(f'CINNS_{3 * k}', "ENABLE"))
                attr_vals.append(AttrVal(f'CINBY_{3 * k}', "ENABLE"))
        else:
            for k in range(2):
                attr_vals.append(AttrVal(f'CEMUX_ASIGN{k}1', ce_val))
                attr_vals.append(AttrVal(f'CLKMUX_ASIGN{k}1', clk_val))
                attr_vals.append(AttrVal(f'RSTMUX_ASIGN{k}1', reset_val))

            if sync_mult_reset:
                for k in range(2):
                    attr_vals.append(AttrVal(f'RSTGENMUX_ASIGN{k}1', 'SYNC'))

        val = int(cell_parms.get('BSIGN_REG', '0'), 2)
        if val == 0:
            for k in range(2):
                attr_vals.append(AttrVal(f'CINNS_{1 + 3 * k}', "ENABLE"))
                attr_vals.append(AttrVal(f'CINBY_{1 + 3 * k}', "ENABLE"))
        else:
            for k in range(2):
                attr_vals.append(AttrVal(f'CEMUX_BSIGN{k}1', ce_val))
                attr_vals.append(AttrVal(f'CLKMUX_BSIGN{k}1', clk_val))
                attr_vals.append(AttrVal(f'RSTMUX_BSIGN{k}1', reset_val))

            if sync_mult_reset:
                for k in range(2):
                    attr_vals.append(AttrVal(f'RSTGENMUX_BSIGN{k}1', 'SYNC'))


        val = int(cell_parms.get('PIPE_REG', '0'), 2)
        if val == 0:
            for k in range(2):
                attr_vals.append(AttrVal(f'CPRNS_{3 * k}', "ENABLE"))
                attr_vals.append(AttrVal(f'CPRBY_{3 * k}', "ENABLE"))
                attr_vals.append(AttrVal(f'CPRNS_{1 + 3 * k}', "ENABLE"))
                attr_vals.append(AttrVal(f'CPRBY_{1 + 3 * k}', "ENABLE"))
                for i, h in self._01LH:
                    attr_vals.append(AttrVal(f'PPREG{k}_NS{h}_{2 * k + i}', "ENABLE"))
                    attr_vals.append(AttrVal(f'PPREG{k}_BYP{h}_{2 * k + i}', "ENABLE"))
        else:
            for k in range(2):
                for i in "AB":
                    attr_vals.append(AttrVal(f'CEMUX_{i}SIGN{k}2', ce_val))
                    attr_vals.append(AttrVal(f'CLKMUX_{i}SIGN{k}2', clk_val))
                    attr_vals.append(AttrVal(f'RSTMUX_{i}SIGN{k}2', reset_val))
                for i in "LH":
                    attr_vals.append(AttrVal(f'CE{i}MUX_REGP{k}', ce_val))
                    attr_vals.append(AttrVal(f'CLK{i}MUX_REGP{k}', clk_val))
                    attr_vals.append(AttrVal(f'RST{i}MUX_REGP{k}', reset_val))

            if sync_mult_reset:
                for k in range(2):
                    attr_vals.append(AttrVal(f'RSTGENMUX_ASIGN{k}2', 'SYNC'))
                    attr_vals.append(AttrVal(f'RSTGENMUX_BSIGN{k}2', 'SYNC'))
                    attr_vals.append(AttrVal(f'RSTGENLMUX_REGP{k}', 'SYNC'))
                    attr_vals.append(AttrVal(f'RSTGENHMUX_REGP{k}', 'SYNC'))

        val = int(cell_parms.get('OUT_REG', '0'), 2)
        # do out reg in unoptimal way because of MULT36X36
        if mac == 0 and bel.cell.typ == 'MULT36X36':
            attr_vals.append(AttrVal('OREG0_NSH_1', "ENABLE"))
            attr_vals.append(AttrVal('OREG0_BYPH_1', "ENABLE"))
            attr_vals.append(AttrVal('OREG1_NSL_2', "ENABLE"))
            attr_vals.append(AttrVal('OREG1_BYPL_2', "ENABLE"))
            attr_vals.append(AttrVal('OREG1_NSH_3', "ENABLE"))
            attr_vals.append(AttrVal('OREG1_BYPH_3', "ENABLE"))
            if val == 0:
                attr_vals.append(AttrVal('OREG0_NSL_0', "ENABLE"))
                attr_vals.append(AttrVal('OREG0_BYPL_0', "ENABLE"))
            else:
                attr_vals.append(AttrVal('CELMUX_OREG0', ce_val))
                attr_vals.append(AttrVal('CLKLMUX_OREG0', clk_val))
                attr_vals.append(AttrVal('RSTLMUX_OREG0', reset_val))

                if sync_mult_reset:
                    attr_vals.append(AttrVal('RSTGENLMUX_OREG0', 'SYNC'))
        else:
            if val == 0:
                for k in range(2):
                    attr_vals.append(AttrVal(f'OREG{k}_NSL_{2 * k}', "ENABLE"))
                    attr_vals.append(AttrVal(f'OREG{k}_BYPL_{2 * k}', "ENABLE"))
                    attr_vals.append(AttrVal(f'OREG{k}_NSH_{2 * k + 1}', "ENABLE"))
                    attr_vals.append(AttrVal(f'OREG{k}_BYPH_{2 * k + 1}', "ENABLE"))
            else:
                for k in range(2):
                    for h in "LH":
                        attr_vals.append(AttrVal(f'CE{h}MUX_OREG{k}', ce_val))
                        attr_vals.append(AttrVal(f'CLK{h}MUX_OREG{k}', clk_val))
                        attr_vals.append(AttrVal(f'RST{h}MUX_OREG{k}', reset_val))

                if sync_mult_reset:
                    for h in "LH":
                        attr_vals.append(AttrVal(f'RSTGEN{h}MUX_OREG0', 'SYNC'))
                        attr_vals.append(AttrVal(f'RSTGEN{h}MUX_OREG1', 'SYNC'))

        val = int(cell_parms.get('ACCLOAD_REG0', '0'), 2)
        if val == 0:
            attr_vals.append(AttrVal('CINNS_2', "ENABLE"))
            attr_vals.append(AttrVal('CINBY_2', "ENABLE"))
        else:
            attr_vals.append(AttrVal('CEMUX_ALUSEL1', ce_val))
            attr_vals.append(AttrVal('CLKMUX_ALUSEL1', clk_val))
            attr_vals.append(AttrVal('RSTMUX_ALUSEL1', reset_val))

            if sync_mult_reset:
                attr_vals.append(AttrVal('RSTGENMUX_ALUSEL1', 'SYNC'))

        val = int(cell_parms.get('ACCLOAD_REG1', '0'), 2)
        if val == 0:
            attr_vals.append(AttrVal('CPRNS_2', "ENABLE"))
            attr_vals.append(AttrVal('CPRBY_2', "ENABLE"))
        else:
            attr_vals.append(AttrVal('CEMUX_ALUSEL2', ce_val))
            attr_vals.append(AttrVal('CLKMUX_ALUSEL2', clk_val))
            attr_vals.append(AttrVal('RSTMUX_ALUSEL2', reset_val))

            if sync_mult_reset:
                attr_vals.append(AttrVal('RSTGENMUX_ALUSEL2', 'SYNC'))

        return attr_vals

    def set_multaddalu18x18_attrvals(self, bel: BelDesc) -> list[AttrVal]:
        """ MULTADDALU18x18 """
        attr_vals = []
        cell_parms = bel.cell.parms
        cell_attrs = bel.cell.attrs

        ce_val = int(cell_attrs.get('CE', '0'), 2)
        clk_val = int(cell_attrs.get('CLK', '0'), 2)
        reset_val = int(cell_attrs.get('RESET', '0'), 2)

        mode = int(cell_parms.get('MULTADDALU18X18_MODE', "0"), 2)
        accload = cell_attrs.get('NET_ACCLOAD', '')

        if mode == 0:
            attr_vals.append(AttrVal("RCISEL_1", "1"))
            attr_vals.append(AttrVal("RCISEL_3", "1"))

        attr_vals.append(AttrVal('OR2CIB_EN0L_0', "ENABLE"))
        attr_vals.append(AttrVal('OR2CIB_EN0H_1', "ENABLE"))
        attr_vals.append(AttrVal('OR2CIB_EN1L_2', "ENABLE"))
        attr_vals.append(AttrVal('OR2CIB_EN1H_3', "ENABLE"))

        val = int(cell_parms.get('B_ADD_SUB', '0'), 2)
        if val == 1:
            attr_vals.append(AttrVal('OPCD_7', "1"))

        if "USE_CASCADE_IN" in cell_attrs:
            attr_vals.append(AttrVal('CSGIN_EXT', "ENABLE"))
            attr_vals.append(AttrVal('CSIGN_PRE', "ENABLE"))
        if "USE_CASCADE_OUT" in cell_attrs:
            attr_vals.append(AttrVal('OR2CASCADE_EN', "ENABLE"))

        attr_vals.append(AttrVal('ALU_EN', "ENABLE"))
        attr_vals.append(AttrVal('OPCD_0', "1"))
        attr_vals.append(AttrVal('OPCD_2', "1"))
        attr_vals.append(AttrVal('OPCD_9', "1"))
        for i in {5, 6}:
            attr_vals.append(AttrVal(f'CINBY_{i}', "ENABLE"))
            attr_vals.append(AttrVal(f'CINNS_{i}', "ENABLE"))
            attr_vals.append(AttrVal(f'CPRBY_{i}', "ENABLE"))
            attr_vals.append(AttrVal(f'CPRNS_{i}', "ENABLE"))

        if mode == 0:
            attr_vals.append(AttrVal('OPCD_4', "1"))
            attr_vals.append(AttrVal('OPCD_5', "1"))
            val = int(cell_parms.get('C_ADD_SUB', '0'), 2)
            if val == 1:
                attr_vals.append(AttrVal('OPCD_8', "1"))
        elif mode == 2:
            attr_vals.append(AttrVal('OPCD_5', "1"))
        else:
            if accload == "VCC":
                attr_vals.append(AttrVal('OPCD_4', "1"))
                attr_vals.append(AttrVal('OPCD_6', "1"))
                attr_vals.append(AttrVal('OR2CASCADE_EN', "ENABLE"))
            elif accload != "GND":
                attr_vals.append(AttrVal('OPCDDYN_4', "ENABLE"))
                attr_vals.append(AttrVal('OPCDDYN_6', "ENABLE"))
                attr_vals.append(AttrVal('OR2CASCADE_EN', "ENABLE"))

        val = cell_attrs.get('NET_ASEL0', '')
        if val != 'GND':
            if val == 'VCC':
                attr_vals.append(AttrVal(f'AIRMUX1_0', "ENABLE"))
            elif val != "":
                attr_vals.append(AttrVal(f'AIRMUX1_SEL_0', "ENABLE"))

        val = cell_attrs.get('NET_ASEL1', '')
        if val != 'GND':
            if val == 'VCC':
                attr_vals.append(AttrVal(f'AIRMUX1_1', "ENABLE"))
            elif val != "":
                attr_vals.append(AttrVal(f'AIRMUX1_SEL_1', "ENABLE"))

        val = cell_attrs.get('NET_BSEL0', '')
        if val != 'GND':
            if val == 'VCC':
                attr_vals.append(AttrVal('BIRMUX1_0', "ENABLE"))
            elif val != "":
                attr_vals.append(AttrVal('BIRMUX0_0', "ENABLE"))
                attr_vals.append(AttrVal('BIRMUX0_1', "ENABLE"))
                attr_vals.append(AttrVal('BIRMUX1_0', "ENABLE"))
                attr_vals.append(AttrVal('BIRMUX1_1', "ENABLE"))

        val = cell_attrs.get('NET_BSEL1', '')
        if val != 'GND':
            if val == 'VCC':
                attr_vals.append(AttrVal('BIRMUX1_2', "ENABLE"))
            elif val != "":
                attr_vals.append(AttrVal('BIRMUX1_2', "ENABLE"))
                attr_vals.append(AttrVal('BIRMUX1_3', "ENABLE"))

        attr_vals.append(AttrVal('MATCH_SHFEN', "ENABLE"))
        attr_vals.append(AttrVal('IRASHFEN_0', "1"))
        attr_vals.append(AttrVal('IRASHFEN_1', "1"))
        attr_vals.append(AttrVal('IRBSHFEN_0', "1"))
        attr_vals.append(AttrVal('IRBSHFEN_1', "1"))

        sync_mult_reset = cell_parms.get('MULT_RESET_MODE', 'ASYNC') == 'SYNC'

        for k in range(2):
            val = int(cell_parms.get(f'A{k}REG', '0'), 2)
            if val == 0:
                for i, h in self._01LH:
                    attr_vals.append(AttrVal(f'IRBY_IREG{k}A{h}_{4 * k + i}', "ENABLE"))
                    attr_vals.append(AttrVal(f'IRNS_IREG{k}A{h}_{4 * k + i}', "ENABLE"))
            else:
                for h in "LH":
                    attr_vals.append(AttrVal(f'CE{h}MUX_REGMA{k}', ce_val))
                    attr_vals.append(AttrVal(f'CLK{h}MUX_REGMA{k}', clk_val))
                    attr_vals.append(AttrVal(f'RST{h}MUX_REGMA{k}', reset_val))

                if sync_mult_reset:
                    for h in "LH":
                        attr_vals.append(AttrVal(f'RSTGEN{h}MUX_REGMA{k}', 'SYNC'))

            val = int(cell_parms.get(f'B{k}REG', '0'), 2)
            if val == 0:
                for i, h in self._01LH:
                    attr_vals.append(AttrVal(f'IRBY_IREG{k}B{h}_{4 * k + 2 + i}', "ENABLE"))
                    attr_vals.append(AttrVal(f'IRNS_IREG{k}B{h}_{4 * k + 2 + i}', "ENABLE"))
            else:
                for h in "LH":
                    attr_vals.append(AttrVal(f'CE{h}MUX_REGMB{k}', ce_val))
                    attr_vals.append(AttrVal(f'CLK{h}MUX_REGMB{k}', clk_val))
                    attr_vals.append(AttrVal(f'RST{h}MUX_REGMB{k}', reset_val))

                if sync_mult_reset:
                    for h in "LH":
                        attr_vals.append(AttrVal(f'RSTGEN{h}MUX_REGMB{k}', 'SYNC'))

            val = int(cell_parms.get(f'ASIGN{k}_REG', '0'), 2)
            if val == 0:
                attr_vals.append(AttrVal(f'CINNS_{3 * k}', "ENABLE"))
                attr_vals.append(AttrVal(f'CINBY_{3 * k}', "ENABLE"))
            else:
                attr_vals.append(AttrVal(f'CEMUX_ASIGN{k}1', ce_val))
                attr_vals.append(AttrVal(f'CLKMUX_ASIGN{k}1', clk_val))
                attr_vals.append(AttrVal(f'RSTMUX_ASIGN{k}1', reset_val))

                if sync_mult_reset:
                    attr_vals.append(AttrVal(f'RSTGENMUX_ASIGN{k}1', 'SYNC'))

            val = int(cell_parms.get(f'BSIGN{k}_REG', '0'), 2)
            if val == 0:
                attr_vals.append(AttrVal(f'CINNS_{1 + 3 * k}', "ENABLE"))
                attr_vals.append(AttrVal(f'CINBY_{1 + 3 * k}', "ENABLE"))
            else:
                attr_vals.append(AttrVal(f'CEMUX_BSIGN{k}1', ce_val))
                attr_vals.append(AttrVal(f'CLKMUX_BSIGN{k}1', clk_val))
                attr_vals.append(AttrVal(f'RSTMUX_BSIGN{k}1', reset_val))

                if sync_mult_reset:
                    attr_vals.append(AttrVal(f'RSTGENMUX_BSIGN{k}1', 'SYNC'))

            val = int(cell_parms.get(f'PIPE{k}_REG', '0'), 2)
            if val == 0:
                attr_vals.append(AttrVal(f'CPRNS_{3 * k}', "ENABLE"))
                attr_vals.append(AttrVal(f'CPRBY_{3 * k}', "ENABLE"))
                attr_vals.append(AttrVal(f'CPRNS_{1 + 3 * k}', "ENABLE"))
                attr_vals.append(AttrVal(f'CPRBY_{1 + 3 * k}', "ENABLE"))
                for i, h in self._01LH:
                    attr_vals.append(AttrVal(f'PPREG{k}_NS{h}_{2 * k + i}', "ENABLE"))
                    attr_vals.append(AttrVal(f'PPREG{k}_BYP{h}_{2 * k + i}', "ENABLE"))
            else:
                for i in "AB":
                    attr_vals.append(AttrVal(f'CEMUX_{i}SIGN{k}2', ce_val))
                    attr_vals.append(AttrVal(f'CLKMUX_{i}SIGN{k}2', clk_val))
                    attr_vals.append(AttrVal(f'RSTMUX_{i}SIGN{k}2', reset_val))
                for i in "LH":
                    attr_vals.append(AttrVal(f'CE{i}MUX_REGP{k}', ce_val))
                    attr_vals.append(AttrVal(f'CLK{i}MUX_REGP{k}', clk_val))
                    attr_vals.append(AttrVal(f'RST{i}MUX_REGP{k}', reset_val))

                if sync_mult_reset:
                    attr_vals.append(AttrVal(f'RSTGENMUX_ASIGN{k}2', 'SYNC'))
                    attr_vals.append(AttrVal(f'RSTGENMUX_BSIGN{k}2', 'SYNC'))
                    attr_vals.append(AttrVal(f'RSTGENLMUX_REGP{k}', 'SYNC'))
                    attr_vals.append(AttrVal(f'RSTGENHMUX_REGP{k}', 'SYNC'))

        val = int(cell_parms.get('ACCLOAD_REG0', '0'), 2)
        if val == 0:
            attr_vals.append(AttrVal('CINNS_2', "ENABLE"))
            attr_vals.append(AttrVal('CINBY_2', "ENABLE"))
        else:
            attr_vals.append(AttrVal('CEMUX_ALUSEL1', ce_val))
            attr_vals.append(AttrVal('CLKMUX_ALUSEL1', clk_val))
            attr_vals.append(AttrVal('RSTMUX_ALUSEL1', reset_val))

            if sync_mult_reset:
                attr_vals.append(AttrVal('RSTGENMUX_ALUSEL1', 'SYNC'))

        val = int(cell_parms.get('ACCLOAD_REG1', '0'), 2)
        if val == 0:
            attr_vals.append(AttrVal('CPRNS_2', "ENABLE"))
            attr_vals.append(AttrVal('CPRBY_2', "ENABLE"))
        else:
            attr_vals.append(AttrVal('CEMUX_ALUSEL2', ce_val))
            attr_vals.append(AttrVal('CLKMUX_ALUSEL2', clk_val))
            attr_vals.append(AttrVal('RSTMUX_ALUSEL2', reset_val))

            if sync_mult_reset:
                attr_vals.append(AttrVal('RSTGENMUX_ALUSEL2', 'SYNC'))

        if mode == 0:
            val = int(cell_parms.get('CREG', '0'), 2)
            if val == 0:
                for i, h in self._01LH:
                    attr_vals.append(AttrVal(f'CIR_BYP{h}_{i}', "1"))
            else:
                for h in "LH":
                    attr_vals.append(AttrVal(f'CE{h}MUX_CREG', ce_val))
                    attr_vals.append(AttrVal(f'CLK{h}MUX_CREG', clk_val))
                    attr_vals.append(AttrVal(f'RST{h}MUX_CREG', reset_val))

                if sync_mult_reset:
                    for h in "LH":
                        attr_vals.append(AttrVal(f'RSTGEN{h}MUX_REGC0', 'SYNC'))

        val = int(cell_parms.get(f'SOA_REG', '0'), 2)
        if val == 0:
            attr_vals.append(AttrVal('IRBY_IRMATCHH_9', "ENABLE"))
            attr_vals.append(AttrVal('IRNS_IRMATCHH_9', "ENABLE"))
            attr_vals.append(AttrVal('IRBY_IRMATCHL_8', "ENABLE"))
            attr_vals.append(AttrVal('IRNS_IRMATCHL_8', "ENABLE"))
        else:
            attr_vals.append(AttrVal('CEHMUX_REGSD', ce_val))
            attr_vals.append(AttrVal('CLKHMUX_REGSD', clk_val))
            attr_vals.append(AttrVal('RSTHMUX_REGSD', reset_val))
            attr_vals.append(AttrVal('CELMUX_REGSD', ce_val))
            attr_vals.append(AttrVal('CLKLMUX_REGSD', clk_val))
            attr_vals.append(AttrVal('RSTLMUX_REGSD', reset_val))

            if sync_mult_reset:
                attr_vals.append(AttrVal('RSTGENHMUX_REGSD', 'SYNC'))
                attr_vals.append(AttrVal('RSTGENLMUX_REGSD', 'SYNC'))

        val = int(cell_parms.get('OUT_REG', '0'), 2)
        if val == 0:
            for k in range(2):
                attr_vals.append(AttrVal(f'OREG{k}_NSL_{2 * k}', "ENABLE"))
                attr_vals.append(AttrVal(f'OREG{k}_BYPL_{2 * k}', "ENABLE"))
                attr_vals.append(AttrVal(f'OREG{k}_NSH_{2 * k + 1}', "ENABLE"))
                attr_vals.append(AttrVal(f'OREG{k}_BYPH_{2 * k + 1}', "ENABLE"))
        else:
            for k in range(2):
                for h in "LH":
                    attr_vals.append(AttrVal(f'CE{h}MUX_OREG{k}', ce_val))
                    attr_vals.append(AttrVal(f'CLK{h}MUX_OREG{k}', clk_val))
                    attr_vals.append(AttrVal(f'RST{h}MUX_OREG{k}', reset_val))

            if sync_mult_reset:
                for h in "LH":
                    attr_vals.append(AttrVal(f'RSTGEN{h}MUX_OREG0', 'SYNC'))
                    attr_vals.append(AttrVal(f'RSTGEN{h}MUX_OREG1', 'SYNC'))

        return attr_vals

    def get_PADD9_fuses(self, bel: BelDesc) -> list[CellFuseBits]:
        attr_vals = [AttrVal('M9MODE_EN', "ENABLE")]

        dsp_indices = self.decode_dsp_indices(bel)
        attr_vals += self.set_padd9_attrvals(bel, dsp_indices)

        return self.common_dsp_handler(bel, attr_vals)

    def get_PADD18_fuses(self, bel: BelDesc) -> list[CellFuseBits]:
        """ Combine two 9 preadders into one 18 """
        attr_vals = []

        dsp_indices = self.decode_dsp_indices(bel)
        dsp_indices = DspIndices(dsp_indices.mac, dsp_indices.idx * 2)
        attr_vals += self.set_padd9_attrvals(bel, dsp_indices)

        dsp_indices = DspIndices(dsp_indices.mac, dsp_indices.idx + 1)
        attr_vals += self.set_padd9_attrvals(bel, dsp_indices)

        return self.common_dsp_handler(bel, attr_vals)

    def get_MULT9X9_fuses(self, bel: BelDesc) -> list[CellFuseBits]:
        attr_vals = [AttrVal('M9MODE_EN', "ENABLE")]

        dsp_indices = self.decode_dsp_indices(bel)
        attr_vals += self.set_mult9x9_attrvals(bel, dsp_indices)

        return self.common_dsp_handler(bel, attr_vals)

    def get_MULT18X18_fuses(self, bel: BelDesc) -> list[CellFuseBits]:
        """ 18x18 Combine two 9x9 multipliers into one 18x18 """
        attr_vals = []

        dsp_indices = self.decode_dsp_indices(bel)
        dsp_indices = DspIndices(dsp_indices.mac, dsp_indices.idx * 2)
        attr_vals += self.set_mult9x9_attrvals(bel, dsp_indices)

        dsp_indices = DspIndices(dsp_indices.mac, dsp_indices.idx + 1)
        attr_vals += self.set_mult9x9_attrvals(bel, dsp_indices)

        return self.common_dsp_handler(bel, attr_vals)

    def get_MULTALU18X18_fuses(self, bel: BelDesc) -> list[CellFuseBits]:
        attr_vals = []

        mod_bel = self.dsp_mod_bel_idx(bel)
        attr_vals += self.set_multalu18x18_attrvals(mod_bel)

        return self.common_dsp_handler(mod_bel, attr_vals)

    def get_MULTALU36X18_fuses(self, bel: BelDesc) -> list[CellFuseBits]:
        attr_vals = []

        mod_bel = self.dsp_mod_bel_idx(bel)
        dsp_indices = self.decode_dsp_indices(mod_bel)
        attr_vals += self.set_multalu36x18_attrvals(mod_bel, dsp_indices)

        return self.common_dsp_handler(mod_bel, attr_vals)

    def get_MULTADDALU18X18_fuses(self, bel: BelDesc) -> list[CellFuseBits]:
        attr_vals = []

        mod_bel = self.dsp_mod_bel_idx(bel)
        attr_vals += self.set_multaddalu18x18_attrvals(mod_bel)

        return self.common_dsp_handler(mod_bel, attr_vals)

    def get_MULT36X36_fuses(self, bel: BelDesc) -> list[CellFuseBits]:
        attr_vals = []

        # use two cells with different attributes/parameters
        # Macro 0
        mod_bel = self.set_bel_idx(bel, "00")
        cell_0_attrs = bel.cell.attrs.copy()
        cell_0_attrs['NET_ASEL'] = 'GND'
        cell_0_attrs['NET_BSEL'] = 'GND'
        cell_0_attrs['NET_ACCLOAD'] = 'GND'

        cell_0_parms = bel.cell.parms.copy()
        cell_0_parms['MULTALU36X18_MODE'] = "1"  # ACC/0 + A*B
        cell_0_parms['OUT_REG'] = cell_0_parms.pop('OUT0_REG', "0")
        cell_0_parms['ACCLOAD_REG0'] = "0"
        cell_0_parms['ACCLOAD_REG1'] = "0"
        cell_0_parms.pop('OUT1_REG', None)

        mod_bel = BelDesc(mod_bel.x, mod_bel.y, mod_bel.idx_str, CellDesc(bel.cell.name, bel.cell.typ, cell_0_parms, cell_0_attrs, bel.cell.connections))

        dsp_indices = self.decode_dsp_indices(mod_bel)
        attr_vals.append(AttrVal('OR2CASCADE_EN', "ENABLE"))
        attr_vals.append(AttrVal('IRNS_IRMATCHH_9', "ENABLE"))
        attr_vals.append(AttrVal('IRNS_IRMATCHL_8', "ENABLE"))
        attr_vals.append(AttrVal('IRBY_IRMATCHH_9', "ENABLE"))
        attr_vals.append(AttrVal('IRBY_IRMATCHL_8', "ENABLE"))
        attr_vals.append(AttrVal('MATCH_SHFEN', "ENABLE"))

        for attrval in self.set_multalu36x18_attrvals(mod_bel, dsp_indices):
            if attrval.attr not in {'IRASHFEN_0', 'RCISEL_1', 'RCISEL_3'}:
                attr_vals.append(attrval)

        fuses = self.common_dsp_handler(mod_bel, attr_vals)

        # Macro 1
        attr_vals = []
        mod_bel = self.set_bel_idx(bel, "10")
        cell_1_attrs = bel.cell.attrs.copy()
        cell_1_attrs['NET_ASEL'] = 'GND'
        cell_1_attrs['NET_BSEL'] = 'GND'
        cell_1_attrs['NET_ACCLOAD'] = 'GND'

        cell_1_parms = bel.cell.parms.copy()
        cell_1_parms['MULTALU36X18_MODE'] = "10" # A*B + CASI
        cell_1_parms['OUT_REG'] = cell_0_parms.pop('OUT1_REG', "0")
        cell_1_parms['ACCLOAD_REG0'] = "0"
        cell_1_parms['ACCLOAD_REG1'] = "0"
        cell_1_parms.pop('OUT0_REG', None)

        mod_bel = BelDesc(mod_bel.x, mod_bel.y, mod_bel.idx_str, CellDesc(bel.cell.name, bel.cell.typ, cell_1_parms, cell_1_attrs, bel.cell.connections))

        dsp_indices = self.decode_dsp_indices(mod_bel)
        attr_vals.append(AttrVal('CSGIN_EXT', "ENABLE"))
        attr_vals.append(AttrVal('CSIGN_PRE', "ENABLE"))
        attr_vals.append(AttrVal('IRNS_IRMATCHH_9', "ENABLE"))
        attr_vals.append(AttrVal('IRNS_IRMATCHL_8', "ENABLE"))
        attr_vals.append(AttrVal('IRBY_IRMATCHH_9', "ENABLE"))
        attr_vals.append(AttrVal('IRBY_IRMATCHL_8', "ENABLE"))
        attr_vals.append(AttrVal('MATCH_SHFEN', "ENABLE"))
        attr_vals.append(AttrVal('OPCD_4', "1"))

        for attrval in self.set_multalu36x18_attrvals(mod_bel, dsp_indices):
            if attrval.attr not in {'IRASHFEN_0', 'RCISEL_1', 'RCISEL_3', 'OPCD_5'}:
                attr_vals.append(attrval)

        fuses += self.common_dsp_handler(mod_bel, attr_vals)

        return fuses

    def get_ALU54D_fuses(self, bel: BelDesc) -> list[CellFuseBits]:
        attr_vals = []

        mod_bel = self.dsp_mod_bel_idx(bel)
        attr_vals += self.set_alu54d_attrvals(mod_bel)

        return self.common_dsp_handler(mod_bel, attr_vals)

    #==============================
    #========== Finalize
    #==============================
    def get_final_fuses(self) -> list[CellFuseBits]:
        """ Delayed fuse generation """
        fuses = self.get_final_slice_fuses()

        # finalize IO
        self.check_io_banks()

        fuses += self.get_io_bank_fuses()
        fuses += self.get_io_fuses()
        fuses += self.get_dualpin_fuses()

        # wip fuses
        fuses += self.get_work_in_progress_fuses()
        return fuses

    # debug
    def __repr__(self):
        return f'|Device| device_name:{self.device_name}, db:{self.chipdb},\ndefault_slice_attrvals:{self.default_slice_attrvals},\ndefault_ssram_slice_attrvals:{self.default_ssram_slice_attrvals},\nmode_eq_ssram:{self.mode_eq_ssram}, \nio_banks:[{len(self.io_banks)}]{self.io_banks}'

################################################################
class GW1N(Device):
    """ GW1N series """
    def __init__(self, cli_args: CliArgs, pnr: Netlist):
        super().__init__(cli_args, pnr)

    #==============================
    #========== PIPs
    #==============================
    def get_all_hclk_pip_fuses(self, x: int, y: int, src: str, dest: str) -> list[CellFuseBits]:
        """ Depending on the chip series, fuses can be either in one cell or in several. """
        fuses = []
        bits = self.get_hclk_pip_fuses(x, y, src, dest)
        if bits:
            fuses.append(CellFuseBits(x, y, bits))
        fuses += self.get_inter_hclk_fuses(x, y, src, dest)
        return fuses

    #==============================
    #========== IO
    #==============================
    def get_default_pull_strength(self) -> str:
        return 'UNKNOWN'

    def get_iob_fuses(self, x: int, y: int, idx_str: str, av: set[int]) -> list[CellFuseBits]:
        """ In the 5A series, A and B blocks have fuses in different cells. To
        avoid repeating common code, we're moving the actual fuse generation to
        an auxiliary method. """

        fuses = []
        bits = self.chipdb.get_iob_fuses(x, y, av, idx_str)
        if bits:
            fuses.append(CellFuseBits(x, y, bits))
        return fuses

    def process_TLVDS_IOBUF(self, bank_desc: BankDesc, bel: BelDesc) -> list[CellFuseBits]:
        raise Exception("The GW1N series does not support TLVDS IOBUF")

    #==============================
    #========== Oscillators
    #==============================

    #==============================
    #========== Misc
    #==============================
    def get_gsr_types(self) -> set[str]:
        return [50, 83]

    def get_cfg_types(self) -> set[str]:
        return [50, 51]

    def get_pins_attr_vals(self) -> list[AttrVal]:
        attrvals = []
        if self.cli_args.args.jtag_as_gpio:
            attrvals.append(AttrVal('JTAG_AS_GPIO', 'YES'))
        if self.cli_args.args.sspi_as_gpio:
            attrvals.append(AttrVal('SSPI_AS_GPIO', 'YES'))
        if self.cli_args.args.mspi_as_gpio:
            attrvals.append(AttrVal('MSPI_AS_GPIO', 'YES'))
        if self.cli_args.args.ready_as_gpio:
            attrvals.append(AttrVal('READY_AS_GPIO', 'YES'))
        if self.cli_args.args.done_as_gpio:
            attrvals.append(AttrVal('DONE_AS_GPIO', 'YES'))
        if self.cli_args.args.reconfign_as_gpio:
            attrvals.append(AttrVal('RECONFIG_AS_GPIO', 'YES'))
        if self.cli_args.args.i2c_as_gpio:
            attrvals.append(AttrVal('I2C_AS_GPIO', 'YES'))
        return attrvals

    def get_GSR_fuses(self, bel: BelDesc) -> list[CellFuseBits]:
        """ Global Set/Reset """
        gsr_attr_vals = [AttrVal('GSRMODE', 'ACTIVE_LOW')]
        cfg_attr_vals = [AttrVal('GSR', 'USED'), AttrVal('GOE', 'F0'), AttrVal('GSR', 'F0'),
                         AttrVal('DONE', 'F0'), AttrVal('GWD', 'F0')]

        # The configuration fuses are described in the ['shortval'][60] table, global set/reset is
        # described in the ['shortval'][20] table. Look for cells with type with these tables
        gsr_types = self.get_gsr_types()
        cfg_types = self.get_cfg_types()
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

    #==============================
    #========== Clocks
    #==============================
    def get_pll_freq_R(self) -> list[tuple[float, float]]:
        return [(2.6, 65100.0), (3.87, 43800.0), (7.53, 22250.0), (14.35, 11800.0), (28.51, 5940.0), (57.01, 2970.0), (114.41, 1480), (206.34, 820.0)]

    def get_pll_coeffs(self, fvco: float) -> tuple[float, float]:
        """ Returns constants for PLL calculation """
        K0 = (497.5 - math.sqrt(247506.25 - (2675.4 - fvco) * 78.46)) / 39.23
        K1 = 4.8714 * K0 * K0 + 6.5257 * K0 + 142.67
        C1 = 6.69244e-11
        return (K1, C1)

    def get_rPLL_fuses(self, bel: BelDesc) -> list[CellFuseBits]:
        return self.common_pll_handler(bel)

    def get_default_clkdiv_divmode(self) -> str:
        return "2"

    def get_valid_clkdiv_divmodes(self) -> set[str]:
        return {"2", "3.5", "4", "5"}

    # debug
    def __repr__(self):
        return super().__repr__() + ""

################################################################
class GW1N_1(GW1N):
    """ GW1N-1 chip. Tangnano board """
    def __init__(self, cli_args: CliArgs, pnr: Netlist):
        super().__init__(cli_args, pnr)

    #==============================
    #========== Oscillators
    #==============================
    def get_OSC_fuses(self, bel: BelDesc) -> list[CellFuseBits]:
        self.error_not_supported_cell_type(bel)

    def get_OSCH_fuses(self, bel: BelDesc) -> list[CellFuseBits]:
        attr_vals = []
        cell_parms = bel.cell.parms

        val = int(cell_parms.get('FREQ_DIV', bin(100)), 2) # default division coefficient 100
        if val % 2 == 1:
            raise Exception(f"Divisor of the cell '{bel.cell.name}' (OSCH) must be even")

        attr_vals.append(AttrVal('MCLKCIB', val))
        attr_vals.append(AttrVal('MCLKCIB_EN', 'ENABLE'))
        attr_vals.append(AttrVal('NORMAL', 'ENABLE'))

        av = self.set_osc_attrvals(bel, attr_vals)

        fuses = []
        bits = self.chipdb.get_osc_fuses(bel.x, bel.y, av)
        if bits:
            fuses.append(CellFuseBits(bel.x, bel.y, bits))
        return fuses


    #==============================
    #========== Misc
    #==============================
    def get_BUFG_fuses(self, bel: BelDesc) -> list[CellFuseBits]:
        """ Logic -> clock gate """
        return []

    #==============================
    #========== IO
    #==============================
    def process_TLVDS_OBUF(self, bank_desc: BankDesc, bel: BelDesc) -> list[CellFuseBits]:
        raise Exception("The GW1N-1 does not support TLVDS OBUF")

    def process_TLVDS_TBUF(self, bank_desc: BankDesc, bel: BelDesc) -> list[CellFuseBits]:
        raise Exception("The GW1N-1 does not support TLVDS TBUF")

    #==============================
    #========== Clocks
    #==============================
    def get_permitted_pll_freqs(self) -> tuple[float, float, float, float, float]:
        """ (max_in, max_out, min_out, max_vco, min_vco) """
        return (400., 450., 3.125, 900., 400.)

    def get_pll_bels(self, bel: BelDesc) -> Iterator[tuple[int, int]]:
        """ PLL can occupy several cells """
        for off in range(2):
            yield (bel.x + off, bel.y)

    # debug
    def __repr__(self):
        return super().__repr__() + ""

################################################################
class GW1NZ_1(GW1N):
    """ GW1NZ-1 chip. Tangnano1k board """
    def __init__(self, cli_args: CliArgs, pnr: Netlist):
        super().__init__(cli_args, pnr)

    #==============================
    #========== Oscillators
    #==============================

    #==============================
    #========== Misc
    #==============================
    def get_BANDGAP_fuses(self, bel: BelDesc) -> list[CellFuseBits]:
        return []

    def get_BUFG_fuses(self, bel: BelDesc) -> list[CellFuseBits]:
        """ Logic -> clock gate """
        return []

    def get_FLASH64KZ_fuses(self, bel: BelDesc) -> list[CellFuseBits]:
        return []

    #==============================
    #========== IO
    #==============================
    def process_TLVDS_IBUF(self, bank_desc: BankDesc, bel: BelDesc) -> list[CellFuseBits]:
        raise Exception("The GW1NZ-1 does not support TLVDS IBUF")

    def process_TLVDS_OBUF(self, bank_desc: BankDesc, bel: BelDesc) -> list[CellFuseBits]:
        raise Exception("The GW1NZ-1 does not support TLVDS OBUF")

    def process_TLVDS_TBUF(self, bank_desc: BankDesc, bel: BelDesc) -> list[CellFuseBits]:
        raise Exception("The GW1NZ-1 does not support TLVDS TBUF")

    def process_ELVDS_IBUF(self, bank_desc: BankDesc, bel: BelDesc) -> list[CellFuseBits]:
        raise Exception("The GW1NZ-1 does not support ELVDS IBUF")

    def process_ELVDS_IOBUF(self, bank_desc: BankDesc, bel: BelDesc) -> list[CellFuseBits]:
        raise Exception("The GW1NZ-1 does not support ELVDS IOBUF")

    #==============================
    #========== Clocks
    #==============================
    def get_permitted_pll_freqs(self) -> tuple[float, float, float, float, float]:
        """ (max_in, max_out, min_out, max_vco, min_vco) """
        return (400., 400., 3.125, 800., 400.)

    def get_pll_bels(self, bel: BelDesc) -> Iterator[tuple[int, int]]:
        """ PLL can occupy several cells """
        for off in range(2):
            yield (bel.x + off, bel.y)

    def get_OSC_fuses(self, bel: BelDesc) -> list[CellFuseBits]:
        self.error_not_supported_cell_type(bel)

    def get_OSCZ_fuses(self, bel: BelDesc) -> list[CellFuseBits]:
        attr_vals = []
        cell_parms = bel.cell.parms

        val = int(cell_parms.get('FREQ_DIV', bin(100)), 2) # default division coefficient 100
        if val % 2 == 1:
            raise Exception(f"Divisor of the cell '{bel.cell.name}' (OSCZ) must be even")

        attr_vals.append(AttrVal('MCLKCIB', val))
        attr_vals.append(AttrVal('MCLKCIB_EN', 'ENABLE'))

        attr_vals.append(AttrVal('NORMAL', 'ENABLE'))
        attr_vals.append(AttrVal('USERPOWER_SAVE', 'ENABLE'))

        av = self.set_osc_attrvals(bel, attr_vals)

        fuses = []
        bits = self.chipdb.get_osc_fuses(bel.x, bel.y, av)
        if bits:
            fuses.append(CellFuseBits(bel.x, bel.y, bits))
        return fuses

    # debug
    def __repr__(self):
        return super().__repr__() + ""

################################################################
class GW1N_4(GW1N):
    """ GW1N-4 chip. runber board """
    def __init__(self, cli_args: CliArgs, pnr: Netlist):
        super().__init__(cli_args, pnr)

    #==============================
    #========== IO
    #==============================
    def set_io_attrvals(self, bel: IoBelDesc, default_attrs: list[tuple[str, str]], defaults_only = False) -> set[int]:
        """ Set IO attributes in addition to those specified in default. Or use only default. """
        lvds = bel.cell.typ[1:].startswith('LVDS')
        av = set()
        for attr, val in default_attrs:
            if defaults_only:
                self.chipdb.get_iob_attr_val(AttrVal(attr, val), av)
                continue
            if lvds and attr == 'DRIVE': # ignore
                continue
            override_val = bel.cell.attrs.get(attr)
            if override_val:
                val = override_val
            # Check for input resistor
            if attr == 'SINGLERESISTOR':
                self.set_input_resistor(val, bel, av)
            self.chipdb.get_iob_attr_val(AttrVal(attr, val), av)
        return av

    #==============================
    #========== Misc
    #==============================
    def get_BUFG_fuses(self, bel: BelDesc) -> list[CellFuseBits]:
        """ Logic -> clock gate """
        return []

    #==============================
    #========== Clocks
    #==============================
    def get_permitted_pll_freqs(self) -> tuple[float, float, float, float, float]:
        """ (max_in, max_out, min_out, max_vco, min_vco) """
        return (400., 500., 3.125,  1000., 400.)

    def get_pll_bels(self, bel: BelDesc) -> Iterator[tuple[int, int]]:
        """ PLL can occupy several cells """
        for off in range(2):
            yield (bel.x + off, bel.y)

    #==============================
    #========== Iologic
    #==============================
    def get_IOLOGIC_fuses(self, bel: BelDesc) -> list[CellFuseBits]:
        """ OSER16/IDES16 """
        mod_bel = self.make_IologicBelDesc(bel)

        if 'OUTMODE' in bel.cell.parms:
            return self.common_out_iologic_handler(mod_bel)
        else:
            return self.common_in_iologic_handler(mod_bel)

    # debug
    def __repr__(self):
        return super().__repr__() + ""
################################################################
class GW1NS_4(GW1N):
    """ GW1NSR-4C chip. Tangnano4k board """
    def __init__(self, cli_args: CliArgs, pnr: Netlist):
        super().__init__(cli_args, pnr)

    #==============================
    #========== IO
    #==============================
    def process_TLVDS_TBUF(self, bank_desc: BankDesc, bel: IoBelDesc) -> list[CellFuseBits]:
        self.check_tlvds_placement(bel)

        fuses = []
        if bel.is_mipi_out():
            if bel.idx_str == 'B':
                av = self.set_iologic_attrvals(bel, [AttrVal('DYNAMICCIBCONTROL', 'MONDISLIVEA0'),
                                                     AttrVal('CLKOMUX_1', '1'),
                                                     AttrVal('LSRIMUX_0', '0'),
                                                     AttrVal('LSROMUX_0', '0')])
                bits = self.chipdb.get_iologic_fuses(bel.x, bel.y, av, bel.idx_str)
                if bits:
                    fuses.append(CellFuseBits(bel.x, bel.y, bits))
            av = self.set_io_attrvals(bel, self.default_mipi_tlvds_tbuf_attrs, defaults_only = True)
        else:
            av = self.set_io_attrvals(bel, self.default_tlvds_tbuf_attrs)

        io_type = bel.cell.attrs.get('IO_TYPE')
        if io_type:
            self.chipdb.get_iob_attr_val(AttrVal("IO_TYPE", io_type), av)
        else:
            self.chipdb.get_iob_attr_val(AttrVal("IO_TYPE", self.get_default_tlvds_io_type()), av)
        if bel.idx_str == 'A':
            self.chipdb.get_iob_attr_val(AttrVal("LVDS_OUT", "ON"), av)
        self.chipdb.get_iob_attr_val(AttrVal("BANK_VCCIO", bank_desc.bank_vccio), av)

        fuses += self.get_iob_fuses(bel.x, bel.y, bel.idx_str, av)
        return fuses

    #==============================
    #========== Oscillators
    #==============================
    def get_OSC_fuses(self, bel: BelDesc) -> list[CellFuseBits]:
        self.error_not_supported_cell_type(bel)

    def get_OSCZ_fuses(self, bel: BelDesc) -> list[CellFuseBits]:
        attr_vals = []
        cell_parms = bel.cell.parms

        val = int(cell_parms.get('FREQ_DIV', bin(100)), 2) # default division coefficient 100
        if val % 2 == 1:
            raise Exception(f"Divisor of the cell '{bel.cell.name}' (OSCZ) must be even")

        attr_vals.append(AttrVal('MCLKCIB', val))
        attr_vals.append(AttrVal('MCLKCIB_EN', 'ENABLE'))

        attr_vals.append(AttrVal('NORMAL', 'ENABLE'))
        attr_vals.append(AttrVal('USERPOWER_SAVE', 'ENABLE'))

        av = self.set_osc_attrvals(bel, attr_vals)

        fuses = []
        bits = self.chipdb.get_osc_fuses(bel.x, bel.y, av)
        if bits:
            fuses.append(CellFuseBits(bel.x, bel.y, bits))
        return fuses

    #==============================
    #========== IO
    #==============================
    def set_io_attrvals(self, bel: IoBelDesc, default_attrs: list[tuple[str, str]], defaults_only = False) -> set[int]:
        """ Set IO attributes in addition to those specified in default. Or use only default. """
        lvds = bel.cell.typ[1:].startswith('LVDS')
        av = set()
        for attr, val in default_attrs:
            if defaults_only:
                self.chipdb.get_iob_attr_val(AttrVal(attr, val), av)
                continue
            if lvds and attr == 'DRIVE': # ignore
                continue
            override_val = bel.cell.attrs.get(attr)
            if override_val:
                val = override_val
            # Check for input resistor
            if attr == 'SINGLERESISTOR':
                self.set_input_resistor(val, bel, av)
            self.chipdb.get_iob_attr_val(AttrVal(attr, val), av)
        return av

    #==============================
    #========== Misc
    #==============================
    def get_BUFG_fuses(self, bel: BelDesc) -> list[CellFuseBits]:
        """ Logic -> clock gate """
        return []

    def get_FLASH256K_fuses(self, bel: BelDesc) -> list[CellFuseBits]:
        return []

    def get_EMCU_fuses(self, bel: BelDesc) -> list[CellFuseBits]:
        return []

    #==============================
    #========== Clocks
    #==============================
    def get_permitted_pll_freqs(self) -> tuple[float, float, float, float, float]:
        """ (max_in, max_out, min_out, max_vco, min_vco) """
        return (400., 600., 4.6875, 1200., 400.)

    def get_pll_bels(self, bel: BelDesc) -> Iterator[tuple[int, int]]:
        """ One cell for PLLVR + common cell """
        yield (bel.x, bel.y)
        # common cell
        yield (37, 0)

    def get_pll_attrvals(self, bel: BelDesc) -> set[int]:
        av = super().get_pll_attrvals(bel)
        self.chipdb.get_pll_attr_val(AttrVal(f'PLLVCC{bel.idx_str}', 'ENABLE'), av)
        return av

    def get_PLLVR_fuses(self, bel: BelDesc) -> list[CellFuseBits]:
        # Even though the two PLLs on the GW1NSR-4C are located at different
        # ends of the chip and cannot conflict, this particular
        # attribute (PLLVCC) is set in common cell so it needs PLL id
        if bel.x != 27:
            mod_bel = self.set_bel_idx(bel, "1")
        else:
            mod_bel = self.set_bel_idx(bel, "0")
        return self.common_pll_handler(mod_bel)

    #==============================
    #========== Iologic
    #==============================
    def get_IOLOGIC_fuses(self, bel: BelDesc) -> list[CellFuseBits]:
        """ OSER16/IDES16 """
        mod_bel = self.make_IologicBelDesc(bel)

        if 'OUTMODE' in bel.cell.parms:
            return self.common_out_iologic_handler(mod_bel)
        else:
            return self.common_in_iologic_handler(mod_bel)

    # debug
    def __repr__(self):
        return super().__repr__() + ""

################################################################
class GW1N_9(GW1N):
    """ GW1N-9 chip. SZFPGA, MINISZFPGA, TEC0117 boards """
    def __init__(self, cli_args: CliArgs, pnr: Netlist):
        super().__init__(cli_args, pnr)

    #==============================
    #========== Misc
    #==============================
    def get_BUFG_fuses(self, bel: BelDesc) -> list[CellFuseBits]:
        """ Logic -> clock gate """
        return []

    def get_FLASH608K_fuses(self, bel: BelDesc) -> list[CellFuseBits]:
        return []

    #==============================
    #========== Clocks
    #==============================
    def get_permitted_pll_freqs(self) -> tuple[float, float, float, float, float]:
        """ (max_in, max_out, min_out, max_vco, min_vco) """
        return (400., 500., 3.125, 1000., 400.)

    def get_pll_bels(self, bel: BelDesc) -> Iterator[tuple[int, int]]:
        """ PLL can occupy several cells """
        if bel.x > 27:
            offx = -1
        else:
            offx = 1
        for off in range(4):
            yield (bel.x + offx * off, bel.y)

    def get_valid_clkdiv_divmodes(self) -> set[str]:
        return {"2", "3.5", "4", "5", "8"}

    #==============================
    #========== Iologic
    #==============================
    def get_IOLOGIC_fuses(self, bel: BelDesc) -> list[CellFuseBits]:
        """ OSER16/IDES16 """
        mod_bel = self.make_IologicBelDesc(bel)

        if 'OUTMODE' in bel.cell.parms:
            return self.common_out_iologic_handler(mod_bel)
        else:
            return self.common_in_iologic_handler(mod_bel)

    # debug
    def __repr__(self):
        return super().__repr__() + ""


################################################################
class GW1N_9C(GW1N):
    """ GW1N-9C chip. Tangnano9k board """
    def __init__(self, cli_args: CliArgs, pnr: Netlist):
        super().__init__(cli_args, pnr)

    #==============================
    #========== Misc
    #==============================
    def get_BUFG_fuses(self, bel: BelDesc) -> list[CellFuseBits]:
        """ Logic -> clock gate """
        return []

    def get_FLASH608K_fuses(self, bel: BelDesc) -> list[CellFuseBits]:
        return []

    #==============================
    #========== Clocks
    #==============================
    def get_permitted_pll_freqs(self) -> tuple[float, float, float, float, float]:
        """ (max_in, max_out, min_out, max_vco, min_vco) """
        return (400., 600., 3.125, 1200., 400.)

    def get_pll_bels(self, bel: BelDesc) -> Iterator[tuple[int, int]]:
        """ PLL can occupy several cells """
        if bel.x > 27:
            offx = -1
        for off in range(4):
            yield (bel.x + offx * off, bel.y)

    def get_valid_clkdiv_divmodes(self) -> set[str]:
        return {"2", "3.5", "4", "5", "8"}

    #==============================
    #========== Iologic
    #==============================
    def get_IOLOGIC_fuses(self, bel: BelDesc) -> list[CellFuseBits]:
        """ OSER16/IDES16 """
        mod_bel = self.make_IologicBelDesc(bel)

        if 'OUTMODE' in bel.cell.parms:
            return self.common_out_iologic_handler(mod_bel)
        else:
            return self.common_in_iologic_handler(mod_bel)

    # debug
    def __repr__(self):
        return super().__repr__() + ""


################################################################
class GW2A(Device):
    """ GW2A series """
    def __init__(self, cli_args: CliArgs, pnr: Netlist):
        super().__init__(cli_args, pnr)

    #==============================
    #========== PIPs
    #==============================
    def get_all_hclk_pip_fuses(self, x: int, y: int, src: str, dest: str) -> list[CellFuseBits]:
        """ Depending on the chip series, fuses can be either in one cell or in several. """
        fuses = []
        bits = self.get_hclk_pip_fuses(x, y, src, dest)
        if bits:
            fuses.append(CellFuseBits(x, y, bits))
        fuses += self.get_inter_hclk_fuses(x, y, src, dest)
        return fuses

    #==============================
    #========== IO
    #==============================
    def get_default_pull_strength(self) -> str:
        return 'UNKNOWN'

    def get_iob_fuses(self, x: int, y: int, idx_str: str, av: set[int]) -> list[CellFuseBits]:
        """ In the 5A series, A and B blocks have fuses in different cells. To
        avoid repeating common code, we're moving the actual fuse generation to
        an auxiliary method. """

        fuses = []
        bits = self.chipdb.get_iob_fuses(x, y, av, idx_str)
        if bits:
            fuses.append(CellFuseBits(x, y, bits))
        return fuses

    #==============================
    #========== Oscillators
    #==============================

    #==============================
    #========== Misc
    #==============================
    def get_pins_attr_vals(self) -> list[AttrVal]:
        attrvals = []
        if self.cli_args.args.jtag_as_gpio:
            attrvals.append(AttrVal('JTAG_AS_GPIO', 'YES'))
        if self.cli_args.args.sspi_as_gpio:
            attrvals.append(AttrVal('SSPI_AS_GPIO', 'YES'))
        if self.cli_args.args.mspi_as_gpio:
            attrvals.append(AttrVal('MSPI_AS_GPIO', 'YES'))
        if self.cli_args.args.ready_as_gpio:
            attrvals.append(AttrVal('READY_AS_GPIO', 'YES'))
        if self.cli_args.args.done_as_gpio:
            attrvals.append(AttrVal('DONE_AS_GPIO', 'YES'))
        if self.cli_args.args.reconfign_as_gpio:
            attrvals.append(AttrVal('RECONFIG_AS_GPIO', 'YES'))
        if self.cli_args.args.i2c_as_gpio:
            attrvals.append(AttrVal('I2C_AS_GPIO', 'YES'))
        return attrvals

    def get_gsr_types(self) -> set[str]:
        return [1, 83]

    def get_cfg_types(self) -> set[str]:
        return [1, 51]

    def get_GSR_fuses(self, bel: BelDesc) -> list[CellFuseBits]:
        """ Global Set/Reset """
        gsr_attr_vals = [AttrVal('GSRMODE', 'ACTIVE_LOW')]
        cfg_attr_vals = [AttrVal('GSR', 'USED'), AttrVal('GOE', 'F0'), AttrVal('GSR', 'F0'),
                         AttrVal('DONE', 'F0'), AttrVal('GWD', 'F0')]

        # The configuration fuses are described in the ['shortval'][60] table, global set/reset is
        # described in the ['shortval'][20] table. Look for cells with type with these tables
        gsr_types = self.get_gsr_types()
        cfg_types = self.get_cfg_types()
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

    def get_BUFG_fuses(self, bel: BelDesc) -> list[CellFuseBits]:
        """ Logic -> clock gate """
        return []

    #==============================
    #========== Clocks
    #==============================
    def get_pll_freq_R(self) -> list[tuple[float, float]]:
        return [(2.4, 69410.0), (3.53, 47150.0), (6.82, 24430.0), (12.93, 12880.0), (25.7, 6480.0), (51.4, 3240.0), (102.81, 1620), (187.13, 890.0)]

    def get_pll_coeffs(self, fvco: float) -> tuple[float, float]:
        """ Returns constants for PLL calculation """
        K0 = (-28.938 + math.sqrt(837.407844 - (385.07 - fvco) * 0.9892)) / 0.4846
        K1 = 0.1942 * K0 * K0 - 13.173 * K0 + 518.86
        C1 = 6.69244e-11
        return (K1, C1)

    def get_pll_bels(self, bel: BelDesc) -> Iterator[tuple[int, int]]:
        """ PLL can occupy several cells """
        if bel.x > 27:
            offx = -1
        for off in range(4):
            yield (bel.x + offx * off, bel.y)

    def get_rPLL_fuses(self, bel: BelDesc) -> list[CellFuseBits]:
        return self.common_pll_handler(bel)

    def get_permitted_pll_freqs(self) -> tuple[float, float, float, float, float]:
        """ (max_in, max_out, min_out, max_vco, min_vco) """
        return (500., 625., 3.90625, 1250., 500.)

    def get_default_clkdiv_divmode(self) -> str:
        return "2"

    def get_valid_clkdiv_divmodes(self) -> set[str]:
        return {"2", "3.5", "4", "5"}

    # debug
    def __repr__(self):
        return super().__repr__() + ""

################################################################
class GW2A_18(GW2A):
    """ GW2A-18 chip. TangPrimer20k board """
    def __init__(self, cli_args: CliArgs, pnr: Netlist):
        super().__init__(cli_args, pnr)

    # debug
    def __repr__(self):
        return super().__repr__() + ""

################################################################
class GW2A_18C(GW2A):
    """ GW2A-18C chip. Tangnano20k board """
    def __init__(self, cli_args: CliArgs, pnr: Netlist):
        super().__init__(cli_args, pnr)

    #==============================
    #========== Misc
    #==============================

    # debug
    def __repr__(self):
        return super().__repr__() + ""

################################################################
class GW5A(Device):
    """ GW5A series """
    def __init__(self, cli_args: CliArgs, pnr: Netlist):
        super().__init__(cli_args, pnr)
        # PLLA, ADC etc
        # { slot_idx: bitmap }
        self.extra_slots = dict()
        # IO
        self._no_pullup_cfgs = { f'D{x:02}' for x in range(8, 32)}
        self._no_pullup_cfgs.update({'INITDLY0', 'INITDLY1'})
        self.default_ibuf_attrs = [('PADDI', 'PADDI'), ('HYSTERESIS', 'NONE'), ('PULLMODE', 'UP'), ('SLEWRATE', 'SLOW'),
                 ('DRIVE', '0'), ('CLAMP', 'OFF'), ('OPENDRAIN', 'OFF'), ('DIFFRESISTOR', 'OFF'),
                 ('VREF', 'OFF'), ('LVDS_OUT', 'OFF'), ('PULL_STRENGTH', 'MEDIUM')]
        self.default_obuf_attrs = [('ODMUX_1', '1'), ('PULLMODE', 'UP'), ('SLEWRATE', 'FAST'),
                 ('DRIVE', '8'), ('HYSTERESIS', 'NONE'), ('CLAMP', 'OFF'),
                 ('SINGLERESISTOR', 'OFF'), ('LVDS_OUT', 'OFF'), ('DDR_DYNTERM', 'NA'),
                 ('TO', 'INV'), ('OPENDRAIN', 'OFF'), ('PULL_STRENGTH', 'MEDIUM'), ('IOB_UNKNOWN51', 'TRIMUX')]
        self.default_tbuf_attrs = [('ODMUX_1', 'UNKNOWN'), ('PULLMODE', 'UP'), ('SLEWRATE', 'FAST'),
                 ('DRIVE', '8'), ('HYSTERESIS', 'NONE'), ('CLAMP', 'OFF'),
                 ('SINGLERESISTOR', 'OFF'), ('LVDS_OUT', 'OFF'), ('DDR_DYNTERM', 'NA'),
                 ('TO', 'INV'), ('PERSISTENT', 'OFF'), ('ODMUX', 'TRIMUX'), ('OPENDRAIN', 'OFF'),
                 ('PULL_STRENGTH', 'MEDIUM'), ('IOB_UNKNOWN51', 'TRIMUX')]
        self.default_iobuf_attrs = [('PULLMODE', 'UP'), ('SLEWRATE', 'FAST'),
                 ('DRIVE', '8'), ('HYSTERESIS', 'NONE'), ('CLAMP', 'OFF'), ('DIFFRESISTOR', 'OFF'),
                 ('SINGLERESISTOR', 'OFF'), ('LVDS_OUT', 'OFF'), ('DDR_DYNTERM', 'NA'),
                 ('PERSISTENT', 'OFF'), ('ODMUX', 'TRIMUX'), ('PADDI', 'PADDI'), ('OPENDRAIN', 'OFF'),
                 ('PULL_STRENGTH', 'MEDIUM'), ('IOB_UNKNOWN51', 'TRIMUX')]
        self.default_tlvds_tbuf_attrs = [('ODMUX_1', 'UNKNOWN'), ('PULLMODE', 'NONE'), ('SLEWRATE', 'FAST'),
                 ('DRIVE', '0'), ('HYSTERESIS', 'NA'), ('CLAMP', 'OFF'), ('DIFFRESISTOR', 'OFF'),
                 ('SINGLERESISTOR', 'OFF'), ('DDR_DYNTERM', 'NA'),
                 ('TO', 'INV'), ('PERSISTENT', 'OFF'), ('ODMUX', 'TRIMUX'),
                 ('OPENDRAIN', 'OFF'), ('PULL_STRENGTH', 'MEDIUM'), ('IOB_UNKNOWN51', 'TRIMUX')]
        self.default_tlvds_obuf_attrs = [('ODMUX_1', 'UNKNOWN'), ('PULLMODE', 'NONE'), ('SLEWRATE', 'FAST'),
                 ('DRIVE', '0'), ('HYSTERESIS', 'NA'), ('CLAMP', 'OFF'), ('DIFFRESISTOR', 'OFF'),
                 ('SINGLERESISTOR', 'OFF'), ('DDR_DYNTERM', 'NA'),
                 ('TO', 'INV'), ('PERSISTENT', 'OFF'), ('ODMUX', 'TRIMUX'),
                 ('OPENDRAIN', 'OFF'), ('PULL_STRENGTH', 'MEDIUM'), ('IOB_UNKNOWN51', 'TRIMUX')]
        self.default_tlvds_iobuf_attrs = [('PULLMODE', 'NONE'), ('SLEWRATE', 'FAST'),
                 ('DRIVE', '0'), ('HYSTERESIS', 'NA'), ('CLAMP', 'OFF'), ('DIFFRESISTOR', 'OFF'),
                 ('SINGLERESISTOR', 'OFF'), ('DDR_DYNTERM', 'NA'),
                 ('PERSISTENT', 'OFF'), ('ODMUX', 'TRIMUX'), ('PADDI', 'PADDI'),
                 ('OPENDRAIN', 'OFF'), ('PULL_STRENGTH', 'MEDIUM'), ('IOB_UNKNOWN51', 'TRIMUX')]

    def get_extra_slots(self) -> dict[int, any]:
        return self.extra_slots

    def create_pll_slot(self, idx: int):
        """ Create bitmap for PLL """
        bitmap = bitmatrix.zeros(8, 35)
        self.extra_slots[idx] = bitmap
        return bitmap

    def create_adc_slot(self, idx: int):
        """ Create bitmap for ADC """
        bitmap = bitmatrix.zeros(8, 6)
        self.extra_slots[idx] = bitmap
        return bitmap

    def set_slot_bits(self, bitmap: any, bits: set[tuple[int, int]]):
        for row, col in bits:
            bitmap[row][col] = 1

    def set_pll_slot_fuses(self, idx: int, av: set[int]):
        bits = self.chipdb.get_pll_slot_fuses(av)
        if bits:
            bitmap = self.create_pll_slot(idx)
            self.set_slot_bits(bitmap, bits)
        return

    def set_adc_slot_fuses(self, idx: int, av: set[int]):
        bits = self.chipdb.get_adc_slot_fuses(av)
        if bits:
            bitmap = self.create_adc_slot(idx)
            self.set_slot_bits(bitmap, bits)
        return

    #==============================
    #========== PIPs
    #==============================
    def get_all_hclk_pip_fuses(self, x: int, y: int, src: str, dest: str) -> list[CellFuseBits]:
        """ Depending on the chip series, fuses can be either in one cell or in several. """
        fuses = []
        for row, col in self.chipdb.get_hclk_pips().keys():
            if x == col and y == row:
                hclk_pip = self.chipdb.get_hclk_pips_by_xy(col, row)
                if dest in hclk_pip and src in hclk_pip[dest]:
                    bits = self.get_hclk_pip_fuses(x, y, src, dest)
                    if bits:
                        fuses.append(CellFuseBits(x, y, bits))
                    fuses += self.get_inter_hclk_fuses(x, y, src, dest)
        return fuses

    def get_all_pips_fuses(self, pips: Iterator[PipDesc]) -> list[CellFuseBits]:
        """ Return fuses for all PIPs """
        fuses = []
        for pip in pips:
            tiledata = self.chipdb.get_tiledata(pip.x, pip.y)
            if self.is_hclk_pip(pip.x, pip.y, pip.src, pip.dest):
                fuses += self.get_all_hclk_pip_fuses(pip.x, pip.y, pip.src, pip.dest)
            elif self.is_clock_pip(tiledata, pip.src, pip.dest):
                fuses += self.get_clock_pip_fuses(tiledata, pip.x, pip.y, pip.src, pip.dest)
            else:
                bits = self.get_simple_pip_fuses(tiledata, pip.src, pip.dest)
                bits |= self.get_alonenode_fuses(tiledata, pip.src, pip.dest)
                if bits:
                    fuses.append(CellFuseBits(pip.x, pip.y, bits))
        return fuses

    #==============================
    #========== LUTs
    #==============================
    def get_slice_fuses(self, x: int, y: int, idx: int, has_dff_0: bool, has_dff_1: bool, attr_vals: list[AttrVal]) -> list[CellFuseBits]:
        """ Add default attributes """
        av =  set()
        alu_mux_set = False
        for attrval in attr_vals:
            if idx == 0 and attrval.attr == 'ALU_CIN_MUX':
                alu_mux_set = True
            self.chipdb.get_slice_attr_val(attrval, av)

        # we must set CIN mux for the first slice
        if idx == 0 and not alu_mux_set:
            self.chipdb.get_slice_attr_val(AttrVal('ALU_CIN_MUX', 'ALU_5A_CIN_COUT'), av)

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
        if bits:
            fuses.append(CellFuseBits(bel.x, bel.y, bits))
        if bel.idx_int < 8:
            self.used_slices.add_slice_attrs(bel.x, bel.y, bel.idx_int // 2, False, False, [])
        return fuses

    #==============================
    #========== ALU
    #==============================
    def get_ALU_fuses(self, bel: BelDesc) -> list[CellFuseBits]:
        alu_slice_attrvals = [AttrVal(f'MODE_5A_{bel.idx_int % 2}', 'ALU')]
        if bel.idx_int == 0:
            cin_mux = bel.cell.parms.get('CIN_NETTYPE', None)
            if cin_mux == 'VCC':
                alu_slice_attrvals.append(AttrVal('ALU_CIN_MUX', 'ALU_5A_CIN_VCC'))
            elif cin_mux == 'GND':
                alu_slice_attrvals.append(AttrVal('ALU_CIN_MUX', 'ALU_5A_CIN_GND'))
            else:
                alu_slice_attrvals.append(AttrVal('ALU_CIN_MUX', 'ALU_5A_CIN_COUT'))

        self.used_slices.add_slice_attrs(bel.x, bel.y, bel.idx_int // 2, False, False, alu_slice_attrvals)
        return super().get_ALU_fuses(bel)

    #==============================
    #========== Oscillators
    #==============================
    #==============================
    #========== Misc
    #==============================
    def get_GSR_fuses(self, bel: BelDesc) -> list[CellFuseBits]:
        """ Global Set/Reset """
        gsr_attr_vals = [AttrVal('GSRMODE', 'ACTIVE_LOW')]
        cfg_attr_vals = [AttrVal('GSR', 'USED'), AttrVal('GOE', 'F1'), AttrVal('GSR', 'F1'),
                         AttrVal('DONE', 'F3'), AttrVal('GWD', 'F1')]

        # The configuration fuses are described in the ['shortval'][60] table, global set/reset is
        # described in the ['shortval'][20] table. Look for cells with type with these tables
        gsr_types = self.get_gsr_types()
        cfg_types = self.get_cfg_types()
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

    #==============================
    #========== IO
    #==============================
    def get_PINCFG_fuses(self, bel: BelDesc) -> list[CellFuseBits]:
        cell_parms = bel.cell.parms
        if self.cli_args.args.i2c_as_gpio != ('I2C' in cell_parms):
            raise Exception(f" i2c_as_gpio has conflicting settings in nexpnr and gowin_pack.")
        if self.cli_args.args.sspi_as_gpio != ('SSPI' in cell_parms):
            raise Exception(f" sspi_as_gpio has conflicting settings in nexpnr and gowin_pack.")
        return []

    def get_default_pull_strength(self) -> str:
        return 'MEDIUM'

    def get_default_unused_io_type(self) -> str:
        """ Default IO_TYPE for unused IO """
        return "LVCMOS33"

    def get_unused_io_attrvals(self, io_cfg: IoCfg, bank_desc: BankDesc) -> list[AttrVal]:
        """ Attributes for unused IO """
        attrvals = [AttrVal('OPENDRAIN', 'OFF'), AttrVal('IO_TYPE', bank_desc.io_type)]
        if bank_desc.io_type == 'LVCMOS10':
            drive = '4'
        else:
            drive = '8'
        attrvals.append(AttrVal('DRIVE', drive))
        attrvals.append(AttrVal('DRIVE_LEVEL', drive))

        pullup_io = [AttrVal('PADDI', 'PADDI'), AttrVal('PULLMODE', 'UP')]
        if 'TDO' in io_cfg.cfgs or 'DOUT' in io_cfg.cfgs:
            pullup_io = [AttrVal('TO', 'INV'), AttrVal('ODMUX_1', '1'), AttrVal('PULLMODE', 'UP')]
        elif 'RDWR' in io_cfg.cfgs or 'RDWR_B' in io_cfg.cfgs or 'PUDC_B' in io_cfg.cfgs:
            pullup_io = [AttrVal('PADDI', 'PADDI'), AttrVal('PULLMODE', 'DOWN')]
        else:
            for cf in io_cfg.cfgs:
                if cf in self._no_pullup_cfgs:
                    pullup_io = [AttrVal('PADDI', 'PADDI'), AttrVal('PULLMODE', 'NONE')]
                    break
        attrvals += pullup_io
        return attrvals

    def check_io_banks(self):
        """ Check BANK IO_TYPE and VCCIO """
        super().check_io_banks()

        for bank_desc in self.io_banks.values():
            if bank_desc.is_used:
                # set True Lvds output flag
                if not bank_desc.has_true_lvds_outputs:
                    bank_desc.set_attr("LVDS_OUT", "OFF")
                if 'PULL_STRENGTH' not in bank_desc.attrs:
                    bank_desc.set_attr('PULL_STRENGTH', self.get_default_pull_strength())

    def get_iob_fuses(self, x: int, y: int, idx_str: str, av: set[int]) -> list[CellFuseBits]:
        """ In the 5A series, A and B blocks have fuses in different cells. To
        avoid repeating common code, we're moving the actual fuse generation to
        an auxiliary method. """

        fuses = []
        fuse_cell_offset = self.chipdb.get_iob_fuse_cell_offset(x, y, idx_str)
        if fuse_cell_offset:
            x += fuse_cell_offset[1]
            y += fuse_cell_offset[0]
        if (x, y, idx_str) == (91, 2, 'B'):
            idx_str = 'A'
        bits = self.chipdb.get_iob_fuses(x, y, av, idx_str)
        if bits:
            fuses.append(CellFuseBits(x, y, bits))
        return fuses

    #==============================
    #========== Clocks
    #==============================
    def get_DCS_fuses(self, bel: BelDesc) -> list[CellFuseBits]:
        self.error_not_supported_cell_type(bel)

    def get_pll_attrvals(self, bel: BelDesc) -> set[int]:
        """ PLLA attributes """
        av = set()
        cell_parms = bel.cell.parms

        # calc pump
        permitted_freqs = self.get_permitted_pll_freqs()

        fclkin = float(cell_parms.get('A_FCLKIN', '100.00'))
        if fclkin < 3 or fclkin > permitted_freqs[0]:
            raise Exception(f"The {fclkin}MHz frequency is outside the permissible range of 3-{permitted_freqs[0]}MHz.")

        attr = 'A_CLKOUT0_EN'
        val = cell_parms.get(attr, 'TRUE')
        self.chipdb.get_pll_attr_val(AttrVal(attr, val), av)

        for i in range(1, 7):
            attr = f'A_CLKOUT{i}_EN'
            val = cell_parms.get(attr, 'FALSE')
            self.chipdb.get_pll_attr_val(AttrVal(attr, val), av)

        for i in range(7):
            attr = f'A_DYN_PE{i}_SEL'
            val = cell_parms.get(attr, 'FALSE')
            self.chipdb.get_pll_attr_val(AttrVal(attr, val), av)

        for i in range(7):
            attr = f'A_DE{i}_EN'
            val = cell_parms.get(attr, 'FALSE')
            self.chipdb.get_pll_attr_val(AttrVal(attr, val), av)

        attr = 'A_CLKFB_SEL'
        val = cell_parms.get(attr, 'INTERNAL')
        if val == 'INTERNAL':
            self.chipdb.get_pll_attr_val(AttrVal(attr, 'CLKFB2'), av)

        attr = 'A_FBDIV_SEL'
        val = cell_parms.get(attr, '1')
        fbdiv = int(val, 2)
        self.chipdb.get_pll_attr_val(AttrVal(attr, fbdiv), av)

        attr = 'A_IDIV_SEL'
        val = cell_parms.get(attr, '1')
        idiv = int(val, 2)
        self.chipdb.get_pll_attr_val(AttrVal(attr, idiv), av)

        attr = 'A_ODIV0_SEL'
        val = cell_parms.get(attr, bin(8))
        odiv = int(val, 2)
        self.chipdb.get_pll_attr_val(AttrVal(attr, odiv), av)

        attr = 'A_ODIV0_FRAC_SEL'
        val = cell_parms.get(attr, '0')
        odiv_frac = int(val, 2)
        self.chipdb.get_pll_attr_val(AttrVal(attr, odiv_frac), av)

        for i in range(1, 7):
            attr = f'A_ODIV{i}_SEL'
            val = int(cell_parms.get(attr, bin(8)), 2)
            self.chipdb.get_pll_attr_val(AttrVal(attr, val), av)

        attr = 'A_MDIV_SEL'
        val = cell_parms.get(attr, bin(8))
        mdiv = int(val, 2)
        self.chipdb.get_pll_attr_val(AttrVal(attr, mdiv), av)

        attr = 'A_MDIV_FRAC_SEL'
        val = cell_parms.get(attr, '0')
        mdiv_frac = int(val, 2)
        self.chipdb.get_pll_attr_val(AttrVal(attr, mdiv_frac), av)

        for i in range(4):
            attr = f'A_CLKOUT{i}_DT_DIR'
            val = int(cell_parms.get(attr, '1'), 2)
            self.chipdb.get_pll_attr_val(AttrVal(attr, val), av)

        for i in range(4):
            attr = f'A_CLKOUT{i}_DT_STEP'
            val = int(cell_parms.get(attr, '0'), 2)
            self.chipdb.get_pll_attr_val(AttrVal(attr, val), av)

        for i in range(6):
            attr = f'A_CLK{i}_IN_SEL'
            val = int(cell_parms.get(attr, '0'), 2)
            self.chipdb.get_pll_attr_val(AttrVal(attr, val), av)

        for i in range(6):
            attr = f'A_CLK{i}_OUT_SEL'
            val = int(cell_parms.get(attr, '0'), 2)
            self.chipdb.get_pll_attr_val(AttrVal(attr, val), av)

        for i in range(7):
            attr = f'A_CLKOUT{i}_PE_COARSE'
            val = int(cell_parms.get(attr, '0'), 2)
            self.chipdb.get_pll_attr_val(AttrVal(attr, val), av)

        for i in range(7):
            attr = f'A_CLKOUT{i}_PE_FINE'
            val = int(cell_parms.get(attr, '0'), 2)
            self.chipdb.get_pll_attr_val(AttrVal(attr, val), av)

        # XXX only static
        self.chipdb.get_pll_attr_val(AttrVal('A_DYN_DPA_EN', 'FALSE'), av)
        self.chipdb.get_pll_attr_val(AttrVal('A_DYN_ICP_SEL', 'FALSE'), av)
        self.chipdb.get_pll_attr_val(AttrVal('A_DYN_LPF_SEL', 'FALSE'), av)
        self.chipdb.get_pll_attr_val(AttrVal('A_LPF_CAP_SEL', '0'), av)
        self.chipdb.get_pll_attr_val(AttrVal('A_SSC_EN', '0'), av)

        fref = fclkin / idiv
        fclkfb = fref * fbdiv
        # XXX internal feedback for now
        fvco = fclkfb * mdiv
        fclkin_idx, icp, r_idx = self.get_pll_pump(fref, fvco)
        self.chipdb.get_pll_attr_val(AttrVal('KVCO', fclkin_idx // 16), av)
        if fvco > 1400.0:
            fclkin_idx += 1
        self.chipdb.get_pll_attr_val(AttrVal('A_ICP_SEL', int(icp)), av)
        self.chipdb.get_pll_attr_val(AttrVal('A_LPF_RES_SEL', f'R{r_idx}'), av)
        self.chipdb.get_pll_attr_val(AttrVal('FLDCOUNT', fclkin_idx), av)

        # set other attributes
        attr = 'A_RESET_I_EN'
        val = cell_parms.get(attr, 'FALSE')
        self.chipdb.get_pll_attr_val(AttrVal(attr, val), av)

        attr = 'A_RESET_O_EN'
        val = cell_parms.get(attr, 'FALSE')
        self.chipdb.get_pll_attr_val(AttrVal(attr, val), av)

        # set internal attrs
        self.chipdb.get_pll_attr_val(AttrVal('A_RESET_EN', 'TRUE'), av)
        self.chipdb.get_pll_attr_val(AttrVal('PWDEN', 'ENABLE'), av)
        self.chipdb.get_pll_attr_val(AttrVal('PDN', 'ENABLE'), av)
        self.chipdb.get_pll_attr_val(AttrVal('PLOCK', 'ENABLE'), av)
        self.chipdb.get_pll_attr_val(AttrVal('FLOCK', 'ENABLE'), av)
        self.chipdb.get_pll_attr_val(AttrVal('FLTOP', 'ENABLE'), av)
        self.chipdb.get_pll_attr_val(AttrVal('A_GMC_SEL', 15), av),
        self.chipdb.get_pll_attr_val(AttrVal('A_CLKIN_SEL', 'CLKIN0'), av)
        self.chipdb.get_pll_attr_val(AttrVal('A_VR_EN', 'DISABLE'), av)
        self.chipdb.get_pll_attr_val(AttrVal('A_SSC_EN', 'FALSE'), av)
        self.chipdb.get_pll_attr_val(AttrVal('A_CLKFBOUT_PE_COARSE', 0), av)
        self.chipdb.get_pll_attr_val(AttrVal('A_CLKFBOUT_PE_FINE', 0), av)

        return av

    def rename_plla_attrs(self, bel: BelDesc) -> BelDesc:
        cell = bel.cell
        cell_parms = cell.parms

        mod_parms = { 'A_' + a : v for a, v in cell_parms.items() }
        mod_cell = CellDesc(cell.name, cell.typ, mod_parms, cell.attrs, cell.connections)

        return BelDesc(bel.x, bel.y, bel.idx_str, mod_cell)

    def get_PLLA_fuses(self, bel: BelDesc) -> list[CellFuseBits]:
        mod_bel = self.rename_plla_attrs(bel)
        return self.common_pll_handler(mod_bel)

    def common_pll_handler(self, bel: BelDesc) -> list[CellFuseBits]:
        av = self.get_pll_attrvals(bel)

        slot_idx = self.chipdb.get_slot_idx(bel.x, bel.y, 'pll')
        self.set_pll_slot_fuses(slot_idx, av)
        return []

    def get_default_clkdiv_divmode(self) -> str:
        return "2"

    def get_valid_clkdiv_divmodes(self) -> set[str]:
        return {"1", "2", "3", "3.5", "4", "5", "6", "7", "8"}

    #==============================
    #========== Memory
    #==============================
    def get_bsram_init_map(self):
        """ Returns matrix of bsram init data  """
        def get_bits(init_data, width):
            bit_no = 0
            ptr = -1
            while ptr >= -width:
                if bit_no == 8 or bit_no == 17:
                    if width == 288:
                        yield (init_data[ptr], bit_no, lambda x: x)
                        ptr -= 1
                    else:
                        yield ('0', bit_no, lambda x: x)
                    bit_no = (bit_no + 1) % 18
                else:
                    yield (init_data[ptr], bit_no, lambda x: x + 1)
                    ptr -= 1
                    bit_no = (bit_no + 1) % 18

        # Explanation of what comes from and magic numbers. The process is this: you
        # create a file with one primitive from the BSRAM family. In my case pROM. You
        # give it a completely zero initialization. You generate an image. You specify
        # one single nonzero bit at address 0 in the initialization. You generate an
        # image. You compare. You sweep away garbage like CRC.
        # Repeat 16 times.
        # The 16th bit did not show much, but it allowed us to discover the meaning of
        # the logicinfo table [39] - this is the location of a bit in the chip
        # depending on its location in a 16-bit word.
        # Next, we set the bits at address 2 (the next 16 bits) and compare. The result
        # is unexpected: the bits no longer end up where we expect, but a certain pattern
        # is present - bits 4 and 5 radically change the position of the bits in the
        # chip, we take this into account.
        # We repeat for bits up to the 13th --- since this is the maximum address in one SRAM block.
        # 72 * bsram rows * chip bit width
        bsram_init_map = bitmatrix.zeros(72 * len(self.chipdb.simplio_rows), self.chipdb.width)

        last_x = -1
        map_offset = -1
        for bel in self.bsram_bels_with_init:
            # 1 BSRAM cell have width 72
            loc_map = bitmatrix.zeros(256, 72)
            width = 288 if self.is_9bit_bsram(bel) else 256
            #print(f'x:{bel.x}, y:{bel.y}, width:{width}')

            addr = -1
            for init_row in range(0x40):
                row_name = f'INIT_RAM_{init_row:02X}'
                # skip missing init rows
                if row_name not in bel.cell.parms:
                    addr += 0x100
                    continue
                init_data = bel.cell.parms[row_name]
                #print(f'row:{row_name}', init_data)
                for ptr_bit_inc in get_bits(init_data, width):
                    addr = ptr_bit_inc[2](addr)
                    if ptr_bit_inc[0] == '0':
                        continue
                    logic_line = ptr_bit_inc[1] * 4 + (addr >> 12)
                    bit = self.chipdb.rev_logicinfo('BSRAM_INIT')[logic_line][0] - 1
                    quad = {0x30: 0xc0, 0x20: 0x40, 0x10: 0x80, 0x00: 0x00}[addr & 0x30]
                    map_row = quad + ((addr >> 6) & 0x3f)
                    #print(f'map_row:{map_row}, addr: {addr}, bit {ptr_bit_inc[1]}, bit:{bit}')
                    loc_map[map_row][bit] = 1

            # now put one cell init data into global space
            height = 72
            loc_map = bitmatrix.transpose(loc_map)
            y = 0
            for brow in self.chipdb.simplio_rows:
                if bel.y == brow:
                    break
                y += height

            if bel.x != last_x:
                last_x = bel.x
                map_offset += 1

            x = 256 * map_offset
            loc_map = bitmatrix.flipud(loc_map)

            for row in loc_map:
                x0 = x
                for val in row:
                    bsram_init_map[y][x0] = val
                    x0 += 1
                y += 1
        return bsram_init_map

    #==============================
    #========== DSP
    #==============================
    def get_dsp_bels(self, bel: BsramBelDesc) -> Iterator[tuple[int, int]]:
        """ DSP occupy several cells """
        for off in range(3):
            yield (bel.x + off, bel.y)

    # debug
    def __repr__(self):
        return super().__repr__()  + f"| extra_slots:{self.extra_slots}, _no_pullup_cfgs:{self._no_pullup_cfgs} "

################################################################
class GW5A_25A(GW5A):
    """ GW5A-25A chip. Tangprimer25k board """
    def __init__(self, cli_args: CliArgs, pnr: Netlist):
        super().__init__(cli_args, pnr)
        # The GW5A-25A has an interesting phenomenon on the bottom side of the
        # chip: if certain pins are used as a clock source (this also applies
        # to the standard soldered E2) and the routing passes through HCLK,
        # fuses are set not only in this IBUF, but also in another one. The
        # purpose of this mechanism is unclear; we have only found a few such
        # pins and are repeating this process.
        self.hclk_io_pairs = {(11, 36): (30, 36), (25, 36): (32, 36), (53, 36): (28, 36), (74, 36): (90, 36), }
        self.used_clock_spines = set()
        # default attrs for DSP
        self.multaddalu12x12_defaults = [
                ('A0REG_CLK', 'BYPASS'), ('A0REG_CE', 'CE0'), ('A0REG_RESET', 'RESET0'),
                ('B0REG_CLK', 'BYPASS'), ('B0REG_CE', 'CE0'), ('B0REG_RESET', 'RESET0'),
                ('A1REG_CLK', 'BYPASS'), ('A1REG_CE', 'CE0'), ('A1REG_RESET', 'RESET0'),
                ('B1REG_CLK', 'BYPASS'), ('B1REG_CE', 'CE0'), ('B1REG_RESET', 'RESET0'),
                ('ADDSUB0_IREG_CLK', 'BYPASS'), ('ADDSUB0_IREG_CE', 'CE0'), ('ADDSUB0_IREG_RESET', 'RESET0'),
                ('ADDSUB0_PREG_CLK', 'BYPASS'), ('ADDSUB0_PREG_CE', 'CE0'), ('ADDSUB0_PREG_RESET', 'RESET0'),
                ('ADDSUB1_IREG_CLK', 'BYPASS'), ('ADDSUB1_IREG_CE', 'CE0'), ('ADDSUB1_IREG_RESET', 'RESET0'),
                ('ADDSUB1_PREG_CLK', 'BYPASS'), ('ADDSUB1_PREG_CE', 'CE0'), ('ADDSUB1_PREG_RESET', 'RESET0'),
                ('CASISEL_IREG_CLK', 'BYPASS'), ('CASISEL_IREG_CE', 'CE0'), ('CASISEL_IREG_RESET', 'RESET0'),
                ('CASISEL_PREG_CLK', 'BYPASS'), ('CASISEL_PREG_CE', 'CE0'), ('CASISEL_PREG_RESET', 'RESET0'),
                ('MULT_RESET_MODE', 'SYNC'), ('ADD_SUB_0', 0), ('DYN_ADD_SUB_0', 'FALSE'), ('FB_PREG_EN', 'FALSE'),
                ('ADD_SUB_1', 0), ('DYN_ADD_SUB_1', 'FALSE'), ('CASI_SEL', 0), ('ACC_SEL', 0), ('DYN_ACC_SEL', 'FALSE'),
                ]
        self.multalu27x18_defaults = [
                ('C_IREG_CLK', 'BYPASS'), ('C_IREG_CE', 'CE0'), ('C_IREG_RESET', 'RESET0'),
                ('C_PREG_CLK', 'BYPASS'), ('C_PREG_CE', 'CE0'), ('C_PREG_RESET', 'RESET0'),
                ('PADDSUB_IREG_CLK', 'BYPASS'), ('PADDSUB_IREG_CE', 'CE0'), ('PADDSUB_IREG_RESET', 'RESET0'),
                ('PSEL_IREG_CLK', 'BYPASS'), ('PSEL_IREG_CE', 'CE0'), ('PSEL_IREG_RESET', 'RESET0'),
                ('CSEL_IREG_CLK', 'BYPASS'), ('CSEL_IREG_CE', 'CE0'), ('CSEL_IREG_RESET', 'RESET0'),
                ('CSEL_PREG_CLK', 'BYPASS'), ('CSEL_PREG_CE', 'CE0'), ('CSEL_PREG_RESET', 'RESET0'),
                ('ADDSUB0_IREG_CLK', 'BYPASS'), ('ADDSUB0_IREG_CE', 'CE0'), ('ADDSUB0_IREG_RESET', 'RESET0'),
                ('ADDSUB0_PREG_CLK', 'BYPASS'), ('ADDSUB0_PREG_CE', 'CE0'), ('ADDSUB0_PREG_RESET', 'RESET0'),
                ('ADDSUB1_IREG_CLK', 'BYPASS'), ('ADDSUB1_IREG_CE', 'CE0'), ('ADDSUB1_IREG_RESET', 'RESET0'),
                ('ADDSUB1_PREG_CLK', 'BYPASS'), ('ADDSUB1_PREG_CE', 'CE0'), ('ADDSUB1_PREG_RESET', 'RESET0'),
                ('CASISEL_IREG_CLK', 'BYPASS'), ('CASISEL_IREG_CE', 'CE0'), ('CASISEL_IREG_RESET', 'RESET0'),
                ('CASISEL_PREG_CLK', 'BYPASS'), ('CASISEL_PREG_CE', 'CE0'), ('CASISEL_PREG_RESET', 'RESET0'),
                ('MULT_RESET_MODE', 'SYNC'), ('ADD_SUB_0', 0), ('DYN_ADD_SUB_0', 'FALSE'), ('FB_PREG_EN', 'FALSE'),
                ('ADD_SUB_1', 0), ('DYN_ADD_SUB_1', 'FALSE'), ('ACC_SEL', 0), ('DYN_ACC_SEL', 'FALSE'),
                ('SOA_PREG_EN', 'FALSE'), ('A_SEL', 0), ('DYN_A_SEL', 'FALSE'), ('P_SEL', 0), ('DYN_P_SEL', 'FALSE'),
                ('P_ADDSUB', 0), ('DYN_P_ADDSUB', 'FALSE'), ('ADD_SUB_0', 0), ('DYN_ADD_SUB_0', 'FALSE'),
                ('ADD_SUB_1', 0), ('DYN_ADD_SUB_1', 'FALSE'), ('ACC_SEL', 0),
                ('DYN_ACC_SEL', 'FALSE'), ('C_SEL', 0), ('DYN_C_SEL', 'FALSE'), ('MULT12X12_EN', 'FALSE')
                ]
        # ADC pins are not the normal pins, do them separately
        self.adc_ios = []

    #==============================
    #========== PIPs
    #==============================
    def get_set_spine_enable_table(self, dest: str) -> str:
        if not dest.startswith('SPINE') or dest in self.used_clock_spines:
            return None
        self.used_clock_spines.add(dest)
        return f'5A_PCLK_ENABLE_{wnames.clknumbers[dest]:02}'

    def get_spine_enable_fuses(self, x: int, y: int, spine_enable_table: str) -> set[Coord]:
        return self.chipdb.get_spine_enable_fuses(x, y, spine_enable_table)

    def is_clock_pip(self, tiledata: Tile, src: str, dest: str) -> bool:
        if src not in wnames.clknumbers:
            return False
        if dest not in wnames.clknumbers:
            return False
        return wnames.clknumbers[src] < wnames.clknumbers['UNK212'] \
                or wnames.clknumbers[src] in range(wnames.clknumbers['MPLL4CLKOUT0'], wnames.clknumbers['UNK569'] + 1)

    def get_clock_pip_fuses(self, tiledata: Tile, x: int, y: int, src: str, dest: str) -> list[CellFuseBits]:
        """ The mux for clock wires can be "spread" across several cells. """
        fuses = []
        # SPINE->{GT00, GT10} must be set in the cell only
        if dest in {'GT00', 'GT10'}:
            bits = self.get_simple_clock_pip_fuses(tiledata, src, dest)
            if bits:
                fuses.append(CellFuseBits(x, y, bits))
            return fuses

        # need to enable spine?
        spine_enable_table = self.get_set_spine_enable_table(dest)

        for x, y in itertools.product(range(self.chipdb.cols), range(self.chipdb.rows)):
            tiledata = self.chipdb.get_tiledata(x, y)
            bits = self.get_simple_clock_pip_fuses(tiledata, src, dest)
            if spine_enable_table:
                bits |= self.get_spine_enable_fuses(x, y, spine_enable_table)
            if bits:
                fuses.append(CellFuseBits(x, y, bits))
        return fuses

    #==============================
    #========== Oscillators
    #==============================
    def set_osc_attrvals(self, bel: BelDesc, attr_vals: list[AttrVal]) -> set[int]:
        av = set()
        for attr_val in attr_vals:
            self.chipdb.get_osc_attr_val(attr_val, av)
        return av

    def get_OSC_fuses(self, bel: BelDesc) -> list[CellFuseBits]:
        self.error_not_supported_cell_type(bel)

    def get_OSCA_fuses(self, bel: BelDesc) -> list[CellFuseBits]:
        attr_vals = []
        cell_parms = bel.cell.parms

        val = int(cell_parms.get('FREQ_DIV', bin(100)), 2) # default division coefficient 100
        if val % 2 == 1:
            raise Exception(f"Divisor of the cell '{bel.cell.name}' (OSC) must be even")

        attr_vals.append(AttrVal('MCLKCIB', val))
        attr_vals.append(AttrVal('MCLKCIB_EN', 'ENABLE'))

        av = self.set_osc_attrvals(bel, attr_vals)

        fuses = []
        bits = self.chipdb.get_osc_fuses(bel.x, bel.y, av)
        if bits:
            fuses.append(CellFuseBits(bel.x, bel.y, bits))
        return fuses

    #==============================
    #========== Misc
    #==============================
    def get_BUFG_fuses(self, bel: BelDesc) -> list[CellFuseBits]:
        """ Logic -> clock gate """
        return []

    def add_check_adc_io(self, bel: BelDesc, adc_io_loc = "", iore = re.compile(r"(\d+)/X(\d+)Y(\d+)")) -> AdcIo:
        if bel.cell.typ == 'ADC':
            res = iore.fullmatch(adc_io_loc)
            if not res:
                raise Exception(f"Bad IOLOC {adc_io_loc} in the ADC src list.")
            bus, x, y = res.groups()
            x = int(x)
            y = int(y)
        else:
            bus = '2'
            x = bel.x
            y = bel.y

        pin_bus = self.chipdb.get_adc_bus(x, y)
        if pin_bus != f'BUS{bus}':
            raise Exception(f"IO({y}, {x}) has ADC bus {pin_bus[-1]}, but used in bus {bus}.")

        for adc_io in self.adc_ios:
            if adc_io.bus == bus and bus in "01":
                raise Exception(f"IO at ({y}, {x}) and at ({adc_io.y}, {adc_io.x}) have same bus {bus}. Only one IO in the one bus allowed.")

        adc_io = AdcIo(x, y, bus)
        self.adc_ios.append(adc_io)

        return adc_io

    def get_pins_attr_vals(self) -> list[AttrVal]:
        attrvals = []
        if self.cli_args.args.jtag_as_gpio:
            attrvals.append(AttrVal('JTAG_AS_GPIO', 'YES'))
        attrvals.append(AttrVal('SSPI_AS_GPIO', 'YES'))
        if self.cli_args.args.mspi_as_gpio:
            attrvals.append(AttrVal('MSPI_AS_GPIO', 'YES'))
        if self.cli_args.args.ready_as_gpio:
            attrvals.append(AttrVal('READY_AS_GPIO', 'YES'))
        if self.cli_args.args.done_as_gpio:
            attrvals.append(AttrVal('DONE_AS_GPIO', 'YES'))
        if self.cli_args.args.reconfign_as_gpio:
            attrvals.append(AttrVal('RECONFIG_AS_GPIO', 'YES'))
        if self.cli_args.args.i2c_as_gpio:
            attrvals.append(AttrVal('I2C_AS_GPIO', 'YES'))
        if self.cli_args.args.cpu_as_gpio:
            attrvals.append(AttrVal('CPU_AS_GPIO_25', 'YES'))
        return attrvals

    def get_gsr_types(self) -> set[str]:
        return [49, 83]

    def get_cfg_types(self) -> set[str]:
        return [49, 51]

    def set_adc_attrvals(self, bel: BelDesc) -> list[AttrVal]:
        attr_vals = []
        cell_parms = bel.cell.parms
        cell_attrs = bel.cell.attrs

        attr = 'DIV_CTL'
        val = int(cell_parms.get(attr, '0'), 2)
        if val:
            attr_vals.append(AttrVal(attr, 2**val))

        attr = 'CSR_VSEN_CTRL'
        val = int(cell_parms.get(attr, '0'), 2)
        if val == 4:
            attr_vals.append(AttrVal(attr, 'UNK1'))
        elif val == 7:
            attr_vals.append(AttrVal(attr, 'UNK0'))

        attr = 'CSR_SAMPLE_CNT_SEL'
        val = int(cell_parms.get(attr, bin(4)), 2)
        if val > 4:
            attr_vals.append(AttrVal(attr, 2048))
        else:
            attr_vals.append(AttrVal(attr, (2**val) * 64))

        attr = 'CSR_RATE_CHANGE_CTRL'
        val = int(cell_parms.get(attr, bin(4)), 2)
        if val > 4:
            attr_vals.append(AttrVal(attr, 80))
        else:
            attr_vals.append(AttrVal(attr, (2**val) * 4))

        attr = 'CSR_OFFSET'
        val = int(cell_parms.get(attr, '101101100100'), 2) # -12'd1180
        if val == 0:
            attr_vals.append(AttrVal(attr, 'DISABLE'))
        else:
            if val & 1 << 11:
                val -= 1 << 12;
            attr_vals.append(AttrVal(attr, val))

        attr = 'CSR_FSCAL'
        val = int(cell_parms.get(attr, '1011011010'), 2) # 10'd730
        if val in range(452, 841):
            attr_vals.append(AttrVal('CSR_FSCAL1', val))
        attr_vals.append(AttrVal('CSR_FSCAL0', val))

        attr = 'CSR_ADC_MODE'
        val = int(cell_parms.get(attr, '1'), 2)
        if val == 1:
            attr_vals.append(AttrVal(attr, '1'))
        else:
            attr_vals.append(AttrVal(attr, 'UNKNOWN'))

        attr = 'CLK_SEL'
        val = int(cell_parms.get(attr, '0'), 2)
        if val == 1:
            attr_vals.append(AttrVal(attr, 'CLK_CLK'))

        attr = 'BUF_EN'
        val = int(cell_parms.get(attr, '0'), 2)
        for i in range(12):
            if val & (2**i):
                attr_vals.append(AttrVal(f'BUF_{i}_EN', 'ON'))

        #for i in range(7):
        #    attr = f'BUF_BK{i}_VREF_EN'
        #    val = int(cell_parms.get(attr, '0'), 2)
        #    attr_vals.append(AttrVal(attr, val))

        attr = 'PHASE_SEL'
        val = int(cell_parms.get(attr, '0'), 2)
        if val == 1:
            attr_vals.append(AttrVal(attr, 'PHASE_180'))

        attr = 'UNK0'
        val = int(cell_parms.get(attr, '101'), 2)
        if val == 0:
            attr_vals.append(AttrVal(attr, 'DISABLE'))
        else:
            attr_vals.append(AttrVal(attr, val))

        attr = 'ADC_EN_SEL'
        val = int(cell_parms.get(attr, '0'), 2)
        if val == 1:
            attr_vals.append(AttrVal(attr, 'ADC'))

        attr = 'IBIAS_CTL'
        val = int(cell_parms.get(attr, '1000'), 2)
        if val == 0:
            attr_vals.append(AttrVal(attr, 'DISABLE'))
        else:
            attr_vals.append(AttrVal(attr, val))

        attr = 'UNK1'
        val = int(cell_parms.get(attr, '1'), 2)
        if val == 1:
            attr_vals.append(AttrVal(attr, 'OFF'))
        else:
            attr_vals.append(AttrVal(attr, val))

        attr = 'UNK2'
        val = int(cell_parms.get(attr, '10000'), 2)
        if val == 0:
            attr_vals.append(AttrVal(attr, 'DISABLE'))
        else:
            attr_vals.append(AttrVal(attr, val))

        attr = 'CHOP_EN'
        val = int(cell_parms.get(attr, '1'), 2)
        if val == 1:
            attr_vals.append(AttrVal(attr, 'ON'))
        else:
            attr_vals.append(AttrVal(attr, 'UNKNOWN'))

        attr = 'GAIN'
        val = int(cell_parms.get(attr, '100'), 2)
        if val == 0:
            attr_vals.append(AttrVal(attr, 'DISABLE'))
        else:
            attr_vals.append(AttrVal(attr, val))

        attr = 'CAP_CTL'
        val = int(cell_parms.get(attr, '0'), 2)
        attr_vals.append(AttrVal(attr, val))

        return attr_vals

    def get_ADC_fuses(self, bel: BelDesc) -> list[CellFuseBits]:
        """ 25k style ADC """

        fuses = []

        # mark IO as ADC in
        for attr, val in bel.cell.attrs.items():
            if attr.startswith('ADC_IO_'):
                adc_io = self.add_check_adc_io(bel, val)
                fuses += self.get_adc_io_fuses(adc_io, 'A')
                fuses += self.get_adc_io_fuses(adc_io, 'B')

        attr_vals = self.set_adc_attrvals(bel)

        av =  set()
        for attrval in attr_vals:
            self.chipdb.get_adc_attr_val(attrval, av)

        slot_idx = self.chipdb.get_slot_idx(bel.x, bel.y, 'adc')
        self.set_adc_slot_fuses(slot_idx, av)

        bits = self.chipdb.get_adc_fuses(bel.x, bel.y, av)
        if bits:
            fuses.append(CellFuseBits(bel.x, bel.y, bits))

        return fuses

    #==============================
    #========== IO
    #==============================
    def do_not_touch_io(self, x: int, y: int, idx_str: str) -> bool:
        """ Do not set fuses for this IO """
        for adc_io in self.adc_ios:
            if x == adc_io.x and y == adc_io.y:
                return True
        return False

    def process_IBUF(self, bank_desc: BankDesc, bel: IoBelDesc) -> list[CellFuseBits]:
        av = self.set_io_attrvals(bel, self.default_ibuf_attrs)
        fuses = []
        self.chipdb.get_iob_attr_val(AttrVal("IO_TYPE", bank_desc.io_type), av)
        self.chipdb.get_iob_attr_val(AttrVal("BANK_VCCIO", bank_desc.bank_vccio), av)

        if 'HCLK' in bel.flags:
            self.chipdb.get_iob_attr_val(AttrVal("IOB_UNKNOWN67", "UNKNOWN263"), av)
        if 'HCLK_PAIR' in bel.flags:
            self.chipdb.get_iob_attr_val(AttrVal("IOB_UNKNOWN67", "UNKNOWN266"), av)

        fuses += self.get_iob_fuses(bel.x, bel.y, bel.idx_str, av)
        return fuses

    def get_adc_io_fuses(self, adc_io: AdcIo, idx_str: str) -> list[CellFuseBits]:
        """ ADC io fuses """

        av = set()
        if idx_str == 'A':
            # pin P
            if adc_io.bus not in '01':
                self.chipdb.get_iob_attr_val(AttrVal('IOB_GW5_ADC_DYN_IN', 'ENABLE'), av)
                self.chipdb.get_iob_attr_val(AttrVal('IOB_UNKNOWN70', 'UNKNOWN'), av)
                self.chipdb.get_iob_attr_val(AttrVal('IOB_UNKNOWN71', 'UNKNOWN'), av)
            self.chipdb.get_iob_attr_val(AttrVal('IO_TYPE', 'GW5_ADC_IN'), av)
            self.chipdb.get_iob_attr_val(AttrVal('IOB_GW5_ADC_IN', 'ENABLE'), av)
            self.chipdb.get_iob_attr_val(AttrVal('PULLMODE', 'NONE'), av)
            self.chipdb.get_iob_attr_val(AttrVal('HYSTERESIS', 'NONE'), av)
            self.chipdb.get_iob_attr_val(AttrVal('CLAMP', 'OFF'), av)
            self.chipdb.get_iob_attr_val(AttrVal('OPENDRAIN', 'OFF'), av)
            self.chipdb.get_iob_attr_val(AttrVal('DDR_DYNTERM', 'NA'), av)
            self.chipdb.get_iob_attr_val(AttrVal('IO_BANK', 'NA'), av)
            self.chipdb.get_iob_attr_val(AttrVal('PADDI', 'PADDI'), av)
            self.chipdb.get_iob_attr_val(AttrVal('PULL_STRENGTH', 'NONE'), av)
            self.chipdb.get_iob_attr_val(AttrVal('IOB_GW5_VCCX_64', '3.3'), av)
        else:
            if adc_io.bus in '01':
                self.chipdb.get_iob_attr_val(AttrVal('IOB_UNKNOWN60', 'ON'), av)
                self.chipdb.get_iob_attr_val(AttrVal('IOB_UNKNOWN61', 'ON'), av)
            else:
                self.chipdb.get_iob_attr_val(AttrVal('IOB_GW5_ADC_DYN_IN', 'ENABLE'), av)
                self.chipdb.get_iob_attr_val(AttrVal('IOB_UNKNOWN70', 'UNKNOWN'), av)
                self.chipdb.get_iob_attr_val(AttrVal('IOB_UNKNOWN71', 'UNKNOWN'), av)
            self.chipdb.get_iob_attr_val(AttrVal('IO_TYPE', 'GW5_ADC_IN'), av)
            self.chipdb.get_iob_attr_val(AttrVal('IOB_GW5_ADC_IN', 'ENABLE'), av)
            self.chipdb.get_iob_attr_val(AttrVal('PULLMODE', 'NONE'), av)
            self.chipdb.get_iob_attr_val(AttrVal('HYSTERESIS', 'NONE'), av)
            self.chipdb.get_iob_attr_val(AttrVal('CLAMP', 'OFF'), av)
            self.chipdb.get_iob_attr_val(AttrVal('OPENDRAIN', 'OFF'), av)
            self.chipdb.get_iob_attr_val(AttrVal('DDR_DYNTERM', 'NA'), av)
            self.chipdb.get_iob_attr_val(AttrVal('IO_BANK', 'NA'), av)
            self.chipdb.get_iob_attr_val(AttrVal('PADDI', 'PADDI'), av)
            self.chipdb.get_iob_attr_val(AttrVal('PULL_STRENGTH', 'NONE'), av)
            self.chipdb.get_iob_attr_val(AttrVal('IOB_GW5_VCCX_64', '3.3'), av)


        fuses = self.get_iob_fuses(adc_io.x, adc_io.y, idx_str, av)
        return fuses

    def get_IBUF_fuses(self, bel: BelDesc) -> list[CellFuseBits]:
        """ Added processing features when routing via HCLK or ADC """
        if bel.cell.parms.get('DIFF_TYPE', None) == 'TLVDS_IBUF_ADC':
            if self.make_IoBelDesc(bel).is_diff_io():
                adc_io = self.add_check_adc_io(bel)
                return self.get_adc_io_fuses(adc_io, bel.idx_str)
        else:
            pair_xy = self.hclk_io_pairs.get((bel.x, bel.y), None)
            is_HCLK_GCLK_net = False
            if pair_xy:
                net = self.pnr.get_net_by_bits(bel.cell.connections.get('O', None))
                if net:
                    # IBUF connected to HCLK_GCLK
                    routing = net['attributes'].get('ROUTING', {})
                    if 'HCLK_GCLK' in routing:
                       is_HCLK_GCLK_net = True
            if is_HCLK_GCLK_net:
                self.common_io_handler(self.make_IoBelDesc(bel, {'HCLK': 1}))
                pair_bel = IoBelDesc(pair_xy[0], pair_xy[1], 'A', bel.cell, {'HCLK_PAIR': 1})
                self.common_io_handler(pair_bel)
            else:
                self.common_io_handler(self.make_IoBelDesc(bel))

        return []

    #==============================
    #========== Iologic
    #==============================
    def get_out_iologic_attrs(self, bel: IologicBelDesc) -> list[AttrVal]:
        """ OUT iologic attrs """
        attr_vals = []
        cell_attrs = bel.cell.attrs
        cell_parms = bel.cell.parms
        fclk = bel.fclk

        if fclk != 'UNKNOWN':
            attr_vals.append(AttrVal('WRFCLKSEL', 'UNK102'))
        if fclk == 'SPINE10':
            attr_vals.append(AttrVal('FCLKSEL0', 'HCLK0'))
            attr_vals.append(AttrVal('FCLKSEL1', 'HCLK0'))
            attr_vals.append(AttrVal('FCLKSEL2', 'HCLK0_'))
            attr_vals.append(AttrVal('FCLKSEL3', 'HCLK0'))
        elif fclk == 'SPINE11':
            attr_vals.append(AttrVal('FCLKSEL0', 'HCLK1'))
            attr_vals.append(AttrVal('FCLKSEL1', 'HCLK1'))
            attr_vals.append(AttrVal('FCLKSEL2', 'HCLK1_'))
            attr_vals.append(AttrVal('FCLKSEL4', 'HCLK1'))
        elif fclk == 'SPINE12':
            attr_vals.append(AttrVal('FCLKSEL0', 'HCLK2'))
            attr_vals.append(AttrVal('FCLKSEL1', 'HCLK2'))
            attr_vals.append(AttrVal('FCLKSEL2', 'HCLK2_'))
            attr_vals.append(AttrVal('FCLKSEL3', 'HCLK2'))
        elif fclk == 'SPINE13':
            attr_vals.append(AttrVal('FCLKSEL0', 'HCLK3'))
            attr_vals.append(AttrVal('FCLKSEL1', 'HCLK3'))
            attr_vals.append(AttrVal('FCLKSEL2', 'HCLK3_'))
            attr_vals.append(AttrVal('FCLKSEL4', 'HCLK3'))

        cell_outmode = cell_parms['OUTMODE']
        attr_vals.append(AttrVal('LSRIMUX_0', '0'))
        if cell_outmode in {'ODDRX1', 'ODDRX2', 'ODDRX4'}:
            attr_vals.append(AttrVal('CLKOMUX', 'ENABLE'))
            attr_vals.append(AttrVal('OCLKCE', 'CE'))
            attr_vals.append(AttrVal('LSROMUX_0', '0'))
            attr_vals.append(AttrVal('OUTMODE', cell_outmode))
        elif cell_outmode in {'ODDRX5'}: # main cell
            attr_vals.append(AttrVal('HWL', 'TRUE'))
            attr_vals.append(AttrVal('CLKOMUX', 'ENABLE'))
            attr_vals.append(AttrVal('CLKOMUX_CLK', 'SIG'))
            attr_vals.append(AttrVal('LSROMUX_0', 'UNKNOWN'))
            attr_vals.append(AttrVal('OCLKCE', 'CE'))
            attr_vals.append(AttrVal('OUTMODE', cell_outmode))
        elif cell_outmode in {'DDRENABLE'}: # aux cell
            if bel.main_cell_outmode == 'VIDEOTX':
                attr_vals.append(AttrVal('OUTMODE', 'LVDSOUT'))
                attr_vals.append(AttrVal('CLKOMUX', 'ENABLE'))
                attr_vals.append(AttrVal('OCLKCE', 'CE'))
                attr_vals.append(AttrVal('LSROMUX_0', '0'))
            else:
                attr_vals.append(AttrVal('OUTMODE', 'UNKNOWN'))
                attr_vals.append(AttrVal('CLKOMUX', 'ENABLE'))
                attr_vals.append(AttrVal('CLKOMUX_CLK', 'SIG'))
                attr_vals.append(AttrVal('LSROMUX_0', 'UNKNOWN'))
                attr_vals.append(AttrVal('OUTCLK', 'ENABLE'))
                attr_vals.append(AttrVal('OCLKCE', 'CE'))
        elif cell_outmode == 'VIDEOTX':
            attr_vals.append(AttrVal('OUTMODE', 'LVDSOUT'))
            attr_vals.append(AttrVal('CLKOMUX', 'ENABLE'))
            attr_vals.append(AttrVal('LSROMUX_0', '0'))
            attr_vals.append(AttrVal('OCLKCE', 'CE'))

        return attr_vals

    def get_in_iologic_attrs(self, bel: IologicBelDesc) -> list[AttrVal]:
        """ IN iologic attrs """
        attr_vals = []
        cell_attrs = bel.cell.attrs
        cell_parms = bel.cell.parms
        fclk = bel.fclk

        if bel.main_cell_inmode == 'DDRENABLE':
            return []
        if fclk == 'SPINE10':
            attr_vals.append(AttrVal('FCLKSEL5', 'HCLK0'))
            attr_vals.append(AttrVal('FCLKSEL6', 'HCLK0'))
            attr_vals.append(AttrVal('FCLKSEL7', 'HCLK0_'))
            attr_vals.append(AttrVal('FCLKSEL3', 'HCLK0'))
        elif fclk == 'SPINE11':
            attr_vals.append(AttrVal('FCLKSEL5', 'HCLK1'))
            attr_vals.append(AttrVal('FCLKSEL6', 'HCLK1'))
            attr_vals.append(AttrVal('FCLKSEL7', 'HCLK1_'))
            attr_vals.append(AttrVal('FCLKSEL4', 'HCLK1'))
        elif fclk == 'SPINE12':
            attr_vals.append(AttrVal('FCLKSEL5', 'HCLK2'))
            attr_vals.append(AttrVal('FCLKSEL6', 'HCLK2'))
            attr_vals.append(AttrVal('FCLKSEL7', 'HCLK2_'))
            attr_vals.append(AttrVal('FCLKSEL3', 'HCLK2'))
        elif fclk == 'SPINE13':
            attr_vals.append(AttrVal('FCLKSEL5', 'HCLK3'))
            attr_vals.append(AttrVal('FCLKSEL6', 'HCLK3'))
            attr_vals.append(AttrVal('FCLKSEL7', 'HCLK3_'))
            attr_vals.append(AttrVal('FCLKSEL4', 'HCLK3'))

        attr_vals.append(AttrVal('LSRMUX_LSR', 'SIG'))
        attr_vals.append(AttrVal('LSRIMUX_0', '0'))
        attr_vals.append(AttrVal('LSROMUX_0', '0'))
        cell_inmode = cell_parms['INMODE']
        if cell_inmode in {'IDDRX1', 'IDDRX2', 'IDDRX4', 'IDDRX5'}:
            attr_vals.append(AttrVal('INMODE', cell_inmode))
            attr_vals.append(AttrVal('CLKIMUX', 'ENABLE'))
        elif cell_inmode == 'VIDEORX':
            attr_vals.append(AttrVal('INMODE', 'LVDSIN'))
            attr_vals.append(AttrVal('CLKIMUX', 'ENABLE'))
        else:
            attr_vals.append(AttrVal('INMODE', cell_inmode))
        return attr_vals

    def common_iologic_handler(self, bel: IologicBelDesc) -> list[AttrVal]:
        attr_vals = []
        cell_parms = bel.cell.parms

        attr = 'TXCLK_POL'
        val = str(int(cell_parms.get(attr, '0'), 2))
        attr_vals.append(AttrVal(attr, val))

        attr = 'HWL'
        val = cell_parms.get(attr, 'FALSE')
        if val != 'FALSE':
            attr_vals.append(AttrVal(attr, val))

        attr_vals.append(AttrVal('GSR', 'ENGSR'))
        return attr_vals

    #==============================
    #========== Clocks
    #==============================
    def get_pll_freq_R(self) -> list[tuple[float, float]]:
        return [(3.24, 72300), (4.79, 48900), (9.22, 25400), (17.09, 13700), (34.08, 6870), (68.05, 3440), (136.1, 1720), (270.95, 864)]

    def get_permitted_pll_freqs(self) -> tuple[float, float, float, float, float]:
        """ (max_in, max_out, min_out, max_vco, min_vco) """
        return (800., 1600., 6.25, 1600., 800.)

    def get_pll_coeffs(self, fvco: float) -> tuple[float, float]:
        """ Returns constants for PLL calculation """
        K1 = 120
        if fvco >= 1400.0:
            K1 = 240
        C1 = 4.725e-11
        return (K1, C1)

    def get_DCS_fuses(self, bel: BelDesc) -> list[CellFuseBits]:
        # DCSs without DCS_MODE are unused
        if 'DCS_MODE' not in bel.cell.attrs:
            return []
        spine = self.chipdb.get_dcs_spine(bel.x, bel.y, bel.idx_int)

        av = self.get_dcs_attrvals(bel, spine)
        _, dcs_str = self.dcs_spine2quadrant_idx[spine]

        fuses = []
        for x, y in itertools.product(range(self.chipdb.cols), range(self.chipdb.rows)):
            bits = self.chipdb.get_dcs_fuses(x, y, av, dcs_str)
            if bits:
                fuses.append(CellFuseBits(x, y, bits))
        return fuses

    def get_CLKDIV_fuses(self, bel: BelDesc) -> list[CellFuseBits]:
        hclk_idx = bel.idx_str[-1]

        av = set()
        self.chipdb.get_hclk_attr_val(AttrVal(f"HCLKDIV{hclk_idx}_DIV", self.get_clkdiv_divmode(bel)), av)

        fuses = []
        bels_x_y = self.get_clkdiv_bels(bel)
        for x_y in bels_x_y:
            x, y = x_y
            bits = self.chipdb.get_hclk_fuses(x, y, av)
            if bits:
                fuses.append(CellFuseBits(x, y, bits))
        return fuses

    def get_CLKDIV2_fuses(self, bel: BelDesc) -> list[CellFuseBits]:
        return []

    #==============================
    #========== DSP
    #==============================
    def common_dsp_handler(self, bel: BelDesc, attr_vals: list[AttrVal]) -> list[CellFuseBits]:
        av =  set()
        for attrval in attr_vals:
            self.chipdb.get_dsp5_attr_val(attrval, av)

        fuses = []
        bels_x_y = self.get_dsp_bels(bel)
        for x_y in bels_x_y:
            x, y = x_y
            bits = self.chipdb.get_dsp5_fuses(x, y, av)
            if bits:
                fuses.append(CellFuseBits(x, y, bits))
        return fuses

    def set_mult12x12_attrvals(self, bel: BelDesc, dsp_indices: DspIndices) -> list[AttrVal]:
        """ 12x12 """
        attr_vals = []
        cell_parms = bel.cell.parms
        cell_attrs = bel.cell.attrs

        pair_idx = dsp_indices.pair_idx
        idx = dsp_indices.idx
        is_even = dsp_indices.is_even

        # The working theory is that the second multiplier needs to be shifted to the left by 24 bits, and perhaps this pair determines that.
        attr_vals.append(AttrVal('UNK_192', 'UNK_23'))
        attr_vals.append(AttrVal('CE0_MUX', 'CE0_IN'))
        attr_vals.append(AttrVal('CE1_MUX', 'CE1_IN'))
        if idx:
            attr_vals.append(AttrVal('MULT12_1_EN', 'TRUE'))
        else:
            attr_vals.append(AttrVal('MULT12X12_EN', 'TRUE'))
            attr_vals.append(AttrVal('ALU_OP0_MUX', 'MULT0'))  # connect the first multiplier as operand 0 ALU — it will be placed in the lower bits of the result.

        for parm in ['AREG_CLK', 'BREG_CLK', 'PREG_CLK', 'OREG_CLK']:
            val = cell_parms.get(parm, 'BYPASS')
            attr_vals.append(AttrVal(f'{parm[0]}{idx}{parm[1:]}', val))

        for parm in ['AREG_CE', 'BREG_CE', 'PREG_CE', 'OREG_CE']:
            val = cell_parms.get(parm, 'CE0')
            attr_vals.append(AttrVal(f'{parm[0]}{idx}{parm[1:]}', val))

        for parm in ['AREG_RESET', 'BREG_RESET', 'PREG_RESET', 'OREG_RESET']:
            val = cell_parms.get(parm, 'RESET0')
            attr_vals.append(AttrVal(f'{parm[0]}{idx}{parm[1:]}', val))

        attr = 'MULT_RESET_MODE'
        val = cell_parms.get(attr, 'SYNC')
        attr_vals.append(AttrVal(attr, val))

        return attr_vals

    def set_multaddalu12x12_attrvals(self, bel: BelDesc, dsp_indices: DspIndices) -> list[AttrVal]:
        """ 12x12 """
        attr_vals = []
        cell_parms = bel.cell.parms
        cell_attrs = bel.cell.attrs

        pair_idx = dsp_indices.pair_idx
        idx = dsp_indices.idx
        is_even = dsp_indices.is_even

        # The working theory is that the second multiplier needs to be shifted to the left by 24 bits, and perhaps this pair determines that.
        attr_vals.append(AttrVal('UNK_192', 'UNK_23')) # see mult12x12
        attr_vals.append(AttrVal('CE0_MUX', 'CE0_IN'))
        attr_vals.append(AttrVal('CE1_MUX', 'CE1_IN'))
        attr_vals.append(AttrVal('MULT12_1_EN', 'TRUE'))
        attr_vals.append(AttrVal('MULT12X12_EN', 'TRUE'))
        attr_vals.append(AttrVal('ALU_OP0_MUX', 'MULT0'))
        attr_vals.append(AttrVal('ALU', 'ENABLE'))
        attr_vals.append(AttrVal('UNK_CLK_191', 'CLK0')) # XXX find out whose clock this is

        if "USE_CASCADE_OUT" in cell_attrs:
            attr_vals.append(AttrVal('CASO', 'ENABLE'))

        for parm in [('OREG_CLK', 'BYPASS'), ('OREG_CE', 'CE0'), ('OREG_RESET', 'RESET0')]:
            attr, default = parm
            attr_vals.append(AttrVal(f'{attr[0]}0{attr[1:]}', cell_parms.get(attr, default)))
            attr_vals.append(AttrVal(f'{attr[0]}1{attr[1:]}', cell_parms.get(attr, default)))

        attr = 'DYN_CASI_SEL'
        val = cell_parms.get(attr, 'FALSE')
        attr_vals.append(AttrVal(attr, val))
        if val == 'TRUE':
            # XXX It seems that this input requires inversion.
            attr_vals.append(AttrVal('CASISEL_PAD', 'INV'))

        for parm in [('PREG0_CLK', 'BYPASS'), ('PREG0_CE', 'CE0'), ('PREG0_RESET', 'RESET0'),
                     ('PREG1_CLK', 'BYPASS'), ('PREG1_CE', 'CE0'), ('PREG1_RESET', 'RESET0')]:
            attr, default = parm
            attr_vals.append(AttrVal(f'P{attr[4]}REG{attr[5:]}', cell_parms.get(attr, default)))

        for parm in [('ACCSEL_IREG_CLK', 'BYPASS'), ('ACCSEL_IREG_CE', 'CE0'), ('ACCSEL_IREG_RESET', 'RESET0'),
                     ('ACCSEL_PREG_CLK', 'BYPASS'), ('ACCSEL_PREG_CE', 'CE0'), ('ACCSEL_PREG_RESET', 'RESET0')]:
            attr, default = parm
            val = cell_parms.get(attr, default)
            attr_vals.append(AttrVal(f'ACCSEL_0{attr[6:]}', val))
            attr_vals.append(AttrVal(f'ACCSEL_1{attr[6:]}', val))

        attr = 'PRE_LOAD'
        val = cell_parms.get(attr, 0)
        pre_load = str(val)
        if len(pre_load) > 58:
            pre_load = pre_load[-48:]
        else:
            pre_load = pre_load.rjust(48, '0')
        for bitnum, pre_loadbit in enumerate(pre_load[::-1]):
            attr_vals.append(AttrVal(f'PRELOAD_BIT_{bitnum}', pre_loadbit))

        for parm in self.multaddalu12x12_defaults:
            attr, default = parm
            attr_vals.append(AttrVal(attr, cell_parms.get(attr, default)))

        return attr_vals

    def set_multalu27x18_attrvals(self, bel: BelDesc, dsp_indices: DspIndices) -> list[AttrVal]:
        """ 27x18 """
        attr_vals = []
        cell_parms = bel.cell.parms
        cell_attrs = bel.cell.attrs

        pair_idx = dsp_indices.pair_idx
        idx = dsp_indices.idx
        is_even = dsp_indices.is_even

        # The working theory is that the second multiplier needs to be shifted to the left by 24 bits, and perhaps this pair determines that.
        attr_vals.append(AttrVal('UNK_192', 'UNK_23')) # see mult12x12
        attr_vals.append(AttrVal('CE0_MUX', 'CE0_IN'))
        attr_vals.append(AttrVal('CE1_MUX', 'CE1_IN'))
        attr_vals.append(AttrVal('ALU_OP0_MUX', 'MULT0'))
        attr_vals.append(AttrVal('ALU', 'ENABLE'))
        attr_vals.append(AttrVal('UNK_CLK_191', 'CLK0')) # XXX find out whose clock this is

        if "MULT27X36_MAIN" in cell_attrs:
            attr_vals.append(AttrVal('MULT27X36', 'ENABLE'))
        elif "MULT27X36_AUX" in cell_attrs:
            attr_vals.append(AttrVal('CASI_SEL', 1))
        else:
            attr = 'CASI_SEL'
            val = int(cell_parms.get(attr, '0'), 2)
            attr_vals.append(AttrVal(attr, val))

        if "USE_CASCADE_OUT" in cell_attrs:
            attr_vals.append(AttrVal('CASO', 'ENABLE'))

        for parm in [('OREG_CLK', 'BYPASS'), ('OREG_CE', 'CE0'), ('OREG_RESET', 'RESET0')]:
            attr, default = parm
            attr_vals.append(AttrVal(f'{attr[0]}0{attr[1:]}', cell_parms.get(attr, default)))
            attr_vals.append(AttrVal(f'{attr[0]}1{attr[1:]}', cell_parms.get(attr, default)))

        attr = 'DYN_CASI_SEL'
        val = cell_parms.get(attr, 'FALSE')
        attr_vals.append(AttrVal(attr, val))
        if val == 'TRUE':
            # XXX It seems that this input requires inversion.
            attr_vals.append(AttrVal('CASISEL_PAD', 'INV'))

        for parm in ['AREG_CLK', 'BREG_CLK']:
            val = cell_parms.get(parm, 'BYPASS')
            attr_vals.append(AttrVal(f'{parm[0]}{idx}{parm[1:]}', val))

        for parm in ['AREG_CE', 'BREG_CE']:
            val = cell_parms.get(parm, 'CE0')
            attr_vals.append(AttrVal(f'{parm[0]}{idx}{parm[1:]}', val))

        for parm in ['AREG_RESET', 'BREG_RESET']:
            val = cell_parms.get(parm, 'RESET0')
            attr_vals.append(AttrVal(f'{parm[0]}{idx}{parm[1:]}', val))

        for parm in [('DREG_CLK', 'BYPASS'), ('DREG_CE', 'CE0'), ('DREG_RESET', 'RESET0')]:
            attr, default = parm
            attr_vals.append(AttrVal(f'A1{attr[1:]}', cell_parms.get(attr, default)))
            attr_vals.append(AttrVal(f'B1{attr[1:]}', cell_parms.get(attr, default)))

        for parm in [('PREG_CLK', 'BYPASS'), ('PREG_CE', 'CE0'), ('PREG_RESET', 'RESET0')]:
            attr, default = parm
            attr_vals.append(AttrVal(f'P0{attr[1:]}', cell_parms.get(attr, default)))

        for parm in [('ACCSEL_IREG_CLK', 'BYPASS'), ('ACCSEL_IREG_CE', 'CE0'), ('ACCSEL_IREG_RESET', 'RESET0'),
                     ('ACCSEL_PREG_CLK', 'BYPASS'), ('ACCSEL_PREG_CE', 'CE0'), ('ACCSEL_PREG_RESET', 'RESET0')]:
            attr, default = parm
            val = cell_parms.get(attr, default)
            attr_vals.append(AttrVal(f'ACCSEL_0{attr[6:]}', val))
            attr_vals.append(AttrVal(f'ACCSEL_1{attr[6:]}', val))

        attr = 'PRE_LOAD'
        val = cell_parms.get(attr, 0)
        pre_load = str(val)
        if len(pre_load) > 58:
            pre_load = pre_load[-48:]
        else:
            pre_load = pre_load.rjust(48, '0')
        for bitnum, pre_loadbit in enumerate(pre_load[::-1]):
            attr_vals.append(AttrVal(f'PRELOAD_BIT_{bitnum}', pre_loadbit))

        for parm in self.multalu27x18_defaults:
            attr, default = parm
            attr_vals.append(AttrVal(attr, cell_parms.get(attr, default)))

        return attr_vals


    def get_MULT12X12_fuses(self, bel: BelDesc) -> list[CellFuseBits]:
        """ 12x12 """
        dsp_indices = self.decode_dsp_indices(bel)
        attr_vals = self.set_mult12x12_attrvals(bel, dsp_indices)

        return self.common_dsp_handler(bel, attr_vals)

    def get_MULTADDALU12X12_fuses(self, bel: BelDesc) -> list[CellFuseBits]:
        """ 12x12 """
        dsp_indices = self.decode_dsp_indices(bel)
        attr_vals = self.set_multaddalu12x12_attrvals(bel, dsp_indices)

        return self.common_dsp_handler(bel, attr_vals)

    def get_MULTALU27X18_fuses(self, bel: BelDesc) -> list[CellFuseBits]:
        """ 27x18 and 27x36 """
        dsp_indices = self.decode_dsp_indices(bel)
        attr_vals = self.set_multalu27x18_attrvals(bel, dsp_indices)

        return self.common_dsp_handler(bel, attr_vals)


    # debug
    def __repr__(self):
        return super().__repr__() + ""

################################################################
class GW5AT_60B(GW5A):
    """ GW5AT-60B chip. TangCosole60k board """
    def __init__(self, cli_args: CliArgs, pnr: Netlist):
        super().__init__(cli_args, pnr)
        self.default_ibuf_attrs = [('PADDI', 'PADDI'), ('HYSTERESIS', 'NONE'), ('PULLMODE', 'UP'), ('SLEWRATE', 'SLOW'),
                 ('DRIVE', '0'), ('CLAMP', 'OFF'), ('OPENDRAIN', 'OFF'), ('DIFFRESISTOR', 'OFF'),
                 ('VREF', 'OFF'), ('LVDS_OUT', 'OFF'), ('PULL_STRENGTH', 'MEDIUM')]
        self.default_obuf_attrs = [('ODMUX_1', '1'), ('PULLMODE', 'UP'), ('SLEWRATE', 'SLOW'),
                 ('DRIVE', '8'), ('HYSTERESIS', 'NONE'), ('CLAMP', 'OFF'),
                 ('SINGLERESISTOR', 'OFF'), ('LVDS_OUT', 'OFF'), ('DDR_DYNTERM', 'NA'),
                 ('TO', 'INV'), ('OPENDRAIN', 'OFF'), ('PULL_STRENGTH', 'MEDIUM'), ('IOB_UNKNOWN51', 'TRIMUX')]
        self.default_tbuf_attrs = [('ODMUX_1', 'UNKNOWN'), ('PULLMODE', 'UP'), ('SLEWRATE', 'SLOW'),
                 ('DRIVE', '8'), ('HYSTERESIS', 'NONE'), ('CLAMP', 'OFF'),
                 ('SINGLERESISTOR', 'OFF'), ('LVDS_OUT', 'OFF'), ('DDR_DYNTERM', 'NA'),
                 ('TO', 'INV'), ('PERSISTENT', 'OFF'), ('ODMUX', 'TRIMUX'), ('OPENDRAIN', 'OFF'),
                 ('PULL_STRENGTH', 'MEDIUM'), ('IOB_UNKNOWN51', 'TRIMUX')]
        self.default_iobuf_attrs = [('PULLMODE', 'UP'), ('SLEWRATE', 'SLOW'),
                 ('DRIVE', '8'), ('HYSTERESIS', 'NONE'), ('CLAMP', 'OFF'), ('DIFFRESISTOR', 'OFF'),
                 ('SINGLERESISTOR', 'OFF'), ('LVDS_OUT', 'OFF'), ('DDR_DYNTERM', 'NA'),
                 ('PERSISTENT', 'OFF'), ('ODMUX', 'TRIMUX'), ('PADDI', 'PADDI'), ('OPENDRAIN', 'OFF'),
                 ('PULL_STRENGTH', 'MEDIUM'), ('IOB_UNKNOWN51', 'TRIMUX')]
        self.default_tlvds_tbuf_attrs = [('ODMUX_1', 'UNKNOWN'), ('PULLMODE', 'NONE'), ('SLEWRATE', 'SLOW'),
                 ('DRIVE', '0'), ('HYSTERESIS', 'NA'), ('CLAMP', 'OFF'), ('DIFFRESISTOR', 'OFF'),
                 ('SINGLERESISTOR', 'OFF'), ('DDR_DYNTERM', 'NA'),
                 ('TO', 'INV'), ('PERSISTENT', 'OFF'), ('ODMUX', 'TRIMUX'),
                 ('OPENDRAIN', 'OFF'), ('PULL_STRENGTH', 'MEDIUM'), ('IOB_UNKNOWN51', 'TRIMUX')]
        self.default_tlvds_obuf_attrs = [('ODMUX_1', 'UNKNOWN'), ('PULLMODE', 'NONE'), ('SLEWRATE', 'SLOW'),
                 ('DRIVE', '0'), ('HYSTERESIS', 'NA'), ('CLAMP', 'OFF'), ('DIFFRESISTOR', 'OFF'),
                 ('SINGLERESISTOR', 'OFF'), ('DDR_DYNTERM', 'NA'),
                 ('TO', 'INV'), ('PERSISTENT', 'OFF'), ('ODMUX', 'TRIMUX'),
                 ('OPENDRAIN', 'OFF'), ('PULL_STRENGTH', 'MEDIUM'), ('IOB_UNKNOWN51', 'TRIMUX')]
        self.default_tlvds_iobuf_attrs = [('PULLMODE', 'NONE'), ('SLEWRATE', 'SLOW'),
                 ('DRIVE', '0'), ('HYSTERESIS', 'NA'), ('CLAMP', 'OFF'), ('DIFFRESISTOR', 'OFF'),
                 ('SINGLERESISTOR', 'OFF'), ('DDR_DYNTERM', 'NA'),
                 ('PERSISTENT', 'OFF'), ('ODMUX', 'TRIMUX'), ('PADDI', 'PADDI'),
                 ('OPENDRAIN', 'OFF'), ('PULL_STRENGTH', 'MEDIUM'), ('IOB_UNKNOWN51', 'TRIMUX')]

    def get_tilemap_func(self):
        # for speed fill closure variables
        empty_x = self.chipdb.empty_x
        empty_y = self.chipdb.empty_y
        last_col = self.chipdb.cols - 1
        last_row = self.chipdb.rows - 1

        def calc_size_func(y:int, x:int) -> tuple[int, int, bool]:
            """ We have one large empty square and one column that don't fit
            into a normal grid. Here, we create empty cells of appropriate
            sizes on the fly. """

            td = self.chipdb.get_tiledata(x, y)
            # first - normal cells
            if td.width and td.height:
                return td.width, td.height, True
            if x == empty_x or x == empty_x - 1:
                h = self.chipdb.get_tiledata(last_col, y).height
                return 0, h, False
            # first row of the empty square doesn't need corrections
            if y == 0:
                return 0, 0, False
            # other rows do not have a height
            w = self.chipdb.get_tiledata(x, last_row).width
            h = 0
            return w, 0, False

        return calc_size_func

    def create_main_tilemap(self) -> dict:
        """ Return chip tilemap """
        return self.chipdb.create_main_tilemap_holes(calc_size_func = self.get_tilemap_func())

    def fuse_bitmap(self, tilemap) -> dict:
        """ Tilemap -> Bitmap """
        return self.chipdb.fuse_bitmap_holes(tilemap, calc_size_func = self.get_tilemap_func())


    #==============================
    #========== Misc
    #==============================
    def get_BUFG_fuses(self, bel: BelDesc) -> list[CellFuseBits]:
        """ Logic -> clock gate """
        return []

    def get_pins_attr_vals(self) -> list[AttrVal]:
        attrvals = []
        if self.cli_args.args.jtag_as_gpio:
            attrvals.append(AttrVal('JTAG_AS_GPIO', 'YES'))
        attrvals.append(AttrVal('SSPI_AS_GPIO', 'YES'))
        if self.cli_args.args.mspi_as_gpio:
            attrvals.append(AttrVal('MSPI_AS_GPIO', 'YES'))
        if self.cli_args.args.ready_as_gpio:
            attrvals.append(AttrVal('READY_AS_GPIO', 'YES'))
        if self.cli_args.args.done_as_gpio:
            attrvals.append(AttrVal('DONE_AS_GPIO', 'YES'))
        if self.cli_args.args.reconfign_as_gpio:
            attrvals.append(AttrVal('RECONFIG_AS_GPIO', 'YES'))
        if self.cli_args.args.i2c_as_gpio:
            attrvals.append(AttrVal('I2C_AS_GPIO', 'YES'))
        if self.cli_args.args.cpu_as_gpio:
            attrvals.append(AttrVal('CPU_AS_GPIO_25', 'YES'))
        # XXX
        # add CPU + MSSPI pin usage - IOR5A
        return attrvals

    def get_gsr_types(self) -> set[str]:
        return [49]

    def get_cfg_types(self) -> set[str]:
        return [48, 49]

    def get_work_in_progress_fuses(self) -> list[CellFuseBits]:
        """ Setting bits whose purpose is unclear or roughly clear, but the
        mechanism hasn't been fully developed. For example, if a chip doesn't
        yet support segment wires in nextpnr, the ends of segments still need
        to be insulated. """

        # 5 full segment spines
        def full_spines() -> Iterator[WireDesc]:
            for x, y in itertools.product(range(self.chipdb.cols), [37, 46, 55, 64]):
                if x != self.chipdb.empty_x:
                    yield WireDesc(x, y, 'LT00')
                    yield WireDesc(x, y, 'LT10')

            for x in range(self.chipdb.cols):
                if x != self.chipdb.empty_x:
                    yield WireDesc(x, 73, 'LT13')
                    yield WireDesc(x, 73, 'LT02')

        # half-spines
        def half_spines() -> Iterator[WireDesc]:
            for x in range(self.chipdb.empty_x):
                yield WireDesc(x, 28, 'LT13')
                yield WireDesc(x, 28, 'LT02')

            for x in range(self.chipdb.empty_x, self.chipdb.cols):
                yield WireDesc(x, 0, 'LT13')
                yield WireDesc(x, 0, 'LT02')

            for x, y in itertools.product(range(self.chipdb.empty_x, self.chipdb.cols), [27, 18, 9]):
                yield WireDesc(x, y, 'LT00')
                yield WireDesc(x, y, 'LT10')

        fuses = self.get_isolated_wire_fuses(itertools.chain(full_spines(), half_spines()))
        return fuses

    # debug
    def __repr__(self):
        return super().__repr__() + ""

################################################################
class GW5AST_138C(GW5A):
    """ GW5AST-138C chip. Tangmega138k board """
    def __init__(self, cli_args: CliArgs, pnr: Netlist):
        super().__init__(cli_args, pnr)
        self.used_clock_spines = set()
        # find the clock bridge tiles
        self.clock_bridge_ttypes = range(80, 86)
        self.clock_bridge_xy = set()
        for x, y in itertools.product(range(self.chipdb.cols), range(self.chipdb.rows)):
            if self.chipdb.get_ttyp(x, y) in self.clock_bridge_ttypes:
                self.clock_bridge_xy.add((x, y))

    #==============================
    #========== Pips
    #==============================
    def get_set_spine_enable_table(self, area: str, dest: str) -> str:
        if not dest.startswith('SPINE') or (area, dest) in self.used_clock_spines:
            return None
        self.used_clock_spines.add((area, dest))
        return f'5A_PCLK_ENABLE_{wnames.clknumbers[dest]:02}'

    def get_spine_enable_fuses(self, x: int, y: int, spine_enable_table: str) -> set[Coord]:
        return self.chipdb.get_spine_enable_fuses(x, y, spine_enable_table)

    def is_clock_pip(self, tiledata: Tile, src: str, dest: str) -> bool:
        if src[8:].startswith('_BOT') or src[8:].startswith('_TOP'):
            return True
        if src not in wnames.clknumbers:
            return False
        if dest not in wnames.clknumbers:
            return False
        return wnames.clknumbers[src] < wnames.clknumbers['UNK269'] \
               or wnames.clknumbers[src] >= wnames.clknumbers['UNK309']

    def get_clock_pip_fuses(self, tiledata: Tile, x: int, y: int, src: str, dest: str) -> list[CellFuseBits]:
        """ The mux for clock wires can be "spread" across several cells. """
        fuses = []
        # SPINE->{GT00, GT10} must be set in the cell only
        if dest in {'GT00', 'GT10'}:
            bits = self.get_simple_clock_pip_fuses(tiledata, src, dest)
            if bits:
                fuses.append(CellFuseBits(x, y, bits))
            return fuses

        # we need to separate top and bottom halves of the 138k clocks
        # area - top, bottom or clock bridge - 'T', 'B', 'C'
        mid_y = 55
        if (x, y) in self.clock_bridge_xy:
            area = 'C'
            area_it = self.clock_bridge_xy
        elif y < 55:
            area = 'T'
            area_it = itertools.product(range(self.chipdb.cols), range(mid_y))
        else:
            area = 'B'
            area_it = itertools.product(range(self.chipdb.cols), range(mid_y, self.chipdb.rows))

        # need to enable spine?
        spine_enable_table = self.get_set_spine_enable_table(area, dest)

        for x, y in area_it:
            # clock bridge is located in top
            if area == 'T' and (x, y) in self.clock_bridge_xy:
                continue
            tiledata = self.chipdb.get_tiledata(x, y)
            bits = self.get_simple_clock_pip_fuses(tiledata, src, dest)
            if spine_enable_table:
                bits |= self.get_spine_enable_fuses(x, y, spine_enable_table)
            if bits:
                fuses.append(CellFuseBits(x, y, bits))
        return fuses

    #==============================
    #========== Misc
    #==============================
    def get_BUFG_fuses(self, bel: BelDesc) -> list[CellFuseBits]:
        """ Logic -> clock gate """
        return []

    def get_gsr_types(self) -> set[str]:
        return [220]

    def get_cfg_types(self) -> set[str]:
        return [220]

    def get_pins_attr_vals(self) -> list[AttrVal]:
        attrvals = []
        if self.cli_args.args.jtag_as_gpio:
            attrvals.append(AttrVal('JTAG_AS_GPIO', 'YES'))
        if self.cli_args.args.mspi_as_gpio:
            attrvals.append(AttrVal('MSPI_AS_GPIO', 'YES'))
        if self.cli_args.args.ready_as_gpio:
            attrvals.append(AttrVal('READY_AS_GPIO', 'YES'))
        if self.cli_args.args.done_as_gpio:
            attrvals.append(AttrVal('DONE_AS_GPIO', 'YES'))
        if self.cli_args.args.reconfign_as_gpio:
            attrvals.append(AttrVal('RECONFIG_AS_GPIO', 'YES'))
        if self.cli_args.args.i2c_as_gpio:
            attrvals.append(AttrVal('I2C_AS_GPIO', 'YES'))
        if self.cli_args.args.cpu_as_gpio:
            attrvals.append(AttrVal('CPU_AS_GPIO_0', 'YES'))
            attrvals.append(AttrVal('CPU_AS_GPIO_1', 'YES'))
        # XXX
        # add CPU + MSSPI pin usage - IOB175B
        return attrvals

    #==============================
    #========== IO
    #==============================
    def get_default_io_type(self) -> str:
        """ Default IO_TYPE """
        return "LVCMOS33"

    # debug
    def __repr__(self):
        return super().__repr__()  + f"| clock_bridge_ttypes:{self.clock_bridge_ttypes}, clock_bridge_xy:{self.clock_bridge_xy} "

################################################################
class Bitstream:
    """ Output bitstream. Base class """
    def __init__(self, cli_args: CliArgs, device: Device):
        self.output_name = cli_args.get_output_filename()
        self.compress = cli_args.get_compress()
        self.multiboot_addr = cli_args.get_multiboot_addr()
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

    def set_multiboot_address(self):
        for command in self.header:
            if command[0] == 0xd2:
                command[4:8] = self.multiboot_addr.to_bytes(4, 'big')
                return
        raise ValueError('Bitstream header does not contain a multiboot address command')

    def fill_header_footer(self, bs):
        raise Exception("fill_header_footer is not implemented.")

    def write_without_bsram(self, main_map):
        raise Exception("write_without_bsram is not implemented.")

    def write_with_bsram(self, main_map):
        raise Exception("write_with_bsram is not implemented.")

    def write(self):
        raise Exception("write is not implemented.")

    # debug
    def __repr__(self):
        return f'|Bitstream| output_name:{self.output_name}, compress:{self.compress}, init_bsram:{self.init_bsram}, header:{self.header}, footer:{self.footer}'

################################################################
class Bitstream_GW1_2(Bitstream):
    """ Output bitstream for GW1N and GW2A series """
    def __init__(self, cli_args: CliArgs, device: Device):
        super().__init__(cli_args, device)

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
        # set SPI address
        self.set_multiboot_address()

    def write_without_bsram(self, main_map):
        bslib.write_bitstream(self.output_name, main_map, self.header, self.footer, self.compress, extra_slots = {})

    def write_with_bsram(self, main_map):
        bsram_init_map = self.device.get_bsram_init_map()
        bslib.write_bitstream_with_bsram_init(self.output_name, main_map, self.header, self.footer, self.compress, extra_slots = {}, bsram_init = bsram_init_map)

    def write(self):
        """ Write bitsream to file """
        main_map = self.device.fuse_bitmap(self.main_tilemap)
        self.fill_header_footer(main_map)

        if self.device.has_bsram_init_data():
            self.write_with_bsram(main_map)
        else:
            self.write_without_bsram(main_map)

    # debug
    def __repr__(self):
        return f'|Bitstream_GW1_2| output_name:{self.output_name}, compress:{self.compress}, init_bsram:{self.init_bsram}, header:{self.header}, footer:{self.footer}'

################################################################
class Bitstream_GW5A(Bitstream):
    """ Output bitstream for GW5A. Base class """
    def __init__(self, cli_args: CliArgs, device: Device):
        super().__init__(cli_args, device)

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
        self.footer.insert(1, bytearray(b'\x68\x00\x00\x00\x00\x00\x00\x00'))
        # set SPI address
        self.set_multiboot_address()

    def write_without_bsram(self, main_map):
        extra_slots = self.device.get_extra_slots()
        bslib.write_bitstream(self.output_name, main_map, self.header, self.footer, self.compress, extra_slots)

    def write_with_bsram(self, main_map):
        error_not_implemented_method('write_with_bsram')

    def write(self):
        """ Write bitsream to file """
        main_map = self.device.fuse_bitmap(self.main_tilemap)
        main_map = bitmatrix.transpose(main_map)

        self.fill_header_footer(main_map)

        if self.device.has_bsram_init_data():
            self.write_with_bsram(main_map)
        else:
            self.write_without_bsram(main_map)

    # debug
    def __repr__(self):
        return f'|Bitstream_GW5A| output_name:{self.output_name}, compress:{self.compress}, init_bsram:{self.init_bsram}, header:{self.header}, footer:{self.footer}'

################################################################
class Bitstream_GW5A_25A(Bitstream_GW5A):
    """ Output bitstream for GW5A-25A """
    def __init__(self, cli_args: CliArgs, device: Device):
        super().__init__(cli_args, device)

    def write_with_bsram(self, main_map):
        extra_slots = self.device.get_extra_slots()
        bsram_init_map = bitmatrix.transpose(self.device.get_bsram_init_map())
        bslib.write_bitstream(self.output_name, main_map, self.header, self.footer, self.compress, extra_slots, bsram_init_map, self.device.get_bsram_cols_iterator(), is_gw5a_138 = False)

    # debug
    def __repr__(self):
        return f'|Bitstream_GW5A_25A| output_name:{self.output_name}, compress:{self.compress}, init_bsram:{self.init_bsram}, header:{self.header}, footer:{self.footer}'

################################################################
class Bitstream_GW5AT_60B(Bitstream_GW5A):
    """ Output bitstream for GW5AT-60B """
    def __init__(self, cli_args: CliArgs, device: Device):
        super().__init__(cli_args, device)

    def write_with_bsram(self, main_map):
        extra_slots = self.device.get_extra_slots()
        bsram_init_map = bitmatrix.transpose(self.device.get_bsram_init_map())
        bslib.write_bitstream(self.output_name, main_map, self.header, self.footer, self.compress, extra_slots, bsram_init_map, self.device.get_bsram_cols_iterator(), is_gw5a_138 = False)

    # debug
    def __repr__(self):
        return f'|Bitstream_GW5AT_60B| output_name:{self.output_name}, compress:{self.compress}, init_bsram:{self.init_bsram}, header:{self.header}, footer:{self.footer}'

################################################################
class Bitstream_GW5AST_138C(Bitstream_GW5A):
    """ Output bitstream for GW5AST-138C """
    def __init__(self, cli_args: CliArgs, device: Device):
        super().__init__(cli_args, device)

    def write_with_bsram(self, main_map):
        extra_slots = self.device.get_extra_slots()
        bsram_init_map = bitmatrix.transpose(self.device.get_bsram_init_map())
        bslib.write_bitstream(self.output_name, main_map, self.header, self.footer, self.compress, extra_slots, bsram_init_map, self.device.get_bsram_cols_iterator(), is_gw5a_138 = True)

    # debug
    def __repr__(self):
        return f'|Bitstream_GW5AST_138C| output_name:{self.output_name}, compress:{self.compress}, init_bsram:{self.init_bsram}, header:{self.header}, footer:{self.footer}'

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
        self.fuses += self.device.get_isolated_wire_fuses(self.pnr.get_wires_to_isolate())

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
        return f'|Pack| device:{self.device}, pnr:{self.pnr}'

################################################################
def create_device(cli_args: CliArgs, pnr: Netlist) -> Device:
    dev = cli_args.get_device()
    if dev == 'GW1N-1':
        return GW1N_1(cli_args, pnr)
    if dev == 'GW1NZ-1':
        return GW1NZ_1(cli_args, pnr)
    if dev == 'GW1N-4':
        return GW1N_4(cli_args, pnr)
    if dev == 'GW1NS-4':
        return GW1NS_4(cli_args, pnr)
    if dev == 'GW1N-9':
        return GW1N_9(cli_args, pnr)
    if dev == 'GW1N-9C':
        return GW1N_9C(cli_args, pnr)
    if dev == 'GW2A-18':
        return GW2A_18(cli_args, pnr)
    if dev == 'GW2A-18C':
        return GW2A_18C(cli_args, pnr)
    # --- GW5A series
    if dev == 'GW5A-25A':
        return GW5A_25A(cli_args, pnr)
    if dev == 'GW5AT-60B':
        return GW5AT_60B(cli_args, pnr)
    if dev == 'GW5AST-138C':
        return GW5AST_138C(cli_args, pnr)
    else:
        raise Exception(f"Unknown device {dev}")

def create_output_bitstream(cli_args: CliArgs, device: Device) -> Bitstream:
    dev = cli_args.get_device()
    if dev in {'GW1N-1', 'GW1NZ-1', 'GW1N-4', 'GW1NS-4', 'GW1N-9', 'GW1N-9C', 'GW2A-18', 'GW2A-18C'}:
        return Bitstream_GW1_2(cli_args, device)
    elif dev in {'GW5A-25A'}:
        return Bitstream_GW5A_25A(cli_args, device)
    elif dev in {'GW5AT-60B'}:
        return Bitstream_GW5AT_60B(cli_args, device)
    elif dev in {'GW5AST-138C'}:
        return Bitstream_GW5AST_138C(cli_args, device)
    else:
        raise Exception(f"Unknown device {dev}")

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
    output.write()

if __name__ == '__main__':
    main()

# vim: set et sw=4 ts=4:
