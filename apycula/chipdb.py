from dataclasses import dataclass, field
from typing import Dict, List, Set, Tuple, Union, ByteString, Any
from itertools import chain
import re
import copy
from functools import reduce
from collections import namedtuple
import numpy as np
import apycula.fuse_h4x as fuse
from apycula.wirenames import wirenames, clknames, clknumbers, hclknames, hclknumbers
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
    # XXX Since Himbaechel uses a system of nodes instead of aliases for clock
    # wires, at first we would like to avoid mixing in a bunch of PIPs of
    # different nature.
    pure_clock_pips: Dict[str, Dict[str, Set[Coord]]] = field(default_factory=dict)
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

    # for Himbaechel arch
    # nodes - always connected wires {node_name: (wire_type, {(row, col, wire_name)})}
    nodes: Dict[str, Tuple[str, Set[Tuple[int, int, str]]]] = field(default_factory = dict)
    # strange bottom row IO. In order for OBUF and Co. to work, one of the four
    # combinations must be applied to two special wires.
    # (wire_a, wire_b, [(wire_a_net, wire_b_net)])
    bottom_io: Tuple[str, str, List[Tuple[str, str]]] = field(default_factory = tuple)
    # simplified IO rows
    simplio_rows: Set[int] = field(default_factory = set)
    # tile types by func. The same ttyp number can correspond to different
    # functional blocks on different chips. For example 86 is the PLL head ttyp
    # for GW2A-18 and the same number is used in GW1N-1 where it has nothing to
    # do with PLL.  { type_name: {type_num} }
    tile_types: Dict[str, Set[int]] = field(default_factory = dict)
    # supported differential IO primitives
    diff_io_types: List[str] = field(default_factory = list)
    # HCLK pips depend on the location of the cell, not on the type, so they
    # are difficult to match with the deduplicated description of the tile
    # { (y, x) : pips}
    hclk_pips: Dict[Tuple[int, int], Dict[str, Dict[str, Set[Coord]]]] = field(default_factory=dict)
    # extra cell functions besides main type like
    # - OSCx
    # - GSR
    # - OSER16/IDES16
    # - ref to hclk_pips
    # - disabled blocks
    # - BUF(G)
    extra_func: Dict[Tuple[int, int], Dict[str, Any]] = field(default_factory=dict)

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

# XXX GW1N-4 and GW1NS-4 have next data in dat['CmuxIns']:
# 62 [11, 1, 126]
# 63 [11, 1, 126]
# this means that the same wire (11, 1, 126) is connected implicitly to two
# other logical wires. Let's remember such connections.
# If suddenly a command is given to assign an already used wire to another
# node, then all the contents of this node are combined with the existing one,
# and the node itself is destroyed.  only for HCLK and clock nets for now
wire2node = {}
def add_node(dev, node_name, wire_type, row, col, wire):
    if (row, col, wire) not in wire2node:
        wire2node[row, col, wire] = node_name
        dev.nodes.setdefault(node_name, (wire_type, set()))[1].add((row, col, wire))
    else:
        if node_name != wire2node[row, col, wire] and node_name in dev.nodes:
            #print(f'{node_name} -> {wire2node[row, col, wire]} share ({row}, {col}, {wire})')
            dev.nodes[wire2node[row, col, wire]][1].update(dev.nodes[node_name][1])
            del dev.nodes[node_name]

# create bels for entry potints to the global clock nets
def add_buf_bel(dev, row, col, wire, buf_type = 'BUFG'):
    # clock pins
    if not wire.startswith('CLK'):
        return
    extra_func = dev.extra_func.setdefault((row, col), {})
    if 'buf' not in extra_func or buf_type not in extra_func['buf']:
        extra_func.update({'buf': {buf_type: [wire]}})
    else:
        # dups not allowed for now
        if wire in extra_func['buf'][buf_type]:
            #print(f'extra buf dup ({row}, {col}) {buf_type}/{wire}')
            return
        extra_func['buf'][buf_type].append(wire)

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
    elif device in {'GW2A-18', 'GW2A-18C'}:
        if ttyp in {42, 45}:
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

    if device in {'GW1N-4', 'GW1N-9', 'GW1N-9C', 'GW2A-18', 'GW2A-18C'}:
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

# HCLK for Himbaechel
#
# hclk - locs of hclk control this side. The location of the HCLK is determined
# by the presence of table 48 in the 'wire' table of the cell. If there is
# such a table, then there are fuses for managing HCLK muxes. HCLK affiliation
# is determined empirically by comparing an empty image and an image with one
# OSER4 located on the side of the chip of interest.
#
# edges - how cells along this side can connect to hclk.
# Usually a specific HCLK is responsible for the nearest half side of the chip,
# but sometimes the IDE refuses to put IOLOGIC in one or two cells in the
# middle of the side, do not specify such cells as controlled by HCLK.
#
# CLK2/HCLK_OUT# - These are determined by putting two OSER4s in the same IO
# with different FCLK networks - this will force the IDE to use two ways to
# provide fast clocks to the primitives in the same cell. What exactly was used
# is determined by the fuses used and table 2 of this cell (if CLK2 was used)
# or table 48 of the HCLK responsible for this half (we already know which of
# the previous chags)

