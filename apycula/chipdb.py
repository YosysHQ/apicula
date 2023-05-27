from dataclasses import dataclass, field
from typing import Dict, List, Set, Tuple, Union, ByteString
from itertools import chain
import re
from functools import reduce
from collections import namedtuple
import numpy as np
import apycula.fuse_h4x as fuse
from apycula.wirenames import wirenames, clknames
from apycula import pindef

# the character that marks the I/O attributes that come from the nextpnr
mode_attr_sep = '&'

# represents a row, column coordinate
# can be either tiles or bits within tiles
Coord = Tuple[int, int]

@dataclass
class Bel:
    """Respresents a Basic ELement
    with the specified modes mapped to bits
    and the specified portmap"""
    # there can be zero or more flags
    flags: Dict[Union[int, str], Set[Coord]] = field(default_factory=dict)
    # this Bel is IOBUF and needs routing to become IBUF or OBUF
    simplified_iob: bool = field(default = False)
    # differential signal capabilities info
    is_diff:      bool = field(default = False)
    is_true_lvds: bool = field(default = False)
    is_diff_p:    bool = field(default = False)
    # there can be only one mode, modes are exclusive
    modes: Dict[Union[int, str], Set[Coord]] = field(default_factory=dict)
    portmap: Dict[str, str] = field(default_factory=dict)

    @property
    def mode_bits(self):
        return set().union(*self.modes.values())

@dataclass
class Tile:
    """Represents all the configurable features
    for this specific tile type"""
    width: int
    height: int
    # At the time of packing/unpacking the information about the types of cells
    # is already lost, it is critical to work through the 'logicinfo' table so
    # store it.
    ttyp: int
    # a mapping from dest, source wire to bit coordinates
    pips: Dict[str, Dict[str, Set[Coord]]] = field(default_factory=dict)
    clock_pips: Dict[str, Dict[str, Set[Coord]]] = field(default_factory=dict)
    # fuses to disable the long wire columns. This is the table 'alonenode[6]' in the vendor file
    # {dst: ({src}, {bits})}
    alonenode_6: Dict[str, Tuple[Set[str], Set[Coord]]] = field(default_factory=dict)
    # always-connected dest, src aliases
    aliases: Dict[str, str] = field(default_factory=dict)
    # a mapping from bel type to bel
    bels: Dict[str, Bel] = field(default_factory=dict)

@dataclass
class Device:
    # a grid of tiles
    grid: List[List[Tile]] = field(default_factory=list)
    timing: Dict[str, Dict[str, List[float]]] = field(default_factory=dict)
    packages: Dict[str, Tuple[str, str, str]] = field(default_factory=dict)
    # {variant: {package: {pin#: (pin_name, [cfgs])}}}
    pinout: Dict[str, Dict[str, Dict[str, Tuple[str, List[str]]]]] = field(default_factory=dict)
    pin_bank: Dict[str, int] = field(default_factory = dict)
    cmd_hdr: List[ByteString] = field(default_factory=list)
    cmd_ftr: List[ByteString] = field(default_factory=list)
    template: np.ndarray = None
    # allowable values of bel attributes
    # {table_name: [(attr_id, attr_value)]}
    logicinfo: Dict[str, List[Tuple[int, int]]] = field(default_factory=dict)
    # fuses for a pair of the "features" (or pairs of parameter values)
    # {ttype: {table_name: {(feature_A, feature_B): {bits}}}
    shortval: Dict[int, Dict[str, Dict[Tuple[int, int], Set[Coord]]]] = field(default_factory=dict)
    # fuses for 16 of the "features"
    # {ttype: {table_name: {(feature_0, feature_1, ..., feature_15): {bits}}}
    longval: Dict[int, Dict[str, Dict[Tuple[int, int, int, int, int, int, int, int, int, int, int, int, int, int, int, int], Set[Coord]]]] = field(default_factory=dict)
    # always-connected dest, src aliases
    aliases: Dict[Tuple[int, int, str], Tuple[int, int, str]] = field(default_factory=dict)

    @property
    def rows(self):
        return len(self.grid)

    @property
    def cols(self):
        return len(self.grid[0])

    @property
    def height(self):
        return sum(row[0].height for row in self.grid)

    @property
    def width(self):
        return sum(tile.width for tile in self.grid[0])

    # XXX consider removing
    @property
    def corners(self):
        # { (row, col) : bank# }
        return {
            (0, 0) : '0',
            (0, self.cols - 1) : '1',
            (self.rows - 1, self.cols - 1) : '2',
            (self.rows - 1, 0) : '3'}

    # Some chips have bits responsible for different banks in the same corner tile.
    # Here stores the correspondence of the bank number to the (row, col) of the tile.
    @property
    def bank_tiles(self):
        # { bank# : (row, col) }
        res = {}
        for pos in self.corners.keys():
            row, col = pos
            for bel in self.grid[row][col].bels.keys():
                if bel[0:4] == 'BANK':
                    res.update({ bel[4:] : pos })
        return res

def unpad(fuses, pad=-1):
    try:
        return fuses[:fuses.index(pad)]
    except ValueError:
        return fuses

def fse_pips(fse, ttyp, table=2, wn=wirenames):
    pips = {}
    if table in fse[ttyp]['wire']:
        for srcid, destid, *fuses in fse[ttyp]['wire'][table]:
            fuses = {fuse.fuse_lookup(fse, ttyp, f) for f in unpad(fuses)}
            if srcid < 0:
                fuses = set()
                srcid = -srcid
            src = wn.get(srcid, str(srcid))
            dest = wn.get(destid, str(destid))
            pips.setdefault(dest, {})[src] = fuses

    return pips

_supported_hclk_wires = {'SPINE2', 'SPINE3', 'SPINE4', 'SPINE5', 'SPINE10', 'SPINE11',
                         'SPINE12', 'SPINE13', 'SPINE16', 'SPINE17', 'SPINE18', 'SPINE19',
                         'VSS', 'VCC', 'PCLKT0', 'PCLKT1', 'PCLKB0', 'PCLKB1',
                         'PCLKL0', 'PCLKL1','PCLKR0', 'PCLKR1',
                         'TBDHCLK0', 'TBDHCLK1', 'TBDHCLK2', 'TBDHCLK3', 'BBDHCLK0',
                         'BBDHCLK1', 'BBDHCLK2', 'BBDHCLK3', 'LBDHCLK0', 'LBDHCLK1',
                         'LBDHCLK2', 'LBDHCLK3', 'RBDHCLK0', 'RBDHCLK1', 'RBDHCLK2',
                         'RBDHCLK3',
                         }
# Some chips at least -9C treat these wires as the same
_xxx_hclk_wires = {'SPINE16': 'SPINE2', 'SPINE18': 'SPINE4'}
def fse_hclk_pips(fse, ttyp, aliases):
    pips = fse_pips(fse, ttyp, table = 48, wn = clknames)
    res = {}
    for dest, src_fuses in pips.items():
        if dest not in _supported_hclk_wires:
            continue
        for src, fuses in src_fuses.items():
            if src in _supported_hclk_wires:
                res.setdefault(dest, {})[src] = fuses
                if src in _xxx_hclk_wires.keys():
                    aliases.update({src: _xxx_hclk_wires[src]})
    return res

def fse_alonenode(fse, ttyp, table = 6):
    pips = {}
    if 'alonenode' in fse[ttyp].keys():
        if table in fse[ttyp]['alonenode']:
            for destid, *tail in fse[ttyp]['alonenode'][table]:
                fuses = {fuse.fuse_lookup(fse, ttyp, f) for f in unpad(tail[-2:])}
                srcs = {wirenames.get(srcid, str(srcid)) for srcid in unpad(tail[:-2])}
                dest = wirenames.get(destid, str(destid))
                pips[dest] = (srcs, fuses)
    return pips