_hclk_to_fclk = {
    'GW1N-1': {
        'B': {
             'hclk': {(10, 0), (10, 19)},
             'edges': {
                 ( 1, 10) : {'CLK2', 'HCLK_OUT2'},
                 (10, 19) : {'CLK2', 'HCLK_OUT3'},
                 },
             },
        'T': {
             'edges': {
                 ( 1, 19) : {'CLK2'},
                 },
             },
        'L': {
             'edges': {
                 ( 1, 10) : {'CLK2'},
                 },
             },
        'R': {
             'edges': {
                 ( 1, 10) : {'CLK2'},
                 },
             },
        },
    'GW1NZ-1': {
        'T': {
             'hclk': {(0, 5)},
             'edges': {
                 ( 1, 10) : {'HCLK_OUT0', 'HCLK_OUT2'},
                 (10, 19) : {'HCLK_OUT1', 'HCLK_OUT3'},
                 },
             },
        'R': {
             'hclk': {(5, 19)},
             'edges': {
                 ( 1,  5) : {'HCLK_OUT0', 'HCLK_OUT2'},
                 ( 6, 10) : {'HCLK_OUT1', 'HCLK_OUT3'},
                 },
             },
        },
    'GW1NS-2': {
        'B': {
             'hclk': {(14, 0), (14, 19)},
             'edges': {
                 ( 1, 10) : {'HCLK_OUT0', 'HCLK_OUT2'},
                 (10, 19) : {'HCLK_OUT1', 'HCLK_OUT3'},
                 },
             },
        'T': {
             'hclk': {(0, 0), (0, 19)},
             'edges': {
                 ( 1, 10) : {'HCLK_OUT0', 'HCLK_OUT2'},
                 (10, 19) : {'HCLK_OUT1', 'HCLK_OUT3'},
                 },
             },
        'L': {
             'hclk': {(5, 0)},
             'edges': {
                 ( 1, 5) : {'HCLK_OUT0', 'HCLK_OUT2'},
                 ( 6, 14) : {'HCLK_OUT1', 'HCLK_OUT3'},
                 },
             },
        'R': {
             'hclk': {(5, 19)},
             'edges': {
                 ( 1, 5) : {'HCLK_OUT0', 'HCLK_OUT2'},
                 (6, 14) : {'HCLK_OUT1', 'HCLK_OUT3'},
                 },
             },
        },
    'GW1N-4': {
        'B': {
             'hclk': {(19, 0), (19, 37)},
             'edges': {
                 ( 1, 19) : {'CLK2', 'HCLK_OUT2'},
                 (19, 37) : {'CLK2', 'HCLK_OUT3'},
                 },
             },
        'T': {
             'edges': {
                 ( 1, 37) : {'CLK2'},
                 },
             },
        'L': {
             'hclk': {(9, 0)},
             'edges': {
                 ( 1, 9) : {'CLK2', 'HCLK_OUT2'},
                 (10, 19) : {'CLK2', 'HCLK_OUT3'},
                 },
             },
        'R': {
             'hclk': {(9, 37)},
             'edges': {
                 ( 1, 9) : {'CLK2', 'HCLK_OUT2'},
                 (10, 19) : {'CLK2', 'HCLK_OUT3'},
                 },
             },
        },
    'GW1NS-4': {
        'B': {
             'hclk': {(19, 16), (19, 17), (19, 20)},
             'edges': {
                 ( 1, 16) : {'HCLK_OUT0', 'HCLK_OUT2'},
                 (21, 37) : {'HCLK_OUT1', 'HCLK_OUT3'},
                 },
             },
        'T': {
             'hclk': {(0, 18)},
             'edges': {
                 ( 1, 10) : {'HCLK_OUT0', 'HCLK_OUT2'},
                 (10, 37) : {'HCLK_OUT1', 'HCLK_OUT3'},
                 },
             },
        'R': {
             'hclk': {(9, 37)},
             'edges': {
                 ( 1, 9) : {'HCLK_OUT0', 'HCLK_OUT2'},
                 (9, 19) : {'HCLK_OUT1', 'HCLK_OUT3'},
                 },
             },
        },
    'GW1N-9': {
        'B': {
             'hclk': {(28, 0), (28, 46)},
             'edges': {
                 ( 1, 28) : {'HCLK_OUT0', 'HCLK_OUT2'},
                 (28, 46) : {'HCLK_OUT1', 'HCLK_OUT3'},
                 },
             },
        'T': {
             'hclk': {(0, 0), (0, 46)},
             'edges': {
                 ( 1, 28) : {'HCLK_OUT0', 'HCLK_OUT2'},
                 (28, 46) : {'HCLK_OUT1', 'HCLK_OUT3'},
                 },
             },
        'L': {
             'hclk': {(18, 0)},
             'edges': {
                 ( 1, 19) : {'HCLK_OUT0', 'HCLK_OUT2'},
                 (19, 28) : {'HCLK_OUT1', 'HCLK_OUT3'},
                 },
             },
        'R': {
             'hclk': {(18, 46)},
             'edges': {
                 ( 1, 19) : {'HCLK_OUT0', 'HCLK_OUT2'},
                 (19, 28) : {'HCLK_OUT1', 'HCLK_OUT3'},
                 },
             },
        },
    'GW1N-9C': {
        'B': {
             'hclk': {(28, 0), (28, 46)},
             'edges': {
                 ( 1, 46) : {'HCLK_OUT1', 'HCLK_OUT3'},
                 },
             },
        'T': {
             'hclk': {(0, 0), (0, 46)},
             'edges': {
                 ( 1, 46) : {'HCLK_OUT1', 'HCLK_OUT3'},
                 },
             },
        'L': {
             'hclk': {(18, 0)},
             'edges': {
                 ( 1, 28) : {'HCLK_OUT1', 'HCLK_OUT3'},
                 },
             },
        'R': {
             'hclk': {(18, 46)},
             'edges': {
                 ( 1, 28) : {'HCLK_OUT1', 'HCLK_OUT3'},
                 },
             },
        },
    'GW2A-18': {
        'B': {
             'hclk': {(54, 27), (54, 28)},
             'edges': {
                 ( 1, 27) : {'HCLK_OUT0', 'HCLK_OUT2'},
                 (29, 55) : {'HCLK_OUT1', 'HCLK_OUT3'},
                 },
             },
        'T': {
             'hclk': {(0, 27), (0, 28)},
             'edges': {
                 ( 1, 27) : {'HCLK_OUT0', 'HCLK_OUT2'},
                 (29, 55) : {'HCLK_OUT1', 'HCLK_OUT3'},
                 },
             },
        'L': {
             'hclk': {(27, 0)},
             'edges': {
                 ( 1, 27) : {'HCLK_OUT0', 'HCLK_OUT2'},
                 (28, 55) : {'HCLK_OUT1', 'HCLK_OUT3'},
                 },
             },
        'R': {
             'hclk': {(27, 55)},
             'edges': {
                 ( 1, 27) : {'HCLK_OUT0', 'HCLK_OUT2'},
                 (28, 55) : {'HCLK_OUT1', 'HCLK_OUT3'},
                 },
             },
        },
    'GW2A-18C': {
        'B': {
             'hclk': {(54, 27), (54, 28)},
             'edges': {
                 ( 1, 27) : {'HCLK_OUT0', 'HCLK_OUT2'},
                 (29, 55) : {'HCLK_OUT1', 'HCLK_OUT3'},
                 },
             },
        'T': {
             'hclk': {(0, 27), (0, 28)},
             'edges': {
                 ( 1, 27) : {'HCLK_OUT0', 'HCLK_OUT2'},
                 (29, 55) : {'HCLK_OUT1', 'HCLK_OUT3'},
                 },
             },
        'L': {
             'hclk': {(27, 0)},
             'edges': {
                 ( 1, 27) : {'HCLK_OUT0', 'HCLK_OUT2'},
                 (28, 55) : {'HCLK_OUT1', 'HCLK_OUT3'},
                 },
             },
        'R': {
             'hclk': {(27, 55)},
             'edges': {
                 ( 1, 27) : {'HCLK_OUT0', 'HCLK_OUT2'},
                 (28, 55) : {'HCLK_OUT1', 'HCLK_OUT3'},
                 },
             },
        },
}

_global_wire_prefixes = {'PCLK', 'TBDHCLK', 'BBDHCLK', 'RBDHCLK', 'LBDHCLK',
                         'TLPLL', 'TRPLL', 'BLPLL', 'BRPLL'}
def fse_create_hclk_nodes(dev, device, fse, dat):
    # XXX
    if device not in _hclk_to_fclk:
        return
    hclk_info = _hclk_to_fclk[device]
    for side in 'BRTL':
        if side not in hclk_info:
            continue

        # create HCLK nodes
        hclks = {}
        # entries to the HCLK from logic
        for hclk_idx, row, col, wire_idx in {(i, dat['CmuxIns'][str(i - 80)][0] - 1, dat['CmuxIns'][str(i - 80)][1] - 1, dat['CmuxIns'][str(i - 80)][2]) for i in range(hclknumbers['TBDHCLK0'], hclknumbers['RBDHCLK3'] + 1)}:
            if row != -2:
                add_node(dev, hclknames[hclk_idx], "HCLK", row, col, wirenames[wire_idx])
                # XXX clock router is doing fine with HCLK w/o any buffering
                # may be placement suffers a bit
                #add_buf_bel(dev, row, col, wirenames[wire_idx], buf_type = 'BUFH')

        if 'hclk' in hclk_info[side]:
            # create HCLK cells pips
            for hclk_loc in hclk_info[side]['hclk']:
                row, col = hclk_loc
                ttyp = fse['header']['grid'][61][row][col]
                dev.hclk_pips[(row, col)] = fse_pips(fse, ttyp, table = 48, wn = hclknames)
                # connect local wires like PCLKT0 etc to the global nodes
                for srcs in dev.hclk_pips[(row, col)].values():
                    for src in srcs.keys():
                        for pfx in _global_wire_prefixes:
                            if src.startswith(pfx):
                                add_node(dev, src, "HCLK", row, col, src)
                # strange GW1N-9C input-input aliases
                for i in {0, 2}:
                    dev.nodes.setdefault(f'X{col}Y{row}/HCLK9-{i}', ('HCLK', {(row, col, f'HCLK_IN{i}')}))[1].add((row, col, f'HCLK_9IN{i}'))

            for i in range(4):
                hnam = f'HCLK_OUT{i}'
                wires = dev.nodes.setdefault(f'{side}{hnam}', ("HCLK", set()))[1]
                hclks[hnam] = wires
                for hclk_loc in hclk_info[side]['hclk']:
                    row, col = hclk_loc
                    wires.add((row, col, hnam))

        # create pips from HCLK spines to FCLK inputs of IO logic
        for edge, srcs in hclk_info[side]['edges'].items():
            if side in 'TB':
                row = {'T': 0, 'B': dev.rows - 1}[side]
                for col in range(edge[0], edge[1]):
                    if 'IOLOGICA' not in dev.grid[row][col].bels:
                        continue
                    pips = dev.hclk_pips.setdefault((row, col), {})
                    for dst in 'AB':
                        for src in srcs:
                            pips.setdefault(f'FCLK{dst}', {}).update({src: set()})
                            if src.startswith('HCLK'):
                                hclks[src].add((row, col, src))
            else:
                col = {'L': 0, 'R': dev.cols - 1}[side]
                for row in range(edge[0], edge[1]):
                    if 'IOLOGICA' not in dev.grid[row][col].bels:
                        continue
                    pips = dev.hclk_pips.setdefault((row, col), {})
                    for dst in 'AB':
                        for src in srcs:
                            pips.setdefault(f'FCLK{dst}', {}).update({src: set()})
                            if src.startswith('HCLK'):
                                hclks[src].add((row, col, src))

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
 'GW2A-18':
   {'TLPLL0CLK0': (9, 2, 'F4'), 'TLPLL0CLK1': (9, 2, 'F7'),
    'TLPLL0CLK2': (9, 2, 'F5'), 'TLPLL0CLK3': (9, 2, 'F6'),
    'TRPLL0CLK0': (9, 53, 'F4'), 'TRPLL0CLK1': (9, 53, 'F7'),
    'TRPLL0CLK2': (9, 53, 'F5'), 'TRPLL0CLK3': (9, 53, 'F6'),
    'BLPLL0CLK0': (45, 2, 'F4'), 'BLPLL0CLK1': (45, 2, 'F7'),
    'BLPLL0CLK2': (45, 2, 'F5'), 'BLPLL0CLK3': (45, 2, 'F6'),
    'BRPLL0CLK0': (45, 53, 'F4'), 'BRPLL0CLK1': (45, 53, 'F7'),
    'BRPLL0CLK2': (45, 53, 'F5'), 'BRPLL0CLK3': (45, 53, 'F6'), },
 'GW2A-18C':
   {'TLPLL0CLK0': (9, 2, 'F4'), 'TLPLL0CLK1': (9, 2, 'F7'),
    'TLPLL0CLK2': (9, 2, 'F5'), 'TLPLL0CLK3': (9, 2, 'F6'),
    'TRPLL0CLK0': (9, 53, 'F4'), 'TRPLL0CLK1': (9, 53, 'F7'),
    'TRPLL0CLK2': (9, 53, 'F5'), 'TRPLL0CLK3': (9, 53, 'F6'),
    'BLPLL0CLK0': (45, 2, 'F4'), 'BLPLL0CLK1': (45, 2, 'F7'),
    'BLPLL0CLK2': (45, 2, 'F5'), 'BLPLL0CLK3': (45, 2, 'F6'),
    'BRPLL0CLK0': (45, 53, 'F4'), 'BRPLL0CLK1': (45, 53, 'F7'),
    'BRPLL0CLK2': (45, 53, 'F5'), 'BRPLL0CLK3': (45, 53, 'F6'), },
}