# make PLL bels
def fse_pll(device, fse, ttyp):
    bels = {}
    if device in {'GW1N-1', 'GW1NZ-1'}:
        if ttyp == 88:
            bel = bels.setdefault('RPLLA', Bel())
        elif ttyp == 89:
            bel = bels.setdefault('RPLLB', Bel())
    elif device in {'GW1NS-2'}:
        if ttyp in {87}:
            bel = bels.setdefault('RPLLA', Bel())
    elif device in {'GW1NS-4'}:
        if ttyp in {88, 89}:
            bel = bels.setdefault('PLLVR', Bel())
    elif device == 'GW1N-4':
        if ttyp in {74, 77}:
            bel = bels.setdefault('RPLLA', Bel())
        elif ttyp in {75, 78}:
            bel = bels.setdefault('RPLLB', Bel())
    elif device in {'GW1N-9C', 'GW1N-9'}:
        if ttyp in {86, 87}:
            bel = bels.setdefault('RPLLA', Bel())
        elif ttyp in {74, 75, 76, 77, 78, 79}:
            bel = bels.setdefault('RPLLB', Bel())
    return bels

# add the ALU mode
# new_mode_bits: string like "0110000010011010"
def add_alu_mode(base_mode, modes, lut, new_alu_mode, new_mode_bits):
    alu_mode = modes.setdefault(new_alu_mode, set())
    alu_mode.update(base_mode)
    for i, bit in enumerate(new_mode_bits):
        if bit == '0':
            alu_mode.update(lut.flags[15 - i])