def fse_create_pll_clock_aliases(db, device):
    # we know exactly where the PLL is and therefore know which aliases to create
    for row in range(db.rows):
        for col in range(db.cols):
            for w_dst, w_srcs in db.grid[row][col].clock_pips.items():
                for w_src in w_srcs.keys():
                    if device in {'GW1N-1', 'GW1NZ-1', 'GW1NS-2', 'GW1NS-4', 'GW1N-4', 'GW1N-9C', 'GW1N-9', 'GW2A-18', 'GW2A-18C'}:
                        if w_src in _pll_loc[device].keys():
                            db.aliases[(row, col, w_src)] = _pll_loc[device][w_src]
                            # Himbaechel node
                            db.nodes.setdefault(w_src, ("PLL_O", set()))[1].add((row, col, w_src))
            # Himbaechel HCLK
            if (row, col) in db.hclk_pips:
                for w_dst, w_srcs in db.hclk_pips[row, col].items():
                    for w_src in w_srcs.keys():
                        if device in {'GW1N-1', 'GW1NZ-1', 'GW1NS-2', 'GW1NS-4', 'GW1N-4', 'GW1N-9C', 'GW1N-9', 'GW2A-18', 'GW2A-18C'}:
                            if w_src in _pll_loc[device]:
                                db.nodes.setdefault(w_src, ("PLL_O", set()))[1].add((row, col, w_src))

# from Gowin Programmable IO (GPIO) User Guide:
#
# IOL6 and IOR6 pins of devices of GW1N-1, GW1NR-1, GW1NZ-1, GW1NS-2,
# GW1NS-2C, GW1NSR-2C, GW1NSR-2 and GW1NSE-2C do not support IO logic.
# IOT2 and IOT3A pins of GW1N-2, GW1NR-2, GW1N-1P5, GW1N-2B, GW1N-1P5B,
# GW1NR-2B devices do not support IO logic.
# IOL10 and IOR10 pins of the devices of GW1N-4, GW1N-4B, GW1NR-4, GW1NR-4B,
# ==========================================================================
# These are cells along the edges of the chip and their types are taken from
# fse['header']['grid'][61][row][col] and it was checked whether or not the IDE
# would allow placing IOLOGIC there.
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
    if device in {'GW1NS-4'} and ttyp in {142, 143, 144, 58, 59}:
            bels['OSER16'] = Bel()
            bels['IDES16'] = Bel()
    if device in {'GW1N-9', 'GW1N-9C'} and ttyp in {52, 66, 63, 91, 92}:
            bels['OSER16'] = Bel()
            bels['IDES16'] = Bel()
    return bels

# create clock aliases
# to understand how the clock works in gowin, it is useful to read the experiments of Pepijndevos
# https://github.com/YosysHQ/apicula/blob/master/clock_experiments.ipynb
# especially since I was deriving everything based on that information.

# It is impossible to get rid of fuzzing, the difference is that I do it
# manually to check the observed patterns and assumptions, and then
# programmatically fix the found formulas.

# We have 8 clocks, which are divided into two parts: 0-3 and 4-7. They are
# located in pairs: 0 and 4, 1 and 5, 2 and 6, 3 and 7. From here it is enough
# to consider only the location of wires 0-3.

# So tap_start describes along which column the wire of a particular clock is located.
# This is derived from the Out[26] table (see
# https://github.com/YosysHQ/apicula/blob/master/clock_experiments.ipynb)
# The index in [1, 0, 3, 2] is the relative position of tap (hence tap_start)
# in the four column space.
# tap column 0 -> clock #1
# tap column 1 -> clock #0
# tap column 2 -> clock #3
# tap column 3 -> clock #2
# Out[26] also implies the repeatability of the columns, here it is fixed as a formula:
# (tap column) % 4 -> clock #
# for example 6 % 4 -> clock #3

# If you look closely at Out[26], then we can say that the formula breaks
# starting from a certain column number. But it's not. Recall that we have at
# least two quadrants located horizontally and at some point there is a
# transition to another quadrant and these four element parts must be counted
# from a new beginning.

# To determine where the left quadrant ends, look at dat['center'] - the
# coordinates of the "central" cell of the chip are stored there. The number of
# the column indicated there is the last column of the left quadrant.

# It is enough to empirically determine the correspondence of clocks and
# speakers in the new quadrant (even three clocks is enough, since the fourth
# becomes obvious).
# [3, 2, 1, 0] turned out to be the unwritten standard for all the chips studied.

# We're not done with that yet - what matters is how the columns of each
# quadrant end.
# For GW1N-1 dat['center'] = [6, 10]
# From Out[26]: 5: {4, 5, 6, 7, 8, 9}, why is the 5th column responsible not
# for four, but for so many columns, including the end of the quadrant, column
# 9 (we have a 0 based system, remember)?
# We cannot answer this question, but based on observations we can formulate a
# rule: after the tap-column there must be a place for one more column,
# otherwise all columns are assigned to the previous one. Let's see Out[26]:
# 5: {4, 5, 6, 7, 8, 9} can't use column 9 because there is no space for one more
# 8: {7, 8, 9}       ok, although not a complete four, we are at a sufficient distance from column 9
# 7: {6, 7, 8, 9}    ok, full four
# 6: {5, 6, 7, 8, 9},   can't use column 10 - wrong quadrant

# 'quads': {( 6, 0, 11, 2, 3)}
# 6 - row of spine->tap
# 0, 11 - segment is located between these rows
# 2, 3 - this is the simplest - left and right quadrant numbers.
# The quadrants are numbered like this:
#  1 | 0
# ------   moreover, two-quadrant chips have only quadrants 2 and 3
#  2 | 3
# Determining the boundary between vertical quadrants and even which line
# contains spine->tap is not as easy as determining the vertical boundary
# between segments. This is done empirically by placing a test DFF along the
# column until the moment of changing the row of muxes is caught.
#
# A bit about the nature of Central (Clock?) mux: wherever there is
# ['wire'][38] some clocks are switched somewhere. That is, this is such a huge
# mux spread over the chip, and this is how we describe it for nextpnr - the
# wires of the same name involved in some kind of switching anywhere in the
# chip are combined into one Himbaechel node. Further, when routing, there is
# already a choice of which pip to use and which cell.
# It also follows that for the Himbaechel watch wires should not be mixed
# together with any other  wires. At least I came to this conclusion and that
# is why the HCLK wires, which have the same numbers as the watch spines, are
# stored separately.

# dat['CmuxIns'] and 80 - here, the places of entry points into the clock
# system are stored in the form [row, col, wire], that is, in order to send a
# signal for propagation through the global clock network, you need to send it
# to this particular wire in this cell. In most cases it will not be possible
# to connect to this wire as they are basically outputs (IO output, PLL output
# etc).

# Let's look at the dat['CmuxIns'] fragment for GW1N-1. We know that this board
# has an external clock generator connected to the IOR5A pin and this is one of
# the PCLKR clock wires (R is for right here). We see that this is index 47,
# and index 48 belongs to another pin on the same side of the chip. If we
# consider the used fuses from the ['wire'][38] table on the simplest example,
# we will see that 47 corresponds to the PCLKR0 wire, whose index in the
# clknames table (irenames.py) is 127.
# For lack of a better way, we assume that the indexes in the dat['CmuxIns']
# table are the wire numbers in clknames minus 80.

# We check on a couple of other chips and leave it that way. This is neither the
# best nor the worst method in the absence of documentation about the internal
# structure of the chip.

# 38 [-1, -1, -1]
# 39 [-1, -1, -1]
# 40 [-1, -1, -1]
# 41 [-1, -1, -1]
# 42 [-1, -1, -1]
# 43 [11, 10, 38]
# 44 [11, 11, 38]
# 45 [5, 1, 38]
# 46 [7, 1, 38]
# 47 [5, 20, 38]    <==  IOR5A (because of 38 = F6)
# 48 [7, 20, 38]
# 49 [1, 11, 124]
# 50 [1, 11, 125]
# 51 [6, 20, 124]

_clock_data = {
        'GW1N-1':  { 'tap_start': [[1, 0, 3, 2], [3, 2, 1, 0]], 'quads': {( 6, 0, 11, 2, 3)}},
        'GW1NZ-1': { 'tap_start': [[1, 0, 3, 2], [3, 2, 1, 0]], 'quads': {( 6, 0, 11, 2, 3)}},
        'GW1NS-2': { 'tap_start': [[1, 0, 3, 2], [3, 2, 1, 0]], 'quads': {( 6, 0, 15, 2, 3)}},
        'GW1N-4':  { 'tap_start': [[2, 1, 0, 3], [3, 2, 1, 0]], 'quads': {(10, 0, 20, 2, 3)}},
        'GW1NS-4': { 'tap_start': [[2, 1, 0, 3], [3, 2, 1, 0]], 'quads': {(10, 0, 20, 2, 3)}},
        'GW1N-9':  { 'tap_start': [[3, 2, 1, 0], [3, 2, 1, 0]], 'quads': {( 1, 0, 10, 1, 0), (19, 10, 29, 2, 3)}},
        'GW1N-9C': { 'tap_start': [[3, 2, 1, 0], [3, 2, 1, 0]], 'quads': {( 1, 0, 10, 1, 0), (19, 10, 29, 2, 3)}},
        'GW2A-18': { 'tap_start': [[3, 2, 1, 0], [3, 2, 1, 0]], 'quads': {(10, 0, 28, 1, 0), (46, 28, 55, 2, 3)}},
        'GW2A-18C': { 'tap_start': [[3, 2, 1, 0], [3, 2, 1, 0]], 'quads': {(10, 0, 28, 1, 0), (46, 28, 55, 2, 3)}},
        }
def fse_create_clocks(dev, device, dat, fse):
    center_col = dat['center'][1] - 1
    clkpin_wires = {}
    taps = {}
    # find center muxes
    for clk_idx, row, col, wire_idx in {(i, dat['CmuxIns'][str(i - 80)][0] - 1, dat['CmuxIns'][str(i - 80)][1] - 1, dat['CmuxIns'][str(i - 80)][2]) for i in range(clknumbers['PCLKT0'], clknumbers['PCLKR1'] + 1)}:
        if row != -2:
            add_node(dev, clknames[clk_idx], "GLOBAL_CLK", row, col, wirenames[wire_idx])
            add_buf_bel(dev, row, col, wirenames[wire_idx])

    spines = {f'SPINE{i}' for i in range(32)}
    for row, rd in enumerate(dev.grid):
        for col, rc in enumerate(rd):
            for dest, srcs in rc.pure_clock_pips.items():
                for src in srcs.keys():
                    if src in spines and not dest.startswith('GT'):
                        add_node(dev, src, "GLOBAL_CLK", row, col, src)
                if dest in spines:
                    add_node(dev, dest, "GLOBAL_CLK", row, col, dest)
                    for src in { wire for wire in srcs.keys() if wire not in {'VCC', 'VSS'}}:
                        add_node(dev, src, "GLOBAL_CLK", row, col, src)
    # GBx0 <- GBOx
    for spine_pair in range(4): # GB00/GB40, GB10/GB50, GB20/GB60, GB30/GB70
        tap_start = _clock_data[device]['tap_start'][0]
        tap_col = tap_start[spine_pair]
        last_col = center_col
        for col in range(dev.cols):
            if col == center_col + 1:
                tap_start = _clock_data[device]['tap_start'][1]
                tap_col = tap_start[spine_pair] + col
                last_col = dev.cols -1
            if (col > tap_col + 2) and (tap_col + 4 < last_col):
                tap_col += 4
            taps.setdefault(spine_pair, {}).setdefault(tap_col, set()).add(col)
    for row in range(dev.rows):
        for spine_pair, tap_desc in taps.items():
            for tap_col, cols in tap_desc.items():
                node0_name = f'X{tap_col}Y{row}/GBO0'
                dev.nodes.setdefault(node0_name, ("GLOBAL_CLK", set()))[1].add((row, tap_col, 'GBO0'))
                node1_name = f'X{tap_col}Y{row}/GBO1'
                dev.nodes.setdefault(node1_name, ("GLOBAL_CLK", set()))[1].add((row, tap_col, 'GBO1'))
                for col in cols:
                    dev.nodes.setdefault(node0_name, ("GLOBAL_CLK", set()))[1].add((row, col, f'GB{spine_pair}0'))
                    dev.nodes.setdefault(node1_name, ("GLOBAL_CLK", set()))[1].add((row, col, f'GB{spine_pair + 4}0'))

    # GTx0 <- center row GTx0
    for spine_row, start_row, end_row, qno_l, qno_r in _clock_data[device]['quads']:
        for spine_pair, tap_desc in taps.items():
            for tap_col, cols in tap_desc.items():
                if tap_col < center_col:
                    quad = qno_l
                else:
                    quad = qno_r
                for col in cols - {center_col}:
                    node0_name = f'X{col}Y{spine_row}/GT00'
                    dev.nodes.setdefault(node0_name, ("GLOBAL_CLK", set()))[1].add((spine_row, col, 'GT00'))
                    node1_name = f'X{col}Y{spine_row}/GT10'
                    dev.nodes.setdefault(node1_name, ("GLOBAL_CLK", set()))[1].add((spine_row, col, 'GT10'))
                    for row in range(start_row, end_row):
                        if row == spine_row:
                            if col == tap_col:
                                spine = quad * 8 + spine_pair
                                dev.nodes.setdefault(f'SPINE{spine}', ("GLOBAL_CLK", set()))[1].add((row, col, f'SPINE{spine}'))
                                # XXX skip clock 6 and 7 for now
                                if spine_pair not in {2, 3}:
                                    dev.nodes.setdefault(f'SPINE{spine + 4}', ("GLOBAL_CLK", set()))[1].add((row, col, f'SPINE{spine + 4}'))
                        else:
                            dev.nodes.setdefault(node0_name, ("GLOBAL_CLK", set()))[1].add((row, col, 'GT00'))
                            dev.nodes.setdefault(node1_name, ("GLOBAL_CLK", set()))[1].add((row, col, 'GT10'))