# also make DFFs, ALUs and shadow RAM
def fse_luts(fse, ttyp):
    data = fse[ttyp]['shortval'][5]

    luts = {}
    for lutn, bit, *fuses in data:
        coord = fuse.fuse_lookup(fse, ttyp, fuses[0])
        bel = luts.setdefault(f"LUT{lutn}", Bel())
        bel.flags[bit] = {coord}

    # dicts are in insertion order
    for num, lut in enumerate(luts.values()):
        lut.portmap = {
            'F': f"F{num}",
            'I0': f"A{num}",
            'I1': f"B{num}",
            'I2': f"C{num}",
            'I3': f"D{num}",
        }

    # main fuse: enable two ALUs in the slice
    # shortval(25/26/27) [1, 0, fuses]
    for cls, fuse_idx in enumerate([25, 26, 27]):
        try:
            data = fse[ttyp]['shortval'][fuse_idx]
        except KeyError:
            continue
        for i in range(2):
            # DFF
            bel = luts.setdefault(f"DFF{cls * 2 + i}", Bel())
            bel.portmap = {
                # D inputs hardwired to LUT F
                'Q'  : f"Q{cls * 2 + i}",
                'CLK': f"CLK{cls}",
                'LSR': f"LSR{cls}", # set/reset
                'CE' : f"CE{cls}", # clock enable
            }

            # ALU
            alu_idx = cls * 2 + i
            bel = luts.setdefault(f"ALU{alu_idx}", Bel())
            mode = set()
            for key0, key1, *fuses in data:
                if key0 == 1 and key1 == 0:
                    for f in (f for f in fuses if f != -1):
                        coord = fuse.fuse_lookup(fse, ttyp, f)
                        mode.update({coord})
                    break
            lut = luts[f"LUT{alu_idx}"]
            # ADD    INIT="0011 0000 1100 1100"
            #              add   0   add  carry
            add_alu_mode(mode, bel.modes, lut, "0",     "0011000011001100")
            # SUB    INIT="1010 0000 0101 1010"
            #              add   0   add  carry
            add_alu_mode(mode, bel.modes, lut, "1",     "1010000001011010")
            # ADDSUB INIT="0110 0000 1001 1010"
            #              add   0   sub  carry
            add_alu_mode(mode, bel.modes, lut, "2",     "0110000010011010")
            add_alu_mode(mode, bel.modes, lut, "hadder", "1111000000000000")
            # NE     INIT="1001 0000 1001 1111"
            #              add   0   sub  carry
            add_alu_mode(mode, bel.modes, lut, "3",     "1001000010011111")
            # GE
            add_alu_mode(mode, bel.modes, lut, "4",     "1001000010011010")
            # LE
            # no mode, just swap I0 and I1
            # CUP
            add_alu_mode(mode, bel.modes, lut, "6",     "1010000010100000")
            # CDN
            add_alu_mode(mode, bel.modes, lut, "7",     "0101000001011111")
            # CUPCDN
            # The functionality of this seems to be the same with SUB
            # add_alu_mode(mode, bel.modes, lut, "8",     "1010000001011010")
            # MULT   INIT="0111 1000 1000 1000"
            #
            add_alu_mode(mode, bel.modes, lut, "9",     "0111100010001000")
            # CIN->LOGIC INIT="0000 0000 0000 0000"
            #                   nop   0   nop  carry
            # side effect: clears the carry
            add_alu_mode(mode, bel.modes, lut, "C2L",   "0000000000000000")
            # 1->CIN     INIT="0000 0000 0000 1111"
            #                  nop   0   nop  carry
            add_alu_mode(mode, bel.modes, lut, "ONE2C", "0000000000001111")
            bel.portmap = {
                'COUT': f"COUT{alu_idx}",
                'CIN': f"CIN{alu_idx}",
                'SUM': f"F{alu_idx}",
                'I0': f"A{alu_idx}",
                'I1': f"B{alu_idx}",
                'I3': f"D{alu_idx}",
            }

    # main fuse: enable shadow SRAM in the slice
    # shortval(28) [2, 0, fuses]
    if 28 in fse[ttyp]['shortval']:
        for i in range(6):
            bel = luts.setdefault(f"DFF{i}", Bel())
            mode = bel.modes.setdefault("RAM", set())
            for key0, key1, *fuses in fse[ttyp]['shortval'][25+i//2]:
                if key0 < 0:
                    for f in fuses:
                        if f == -1: break
                        coord = fuse.fuse_lookup(fse, ttyp, f)
                        mode.add(coord)

        bel = luts.setdefault(f"RAM16", Bel())
        mode = bel.modes.setdefault("0", set())
        for key0, key1, *fuses in fse[ttyp]['shortval'][28]:
            if key0 == 2 and key1 == 0:
                for f in fuses:
                    if f == -1: break
                    coord = fuse.fuse_lookup(fse, ttyp, f)
                    mode.add(coord)
        bel.portmap = {
            'DI': ("A5", "B5", "C5", "D5"),
            'CLK': "CLK2",
            'WRE': "LSR2",
            'WAD': ("A4", "B4", "C4", "D4"),
            'RAD': tuple(tuple(f"{j}{i}" for i in range(4)) for j in ["A", "B", "C", "D"]),
            'DO': ("F0", "F1", "F2", "F3"),
        }
    return luts

def fse_osc(device, fse, ttyp):
    osc = {}

    if device in {'GW1N-4', 'GW1N-9', 'GW1N-9C'}:
        bel = osc.setdefault(f"OSC", Bel())
    elif device in {'GW1NZ-1', 'GW1NS-4'}:
        bel = osc.setdefault(f"OSCZ", Bel())
    elif device == 'GW1NS-2':
        bel = osc.setdefault(f"OSCF", Bel())
    elif device == 'GW1N-1':
        bel = osc.setdefault(f"OSCH", Bel())
    elif device == 'GW2AN-18':
        bel = osc.setdefault(f"OSCW", Bel())
    elif device == 'GW1N-2':
        bel = osc.setdefault(f"OSCO", Bel())
    else:
        raise Exception(f"Oscillator not yet supported on {device}")
    bel.portmap = {}
    return osc

def set_banks(fse, db):
    # fill the bank# : corner tile table
    w = db.cols - 1
    h = db.rows - 1
    for row, col in [(0, 0), (0, w), (h, 0), (h, w)]:
        ttyp = fse['header']['grid'][61][row][col]
        if 'longval' in fse[ttyp].keys():
            if 37 in fse[ttyp]['longval'].keys():
                for rd in fse[ttyp]['longval'][37]:
                    db.grid[row][col].bels.setdefault(f"BANK{rd[0]}", Bel())

_known_logic_tables = {
            8:  'DCS',
            9:  'GSR',
            10: 'IOLOGIC',
            11: 'IOB',
            12: 'SLICE',
            13: 'BSRAM',
            14: 'DSP',
            15: 'PLL',
            59: 'CFG',
            62: 'OSC',
            63: 'USB',
        }

_known_tables = {
             4: 'CONST',
             5: 'LUT',
            20: 'GSR',
            21: 'IOLOGICA',
            22: 'IOLOGICB',
            23: 'IOBA',
            24: 'IOBB',
            25: 'CLS0',
            26: 'CLS1',
            27: 'CLS2',
            28: 'CLS3',
            35: 'PLL',
            37: 'BANK',
            40: 'IOBC',
            41: 'IOBD',
            42: 'IOBE',
            43: 'IOBF',
            44: 'IOBG',
            45: 'IOBH',
            46: 'IOBI',
            47: 'IOBJ',
            51: 'OSC',
            53: 'DLLDEL0',
            54: 'DLLDEL1',
            56: 'DLL0',
            60: 'CFG',
            64: 'USB',
            66: 'EFLASH',
            68: 'ADC',
            80: 'DLL1',
            82: 'POWERSAVE',
        }

def fse_fill_logic_tables(dev, fse):
    # logicinfo
    for ltable in fse['header']['logicinfo'].keys():
        if ltable in _known_logic_tables.keys():
            table = dev.logicinfo.setdefault(_known_logic_tables[ltable], [])
        else:
            table = dev.logicinfo.setdefault(f"unknown_{ltable}", [])
        for attr, val, _ in fse['header']['logicinfo'][ltable]:
            table.append((attr, val))
    # shortval
    ttypes = {t for row in fse['header']['grid'][61] for t in row}
    for ttyp in ttypes:
        if 'shortval' in fse[ttyp].keys():
            ttyp_rec = dev.shortval.setdefault(ttyp, {})
            for stable in fse[ttyp]['shortval'].keys():
                if stable in _known_tables:
                    table = ttyp_rec.setdefault(_known_tables[stable], {})
                else:
                    table = ttyp_rec.setdefault(f"unknown_{stable}", {})
                for f_a, f_b, *fuses in fse[ttyp]['shortval'][stable]:
                    table[(f_a, f_b)] = {fuse.fuse_lookup(fse, ttyp, f) for f in unpad(fuses)}
        if 'longval' in fse[ttyp].keys():
            ttyp_rec = dev.longval.setdefault(ttyp, {})
            for ltable in fse[ttyp]['longval'].keys():
                if ltable in _known_tables:
                    table = ttyp_rec.setdefault(_known_tables[ltable], {})
                else:
                    table = ttyp_rec.setdefault(f"unknown_{ltable}", {})
                for f0, f1, f2, f3, f4, f5, f6, f7, f8, f9, f10, f11, f12, f13, f14, f15, *fuses in fse[ttyp]['longval'][ltable]:
                    table[(f0, f1, f2, f3, f4, f5, f6, f7, f8, f9, f10, f11, f12, f13, f14, f15)] = {fuse.fuse_lookup(fse, ttyp, f) for f in unpad(fuses)}

_hclk_in = {
            'TBDHCLK0': 0,  'TBDHCLK1': 1,  'TBDHCLK2': 2,  'TBDHCLK3': 3,
            'BBDHCLK0': 4,  'BBDHCLK1': 5,  'BBDHCLK2': 6,  'BBDHCLK3': 7,
            'LBDHCLK0': 8,  'LBDHCLK1': 9,  'LBDHCLK2': 10, 'LBDHCLK3': 11,
            'RBDHCLK0': 12, 'RBDHCLK1': 13, 'RBDHCLK2': 14, 'RBDHCLK3': 15}
def fse_create_hclk_aliases(db, device, dat):
    for row in range(db.rows):
        for col in range(db.cols):
            for src_fuses in db.grid[row][col].clock_pips.values():
                for src in src_fuses.keys():
                    if src in _hclk_in.keys():
                        source = dat['CmuxIns'][str(90 + _hclk_in[src])]
                        db.aliases[(row, col, src)] = (source[0] - 1, source[1] - 1, wirenames[source[2]])
    # hclk->fclk
    # top
    row = 0
    if device == 'GW1N-1':
        for col in range(1, db.cols - 1):
            db.grid[row][col].clock_pips['FCLK'] = {'CLK2': {}}
    elif device in {'GW1NZ-1'}:
        for col in range(1, 10):
            db.grid[row][col].clock_pips['FCLK'] = {'HCLK0': {}}
            db.aliases[(row, col, 'HCLK0')] = (0, 5, 'SPINE10')
            db.grid[row][col].clock_pips['FCLK'] = {'HCLK1': {}}
            db.aliases[(row, col, 'HCLK1')] = (0, 5, 'SPINE12')
        for col in range(10, db.cols - 1):
            db.grid[row][col].clock_pips['FCLK'] = {'HCLK0': {}}
            db.aliases[(row, col, 'HCLK0')] = (0, 5, 'SPINE11')
            db.grid[row][col].clock_pips['FCLK'] = {'HCLK1': {}}
            db.aliases[(row, col, 'HCLK1')] = (0, 5, 'SPINE13')
    elif device in {'GW1N-4'}:
        for col in range(1, db.cols - 1):
            db.grid[row][col].clock_pips['FCLK'] = {'CLK2': {}}
    elif device in {'GW1NS-4'}:
        for col in range(1, 11):
            db.grid[row][col].clock_pips['FCLK'] = {'HCLK0': {}}
            db.aliases[(row, col, 'HCLK0')] = (row, 18, 'SPINE10')
            db.grid[row][col].clock_pips['FCLK'] = {'HCLK1': {}}
            db.aliases[(row, col, 'HCLK1')] = (row, 18, 'SPINE12')
        for col in range(11, db.cols - 1):
            db.grid[row][col].clock_pips['FCLK'] = {'HCLK0': {}}
            db.aliases[(row, col, 'HCLK0')] = (row, 18, 'SPINE11')
            db.grid[row][col].clock_pips['FCLK'] = {'HCLK1': {}}
            db.aliases[(row, col, 'HCLK1')] = (row, 18, 'SPINE13')
    elif device in {'GW1N-9'}:
        for col in range(1, 28):
            db.grid[row][col].clock_pips['FCLK'] = {'HCLK0': {}}
            db.aliases[(row, col, 'HCLK0')] = (row, 0, 'SPINE10')
            db.grid[row][col].clock_pips['FCLK'] = {'HCLK1': {}}
            db.aliases[(row, col, 'HCLK1')] = (row, db.cols - 1, 'SPINE12')
        for col in range(28, db.cols - 1):
            db.grid[row][col].clock_pips['FCLK'] = {'HCLK0': {}}
            db.aliases[(row, col, 'HCLK0')] = (row, 0, 'SPINE11')
            db.grid[row][col].clock_pips['FCLK'] = {'HCLK1': {}}
            db.aliases[(row, col, 'HCLK1')] = (row, db.cols - 1, 'SPINE13')
    elif device in {'GW1N-9C'}:
        for col in range(1, db.cols - 1):
            db.grid[row][col].clock_pips['FCLK'] = {'HCLK0': {}}
            db.aliases[(row, col, 'HCLK0')] = (0, db.cols - 1, 'SPINE11')
            db.grid[row][col].clock_pips['FCLK'] = {'HCLK1': {}}
            db.aliases[(row, col, 'HCLK1')] = (0, db.cols - 1, 'SPINE13')

    # right
    col = db.cols - 1
    if device == 'GW1N-1':
        for row in range(1, db.rows - 1):
            db.grid[row][col].clock_pips['FCLK'] = {'CLK2': {}}
    elif device in {'GW1NZ-1'}:
        for row in range(1, 5):
            db.grid[row][col].clock_pips['FCLK'] = {'HCLK0': {}}
            db.aliases[(row, col, 'HCLK0')] = (5, col, 'SPINE10')
            db.grid[row][col].clock_pips['FCLK'] = {'HCLK1': {}}
            db.aliases[(row, col, 'HCLK1')] = (5, col, 'SPINE12')
        for row in range(6, db.rows - 1):
            db.grid[row][col].clock_pips['FCLK'] = {'HCLK0': {}}
            db.aliases[(row, col, 'HCLK0')] = (5, col, 'SPINE11')
            db.grid[row][col].clock_pips['FCLK'] = {'HCLK1': {}}
            db.aliases[(row, col, 'HCLK1')] = (5, col, 'SPINE13')
    elif device in {'GW1N-4'}:
        for row in range(1, db.rows - 1):
            if row not in {8, 9, 10, 11}:
                db.grid[row][col].clock_pips['FCLK'] = {'CLK2': {}}
        for row in range(1, 9):
            db.grid[row][col].clock_pips['FCLK'] = {'HCLK1': {}}
            db.aliases[(row, col, 'HCLK1')] = (9, col, 'SPINE12')
        for row in range(10, db.rows - 1):
            db.grid[row][col].clock_pips['FCLK'] = {'HCLK1': {}}
            db.aliases[(row, col, 'HCLK1')] = (9, col, 'SPINE13')
    elif device in {'GW1NS-4'}:
        for row in range(1, 9):
            db.grid[row][col].clock_pips['FCLK'] = {'HCLK0': {}}
            db.aliases[(row, col, 'HCLK0')] = (9, col, 'SPINE10')
            db.grid[row][col].clock_pips['FCLK'] = {'HCLK1': {}}
            db.aliases[(row, col, 'HCLK1')] = (9, col, 'SPINE12')
        for row in range(9, db.rows - 1):
            db.grid[row][col].clock_pips['FCLK'] = {'HCLK0': {}}
            db.aliases[(row, col, 'HCLK0')] = (9, col, 'SPINE11')
            db.grid[row][col].clock_pips['FCLK'] = {'HCLK1': {}}
            db.aliases[(row, col, 'HCLK1')] = (9, col, 'SPINE13')
    elif device in {'GW1N-9'}:
        for row in range(1, 19):
            db.grid[row][col].clock_pips['FCLK'] = {'HCLK0': {}}
            db.aliases[(row, col, 'HCLK0')] = (18, col, 'SPINE10')
            db.grid[row][col].clock_pips['FCLK'] = {'HCLK1': {}}
            db.aliases[(row, col, 'HCLK1')] = (18, col, 'SPINE12')
        for row in range(19, db.rows - 1):
            db.grid[row][col].clock_pips['FCLK'] = {'HCLK0': {}}
            db.aliases[(row, col, 'HCLK0')] = (18, col, 'SPINE11')
            db.grid[row][col].clock_pips['FCLK'] = {'HCLK1': {}}
            db.aliases[(row, col, 'HCLK1')] = (18, col, 'SPINE13')
    elif device in {'GW1N-9C'}:
        for row in range(1, db.rows - 1):
            db.grid[row][col].clock_pips['FCLK'] = {'HCLK0': {}}
            db.aliases[(row, col, 'HCLK0')] = (18, col, 'SPINE11')
            db.grid[row][col].clock_pips['FCLK'] = {'HCLK1': {}}
            db.aliases[(row, col, 'HCLK1')] = (18, col, 'SPINE13')

    # left
    col = 0
    if device == 'GW1N-1':
        for row in range(1, db.rows - 1):
            db.grid[row][col].clock_pips['FCLK'] = {'CLK2': {}}
    elif device in {'GW1N-4'}:
        for row in range(1, db.rows - 1):
            if row not in {8, 9, 10, 11}:
                db.grid[row][col].clock_pips['FCLK'] = {'CLK2': {}}
        for row in range(1, 9):
            db.grid[row][col].clock_pips['FCLK'] = {'HCLK1': {}}
            db.aliases[(row, col, 'HCLK1')] = (9, col, 'SPINE12')
        for row in range(10, db.rows - 1):
            db.grid[row][col].clock_pips['FCLK'] = {'HCLK1': {}}
            db.aliases[(row, col, 'HCLK1')] = (9, col, 'SPINE13')
    elif device in {'GW1N-9'}:
        for row in range(1, 19):
            db.grid[row][col].clock_pips['FCLK'] = {'HCLK0': {}}
            db.aliases[(row, col, 'HCLK0')] = (18, col, 'SPINE10')
            db.grid[row][col].clock_pips['FCLK'] = {'HCLK1': {}}
            db.aliases[(row, col, 'HCLK1')] = (18, col, 'SPINE12')
        for row in range(19, db.rows - 1):
            db.grid[row][col].clock_pips['FCLK'] = {'HCLK0': {}}
            db.aliases[(row, col, 'HCLK0')] = (18, col, 'SPINE11')
            db.grid[row][col].clock_pips['FCLK'] = {'HCLK1': {}}
            db.aliases[(row, col, 'HCLK1')] = (18, col, 'SPINE13')
    elif device in {'GW1N-9C'}:
        for row in range(1, db.rows - 1):
            db.grid[row][col].clock_pips['FCLK'] = {'HCLK0': {}}
            db.aliases[(row, col, 'HCLK0')] = (18, 0, 'SPINE11')
            db.grid[row][col].clock_pips['FCLK'] = {'HCLK1': {}}
            db.aliases[(row, col, 'HCLK1')] = (18, 0, 'SPINE13')

    # bottom
    row = db.rows - 1
    if device == 'GW1N-1':
        for col in range(1, 10):
            if col not in {8, 9}:
                db.grid[row][col].clock_pips['FCLK'] = {'CLK2': {}}
            db.grid[row][col].clock_pips['FCLK'] = {'HCLK1': {}}
            db.aliases[(row, col, 'HCLK1')] = (row, db.cols -1, 'SPINE12')
        for col in range(10, db.cols - 1):
            if col not in {10, 11}:
                db.grid[row][col].clock_pips['FCLK'] = {'CLK2': {}}
            db.grid[row][col].clock_pips['FCLK'] = {'HCLK1': {}}
            db.aliases[(row, col, 'HCLK1')] = (row, db.cols - 1, 'SPINE13')
    elif device in {'GW1N-4'}:
        for col in range(1, 19):
            if col not in {17, 18}:
                db.grid[row][col].clock_pips['FCLK'] = {'CLK2': {}}
            db.grid[row][col].clock_pips['FCLK'] = {'HCLK1': {}}
            db.aliases[(row, col, 'HCLK1')] = (row, db.cols -1, 'SPINE12')
        for col in range(19, db.cols - 1):
            if col not in {19, 20}:
                db.grid[row][col].clock_pips['FCLK'] = {'CLK2': {}}
            db.grid[row][col].clock_pips['FCLK'] = {'HCLK1': {}}
            db.aliases[(row, col, 'HCLK1')] = (row, db.cols - 1, 'SPINE13')
    elif device in {'GW1NS-4'}:
        db.aliases[(row, 17, 'SPINE2')] = (row, 16, 'SPINE2')
        for col in range(1, 16):
            db.grid[row][col].clock_pips['FCLK'] = {'HCLK0': {}}
            db.aliases[(row, col, 'HCLK0')] = (row, 17, 'SPINE10')
            db.grid[row][col].clock_pips['FCLK'] = {'HCLK1': {}}
            db.aliases[(row, col, 'HCLK1')] = (row, 20, 'SPINE12')
        for col in range(21, db.cols - 1):
            db.grid[row][col].clock_pips['FCLK'] = {'HCLK0': {}}
            db.aliases[(row, col, 'HCLK0')] = (row, 17, 'SPINE11')
            db.grid[row][col].clock_pips['FCLK'] = {'HCLK1': {}}
            db.aliases[(row, col, 'HCLK1')] = (row, 20, 'SPINE13')
    elif device in {'GW1N-9'}:
        for col in range(1, 28):
            db.grid[row][col].clock_pips['FCLK'] = {'HCLK0': {}}
            db.aliases[(row, col, 'HCLK0')] = (row, 0, 'SPINE10')
            db.grid[row][col].clock_pips['FCLK'] = {'HCLK1': {}}
            db.aliases[(row, col, 'HCLK1')] = (row, db.cols - 1, 'SPINE12')
        for col in range(28, db.cols - 1):
            db.grid[row][col].clock_pips['FCLK'] = {'HCLK0': {}}
            db.aliases[(row, col, 'HCLK0')] = (row, 0, 'SPINE11')
            db.grid[row][col].clock_pips['FCLK'] = {'HCLK1': {}}
            db.aliases[(row, col, 'HCLK1')] = (row, db.cols - 1, 'SPINE13')
    elif device in {'GW1N-9C'}:
        for col in range(1, db.cols - 1):
            db.grid[row][col].clock_pips['FCLK'] = {'HCLK0': {}}
            db.aliases[(row, col, 'HCLK0')] = (row, 0, 'SPINE11')
            db.grid[row][col].clock_pips['FCLK'] = {'HCLK1': {}}
            db.aliases[(row, col, 'HCLK1')] = (row, db.cols - 1, 'SPINE13')

_pll_loc = {
 'GW1N-1':
   {'TRPLL0CLK0': (0, 17, 'F4'), 'TRPLL0CLK1': (0, 17, 'F5'),
    'TRPLL0CLK2': (0, 17, 'F6'), 'TRPLL0CLK3': (0, 17, 'F7'), },
 'GW1NZ-1':
   {'TRPLL0CLK0': (0, 17, 'F4'), 'TRPLL0CLK1': (0, 17, 'F5'),
    'TRPLL0CLK2': (0, 17, 'F6'), 'TRPLL0CLK3': (0, 17, 'F7'), },
 'GW1NS-2':
   {'TRPLL0CLK0': (5, 19, 'F4'), 'TRPLL0CLK1': (5, 19, 'F7'),
    'TRPLL0CLK2': (5, 19, 'F5'), 'TRPLL0CLK3': (5, 19, 'F6'), },
 'GW1N-4':
   {'TLPLL0CLK0': (0, 9, 'F4'), 'TLPLL0CLK1': (0, 9, 'F7'),
    'TLPLL0CLK2': (0, 9, 'F6'), 'TLPLL0CLK3': (0, 9, 'F5'),
    'TRPLL0CLK0': (0, 27, 'F4'), 'TRPLL0CLK1': (0, 27, 'F7'),
    'TRPLL0CLK2': (0, 27, 'F6'), 'TRPLL0CLK3': (0, 27, 'F5'), },
 'GW1NS-4':
   {'TLPLL0CLK0': (0, 27, 'F4'), 'TLPLL0CLK1': (0, 27, 'F7'),
    'TLPLL0CLK2': (0, 27, 'F6'), 'TLPLL0CLK3': (0, 27, 'F5'),
    'TRPLL0CLK0': (0, 36, 'F4'), 'TRPLL0CLK1': (0, 36, 'F7'),
    'TRPLL0CLK2': (0, 36, 'F6'), 'TRPLL0CLK3': (0, 36, 'F5'), },
 'GW1N-9C':
   {'TLPLL0CLK0': (9, 2, 'F4'), 'TLPLL0CLK1': (9, 2, 'F7'),
    'TLPLL0CLK2': (9, 2, 'F5'), 'TLPLL0CLK3': (9, 2, 'F6'),
    'TRPLL0CLK0': (9, 44, 'F4'), 'TRPLL0CLK1': (9, 44, 'F7'),
    'TRPLL0CLK2': (9, 44, 'F5'), 'TRPLL0CLK3': (9, 44, 'F6'), },
 'GW1N-9':
   {'TLPLL0CLK0': (9, 2, 'F4'), 'TLPLL0CLK1': (9, 2, 'F7'),
    'TLPLL0CLK2': (9, 2, 'F5'), 'TLPLL0CLK3': (9, 2, 'F6'),
    'TRPLL0CLK0': (9, 44, 'F4'), 'TRPLL0CLK1': (9, 44, 'F7'),
    'TRPLL0CLK2': (9, 44, 'F5'), 'TRPLL0CLK3': (9, 44, 'F6'), },
}

def fse_create_pll_clock_aliases(db, device):
    # we know exactly where the PLL is and therefore know which aliases to create
    for row in range(db.rows):
        for col in range(db.cols):
            for w_dst, w_srcs in db.grid[row][col].clock_pips.items():
                for w_src in w_srcs.keys():
                    # XXX
                    if device in {'GW1N-1', 'GW1NZ-1', 'GW1NS-2', 'GW1NS-4', 'GW1N-4', 'GW1N-9C', 'GW1N-9'}:
                        if w_src in _pll_loc[device].keys():
                            db.aliases[(row, col, w_src)] = _pll_loc[device][w_src]

def fse_iologic(device, fse, ttyp):
    bels = {}
    # some iocells nave no iologic
    if ttyp in {48, 49, 50, 51}:
        return bels
    if device in {'GW1N-1', 'GW1NZ-1', 'GW1NS-2', 'GW1N-4', 'GW1NS-4'} and ttyp in {86, 87}:
        return bels
    if device in {'GW1NS-4'} and ttyp in {86, 87, 135, 136, 137, 138}:
        return bels
    if 'shortval' in fse[ttyp].keys():
        if 21 in fse[ttyp]['shortval'].keys():
            bels['IOLOGICA'] = Bel()
        if 22 in fse[ttyp]['shortval'].keys():
            bels['IOLOGICB'] = Bel()
    # 16bit
    if device in {'GW1NS-4'} and ttyp in {142, 144, 59}:
            bels['OSER16'] = Bel()
            bels['IDES16'] = Bel()
    if device in {'GW1N-9', 'GW1N-9C'} and ttyp in {52, 66}:
            bels['OSER16'] = Bel()
            bels['IDES16'] = Bel()
    return bels

def from_fse(device, fse, dat):
    dev = Device()
    ttypes = {t for row in fse['header']['grid'][61] for t in row}
    tiles = {}
    for ttyp in ttypes:
        w = fse[ttyp]['width']
        h = fse[ttyp]['height']
        tile = Tile(w, h, ttyp)
        tile.pips = fse_pips(fse, ttyp, 2, wirenames)
        tile.clock_pips = fse_pips(fse, ttyp, 38, clknames)
        tile.clock_pips.update(fse_hclk_pips(fse, ttyp, tile.aliases))
        tile.alonenode_6 = fse_alonenode(fse, ttyp, 6)
        if 5 in fse[ttyp]['shortval']:
            tile.bels = fse_luts(fse, ttyp)
        if 51 in fse[ttyp]['shortval']:
            tile.bels = fse_osc(device, fse, ttyp)
        if ttyp in [74, 75, 76, 77, 78, 79, 86, 87, 88, 89]:
            tile.bels = fse_pll(device, fse, ttyp)
        tile.bels.update(fse_iologic(device, fse, ttyp))
        tiles[ttyp] = tile

    fse_fill_logic_tables(dev, fse)
    dev.grid = [[tiles[ttyp] for ttyp in row] for row in fse['header']['grid'][61]]
    fse_create_pll_clock_aliases(dev, device)
    fse_create_hclk_aliases(dev, device, dat)
    return dev

# get fuses for attr/val set using short/longval table
# returns a bit set
def get_table_fuses(attrs, table):
    bits = set()
    for key, fuses in table.items():
        # all 2/16 "features" must be present to be able to use a set of bits from the record
        have_full_key = True
        for attrval in key:
            if attrval == 0: # no "feature"
                break
            if attrval > 0:
                # this "feature" must present
                if attrval not in attrs:
                    have_full_key = False
                    break
                continue
            if attrval < 0:
                # this "feature" is set by default and can only be unset
                if abs(attrval) in attrs:
                    have_full_key = False
                    break
        if not have_full_key:
            continue
        bits.update(fuses)
    return bits

# get fuses for attr/val set using shortval table for ttyp
# returns a bit set
def get_shortval_fuses(dev, ttyp, attrs, table_name):
    return get_table_fuses(attrs, dev.shortval[ttyp][table_name])

# get fuses for attr/val set using longval table for ttyp
# returns a bit set
def get_longval_fuses(dev, ttyp, attrs, table_name):
    return get_table_fuses(attrs, dev.longval[ttyp][table_name])

# get bank fuses
# The table for banks is different in that the first element in it is the
# number of the bank, thus allowing the repetition of elements in the key
def get_bank_fuses(dev, ttyp, attrs, table_name, bank_num):
    return get_table_fuses(attrs, {k[1:]:val for k, val in dev.longval[ttyp][table_name].items() if k[0] == bank_num})

# add the attribute/value pair into an set, which is then passed to
# get_longval_fuses() and get_shortval_fuses()
def add_attr_val(dev, logic_table, attrs, attr, val):
    for idx, attr_val in enumerate(dev.logicinfo[logic_table]):
        if attr_val[0] == attr and attr_val[1] == val:
            attrs.add(idx)
            break

def get_pins(device):
    if device not in {"GW1N-1", "GW1NZ-1", "GW1N-4", "GW1N-9", "GW1NR-9", "GW1N-9C", "GW1NR-9C", "GW1NS-2", "GW1NS-2C", "GW1NS-4", "GW1NSR-4C"}:
        raise Exception(f"unsupported device {device}")
    pkgs = pindef.all_packages(device)
    res = {}
    res_bank_pins = {}
    for pkg_rec in pkgs.values():
        pkg = pkg_rec[0]
        if pkg in res:
            continue
        res[pkg] = pindef.get_pin_locs(device, pkg, pindef.VeryTrue)
        res_bank_pins.update(pindef.get_bank_pins(device, pkg))
    return (pkgs, res, res_bank_pins)

# returns ({partnumber: (package, device, speed)}, {pins}, {bank_pins})
def json_pinout(device):
    if device == "GW1N-1":
        pkgs, pins, bank_pins = get_pins("GW1N-1")
        return (pkgs, {
            "GW1N-1": pins
        }, bank_pins)
    elif device == "GW1NZ-1":
        pkgs, pins, bank_pins = get_pins("GW1NZ-1")
        return (pkgs, {
            "GW1NZ-1": pins
        }, bank_pins)
    elif device == "GW1N-4":
        pkgs, pins, bank_pins = get_pins("GW1N-4")
        return (pkgs, {
            "GW1N-4": pins
        }, bank_pins)
    elif device == "GW1NS-4":
        pkgs_sr, pins_sr, bank_pins_sr = get_pins("GW1NSR-4C")
        pkgs, pins, bank_pins = get_pins("GW1NS-4")
        res = {}
        res.update(pkgs)
        res.update(pkgs_sr)
        res_bank_pins = {}
        res_bank_pins.update(bank_pins)
        res_bank_pins.update(bank_pins_sr)
        return (res, {
            "GW1NS-4": pins,
            "GW1NSR-4C": pins_sr
        }, res_bank_pins)
    elif device == "GW1N-9":
        pkgs, pins, bank_pins = get_pins("GW1N-9")
        pkgs_r, pins_r, bank_pins_r = get_pins("GW1NR-9")
        res = {}
        res.update(pkgs)
        res.update(pkgs_r)
        res_bank_pins = {}
        res_bank_pins.update(bank_pins)
        res_bank_pins.update(bank_pins_r)
        return (res, {
            "GW1N-9": pins,
            "GW1NR-9": pins_r
        }, res_bank_pins)
    elif device == "GW1N-9C":
        pkgs, pins, bank_pins = get_pins("GW1N-9C")
        pkgs_r, pins_r, bank_pins_r = get_pins("GW1NR-9C")
        res = {}
        res.update(pkgs)
        res.update(pkgs_r)
        res_bank_pins = {}
        res_bank_pins.update(bank_pins)
        res_bank_pins.update(bank_pins_r)
        return (res, {
            "GW1N-9C": pins,
            "GW1NR-9C": pins_r
        }, res_bank_pins)
    elif device == "GW1NS-2":
        pkgs, pins, bank_pins = get_pins("GW1NS-2")
        pkgs_c, pins_c, bank_pins_c = get_pins("GW1NS-2C")
        res = {}
        res.update(pkgs)
        res.update(pkgs_c)
        res_bank_pins = {}
        res_bank_pins.update(bank_pins)
        res_bank_pins.update(bank_pins_c)
        return (res, {
            "GW1NS-2": pins,
            "GW1NS-2C": pins_c
        }, res_bank_pins)
    else:
        raise Exception("unsupported device")

_pll_inputs = [(5, 'CLKFB'), (6, 'FBDSEL0'), (7, 'FBDSEL1'), (8, 'FBDSEL2'), (9, 'FBDSEL3'),
               (10, 'FBDSEL4'), (11, 'FBDSEL5'),
               (12, 'IDSEL0'), (13, 'IDSEL1'), (14, 'IDSEL2'), (15, 'IDSEL3'), (16, 'IDSEL4'),
               (17, 'IDSEL5'),
               (18, 'ODSEL0'), (19, 'ODSEL1'), (20, 'ODSEL2'), (21, 'ODSEL3'), (22, 'ODSEL4'),
               (23, 'ODSEL5'), (0, 'RESET'), (1, 'RESET_P'),
               (24, 'PSDA0'), (25, 'PSDA1'), (26, 'PSDA2'), (27, 'PSDA3'),
               (28, 'DUTYDA0'), (29, 'DUTYDA1'), (30, 'DUTYDA2'), (31, 'DUTYDA3'),
               (32, 'FDLY0'), (33, 'FDLY1'), (34, 'FDLY2'), (35, 'FDLY3')]
_pll_outputs = [(0, 'CLKOUT'), (1, 'LOCK'), (2, 'CLKOUTP'), (3, 'CLKOUTD'), (4, 'CLKOUTD3')]
_iologic_inputs =  [(0, 'D'), (1, 'D0'), (2, 'D1'), (3, 'D2'), (4, 'D3'), (5, 'D4'),
                    (6, 'D5'), (7, 'D6'), (8, 'D7'), (9, 'D8'), (10, 'D9'), (11, 'D10'),
                    (12, 'D11'), (13, 'D12'), (14, 'D13'), (15, 'D14'), (16, 'D15'),
                    (17, 'CLK'), (18, 'ICLK'), (19, 'PCLK'), (20, 'FCLK'), (21, 'TCLK'),
                    (22, 'MCLK'), (23, 'SET'), (24, 'RESET'), (25, 'PRESET'), (26, 'CLEAR'),
                    (27, 'TX'), (28, 'TX0'), (29, 'TX1'), (30, 'TX2'), (31, 'TX3'),
                    (32, 'WADDR0'), (33, 'WADDR1'), (34, 'WADDR2'), (35, 'RADDR0'),
                    (36, 'RADDR1'), (37, 'RADDR2'), (38, 'CALIB'), (39, 'DI'), (40, 'SETN'),
                    (41, 'SDTAP'), (42, 'VALUE'), (43, 'DASEL'), (44, 'DASEL0'), (45, 'DASEL1'),
                    (46, 'DAADJ'), (47, 'DAADJ0'), (48, 'DAADJ1')]
_iologic_outputs = [(0, 'Q'),  (1, 'Q0'), (2, 'Q1'), (3, 'Q2'), (4, 'Q3'), (5, 'Q4'),
                    (6, 'Q5'), (7, 'Q6'), (8, 'Q7'), (9, 'Q8'), (10, 'Q9'), (11, 'Q10'),
                    (12, 'Q11'), (13, 'Q12'), (14, 'Q13'), (15, 'Q14'), (16, 'Q15'),
                    (17, 'DO'), (18, 'DF'), (19, 'LAG'), (20, 'LEAD'), (21, 'DAO')]
_oser16_inputs =  [(19, 'PCLK'), (20, 'FCLK'), (25, 'RESET')]
_oser16_fixed_inputs = {'D0': 'A0', 'D1': 'A1', 'D2': 'A2', 'D3': 'A3', 'D4': 'C1',
                        'D5': 'C0', 'D6': 'D1', 'D7': 'D0', 'D8': 'C3', 'D9': 'C2',
                        'D10': 'B4', 'D11': 'B5', 'D12': 'A0', 'D13': 'A1', 'D14': 'A2',
                        'D15': 'A3'}
_oser16_outputs = [(1, 'Q0')]
_ides16_inputs = [(19, 'PCLK'), (20, 'FCLK'), (38, 'CALIB'), (25, 'RESET'), (0, 'D')]
_ides16_fixed_outputs = { 'Q0': 'F2', 'Q1': 'F3', 'Q2': 'F4', 'Q3': 'F5', 'Q4': 'Q0',
                          'Q5': 'Q1', 'Q6': 'Q2', 'Q7': 'Q3', 'Q8': 'Q4', 'Q9': 'Q5', 'Q10': 'F0',
                         'Q11': 'F1', 'Q12': 'F2', 'Q13': 'F3', 'Q14': 'F4', 'Q15': 'F5'}
# (osc-type, devices) : ({local-ports}, {aliases})
_osc_ports = {('OSCZ', 'GW1NZ-1'): ({}, {'OSCOUT' : (0, 5, 'OF3'), 'OSCEN': (0, 2, 'A6')}),
              ('OSCZ', 'GW1NS-4'): ({'OSCOUT': 'Q4', 'OSCEN': 'D6'}, {}),
              ('OSCF', 'GW1NS-2'): ({}, {'OSCOUT': (10, 19, 'Q4'), 'OSCEN': (13, 19, 'B3')}),
              ('OSCH', 'GW1N-1'):  ({'OSCOUT': 'Q4'}, {}),
              ('OSC',  'GW1N-4'):  ({'OSCOUT': 'Q4'}, {}),
              ('OSC',  'GW1N-9'):  ({'OSCOUT': 'Q4'}, {}),
              ('OSC',  'GW1N-9C'):  ({'OSCOUT': 'Q4'}, {}),
              # XXX unsupported boards, pure theorizing
              ('OSCO', 'GW1N-2'):  ({'OSCOUT': 'Q7'}, {'OSCEN': (9, 1, 'B4')}),
              ('OSCW', 'GW2AN-18'):  ({'OSCOUT': 'Q4'}, {}),
              }
def dat_portmap(dat, dev, device):
    for row, row_dat in enumerate(dev.grid):
        for col, tile in enumerate(row_dat):
            for name, bel in tile.bels.items():
                if bel.portmap: continue
                if name.startswith("IOB"):
                    if name[3] > 'B':
                        idx = ord(name[-1]) - ord('A')
                        inp = wirenames[dat['IobufIns'][idx]]
                        bel.portmap['I'] = inp
                        out = wirenames[dat['IobufOuts'][idx]]
                        bel.portmap['O'] = out
                        oe = wirenames[dat['IobufOes'][idx]]
                        bel.portmap['OE'] = oe
                    else:
                        pin = name[-1]
                        inp = wirenames[dat[f'Iobuf{pin}Out']]
                        bel.portmap['O'] = inp
                        out = wirenames[dat[f'Iobuf{pin}In']]
                        bel.portmap['I'] = out
                        oe = wirenames[dat[f'Iobuf{pin}OE']]
                        bel.portmap['OE'] = oe
                elif name.startswith("IOLOGIC"):
                    buf = name[-1]
                    for idx, nam in _iologic_inputs:
                        w_idx = dat[f'Iologic{buf}In'][idx]
                        if w_idx >= 0:
                            bel.portmap[nam] = wirenames[w_idx]
                        elif nam == 'FCLK':
                            # dummy Input, we'll make a special pips for it
                            bel.portmap[nam] = "FCLK"
                    for idx, nam in _iologic_outputs:
                        w_idx = dat[f'Iologic{buf}Out'][idx]
                        if w_idx >= 0:
                            bel.portmap[nam] = wirenames[w_idx]
                elif name.startswith("OSER16"):
                    for idx, nam in _oser16_inputs:
                        w_idx = dat[f'IologicAIn'][idx]
                        if w_idx >= 0:
                            bel.portmap[nam] = wirenames[w_idx]
                        elif nam == 'FCLK':
                            # dummy Input, we'll make a special pips for it
                            bel.portmap[nam] = "FCLK"
                    for idx, nam in _oser16_outputs:
                        w_idx = dat[f'IologicAOut'][idx]
                        if w_idx >= 0:
                            bel.portmap[nam] = wirenames[w_idx]
                    bel.portmap.update(_oser16_fixed_inputs)
                elif name.startswith("IDES16"):
                    for idx, nam in _ides16_inputs:
                        w_idx = dat[f'IologicAIn'][idx]
                        if w_idx >= 0:
                            bel.portmap[nam] = wirenames[w_idx]
                        elif nam == 'FCLK':
                            # dummy Input, we'll make a special pips for it
                            bel.portmap[nam] = "FCLK"
                    bel.portmap.update(_ides16_fixed_outputs)
                elif name == 'RPLLA':
                    # The PllInDlt table seems to indicate in which cell the
                    # inputs are actually located.
                    offx = 1
                    if device in {'GW1N-9C', 'GW1N-9'}:
                        # two mirrored PLLs
                        if col > dat['center'][1] - 1:
                            offx = -1
                    for idx, nam in _pll_inputs:
                        wire = wirenames[dat['PllIn'][idx]]
                        off = dat['PllInDlt'][idx] * offx
                        if device in {'GW1NS-2'}:
                            # NS-2 is a strange thingy
                            if nam in {'RESET', 'RESET_P', 'IDSEL1', 'IDSEL2', 'ODSEL5'}:
                                bel.portmap[nam] = f'rPLL{nam}{wire}'
                                dev.aliases[row, col, f'rPLL{nam}{wire}'] = (9, col, wire)
                            else:
                                bel.portmap[nam] = wire
                        elif off == 0:
                            bel.portmap[nam] = wire
                        else:
                            # not our cell, make an alias
                            bel.portmap[nam] = f'rPLL{nam}{wire}'
                            dev.aliases[row, col, f'rPLL{nam}{wire}'] = (row, col + off, wire)
                    for idx, nam in _pll_outputs:
                        wire = wirenames[dat['PllOut'][idx]]
                        off = dat['PllOutDlt'][idx] * offx
                        if off == 0 or device in {'GW1NS-2'}:
                            bel.portmap[nam] = wire
                        else:
                            # not our cell, make an alias
                            bel.portmap[nam] = f'rPLL{nam}{wire}'
                            dev.aliases[row, col, f'rPLL{nam}{wire}'] = (row, col + off, wire)
                    # clock input
                    nam = 'CLKIN'
                    wire = wirenames[dat['PllClkin'][1][0]]
                    off = dat['PllClkin'][1][1] * offx
                    if off == 0:
                        bel.portmap[nam] = wire
                    else:
                        # not our cell, make an alias
                        bel.portmap[nam] = f'rPLL{nam}{wire}'
                        dev.aliases[row, col, f'rPLL{nam}{wire}'] = (row, col + off, wire)
                elif name == 'PLLVR':
                    pll_idx = 0
                    if col != 27:
                        pll_idx = 1
                    for idx, nam in _pll_inputs:
                        pin_row = dat[f'SpecPll{pll_idx}Ins'][idx * 3 + 0]
                        wire = wirenames[dat[f'SpecPll{pll_idx}Ins'][idx * 3 + 2]]
                        if pin_row == 1:
                            bel.portmap[nam] = wire
                        else:
                            # some of the PLLVR inputs are in a special cell
                            # (9, 37), here we create aliases where the
                            # destination is the ports of the primitive, but
                            # you should keep in mind that nextpnr is designed
                            # so that it will not use such aliases. They have
                            # to be taken care of separately.
                            bel.portmap[nam] = f'PLLVR{nam}{wire}'
                            dev.aliases[row, col, f'PLLVR{nam}{wire}'] = (9, 37, wire)
                    for idx, nam in _pll_outputs:
                        wire = wirenames[dat[f'SpecPll{pll_idx}Outs'][idx * 3 + 2]]
                        bel.portmap[nam] = wire
                    bel.portmap['CLKIN'] = wirenames[124];
                    reset = wirenames[dat[f'SpecPll{pll_idx}Ins'][0 + 2]]
                    # VREN pin is placed in another cell
                    if pll_idx == 0:
                        vren = 'D0'
                    else:
                        vren = 'B0'
                    bel.portmap['VREN'] = f'PLLVRV{vren}'
                    dev.aliases[row, col, f'PLLVRV{vren}'] = (0, 37, vren)
                if name.startswith('OSC'):
                    # local ports
                    local_ports, aliases = _osc_ports[name, device]
                    bel.portmap.update(local_ports)
                    for port, alias in aliases.items():
                        bel.portmap[port] = port
                        dev.aliases[row, col, port] = alias

def dat_aliases(dat, dev):
    for row in dev.grid:
        for td in row:
            for dest, (src,) in zip(dat['X11s'], dat['X11Ins']):
                td.aliases[wirenames[dest]] = wirenames[src]

def tile_bitmap(dev, bitmap, empty=False):
    res = {}
    y = 0
    for idx, row in enumerate(dev.grid):
        x=0
        for jdx, td in enumerate(row):
            w = td.width
            h = td.height
            tile = bitmap[y:y+h,x:x+w]
            if tile.any() or empty:
                res[(idx, jdx)] = tile
            x+=w
        y+=h

    return res

def fuse_bitmap(db, bitmap):
    res = np.zeros((db.height, db.width), dtype=np.uint8)
    y = 0
    for idx, row in enumerate(db.grid):
        x=0
        for jdx, td in enumerate(row):
            w = td.width
            h = td.height
            res[y:y+h,x:x+w] = bitmap[(idx, jdx)]
            x+=w
        y+=h

    return res

def shared2flag(dev):
    "Convert mode bits that are shared between bels to flags"
    for idx, row in enumerate(dev.grid):
        for jdx, td in enumerate(row):
            for namea, bela in td.bels.items():
                bitsa = bela.mode_bits
                for nameb, belb in td.bels.items():
                    bitsb = belb.mode_bits
                    common_bits = bitsa & bitsb
                    if bitsa != bitsb and common_bits:
                        print(idx, jdx, namea, "and", nameb, "have common bits:", common_bits)
                        for mode, bits in bela.modes.items():
                            mode_cb = bits & common_bits
                            if mode_cb:
                                bela.flags[mode+"C"] = mode_cb
                                bits -= mode_cb
                        for mode, bits in belb.modes.items():
                            mode_cb = bits & common_bits
                            if mode_cb:
                                belb.flags[mode+"C"] = mode_cb
                                bits -= mode_cb

def get_route_bits(db, row, col):
    """ All routing bits for the cell """
    bits = set()
    for w in db.grid[row][col].pips.values():
        for v in w.values():
            bits.update(v)
    for w in db.grid[row][col].clock_pips.values():
        for v in w.values():
            bits.update(v)
    return bits

uturnlut = {'N': 'S', 'S': 'N', 'E': 'W', 'W': 'E'}
dirlut = {'N': (1, 0),
          'E': (0, -1),
          'S': (-1, 0),
          'W': (0, 1)}
def wire2global(row, col, db, wire):
    if wire in {'VCC', 'VSS'}:
        return wire

    m = re.match(r"([NESW])([128]\d)(\d)", wire)
    if not m: # not an inter-tile wire
        return f"R{row}C{col}_{wire}"
    direction, num, segment = m.groups()

    rootrow = row + dirlut[direction][0]*int(segment)
    rootcol = col + dirlut[direction][1]*int(segment)
    # wires wrap around the edges
    # assumes 1-based indexes
    if rootrow < 1:
        rootrow = 1 - rootrow
        direction = uturnlut[direction]
    if rootcol < 1:
        rootcol = 1 - rootcol
        direction = uturnlut[direction]
    if rootrow > db.rows:
        rootrow = 2*db.rows+1 - rootrow
        direction = uturnlut[direction]
    if rootcol > db.cols:
        rootcol = 2*db.cols+1 - rootcol
        direction = uturnlut[direction]
    # map cross wires to their origin
    #name = diaglut.get(direction+num, direction+num)
    return f"R{rootrow}C{rootcol}_{direction}{num}"

def loc2pin_name(db, row, col):
    """ returns name like "IOB3" without [A,B,C...]
    """
    if row == 0:
        side = 'T'
        idx = col + 1
    elif row == db.rows - 1:
        side = 'B'
        idx =  col + 1
    elif col == 0:
        side = 'L'
        idx =  row + 1
    else:
        side = 'R'
        idx = row + 1
    return f"IO{side}{idx}"

def loc2bank(db, row, col):
    """ returns bank index '0'...'n'
    """
    bank =  db.corners.get((row, col))
    if bank == None:
        name = loc2pin_name(db, row, col)
        nameA = name + 'A'
        if nameA in db.pin_bank:
            bank = db.pin_bank[nameA]
        else:
            bank = db.pin_bank[name + 'B']
    return bank