# These features of IO on the underside of the chip were revealed during
# operation. The first (normal) mode was found in a report by @LoneTech on
# 4/1/2022, when it turned out that the pins on the bottom edge of the GW1NR-9
# require voltages to be applied to strange wires to function.

# The second mode was discovered when the IOLOGIC implementation appeared and
# it turned out that even ODDR does not work without applying other voltages.
# Other applications of these wires are not yet known.

# function 0 - usual io
# function 1 - DDR
def fse_create_bottom_io(dev, device):
    if device in {'GW1NS-4', 'GW1N-9C'}:
        dev.bottom_io = ('D6', 'C6', [('VSS', 'VSS'), ('VCC', 'VSS')])
    elif device in {'GW1N-9'}:
        dev.bottom_io = ('A6', 'CE2', [('VSS', 'VSS'), ('VCC', 'VSS')])
    else:
        dev.bottom_io = ('', '', [])

# It was noticed that the "simplified" IO line matched the BRAM line, whose
# position can be found from dat['grid']. Later this turned out to be not very
# true - for chips other than GW1N-1 IO in these lines may be with reduced
# functionality, or may be normal.  It may be worth renaming these lines to
# BRAM-rows, but for now this is an acceptable mechanism for finding
# non-standard IOs, taking into account the chip series, eliminating the
# "magic" coordinates.
def fse_create_simplio_rows(dev, dat):
    for row, rd in enumerate(dat['grid']):
        if [r for r in rd if r in "Bb"]:
            if row > 0:
                row -= 1
            if row == dev.rows:
                row -= 1
            dev.simplio_rows.add(row)

def fse_create_tile_types(dev, dat):
    type_chars = 'PCMI'
    for fn in type_chars:
        dev.tile_types[fn] = set()
    for row, rd in enumerate(dat['grid']):
        for col, fn in enumerate(rd):
            if fn in type_chars:
                i = row
                if i > 0:
                    i -= 1
                if i == dev.rows:
                    i -= 1
                j = col
                if j > 0:
                    j -= 1
                if j == dev.cols:
                    j -= 1
                dev.tile_types[fn].add(dev.grid[i][j].ttyp)

def fse_create_diff_types(dev, device):
    dev.diff_io_types = ['ELVDS_IBUF', 'ELVDS_OBUF', 'ELVDS_IOBUF', 'ELVDS_TBUF',
                         'TLVDS_IBUF', 'TLVDS_OBUF', 'TLVDS_IOBUF', 'TLVDS_TBUF']
    if device == 'GW1NZ-1':
        dev.diff_io_types.remove('TLVDS_IBUF')
        dev.diff_io_types.remove('TLVDS_OBUF')
        dev.diff_io_types.remove('TLVDS_TBUF')
        dev.diff_io_types.remove('TLVDS_IOBUF')
        dev.diff_io_types.remove('ELVDS_IOBUF')
    elif device == 'GW1N-1':
        dev.diff_io_types.remove('TLVDS_OBUF')
        dev.diff_io_types.remove('TLVDS_TBUF')
        dev.diff_io_types.remove('TLVDS_IOBUF')
        dev.diff_io_types.remove('ELVDS_IOBUF')
    elif device not in {'GW2A-18', 'GW2A-18C', 'GW1N-4'}:
        dev.diff_io_types.remove('TLVDS_IOBUF')

def fse_create_io16(dev, device):
    # 16-bit serialization/deserialization primitives occupy two consecutive
    # cells. For the top and bottom sides of the chip, this means that the
    # "main" cell is located in the column with a lower number, and for the
    # sides of the chip - in the row with a lower number.

    # But the IDE does not allow placing OSER16/IDES16 in all cells of a
    # row/column. Valid ranges are determined by placing the OSER16 primitive
    # sequentially (at intervals of 2 since all "master" cells are either odd
    # or even) along the side of the chip one at a time and compiling with the
    # IDE.

    # It is unlikely that someone will need to repeat this work since OSER16 /
    # IDES16 were only in three chips and these primitives simply do not exist
    # in the latest series.

    df = dev.extra_func
    if device in {'GW1N-9', 'GW1N-9C'}:
        for i in chain(range(1, 8, 2), range(10, 17, 2), range(20, 35, 2), range(38, 45, 2)):
            df.setdefault((0, i), {})['io16'] = {'role': 'MAIN', 'pair': (0, 1)}
            df.setdefault((0, i + 1), {})['io16'] = {'role': 'AUX', 'pair': (0, -1)}
            df.setdefault((dev.rows - 1, i), {})['io16'] = {'role': 'MAIN', 'pair': (0, 1)}
            df.setdefault((dev.rows - 1, i + 1), {})['io16'] = {'role': 'AUX', 'pair': (0, -1)}
    elif device in {'GW1NS-4'}:
        for i in chain(range(1, 8, 2), range(10, 17, 2), range(20, 26, 2), range(28, 35, 2)):
            df.setdefault((0, i), {})['io16'] = {'role': 'MAIN', 'pair': (0, 1)}
            df.setdefault((0, i + 1), {})['io16'] = {'role': 'AUX', 'pair': (0, -1)}
            if i < 17:
                df.setdefault((i, dev.cols - 1), {})['io16'] = {'role': 'MAIN', 'pair': (1, 0)}
                df.setdefault((i + 1, dev.cols - 1), {})['io16'] = {'role': 'AUX', 'pair': (-1, 0)}

# (osc-type, devices) : ({local-ports}, {aliases})
_osc_ports = {('OSCZ', 'GW1NZ-1'): ({}, {'OSCOUT' : (0, 5, 'OF3'), 'OSCEN': (0, 2, 'A6')}),
              ('OSCZ', 'GW1NS-4'): ({'OSCOUT': 'Q4', 'OSCEN': 'D6'}, {}),
              ('OSCF', 'GW1NS-2'): ({}, {'OSCOUT': (10, 19, 'Q4'), 'OSCEN': (13, 19, 'B3')}),
              ('OSCH', 'GW1N-1'):  ({'OSCOUT': 'Q4'}, {}),
              ('OSC',  'GW1N-4'):  ({'OSCOUT': 'Q4'}, {}),
              ('OSC',  'GW1N-9'):  ({'OSCOUT': 'Q4'}, {}),
              ('OSC',  'GW1N-9C'):  ({'OSCOUT': 'Q4'}, {}),
              ('OSC',  'GW2A-18'):  ({'OSCOUT': 'Q4'}, {}),
              ('OSC',  'GW2A-18C'):  ({'OSCOUT': 'Q4'}, {}),
              # XXX unsupported boards, pure theorizing
              ('OSCO', 'GW1N-2'):  ({'OSCOUT': 'Q7'}, {'OSCEN': (9, 1, 'B4')}),
              ('OSCW', 'GW2AN-18'):  ({'OSCOUT': 'Q4'}, {}),
              }

# from logic to global clocks. An interesting piece of dat['CmuxIns'], it was
# found out experimentally that this range is responsible for the wires
# 129: 'TRBDCLK0' - 152: 'TRMDCLK1'. Again we have a shift of 80 from the wire number
# (see create clock aliases).
# 124-126 equal CLK0-CLK2 so these are clearly inputs to the clock system
# (GW1N-1 data)
# 49 [1, 11, 124]
# 50 [1, 11, 125]
# 51 [6, 20, 124]
# 52 [6, 20, 125]
# 53 [1, 10, 125]
# 54 [6, 1, 124]
# 55 [6, 1, 125]
# 56 [1, 10, 124]
# 57 [11, 11, 124]
# 58 [11, 11, 125]
# 59 [7, 20, 126]
# 60 [8, 20, 126]
# 61 [11, 10, 125]
# 62 [7, 1, 126]
# 63 [8, 1, 126]
# 64 [11, 10, 124]
# 65 [-1, -1, -1]
# 66 [-1, -1, -1]
# 67 [-1, -1, -1]
# 68 [-1, -1, -1]
# 69 [-1, -1, -1]
# 70 [-1, -1, -1]
# 71 [6, 10, 126]
# 72 [6, 11, 126]
# We don't need to worry about routing TRBDCLK0 and the family - this was
# already done when we created pure clock pips. But what we need to do is
# indicate that these CLKs at these coordinates are TRBDCLK0, etc. Therefore,
# we create Himbaechel nodes.
def fse_create_logic2clk(dev, device, dat):
    for clkwire_idx, row, col, wire_idx in {(i, dat['CmuxIns'][str(i - 80)][0] - 1, dat['CmuxIns'][str(i - 80)][1] - 1, dat['CmuxIns'][str(i - 80)][2]) for i in range(clknumbers['TRBDCLK0'], clknumbers['TRMDCLK1'] + 1)}:
        if row != -2:
            add_node(dev, clknames[clkwire_idx], "GLOBAL_CLK", row, col, wirenames[wire_idx])
            add_buf_bel(dev, row, col, wirenames[wire_idx])

def fse_create_osc(dev, device, fse):
    for row, rd in enumerate(dev.grid):
        for col, rc in enumerate(rd):
            if 51 in fse[rc.ttyp]['shortval']:
                osc_type = list(fse_osc(device, fse, rc.ttyp).keys())[0]
                dev.extra_func.setdefault((row, col), {}).update(
                        {'osc': {'type': osc_type}})
                _, aliases = _osc_ports[osc_type, device]
                for port, alias in aliases.items():
                    dev.nodes.setdefault(f'X{col}Y{row}/{port}', (port, {(row, col, port)}))[1].add(alias)

def fse_create_gsr(dev, device):
    # Since, in the general case, there are several cells that have a
    # ['shortval'][20] table, in this case we do a test example with the GSR
    # primitive (Gowin Primitives User Guide.pdf - GSR), connect the GSRI input
    # to the button and see how the routing has changed in which of the
    # previously found cells.
    row, col = (0, 0)
    if device in {'GW2A-18', 'GW2A-18C'}:
        row, col = (27, 50)
    dev.extra_func.setdefault((row, col), {}).update(
        {'gsr': {'wire': 'C4'}})

def disable_plls(dev, device):
    if device in {'GW2A-18C'}:
        # (9, 0) and (9, 55) are the coordinates of cells when trying to place
        # a PLL in which the IDE gives an error.
        dev.extra_func.setdefault((9, 0), {}).setdefault('disabled', {}).update({'PLL': True})
        dev.extra_func.setdefault((9, 55), {}).setdefault('disabled', {}).update({'PLL': True})

def sync_extra_func(dev):
    for loc, pips in dev.hclk_pips.items():
        row, col = loc
        dev.extra_func.setdefault((row, col), {})['hclk_pips'] = pips

def from_fse(device, fse, dat):
    dev = Device()
    fse_create_simplio_rows(dev, dat)
    ttypes = {t for row in fse['header']['grid'][61] for t in row}
    tiles = {}
    for ttyp in ttypes:
        w = fse[ttyp]['width']
        h = fse[ttyp]['height']
        tile = Tile(w, h, ttyp)
        tile.pips = fse_pips(fse, ttyp, 2, wirenames)
        tile.clock_pips = fse_pips(fse, ttyp, 38, clknames)
        # copy for Himbaechel without hclk
        tile.pure_clock_pips = copy.deepcopy(tile.clock_pips)
        tile.clock_pips.update(fse_hclk_pips(fse, ttyp, tile.aliases))
        tile.alonenode_6 = fse_alonenode(fse, ttyp, 6)
        if 5 in fse[ttyp]['shortval']:
            tile.bels = fse_luts(fse, ttyp)
        if 51 in fse[ttyp]['shortval']:
            tile.bels = fse_osc(device, fse, ttyp)
        # These are the cell types in which PLLs can be located. To determine,
        # we first take the coordinates of the cells with the letters P and p
        # from the dat['grid'] table, and then, using these coordinates,
        # determine the type from fse['header']['grid'][61][row][col]
        if ttyp in [42, 45, 74, 75, 76, 77, 78, 79, 86, 87, 88, 89]:
            tile.bels = fse_pll(device, fse, ttyp)
        tile.bels.update(fse_iologic(device, fse, ttyp))
        tiles[ttyp] = tile

    fse_fill_logic_tables(dev, fse)
    dev.grid = [[tiles[ttyp] for ttyp in row] for row in fse['header']['grid'][61]]
    fse_create_clocks(dev, device, dat, fse)
    fse_create_pll_clock_aliases(dev, device)
    fse_create_hclk_aliases(dev, device, dat)
    fse_create_bottom_io(dev, device)
    fse_create_tile_types(dev, dat)
    fse_create_diff_types(dev, device)
    fse_create_hclk_nodes(dev, device, fse, dat)
    fse_create_io16(dev, device)
    fse_create_osc(dev, device, fse)
    fse_create_gsr(dev, device)
    fse_create_logic2clk(dev, device, dat)
    disable_plls(dev, device)
    sync_extra_func(dev)
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
    if device not in {"GW1N-1", "GW1NZ-1", "GW1N-4", "GW1N-9", "GW1NR-9", "GW1N-9C", "GW1NR-9C", "GW1NS-2", "GW1NS-2C", "GW1NS-4", "GW1NSR-4C", "GW2A-18", "GW2A-18C", "GW2AR-18C"}:
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
    elif device == "GW2A-18":
        pkgs, pins, bank_pins = get_pins("GW2A-18")
        return (pkgs, {
            "GW2A-18": pins
        }, bank_pins)
    elif device == "GW2A-18C":
        pkgs, pins, bank_pins = get_pins("GW2A-18C")
        pkgs_r, pins_r, bank_pins_r = get_pins("GW2AR-18C")
        res = {}
        res.update(pkgs)
        res.update(pkgs_r)
        res_bank_pins = {}
        res_bank_pins.update(bank_pins)
        res_bank_pins.update(bank_pins_r)
        return (res, {
            "GW2A-18C": pins,
            "GW2AR-18C": pins_r
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
def get_pllout_global_name(row, col, wire, device):
    for name, loc in _pll_loc[device].items():
        if loc == (row, col, wire):
            return name
    raise Exception(f"bad PLL output {device} ({row}, {col}){wire}")

def dat_portmap(dat, dev, device):
    for row, row_dat in enumerate(dev.grid):
        for col, tile in enumerate(row_dat):
            for name, bel in tile.bels.items():
                if bel.portmap:
                    # GW2A has same PLL in different rows
                    if not (name.startswith("RPLLA") and device in {'GW2A-18', 'GW2A-18C'}):
                        continue
                if name.startswith("IOB"):
                    if row in dev.simplio_rows:
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
                        if row == dev.rows - 1:
                            # bottom io
                            bel.portmap['BOTTOM_IO_PORT_A'] = dev.bottom_io[0]
                            bel.portmap['BOTTOM_IO_PORT_B'] = dev.bottom_io[1]
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
                    if device in {'GW1N-9C', 'GW1N-9', 'GW2A-18', 'GW2A-18C'}:
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
                            # Himbaechel node
                            dev.nodes.setdefault(f'X{col}Y{row}/rPLL{nam}{wire}', ("PLL_I", {(row, col, f'rPLL{nam}{wire}')}))[1].add((row, col + off, wire))

                    for idx, nam in _pll_outputs:
                        wire = wirenames[dat['PllOut'][idx]]
                        off = dat['PllOutDlt'][idx] * offx
                        if off == 0 or device in {'GW1NS-2'}:
                            bel.portmap[nam] = wire
                        else:
                            # not our cell, make an alias
                            bel.portmap[nam] = f'rPLL{nam}{wire}'
                            dev.aliases[row, col, f'rPLL{nam}{wire}'] = (row, col + off, wire)
                        # Himbaechel node
                        if nam != 'LOCK':
                            global_name = get_pllout_global_name(row, col + off, wire, device)
                        else:
                            global_name = f'X{col}Y{row}/rPLL{nam}{wire}'
                        dev.nodes.setdefault(global_name, ("PLL_O", set()))[1].update({(row, col, f'rPLL{nam}{wire}'), (row, col + off, wire)})
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
                        # Himbaechel node
                        dev.nodes.setdefault(f'X{col}Y{row}/rPLL{nam}{wire}', ("PLL_I", {(row, col, f'rPLL{nam}{wire}')}))[1].add((row, col + off, wire))
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
                            # Himbaechel node
                            dev.nodes.setdefault(f'X{col}Y{row}/PLLVR{nam}{wire}', ("PLL_I", {(row, col, f'PLLVR{nam}{wire}')}))[1].add((9, 37, wire))
                    for idx, nam in _pll_outputs:
                        wire = wirenames[dat[f'SpecPll{pll_idx}Outs'][idx * 3 + 2]]
                        bel.portmap[nam] = wire
                        # Himbaechel node
                        if nam != 'LOCK':
                            global_name = get_pllout_global_name(row, col, wire, device)
                        else:
                            global_name = f'X{col}Y{row}/PLLVR{nam}{wire}'
                        dev.nodes.setdefault(global_name, ("PLL_O", set()))[1].update({(row, col, f'PLLVR{nam}{wire}'), (row, col, wire)})
                    bel.portmap['CLKIN'] = wirenames[124];
                    reset = wirenames[dat[f'SpecPll{pll_idx}Ins'][0 + 2]]
                    # VREN pin is placed in another cell
                    if pll_idx == 0:
                        vren = 'D0'
                    else:
                        vren = 'B0'
                    bel.portmap['VREN'] = f'PLLVRV{vren}'
                    dev.aliases[row, col, f'PLLVRV{vren}'] = (0, 37, vren)
                    # Himbaechel node
                    dev.nodes.setdefault(f'X{col}Y{row}/PLLVRV{vren}', ("PLL_I", {(row, col, f'PLLVRV{vren}')}))[1].add((0, 37, vren))
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


