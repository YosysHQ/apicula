from dataclasses import dataclass, field
from typing import Dict, List, Set, Tuple, Union, Any
from itertools import chain
import re
import copy
from functools import reduce
from collections import namedtuple
from apycula.dat19 import Datfile
import apycula.fuse_h4x as fuse
from apycula import wirenames as wnames
from apycula import pindef
from apycula import bitmatrix

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
    # where to set the fuses for the bel
    fuse_cell_offset: Coord = field(default_factory=tuple)

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
    # This table plays an important role when setting the fuse,
    # The fuse pair specified here is installed in case the sink is not
    # connected to any of the listed sources. In the old IDE this was an
    # unnecessary mechanism since all the fuses were listed in the rows of the
    # [‘wire’][2] table, this is not the case in the new IDE.
    # {dst: [({src}, {bits})]}
    alonenode: Dict[str, List[Tuple[Set[str], Set[Coord]]]] = field(default_factory=dict)
    # for now as nextpnr is still counting on this field
    clock_pips: Dict[str, Dict[str, Set[Coord]]] = field(default_factory=dict)
    # fuses to disable the long wire columns. This is the table 'alonenode[6]' in the vendor file
    # {dst: [({src}, {bits})]}
    alonenode_6: Dict[str, List[Tuple[Set[str], Set[Coord]]]] = field(default_factory=dict)
    # a mapping from bel type to bel
    bels: Dict[str, Bel] = field(default_factory=dict)

@dataclass
class Device:
    # a grid of tiles
    grid: List[List[Tile]] = field(default_factory=list)
    timing: Dict[str, Dict[str, List[float]]] = field(default_factory=dict)
    # {wine_name: type_name}
    wire_delay: Dict[str, str] = field(default_factory=dict)
    packages: Dict[str, Tuple[str, str, str]] = field(default_factory=dict)
    # {variant: {package: {pin#: (pin_name, [cfgs])}}}
    pinout: Dict[str, Dict[str, Dict[str, Tuple[str, List[str]]]]] = field(default_factory=dict)
    # {variant: {package: (net, row, col, AB, iostd)}}
    sip_cst: Dict[str, Dict[str, Tuple[str, int, int, str, str]]] = field(default_factory=dict)
    pin_bank: Dict[str, int] = field(default_factory = dict)
    cmd_hdr: List[bytearray] = field(default_factory=list)
    cmd_ftr: List[bytearray] = field(default_factory=list)
    template: List[List[int]] = None
    # allowable values of bel attributes
    # {table_name: {(attr_id, attr_value): code}}
    logicinfo: Dict[str, Dict[Tuple[int, int], int]] = field(default_factory=dict)
    # reverse logicinfo, is not stored in the pickle
    rev_li: Dict[str, Dict[int, Tuple[int, int]]]  = field(default_factory=dict)
    # fuses for single feature only
    # {ttype: {table_name: {feature: {bits}}}
    longfuses: Dict[int, Dict[str, Dict[Tuple[int,], Set[Coord]]]] = field(default_factory=dict)
    # fuses for a pair of the "features" (or pairs of parameter values)
    # {ttype: {table_name: {(feature_A, feature_B): {bits}}}
    shortval: Dict[int, Dict[str, Dict[Tuple[int, int], Set[Coord]]]] = field(default_factory=dict)
    # fuses for 16 of the "features"
    # {ttype: {table_name: {(feature_0, feature_1, ..., feature_15): {bits}}}
    longval: Dict[int, Dict[str, Dict[Tuple[int, int, int, int, int, int, int, int, int, int, int, int, int, int, int, int], Set[Coord]]]] = field(default_factory=dict)
    # constant fuses
    # we will use the list in case it turns out that order is important.
    # {ttype: [bits, bits]}
    const: Dict[int, List[int]] = field(default_factory=dict)
    # for Himbaechel arch
    # nodes - always connected wires {node_name: (wire_type, {(row, col, wire_name)})}
    nodes: Dict[str, Tuple[str, Set[Tuple[int, int, str]]]] = field(default_factory = dict)
    # strange bottom row IO. In order for OBUF and Co. to work, one of the four
    # combinations must be applied to two special wires.
    # (wire_a, wire_b, [(wire_a_net, wire_b_net)])
    bottom_io: Tuple[str, str, List[Tuple[str, str]]] = field(default_factory = tuple)
    # simplified IO rows
    simplio_rows: Set[int] = field(default_factory = set)
    # which PLL does this pad belong to. {IOLOC: (row, col, type, bel_name)}
    # type = {'CLKIN_T', 'CLKIN_C', 'FB_T', 'FB_C'}
    pad_pll: Dict[str, Tuple[int, int, str, str]] = field(default_factory = dict)
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
    # - MIPI
    extra_func: Dict[Tuple[int, int], Dict[str, Any]] = field(default_factory=dict)
    # Chip features currently related to block memory like "HAS_SP32", "NEED_SP_FIX", etc
    chip_flags: List[str] = field(default_factory=list)
    # Segmented clock columns description
    # { (y, x, idx) : {min_x, min_y, max_x, max_y, top_row, bottom_row, top_wire, bottom_wire,
    # top_gate_wire[name, ], bottom_gate_wire[name,]}}
    segments: Dict[Tuple[int, int, int], Dict[str, Any]] = field(default_factory=dict)
    # GW5A renames the DCS inputs from CLK to CLKIN
    dcs_prefix: str = field(default = "CLK")

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
        for row in range(self.rows):
            for col in range(self.cols):
                for bel in self.grid[row][col].bels.keys():
                    if bel.startswith('BANK'):
                        res.update({ bel[4:] : (row, col) })
        return res

    # make reverse logicinfo tables on demand
    def rev_logicinfo(self, name):
        if name not in self.rev_li:
            table = self.rev_li.setdefault(name, {})
            for attrval, code in self.logicinfo[name].items():
                table[code] = attrval
        return self.rev_li[name]

def is_GW5_family(device):
    return device in {'GW5A-25A', 'GW5AST-138C'}


# XXX GW1N-4 and GW1NS-4 have next data in dat.portmap['CmuxIns']:
# 62 [11, 1, 126]
# 63 [11, 1, 126]
# this means that the same wire (11, 1, 126) is connected implicitly to two
# other logical wires. Let's remember such connections.
# If suddenly a command is given to assign an already used wire to another
# node, then all the contents of this node are combined with the existing one,
# and the node itself is destroyed.
# To prevent further attempts to add wires to the destroyed node, we return the
# name of the node to which the connection was made
wire2node = {}
def add_node(dev, node_name, wire_type, row, col, wire):
    if (row, col, wire) not in wire2node:
        wire2node[row, col, wire] = node_name
        dev.nodes.setdefault(node_name, (wire_type, set()))[1].add((row, col, wire))
        return node_name
    else:
        old_node_name = wire2node[row, col, wire]
        if node_name != old_node_name:
            if node_name in dev.nodes:
                #print(f'#0 {node_name} -> {wire2node[row, col, wire]} share ({row}, {col}, {wire})')
                dev.nodes[old_node_name][1].update(dev.nodes[node_name][1])
                del dev.nodes[node_name]
            else:
                #print(f'#1 {node_name} -> {wire2node[row, col, wire]} share ({row}, {col}, {wire})')
                dev.nodes[old_node_name][1].add((row, col, wire))
        return old_node_name
    return node_name

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

def fse_pips(fse, ttyp, device, table=2, wn=wnames.wirenames):
    pips = {}
    if table in fse[ttyp]['wire']:
        for srcid, destid, *fuses in fse[ttyp]['wire'][table]:
            fuses = {fuse.fuse_lookup(fse, ttyp, f, device) for f in unpad(fuses)}
            if srcid < 0:
                fuses = set()
                srcid = -srcid
            src = wn[srcid]
            dest = wn[destid]
            pips.setdefault(dest, {})[src] = fuses

    return pips

# use sources from alonenode to find missing source->sink pairs in pips
def create_default_pips(tiles):
    for tile in tiles.values():
        for dest, srcs_fuses in tile.alonenode.items():
            if dest in tile.pips:
                for srcs_fuse in srcs_fuses:
                    for src in srcs_fuse[0]:
                        if src not in tile.pips[dest]:
                            tile.pips.setdefault(dest, {})[src] = set()

# The new IDE introduces Q6 and Q7 as sources, and their connection fuses look suspiciously
# similar to VCC connection fuses, so we rename Q6 and Q7 to VCC.
def create_vcc_pips(dev, tiles):
    for ttyp, tile in tiles.items():
        if ttyp in dev.tile_types['C'] or ttyp in dev.tile_types['M']: # only CFU cells
            for src_fuses in tile.pips.values():
                for q in ['Q6', 'Q7']:
                    if q in src_fuses:
                        src_fuses['VCC'] = src_fuses[q]
                src_fuses.pop('Q6', None)
                src_fuses.pop('Q7', None)
            for dest, srcs_fuses in tile.alonenode.items():
                for idx, srcs_fuse in enumerate(srcs_fuses):
                    if 'Q6' in srcs_fuse[0] or 'Q7' in srcs_fuse[0]:
                        srcs_fuse[0].discard('Q6')
                        srcs_fuse[0].discard('Q7')
                        tile.alonenode[dest][idx] = (srcs_fuse[0] | {'VCC'}, srcs_fuse[1])

def fse_alonenode(fse, ttyp, device, table = 6):
    pips = {}
    if 'alonenode' in fse[ttyp].keys():
        if table in fse[ttyp]['alonenode']:
            for destid, *tail in fse[ttyp]['alonenode'][table]:
                fuses = {fuse.fuse_lookup(fse, ttyp, f, device) for f in unpad(tail[-2:])}
                srcs = {wnames.wirenames.get(srcid, str(srcid)) for srcid in unpad(tail[:-2])}
                dest = wnames.wirenames.get(destid, str(destid))
                pips.setdefault(dest, []).append((srcs, fuses))
    return pips

# make PLL bels
def fse_pll(device, fse, ttyp):
    bels = {}
    #print("requested fse_pll types:", ttyp)

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
    elif device in {'GW5A-25A'}:
        # GW5A-25A does not use the main grid
        pass
    return bels

# add the ALU mode
# new_mode_bits: string like "0110000010011010"
def add_alu_mode(modes, lut, new_alu_mode, new_mode_bits):
    alu_mode = modes.setdefault(new_alu_mode, set())
    for i, bit in enumerate(new_mode_bits):
        if bit == '0':
            alu_mode.update(lut.flags[15 - i])

# also make DFFs, ALUs and shadow RAM
def fse_luts(fse, ttyp, device):
    data = fse[ttyp]['shortval'][5]

    luts = {}
    for lutn, bit, *fuses in data:
        coord = fuse.fuse_lookup(fse, ttyp, fuses[0], device)
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
    for cls, fuse_idx in enumerate([25, 26, 27, 28]):
        if fuse_idx == 28 and device not in {'GW5A-25A'}:
            continue
        data = fse[ttyp]['shortval'][fuse_idx]
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
            lut = luts[f"LUT{alu_idx}"]
            # ADD    INIT="0110 0000 1100 1010"
            #              add   0   add  carry
            add_alu_mode(bel.modes, lut, "0",     "0110000001101010")
            # SUB    INIT="1001 0000 1001 1010"
            #              sub   0   sub  carry
            add_alu_mode(bel.modes, lut, "1",     "1001000010011010")
            # ADDSUB INIT="0110 0000 1001 1010"
            #              add   0   sub  carry
            add_alu_mode(bel.modes, lut, "2",     "0110000010011010")
            add_alu_mode(bel.modes, lut, "hadder", "1111000000000000")
            # NE     INIT="1001 0000 1001 1111"
            #              add   0   sub  carry
            add_alu_mode(bel.modes, lut, "3",     "1001000010011111")
            # GE
            add_alu_mode(bel.modes, lut, "4",     "1001000010011010")
            # LE
            # no mode, just swap I0 and I1
            # CUP
            add_alu_mode(bel.modes, lut, "6",     "1010000010100000")
            # CDN
            add_alu_mode(bel.modes, lut, "7",     "0101000001011111")
            # CUPCDN
            # We set bits 8 through 11 to make it distinct from SUB
            add_alu_mode(bel.modes, lut, "8",     "1010111101011010")
            # MULT   INIT="0111 1000 1000 1000"
            #
            add_alu_mode(bel.modes, lut, "9",     "0111100010001000")
            # CIN->LOGIC INIT="0000 0000 0000 0000"
            #                   nop   0   nop  carry
            # side effect: clears the carry
            add_alu_mode(bel.modes, lut, "C2L",   "0000000000000000")
            # 1->CIN     INIT="0000 0000 0000 1111"
            #                  nop   0   nop  carry
            add_alu_mode(bel.modes, lut, "ONE2C", "0000000000001111")
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
    #XXX no SRAM for GW5A for now
    if device not in {'GW5A-25A'} and 28 in fse[ttyp]['shortval']:
        for i in range(6):
            bel = luts.setdefault(f"DFF{i}", Bel())
            mode = bel.modes.setdefault("RAM", set())
            for key0, key1, *fuses in fse[ttyp]['shortval'][25+i//2]:
                if key0 < 0:
                    for f in fuses:
                        if f == -1: break
                        coord = fuse.fuse_lookup(fse, ttyp, f, device)
                        mode.add(coord)

        bel = luts.setdefault(f"RAM16", Bel())
        mode = bel.modes.setdefault("0", set())
        for key0, key1, *fuses in fse[ttyp]['shortval'][28]:
            if key0 == 2 and key1 == 0:
                for f in fuses:
                    if f == -1: break
                    coord = fuse.fuse_lookup(fse, ttyp, f, device)
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
    elif device == 'GW5A-25A':
        bel = osc.setdefault(f"OSCA", Bel())
    else:
        raise Exception(f"Oscillator not yet supported on {device}")
    bel.portmap = {}
    return osc

def set_banks(fse, db):
    for row in range(db.rows):
        for col in range(db.cols):
            ttyp = db.grid[row][col].ttyp
            if ttyp in db.longval:
                if 'BANK' in db.longval[ttyp]:
                    for rd in db.longval[ttyp]['BANK']:
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
            39: 'BSRAM_INIT',
            49: 'HCLK',
            52: 'DLLDLY',
            59: 'CFG',
            62: 'OSC',
            63: 'USB',
            67: 'ADC',
            92: '5A_PCLK_ENABLE',
        }

_known_tables = {
             4: 'CONST',
             5: 'LUT',
            18: 'DCS6',
            19: 'DCS7',
            20: 'GSR',
            21: 'IOLOGICA',
            22: 'IOLOGICB',
            23: 'IOBA',
            24: 'IOBB',
            25: 'CLS0',
            26: 'CLS1',
            27: 'CLS2',
            28: 'CLS3',
            29: 'BSRAM_DP',
            30: 'BSRAM_SDP',
            31: 'BSRAM_SP',
            32: 'BSRAM_ROM',
            33: 'DSP0',
            34: 'DSP1',
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
            50: 'HCLK',
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
            93: '5A_PCLK_ENABLE_08',
            94: '5A_PCLK_ENABLE_09',
            95: '5A_PCLK_ENABLE_10',
            96: '5A_PCLK_ENABLE_11',
            97: '5A_PCLK_ENABLE_12',
            98: '5A_PCLK_ENABLE_13',
            99: '5A_PCLK_ENABLE_00',
           100: '5A_PCLK_ENABLE_01',
           101: '5A_PCLK_ENABLE_02',
           102: '5A_PCLK_ENABLE_03',
           103: '5A_PCLK_ENABLE_04',
           104: '5A_PCLK_ENABLE_05',
           105: '5A_PCLK_ENABLE_16',
           106: '5A_PCLK_ENABLE_17',
           107: '5A_PCLK_ENABLE_18',
           108: '5A_PCLK_ENABLE_19',
           109: '5A_PCLK_ENABLE_20',
           110: '5A_PCLK_ENABLE_21',
           111: '5A_PCLK_ENABLE_24',
           112: '5A_PCLK_ENABLE_25',
           113: '5A_PCLK_ENABLE_26',
           114: '5A_PCLK_ENABLE_27',
           115: '5A_PCLK_ENABLE_28',
           116: '5A_PCLK_ENABLE_29',
        }

def fse_fill_logic_tables(dev, fse, device):
    # logicinfo
    for ltable in fse['header']['logicinfo']:
        if ltable in _known_logic_tables:
            table = dev.logicinfo.setdefault(_known_logic_tables[ltable], {})
        else:
            table = dev.logicinfo.setdefault(f"unknown_{ltable}", {})
        for code, av in enumerate(fse['header']['logicinfo'][ltable]):
            attr, val, _ = av
            table[(attr, val)] = code
    # shortval
    ttypes = chain({t for row in fse['header']['grid'][61] for t in row}, range(1024, 1027))
    for ttyp in ttypes:
        if ttyp not in fse:
            continue
        if 'longfuse' in fse[ttyp]:
            ttyp_rec = dev.longfuses.setdefault(ttyp, {})
            for lftable in fse[ttyp]['longfuse']:
                if lftable in _known_tables:
                    table = ttyp_rec.setdefault(_known_tables[lftable], {})
                else:
                    table = ttyp_rec.setdefault(f"unknown_{lftable}", {})
                for f, *fuses in fse[ttyp]['longfuse'][lftable]:
                    table[(f, )] = {fuse.fuse_lookup(fse, ttyp, f, device) for f in unpad(fuses)}
        if 'const' in fse[ttyp]:
            ttyp_rec = dev.const.setdefault(ttyp, [])
            for fuse_list in fse[ttyp]['const'][4]:
                for f in fuse_list:
                    ttyp_rec.append(fuse.fuse_lookup(fse, ttyp, f, device))
        if 'shortval' in fse[ttyp]:
            ttyp_rec = dev.shortval.setdefault(ttyp, {})
            for stable in fse[ttyp]['shortval']:
                if stable in _known_tables:
                    table = ttyp_rec.setdefault(_known_tables[stable], {})
                else:
                    table = ttyp_rec.setdefault(f"unknown_{stable}", {})
                for f_a, f_b, *fuses in fse[ttyp]['shortval'][stable]:
                    if ttyp < 1024:
                        table[(f_a, f_b)] = {fuse.fuse_lookup(fse, ttyp, f, device) for f in unpad(fuses)}
                    else:
                        table[(f_a, f_b)] = {fuse.drpfuse_lookup(fse, ttyp - 1024, f, device) for f in unpad(fuses)}
        if 'longval' in fse[ttyp]:
            ttyp_rec = dev.longval.setdefault(ttyp, {})
            for ltable in fse[ttyp]['longval']:
                if ltable in _known_tables:
                    table = ttyp_rec.setdefault(_known_tables[ltable], {})
                else:
                    table = ttyp_rec.setdefault(f"unknown_{ltable}", {})
                for f0, f1, f2, f3, f4, f5, f6, f7, f8, f9, f10, f11, f12, f13, f14, f15, *fuses in fse[ttyp]['longval'][ltable]:
                    table[(f0, f1, f2, f3, f4, f5, f6, f7, f8, f9, f10, f11, f12, f13, f14, f15)] = {fuse.fuse_lookup(fse, ttyp, f, device) for f in unpad(fuses)}

# In the cell, the table [‘wire’][48] describes the fuses for the HCLK wires.
# The problem is that the wire numbers used in these tables are the same for
# all 4 HCLKs. This function returns the HCLK index by cell type.
_ttyp_2_hclk = { 242: 0, 411: 0, 422: 0, 466: 0,
                48: 1,  60: 1, 274: 1, 437: 1,
                50: 2, 272: 2, 403: 2,
                49: 3, 220: 3, 392: 3, 407: 3}
def gw5_ttyp_to_hclk_idx(ttyp):
    if ttyp not in _ttyp_2_hclk:
        return None
    return _ttyp_2_hclk[ttyp]

def gw5_make_hclk_pips(dev, device, fse, dat: Datfile):
    for row, rd in enumerate(dev.grid):
        for col, rc in enumerate(rd):
            hclk_idx = gw5_ttyp_to_hclk_idx(rc.ttyp)
            if hclk_idx and 48 in fse[rc.ttyp]['wire']:
                for srcid, destid, *fuses in fse[rc.ttyp]['wire'][48]:
                    fuses = {fuse.fuse_lookup(fse, rc.ttyp, f, device) for f in unpad(fuses)}
                    # This is not a magic number, but simply the number of wires in a
                    # single HCLK. Their indices are the same for all HCLKs,
                    # but we renumber them for routing purposes so that each HCLK
                    # has unique wire numbering.
                    src = wnames.hclknames[srcid + 187]
                    dest = wnames.hclknames[destid + 187]
                    dev.hclk_pips.setdefault((row, col), {}).setdefault(dest, {}).update({src: fuses})
                    # make hclk_nodes
                    add_node(dev, f'HCLK{hclk_idx}_{src}', "GLOBAL_CLK", row, col, src)
                    add_node(dev, f'HCLK{hclk_idx}_{dest}', "GLOBAL_CLK", row, col, dest)


# So far, there is only one match (as the clock is soldered in TangPrimer25k),
# since it is unclear whether there is a table or whether it will be necessary
# to experimentally connect the oscillator to the pins and see which route the
# IDE chooses.
def gw5_make_pin_to_hclk(dev):
    pin_hclk_wire = [ {'row': 36, 'col': 11, 'wire': 'F5', 'hclk_idx': 1, 'hclk_wire_idx': 311} ]
    for node_desc in pin_hclk_wire:
        row = node_desc['row']
        col = node_desc['col']
        wire = node_desc['wire']
        hclk_wire = wnames.hclknames[node_desc['hclk_wire_idx']]
        node_name = add_node(dev, f"HCLK{node_desc['hclk_idx']}_{hclk_wire}", "HCLK", row, col, wire)
        add_node(dev, node_name, "HCLK", row, col, hclk_wire)
    # XXX !!!
    # This is a terrible patch — we are introducing PIPs, some of which do not
    # have fuses, but we cannot simply make the Himbaechel 311<->215 node
    # because the HCLK(48) tables contain PIPs for both 215 and 211 and for
    # 318, but they don't have the ones we need, so we assume that these are
    # default connections (without fuses).
    # And at the moment, only pin E2 is described, which is soldered to the
    # external quartz on the TangPrime25k board.
    row, col = 36, 11
    add_node(dev, f"HCLK1_{wnames.hclknames[211]}", "GLOBAL_CLK", row, col, 'DUMMY_HCLK211')
    add_node(dev, f"HCLK1_{wnames.hclknames[215]}", "GLOBAL_CLK", row, col, 'DUMMY_HCLK215')
    dev.hclk_pips.setdefault((row, col), {}).setdefault('DUMMY_HCLK215', {}).update({'DUMMY_HCLK211': set()})
    row, col = 36, 27
    dev.hclk_pips.setdefault((row, col), {}).setdefault(wnames.hclknames[211], {}).update({wnames.hclknames[318]: set()})


# HCLK to global clock network gates
# The wire numbers in the tables are the same for all four HCLKs, and we can
# basically make them unique by automatically generating the wire name based on
# the HCLK number. However, with PIPs that connect HCLK to the global clock
# system, the situation is different: the source wire still needs to be
# modified based on the HCLK number, but the receiver wire remains unchanged
# because the wire numbers in the global clock system already take into account
# the chip side.
# Thus, we process the tables of certain cell types separately.
def gw5_make_hclk_to_clk_gates(dev, device, fse, dat: Datfile):
    spec_ttyp = {'B': { 'row': 36, 'col': 46, 'ttyp': 393, 'hclk_idx': 1},
                 'T': { 'row':  0, 'col': 59, 'ttyp': 410, 'hclk_idx': 0},
                 'R': { 'row': 27, 'col': 91, 'ttyp': 187, 'hclk_idx': 3},
                 'L': { 'row': 10, 'col':  0, 'ttyp': 257, 'hclk_idx': 2},}
    def make_node_and_gate_pip(row, col, side, clk_name):
        node_name = f'HCLK_GATE{side}{clk_name}'
        node_name = add_node(dev, node_name, "GLOBAL_CLK", row, col, clk_name)
        add_node(dev, node_name, "GLOBAL_CLK", spec_ttyp[side]['row'], spec_ttyp[side]['col'],
                 wnames.hclknames[wnames.clknumbers[clk_name]])
        # extract HCLK->GCLK fuses, make wire and pip
        clk_wire_idx = wnames.clknumbers[clk_name]
        for srcid, destid, *fuses in fse[spec_ttyp[side]['ttyp']]['wire'][48]:
            if destid != clk_wire_idx:
                continue
            fuses = {fuse.fuse_lookup(fse, spec_ttyp[side]['ttyp'], f, device) for f in unpad(fuses)}
            # This is not a magic number, but simply the number of wires in a
            # single HCLK. Their indices are the same for all HCLKs,
            # but we renumber them for routing purposes so that each HCLK
            # has unique wire numbering.
            src = wnames.hclknames[srcid + 187 * spec_ttyp[side]['hclk_idx']]
            dest = wnames.hclknames[destid]
            dev.hclk_pips.setdefault((spec_ttyp[side]['row'], spec_ttyp[side]['col']), {}).setdefault(dest, {}).update({src: fuses})
            # expose HCLK src wire as node
            add_node(dev, f"HCLK{spec_ttyp[side]['hclk_idx']}_{src}", "GLOBAL_CLK",
                     spec_ttyp[side]['row'], spec_ttyp[side]['col'], src)


    # Since the clock MUX is spread across the entire chip and the fuses for
    # connecting the same input may be located in different cells, for routing
    # purposes we create only one Himbaechel node in the first cell of the
    # clock MUX where the HCLK input is mentioned.
    # Once the necessary items have been created for a specific HCLK input, we
    # no longer take it into account.
    # XXX no DCS for now
    to_create = { f'SPINE{spine}' : { (side, f'{side}BDHCLK{i}') for side in "TBRL" for i in range(4)}
                 for spine in [0, 1, 2, 3, 4, 5,
                               8, 9, 10, 11, 12, 13,
                               16, 17, 18, 19, 20, 21,
                               24, 25, 26, 27, 28, 29]}
    for row, rd in enumerate(dev.grid):
        for col, rc in enumerate(rd):
            for spine, spine_in in to_create.items():
                if spine in rc.clock_pips:
                    remove_hclk_in = set()
                    for side, hclk_in in spine_in:
                        if hclk_in in rc.clock_pips[spine]:
                            make_node_and_gate_pip(row, col, side, hclk_in)
                            remove_hclk_in.add(hclk_in)
                    for hclk_in in remove_hclk_in:
                        to_create[spine].discard(hclk_in)

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

HCLK_PINS = namedtuple("HCLK_PINS", ["hclk_loc", "clkdiv", "clkdiv2a", "clkdiv2b"])

_device_hclk_pin_dict = {
    "GW2A-18": {
        "TOPSIDE":{
            0: HCLK_PINS((0,27), [("CALIB",0,27,"C0"), ("RESETN",0,27,"B0")], [("RESETN",0,27,"A4")], [("RESETN",0,27,"B4")]),
            1: HCLK_PINS((0,28), [("CALIB",0,27,"C5"), ("RESETN",0,27,"B5")], [("RESETN",0,27,"A1")], [("RESETN",0,27,"C1")])
        },
        "RIGHTSIDE":{
            0: HCLK_PINS((27,55), [("CALIB",27,55,"C0"), ("RESETN",27,55,"B0")], [("RESETN",27,55,"A4")], [("RESETN",27,55,"B4")]),
            1: HCLK_PINS((27,55), [("CALIB",27,55,"C5"), ("RESETN",27,55,"B5")], [("RESETN",27,55,"A1")], [("RESETN",27,55,"C1")])
        },
        "BOTTOMSIDE":{
            0: HCLK_PINS((54, 27), [("CALIB",54,27,"C0"), ("RESETN",54,27,"B0")], [("RESETN",54,27,"A4")], [("RESETN",54,27,"B4")]),
            1: HCLK_PINS((54, 28), [("CALIB",54,27,"C5"), ("RESETN",54,27,"B5")], [("RESETN",54,27,"A1")], [("RESETN",54,27,"C1")])
        },
        "LEFTSIDE":{
            0: HCLK_PINS((27,0), [("CALIB",27,0,"C0"), ("RESETN",27,0,"B0") ], [("RESETN",27,0,"A4") ], [("RESETN",27,0,"B4")]),
            1: HCLK_PINS((27,0), [("CALIB",27,0,"C5"), ("RESETN",27,0,"B5") ], [("RESETN",27,0,"A1") ], [("RESETN",27,0,"C1")])
        }
    },
    "GW1N-9": {
        "TOPSIDE":{
            0: HCLK_PINS((0,0), [("CALIB",9,0,"A2"), ("RESETN",9,0,"B0")], [("RESETN",9,0,"B2")], [("RESETN",9,0,"B4")]),
            1: HCLK_PINS((0,46), [("CALIB",9,0,"A3"), ("RESETN",9,0,"B1")], [("RESETN",9,0,"B3")], [("RESETN",9,0,"B5")])
        },
        "RIGHTSIDE":{
            0: HCLK_PINS((18,46), [("CALIB",18,46,"A2"), ("RESETN",18,46,"B0")], [("RESETN",18,46,"B2")], [("RESETN",18,46,"B4")]),
            1: HCLK_PINS((18,46), [("CALIB",18,46,"A3"), ("RESETN",18,46,"B1")], [("RESETN",18,46,"B3")], [("RESETN",18,46,"B5")])
        },
        "BOTTOMSIDE":{
            0: HCLK_PINS((28,0), [("CALIB",28,0,"D0"), ("RESETN",28,0,"D2")], [("RESETN",28,0,"D4")], [("RESETN",28,0,"C0")]),
            1: HCLK_PINS((28,46), [("CALIB",28,0,"D1"), ("RESETN",28,0,"D3")], [("RESETN",28,0,"D5")], [("RESETN",28,0,"C1")])
        },
        "LEFTSIDE":{
            0: HCLK_PINS((18,0), [("CALIB",18,0,"A2"), ("RESETN",18,0,"B0") ], [("RESETN",18,0,"B2") ], [("RESETN",18,0,"B4") ]),
            1: HCLK_PINS((18,0), [("CALIB",18,0,"A3"), ("RESETN",18,0,"B1") ], [("RESETN",18,0,"B3") ], [("RESETN",18,0,"B5") ])
        }
    },
    "GW1N-9C": {
        "TOPSIDE":{
            0: HCLK_PINS((0,0), [("CALIB",9,0,"A2"), ("RESETN",9,0,"B0")], [("RESETN",9,0,"B2")], [("RESETN",9,0,"B4")]),
            1: HCLK_PINS((0,46), [("CALIB",9,0,"A3"), ("RESETN",9,0,"B1")], [("RESETN",9,0,"B3")], [("RESETN",9,0,"B5")])
        },
        "RIGHTSIDE":{
            0: HCLK_PINS((18,46), [("CALIB",18,46,"A2"), ("RESETN",18,46,"B0")], [("RESETN",18,46,"B2")], [("RESETN",18,46,"B4")]),
            1: HCLK_PINS((18,46), [("CALIB",18,46,"A3"), ("RESETN",18,46,"B1")], [("RESETN",18,46,"B3")], [("RESETN",18,46,"B5")])
        },
        "BOTTOMSIDE":{
            0: HCLK_PINS((28,0), [("CALIB",28,0,"D0"), ("RESETN",28,0,"D2")], [("RESETN",28,0,"D4")], [("RESETN",28,0,"C0")]),
            1: HCLK_PINS((28,46), [("CALIB",28,0,"D1"), ("RESETN",28,0,"D3")], [("RESETN",28,0,"D5")], [("RESETN",28,0,"C1")])
        },
        "LEFTSIDE":{
            0: HCLK_PINS((18,0), [("CALIB",18,0,"A2"), ("RESETN",18,0,"B0") ], [("RESETN",18,0,"B2") ], [("RESETN",18,0,"B4") ]),
            1: HCLK_PINS((18,0), [("CALIB",18,0,"A3"), ("RESETN",18,0,"B1") ], [("RESETN",18,0,"B3") ], [("RESETN",18,0,"B5") ])
        }
    },
    "GW1N-1": {
        "BOTTOMSIDE":{
            0: HCLK_PINS((10, 0), [("CALIB", 10, 0, "D2"), ("RESETN", 10, 0, "D0")], [("RESETN", 10, 0, "D4")], [("RESETN", 10, 0, "D6")]),
            1: HCLK_PINS((10, 19), [("CALIB", 10, 0, "D3"), ("RESETN", 10, 0, "D1")], [("RESETN", 10, 0, "D5")], [("RESETN", 10, 0, "D7")])
        },
    },
    "GW1NZ-1": {
        "TOPSIDE":{
            0: HCLK_PINS((0, 5), [("CALIB", 0, 19, "D3"), ("RESETN", 0, 19, "D1")], [("RESETN", 0, 18, "C2")], [("RESETN", 0, 18, "C4")]),
            1: HCLK_PINS((0, 5), [("CALIB", 0, 19, "D2"), ("RESETN", 0, 19, "D0")], [("RESETN", 0, 18, "C3")], [("RESETN", 0, 18, "C5")])
        },
        "RIGHTSIDE":{
            0: HCLK_PINS((5, 19), [("CALIB", 10, 19, "D3"), ("RESETN", 10, 19, "D1")], [("RESETN", 10, 18, "C2")], [("RESETN", 10, 18, "C4")]),
            1: HCLK_PINS((5, 19), [("CALIB", 10, 19, "D2"), ("RESETN", 10, 19, "D1")], [("RESETN", 10, 18, "C3")], [("RESETN", 10, 18, "C5")])
        },
    },
    "GW1NS-4": {
        "TOPSIDE":{
            0: HCLK_PINS((0, 18), [("CALIB", 1, 0, "C0"), ("RESETN", 0, 0, "C5")], [("RESETN", 0, 0, "B1")], [("RESETN", 1, 0, "C6")]),
            1: HCLK_PINS((0, 18), [("CALIB", 1, 0, "D7"), ("RESETN", 0, 0, "B0")], [("RESETN", 1, 0, "C7")], [("RESETN", 1, 0, "C5")])
        },
        "RIGHTSIDE":{
            0: HCLK_PINS((9, 37), [("CALIB", 0, 37, "D7"), ("RESETN", 0, 37, "D5")], [("RESETN", 0, 37, "C3")], [("RESETN", 0, 37, "C1")]),
            1: HCLK_PINS((9, 37), [("CALIB", 0, 37, "D6"), ("RESETN", 0, 37, "D6")], [("RESETN", 0, 37, "C2")], [("RESETN", 0, 37, "C0")])
        },
        "BOTTOMSIDE":{
            0: HCLK_PINS((19, 16), [("CALIB", 19, 0, "D0"), ("RESETN", 19, 0, "D2")], [("RESETN", 19, 0, "D4")], [("RESETN", 19, 0, "C0")]),
            1: HCLK_PINS((19, 17), [("CALIB", 19, 0, "D1"), ("RESETN", 19, 0, "D3")], [("RESETN", 19, 0, "D5")], [("RESETN", 19, 0, "C1")])
        },
    },
    "GW1N-4": {
        "LEFTSIDE":{
            0: HCLK_PINS((9, 0), [("CALIB", 19, 0,"B4"), ("RESETN", 19, 0, "B6") ], [("RESETN", 19, 0, "A0")], [("RESETN", 19, 0, "A2")]),
            1: HCLK_PINS((9 ,0), [("CALIB", 19, 0,"B5"), ("RESETN", 19, 0, "B7") ], [("RESETN", 19, 0, "A1")], [("RESETN", 19, 0, "A3")])
        },
        "RIGHTSIDE":{
            0: HCLK_PINS((9, 37), [("CALIB", 0, 37, "B7"), ("RESETN", 0, 37, "B5")], [("RESETN", 0, 37, "C3")], [("RESETN", 0, 37, "C1")]),
            1: HCLK_PINS((9, 37), [("CALIB", 0, 37, "B6"), ("RESETN", 0, 37, "B6")], [("RESETN", 0, 37, "C2")], [("RESETN", 0, 37, "C0")])
        },
        "BOTTOMSIDE":{
            0: HCLK_PINS((19, 0),  [("CALIB", 19, 0, "D0"), ("RESETN", 19, 0, "D2")], [("RESETN", 19, 0, "D4")], [("RESETN", 19, 0, "C0")]),
            1: HCLK_PINS((19, 37), [("CALIB", 19, 0, "D1"), ("RESETN", 19, 0, "D3")], [("RESETN", 19, 0, "D5")], [("RESETN", 19, 0, "C1")])
        },
    },
}



def _iter_edge_coords(dev):
    "iterate through edge tiles in clockwise order, starting from the top left corner"
    Y = dev.rows
    X = dev.cols

    for x in range(X):
        yield (0, x)
    for y in range(Y):
        yield (y, X-1)
    for x in range(X-1, -1, -1):
        yield (Y-1, x)
    for y in range(Y-1,-1,-1):
        yield (y, 0)


def add_hclk_bels(dat, dev, device):
    #Stub for parts that don't have HCLK bel support yet
    if device not in ("GW2A-18", "GW2A-18C", "GW1N-9", "GW1N-9C", "GW1N-1", "GW1NZ-1", "GW1NS-4", "GW1N-4"):
        to_connect = ['HCLK0_SECT0_IN', 'HCLK0_SECT1_IN', 'HCLK1_SECT0_IN', 'HCLK1_SECT1_IN']
        for x in range(dev.cols):
            for y in range(dev.rows):
                if (y,x) not in dev.hclk_pips:
                    continue
                tile_hclk_pips = dev.hclk_pips[(y,x)]
                for (idx, wire) in enumerate(to_connect):
                    if wire in tile_hclk_pips:
                        tile_hclk_pips[f"HCLK_OUT{idx}"] = {wire:set()}
        return

    #Add HCLK bels and the pips/wires to support them
    if device == "GW2A-18C":
        device = "GW2A-18"
    device_hclk_pins = _device_hclk_pin_dict[device]

    if device == 'GW1NS-4':
        node_name = 'X16Y19/HCLK0_SECT0_IN'
        node_name = add_node(dev, node_name, 'HCLK', 19, 16, 'HCLK0_SECT0_IN')
        node_name = add_node(dev, node_name, 'HCLK', 19, 17, 'HCLK0_SECT0_IN')
        node_name = 'X17Y19/HCLK1_SECT0_IN'
        node_name = add_node(dev, node_name, 'HCLK', 19, 17, 'HCLK1_SECT0_IN')
        node_name = add_node(dev, node_name, 'HCLK', 19, 20, 'HCLK1_SECT0_IN')
        node_name = 'X17Y19/HCLK1_SECT1_IN'
        node_name = add_node(dev, node_name, 'HCLK', 19, 17, 'HCLK1_SECT1_IN')
        node_name = add_node(dev, node_name, 'HCLK', 19, 20, 'HCLK1_SECT1_IN')
        node_name = 'X17Y19/HCLK_IN2'
        node_name = add_node(dev, node_name, 'HCLK', 19, 17, 'HCLK_IN2')
        node_name = add_node(dev, node_name, 'HCLK', 19, 20, 'HCLK_IN2')
        node_name = 'X17Y19/HCLK_IN3'
        node_name = add_node(dev, node_name, 'HCLK', 19, 17, 'HCLK_IN3')
        add_node(dev, node_name, 'HCLK', 19, 20, 'HCLK_IN3')

    #There is a sleight of hand going on here - there is likely only one physical CLKDIV bel per HCLK
    #However because of how they are connected, and how I suspect that the muxes that utilize them are,
    #it is more convenient, for Pnr, to pretend that there are 2, one in each section.

    for side, hclks in device_hclk_pins.items():
        for idx, pins in hclks.items():
            tile_row, tile_col = pins.hclk_loc
            shared_clkdiv_wire = f"CLKDIV_{idx}_CLKOUT"

            for section in range(2):
                #CLKDIV2
                clkdiv2 = Bel()
                if section == 0:
                    div2_pins = pins.clkdiv2a
                elif section == 1:
                    div2_pins = pins.clkdiv2b
                else:
                    break

                clkdiv2_name = f"CLKDIV2_HCLK{idx}_SECT{section}"
                for pin in [*div2_pins, ("HCLKIN",tile_row,tile_col,""), ("CLKOUT",tile_row,tile_col,"")]:
                    port, row, col, wire = pin
                    wire_type = "HCLK_CTRL" if port in ("CALIB", "RESETN") else "HCLK"
                    if not wire:
                        wire = f"{clkdiv2_name}_{port}"
                    create_port_wire(dev, tile_row, tile_col, row-tile_row, col-tile_col, clkdiv2, clkdiv2_name, port, wire, wire_type)

                clkdiv_name =  f"CLKDIV_HCLK{idx}_SECT{section}"
                clkdiv = Bel()
                for pin in [*pins.clkdiv, ("HCLKIN",tile_row,tile_col,""), ("CLKOUT",tile_row,tile_col,"")]:
                    port, row, col, wire = pin
                    if not wire:
                        wire = f"{clkdiv_name}_{port}"
                    wire_type = "HCLK_CTRL" if port in ("CALIB", "RESETN") else "HCLK"
                    create_port_wire(dev, tile_row, tile_col, row-tile_row, col-tile_col, clkdiv, clkdiv_name, port, wire, wire_type)

                dev.grid[tile_row][tile_col].bels[clkdiv2_name] = clkdiv2
                dev.grid[tile_row][tile_col].bels[clkdiv_name] = clkdiv #We still create this so as not to break the PnR logic

                if device == "GW1N-9C":
                    clkdiv2_in = f"HCLK{idx}_SECT{section}_IN" if section==0 else f"HCLK_IN{idx*2+section}"
                    dev.hclk_pips[tile_row,tile_col][clkdiv2.portmap["HCLKIN"]] = {clkdiv2_in:set()}
                    sect_div2_mux = f"HCLK{idx}_SECT{section}_MUX_DIV2"
                    # clkdiv2_out_node = f"HCLK_9_CLKDIV2_SECT{section}_OUT"
                    clkdiv2_out_node = f"HCLK_9_CLKDIV2_{section}_OUT"
                    if section==0:
                        dev.hclk_pips[tile_row,tile_col][sect_div2_mux] = {clkdiv2.portmap["CLKOUT"]:set()}
                        dev.hclk_pips[tile_row,tile_col][clkdiv.portmap["HCLKIN"]] = {f"HCLK{idx}_SECT{section}_IN":set(), sect_div2_mux:set()}
                        dev.nodes.setdefault(clkdiv2_out_node, ('HCLK', set()))[1].add((tile_row, tile_col, sect_div2_mux))

                    if section==1:
                        dev.hclk_pips[tile_row,tile_col][sect_div2_mux] = {clkdiv2_in:set(),clkdiv2.portmap["CLKOUT"]:set()}
                        dev.hclk_pips[tile_row,tile_col][clkdiv.portmap["HCLKIN"]] = {f"HCLK_IN{2*idx+section}":set(), sect_div2_mux:set()}
                        dev.hclk_pips[tile_row,tile_col][f"HCLK_OUT{idx*2+section}"] = {f"HCLK{idx}_SECT{section}_IN":set()}

                else:
                    dev.hclk_pips[tile_row,tile_col][clkdiv2.portmap["HCLKIN"]] = {f"HCLK{idx}_SECT{section}_IN":set()}
                    sect_div2_mux = f"HCLK{idx}_SECT{section}_MUX2"
                    dev.hclk_pips[tile_row,tile_col][sect_div2_mux] = {f"HCLK{idx}_SECT{section}_IN":set(), clkdiv2.portmap["CLKOUT"]:set()}
                    dev.hclk_pips[tile_row,tile_col][clkdiv.portmap["HCLKIN"]] = {sect_div2_mux:set()}
                    if device in {"GW2A-18", "GW2A-18C"}:
                        dev.hclk_pips[tile_row,tile_col][f"HCLK_OUT{idx*2+section}"] = {sect_div2_mux: set(), clkdiv.portmap["CLKOUT"]:set()}
                    else:
                        dev.hclk_pips[tile_row,tile_col][f"HCLK_OUT{idx*2+section}"] = {sect_div2_mux: set()}

                dev.hclk_pips[tile_row,tile_col].setdefault(shared_clkdiv_wire, {}).update({clkdiv.portmap["CLKOUT"]:set()})
            #Conenction from the output of CLKDIV to the global clock network
            clkdiv_out_node = f"{side[0]}HCLK{idx}CLKDIV"
            dev.nodes.setdefault(clkdiv_out_node, ('GLOBAL_CLK', set()))[1].add((tile_row, tile_col, shared_clkdiv_wire))


_global_wire_prefixes = {'PCLK', 'TBDHCLK', 'BBDHCLK', 'RBDHCLK', 'LBDHCLK',
                         'TLPLL', 'TRPLL', 'BLPLL', 'BRPLL'}
def fse_create_hclk_nodes(dev, device, fse, dat: Datfile):
    if device in {'GW5A-25A'}:
        gw5_make_pin_to_hclk(dev)
        gw5_make_hclk_to_clk_gates(dev, device, fse, dat)
        gw5_make_hclk_pips(dev, device, fse, dat)
        return

    if device not in _hclk_to_fclk:
        return
    hclk_info = _hclk_to_fclk[device]
    for side in 'BRTL':
        if side not in hclk_info:
            continue

        # create HCLK nodes
        hclks = {}
        # entries to the HCLK from logic
        for hclk_idx, row, col, wire_idx in {(i, dat.cmux_ins[i - 80][0] - 1, dat.cmux_ins[i - 80][1] - 1, dat.cmux_ins[i - 80][2]) for i in range(wnames.hclknumbers['TBDHCLK0'], wnames.hclknumbers['RBDHCLK3'] + 1)}:
            if row != -2:
                add_node(dev, wnames.hclknames[hclk_idx], "HCLK", row, col, wnames.wirenames[wire_idx])
                # XXX clock router is doing fine with HCLK w/o any buffering
                # may be placement suffers a bit
                #add_buf_bel(dev, row, col, wnames.wirenames[wire_idx], buf_type = 'BUFH')

        if 'hclk' in hclk_info[side]:
            # create HCLK cells pips
            for hclk_loc in hclk_info[side]['hclk']:
                row, col = hclk_loc
                ttyp = fse['header']['grid'][61][row][col]
                dev.hclk_pips[(row, col)] = fse_pips(fse, ttyp, device, table = 48, wn = wnames.hclknames)
                for dst in dev.hclk_pips[(row, col)].keys():
                    # from HCLK to interbank MUX
                    if dst in {'HCLK_BANK_OUT0', 'HCLK_BANK_OUT1'}:
                        add_node(dev, f'HCLK{"TBLR".index(side)}_BANK_OUT{dst[-1]}', "GLOBAL_CLK", row, col, dst)
                # connect local wires like PCLKT0 etc to the global nodes
                for srcs in dev.hclk_pips[(row, col)].values():
                    for src in srcs.keys():
                        for pfx in _global_wire_prefixes:
                            if src.startswith(pfx):
                                add_node(dev, src, "HCLK", row, col, src)
                        # from interbank MUX to HCLK
                        if src in {'HCLK_BANK_IN0', 'HCLK_BANK_IN1'}:
                            add_node(dev, f'HCLKMUX{src[-1]}', "GLOBAL_CLK", row, col, src)
                # strange GW1N-9C input-input aliases
                for i in {0, 2}:
                    add_node(dev, f'X{col}Y{row}/HCLK9-{i}', 'HCLK', row, col, f'HCLK_IN{i}')
                    add_node(dev, f'X{col}Y{row}/HCLK9-{i}', 'HCLK', row, col, f'HCLK_9IN{i}')
                # GW1N-9C clock pin aliases
                if side != 'B': # it’s still unclear on this side, but the
                                # Tangnano9k external clock is not connected here, so we
                                # won’t run into problems anytime soon
                    for i in range(2):
                        add_node(dev, f'PCLK{side}{i}', "HCLK", row, col, f'LWSPINET{side}{i + 1}');


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
                    if 'IOLOGICA' in dev.grid[row][col].bels:
                        pips = dev.hclk_pips.setdefault((row, col), {})
                        for dst in 'AB':
                            for src in srcs:
                                pips.setdefault(f'FCLK{dst}', {}).update({src: set()})
                                if src.startswith('HCLK'):
                                    hclks[src].add((row, col, src))
                    pll = None
                    if 'RPLLA' in dev.grid[row][col].bels:
                        pll = 'RPLLA'
                    elif 'PLLVR' in dev.grid[row][col].bels:
                        pll = 'PLLVR'
                    if pll:
                        portmap = dev.grid[row][col].bels[pll].portmap
                        pips = dev.hclk_pips.setdefault((row, col), {})
                        for dst in ['PLL_CLKIN', 'PLL_CLKFB']:
                            for src in srcs:
                                pips.setdefault(dst, {}).update({src: set()})
                                if src.startswith('HCLK'):
                                    hclks[src].add((row, col, src))
            else:
                col = {'L': 0, 'R': dev.cols - 1}[side]
                for row in range(edge[0], edge[1]):
                    if 'IOLOGICA' in dev.grid[row][col].bels:
                        pips = dev.hclk_pips.setdefault((row, col), {})
                        for dst in 'AB':
                            for src in srcs:
                                pips.setdefault(f'FCLK{dst}', {}).update({src: set()})
                                if src.startswith('HCLK'):
                                    hclks[src].add((row, col, src))
                    pll = None
                    if 'RPLLA' in dev.grid[row][col].bels:
                        pll = 'RPLLA'
                    elif 'PLLVR' in dev.grid[row][col].bels:
                        pll = 'PLLVR'
                    if pll:
                        portmap = dev.grid[row][col].bels[pll].portmap
                        pips = dev.hclk_pips.setdefault((row, col), {})
                        for dst in ['PLL_CLKIN', 'PLL_CLKFB']:
                            for src in srcs:
                                pips.setdefault(dst, {}).update({src: set()})
                                if src.startswith('HCLK'):
                                    hclks[src].add((row, col, src))

# ADC in GW5A series are placed in slots AND in the main grid.
def fse_create_adc(dev, device, fse, dat):
    if device not in {"GW5A-25A"}:
        return
    row, col = 0, dev.cols - 1
    dev.grid[row][col].bels['ADC'] = Bel()
    extra = dev.extra_func.setdefault((row, col), {})
    adc = extra.setdefault('adc', {})
    adc['slot_idx'] = 1 # 25A has one adc and it is placed in the slot 1

    portmap = adc.setdefault('inputs', {})
    for idx, nam in _adc_inputs:
        wrow, wcol, wire_idx = dat.gw5aStuff['Adc25kIns'][idx]
        if wrow == -1 or wcol == -1:
            continue
        wrow -= 1
        wcol -= 1
        wire_type = 'ADC_I'
        if nam == 'CLK' or nam == 'MDRP_CLK':
            wire_type = 'TILE_CLK'
        wire = wnames.wirenames[wire_idx]
        if wrow == row and wcol == col:
            portmap[nam] = wire
        else:
            # not our cell, make an alias
            portmap[nam] = f'ADC{nam}{wire}'
            # Himbaechel node
            dev.nodes.setdefault(f'X{col}Y{row}/ADC{nam}{wire}', (wire_type, {(row, col, f'ADC{nam}{wire}')}))[1].add((wrow, wcol, wire))

    portmap = adc.setdefault('outputs', {})
    for idx, nam in _adc_outputs:
        wrow, wcol, wire_idx = dat.gw5aStuff['Adc25kOuts'][idx]
        if wrow == -1 or wcol == -1:
            continue
        wrow -= 1
        wcol -= 1
        wire_type = 'ADC_O'
        wire = wnames.wirenames[wire_idx]
        if wrow == row and wcol == col:
            portmap[nam] = wire
        else:
            # not our cell, make an alias
            portmap[nam] = f'ADC{nam}{wire}'
            # Himbaechel node
            dev.nodes.setdefault(f'X{col}Y{row}/ADC{nam}{wire}', (wire_type, {(row, col, f'ADC{nam}{wire}')}))[1].add((wrow, wcol, wire))


# GW5A PLLs do not use the main grid, but are located in so-called slots, so it
# makes sense to use the extra_func mechanism for their arbitrary placement.
# Slots (name is chosen arbitrarily) are bit cells of different widths
# but equal heights, with no geometric organization but with unique numbers.
# A slot with a specific number is responsible for a fixed primitive—for
# example, slot 6 is the left PLL, slot 8 is the lower PLL.
# Only the slots that are used are added to the binary image.
def fse_create_slot_plls(dev, device, fse, dat):
    if device not in {"GW5A-25A"}:
        return
    for row, col, slot_idx, io_table in {(27, 0, 6, 'PllLB'), (27, 91, 2, 'PllRB'), (0, 0, 5, 'PllLT'), (0, 91, 3, 'PllRT'), (0, 45, 4, 'old_style'), (36, 45, 8, 'old_style')}:
        extra = dev.extra_func.setdefault((row, col), {})
        pll = extra.setdefault('pll', {})
        pll['slot_idx'] = slot_idx
        portmap = pll.setdefault('inputs', {})
        pll_idx = slot_idx
        # inputs
        wire_type = 'PLL_I'
        for idx, nam in _plla_inputs:
            if io_table == 'old_style':
                wire_idx, wrow, wcol = dat.gw5aStuff['PllIn'][idx], row + 1, col + 1 + dat.gw5aStuff['PllInDlt'][idx]
            else:
                wire_idx, wrow, wcol = dat.gw5aStuff[io_table + 'Ins'][idx]
            wrow -= 1
            wcol -= 1
            wire = wnames.wirenames[wire_idx]
            if wrow == row and wcol == col:
                portmap[nam] = wire
            else:
                # not our cell, make an alias
                portmap[nam] = f'PLLA{nam}{wire}'
                # Himbaechel node
                dev.nodes.setdefault(f'X{col}Y{row}/PLLA{nam}{wire}', (wire_type, {(row, col, f'PLLA{nam}{wire}')}))[1].add((wrow, wcol, wire))
        # For PLL outputs, we specify wires from tables, but they
        # are not particularly important because they are logic
        # wires, and PLL output only makes sense when routing
        # through a global clock system.
        # The global MUX is spread across the entire chip, so it
        # doesn't matter what coordinates we specify — gowin_pack for
        # the GW5 series goes through all the cells in search of
        # the necessary fuses — but what does matter is the
        # uniqueness of the wire name. So we create coordinate - free
        # Himbaechel nodes by carefully selecting names for the
        # outputs.
        # There is one interesting catch here: the hardware has one
        # physical wire as a PLL output, which acts as both a logic
        # and clock signal (let's say F0 and MPLL0CLKOUT0). But if
        # we make a Himbaechel node out of them, only one wire will
        # remain with its type, and it will be F0, and the type
        # will be logical, and the global router will refuse to
        # route.  As a workaround, we can make MPLL0CLKOUT0->F0 PIP
        # without a fuse. This will artificially separate the
        # wires.
        portmap = pll.setdefault('outputs', {})
        for idx, nam in _plla_outputs:
            wire_type = 'PLL_O'
            portmap[nam] = f'MPLL{nam}'
            dev.wire_delay[portmap[nam]] = 'X0'
            if io_table == 'old_style':
                wire_idx, wrow, wcol = dat.gw5aStuff['PllOut'][idx], row + 1, col + 1 + dat.gw5aStuff['PllOutDlt'][idx]
            else:
                wire_idx, wrow, wcol = dat.gw5aStuff[io_table + 'Outs'][idx]
            wrow -= 1
            wcol -= 1
            wire = wnames.wirenames[wire_idx]
            logic_wire = wire
            if wrow != row or wcol != col:
                logic_wire = f'PLLA{nam}{wire}'
                # not our cell, make an alias
                # Himbaechel node
                dev.nodes.setdefault(f'X{col}Y{row}/PLLA{nam}{wire}', (wire_type, set()))[1].add((row, col, logic_wire))
                dev.nodes.setdefault(f'X{col}Y{row}/PLLA{nam}{wire}', (wire_type, set()))[1].add((wrow, wcol, wire))
            if nam.startswith('CLKOUT'):
                dev.nodes.setdefault(f'MPLL{pll_idx}{nam}', (wire_type, set()))[1].add((row, col, f'MPLL{nam}'))
            dev.grid[row][col].pips.setdefault(logic_wire, {}).update({portmap[nam]:set()})
        # CLKFBOUT is missing from the tables, so we create it manually.
        nam = 'CLKFBOUT'
        portmap[nam] = f'PLLA{nam}'
        # Himbaechel node
        dev.nodes.setdefault(f'MPLL{pll_idx}{nam}', (wire_type, set()))[1].add((row, col, f'PLLA{nam}'))

# DHCEN (as I imagine) is an additional control input of the HCLK input
# multiplexer. We have four input multiplexers - HCLK_IN0, HCLK_IN1, HCLK_IN2,
# HCLK_IN3 (GW1N-9C with its additional four multiplexers stands separately,
# but we will deal with it later) and two interbank inputs.
# Creating images using IDE where we use the maximum allowable number of DHCEN,
# the CE port of which is connected to the IO ports, then we trace the route
# from IO to the final wire, which will be the CE port of the DHCEN primitive.
# We are not interested in the CLKIN and CLKOUT ports because we are supposed
# to simply disable/enable one of the input multiplexers.
# Let's summarize the experimental data in a table.
# There are 4 multiplexers and interbank inputs on each side of the chip
# (sides: Right Bottom Left Top).
_dhcen_ce = {
        'GW1N-1':
        {'B' : [(10, 19, 'D5'), (10, 19, 'D3'), (10, 19, 'D4'), (10, 19, 'D2'), (10,  0, 'C0'), (10,  0, 'C1')]},
        'GW1NZ-1':
        {'R' : [( 0, 19, 'A2'), ( 0, 19, 'A4'), ( 0, 19, 'A3'), ( 0, 19, 'A5'), ( 0, 18, 'C6'), ( 0, 18, 'C7')],
         'T' : [(10, 19, 'A2'), (10, 19, 'A4'), (10, 19, 'A3'), (10, 19, 'A5'), (10, 19, 'C6'), (10, 19, 'C7')]},
        'GW1NS-2':
        {'R' : [(10, 19, 'A4'), (10, 19, 'A6'), (10, 19, 'A5'), (10, 19, 'A7'), (10, 19, 'C4'), (10, 19, 'C5')],
         'B' : [(11, 19, 'A4'), (11, 19, 'A6'), (11, 19, 'A5'), (11, 19, 'A7'), (11, 19, 'C4'), (11, 19, 'C5')],
         'L' : [( 9,  0, 'A0'), ( 9,  0, 'A2'), ( 9,  0, 'A1'), ( 9,  0, 'A3'), ( 9,  0, 'C0'), ( 9,  0, 'C1')],
         'T' : [( 0, 19, 'D5'), ( 0, 19, 'D3'), ( 0, 19, 'D4'), ( 0, 19, 'D2'), ( 0,  0, 'B1'), ( 0,  0, 'B0')]},
        'GW1N-4':
        {'R' : [(18, 37, 'C6'), (18, 37, 'D7'), (18, 37, 'C7'), (18, 37, 'D6'), ( 0, 37, 'D7'), ( 0, 37, 'D6')],
         'B' : [(19, 37, 'A2'), (19, 37, 'A4'), (19, 37, 'A3'), (19, 37, 'A5'), (19,  0, 'B2'), (19,  0, 'B3')],
         'L' : [(18,  0, 'C6'), (18,  0, 'D7'), (18,  0, 'C7'), (18,  0, 'D6'), (19,  0, 'A4'), ( 0,  0, 'B1')]},
        'GW1NS-4':
        {'R' : [(18, 37, 'C6'), (18, 37, 'D7'), (18, 37, 'C7'), (18, 37, 'D6'), ( 0, 37, 'D7'), ( 0, 37, 'D6')],
         'B' : [(19, 37, 'A2'), (19, 37, 'A4'), (19, 37, 'A3'), (19, 37, 'A5'), (19,  0, 'B2'), (19,  0, 'B3')],
         'T' : [( 1,  0, 'B6'), ( 1,  0, 'A0'), ( 1,  0, 'B7'), ( 1,  0, 'A1'), ( 1,  0, 'C4'), ( 1,  0, 'C3')]},
        'GW1N-9':
        {'R' : [(18, 46, 'C6'), (18, 46, 'D7'), (18, 46, 'C7'), (18, 46, 'D6'), (18, 46, 'B6'), (18, 46, 'B7')],
         'B' : [(28, 46, 'A2'), (28, 46, 'A4'), (28, 46, 'A3'), (28, 46, 'A5'), (28,  0, 'B2'), (28,  0, 'B3')],
         'L' : [(18,  0, 'C6'), (18,  0, 'D7'), (18,  0, 'C7'), (18,  0, 'D6'), (18,  0, 'B6'), (18,  0, 'B7')],
         'T' : [( 9,  0, 'C6'), ( 9,  0, 'D7'), ( 9,  0, 'C7'), ( 9,  0, 'D6'), ( 9,  0, 'B6'), ( 9,  0, 'B7')]},
        'GW1N-9C':
        {'R' : [(18, 46, 'C6'), (18, 46, 'D7'), (18, 46, 'C7'), (18, 46, 'D6'), (18, 46, 'B6'), (18, 46, 'B7')],
         'B' : [(28, 46, 'A2'), (28, 46, 'A4'), (28, 46, 'A3'), (28, 46, 'A5'), (28,  0, 'B2'), (28,  0, 'B3')],
         'L' : [(18,  0, 'C6'), (18,  0, 'D7'), (18,  0, 'C7'), (18,  0, 'D6'), (18,  0, 'B6'), (18,  0, 'B7')],
         'T' : [( 9,  0, 'C6'), ( 9,  0, 'D7'), ( 9,  0, 'C7'), ( 9,  0, 'D6'), ( 9,  0, 'B6'), ( 9,  0, 'B7')]},
        'GW2A-18':
        {'R' : [(27, 55, 'A2'), (27, 55, 'A3'), (27, 55, 'D2'), (27, 55, 'D3'), (27, 55, 'D0'), (27, 55, 'D1')],
         'B' : [(54, 27, 'A2'), (54, 27, 'A3'), (54, 27, 'D2'), (54, 27, 'D3'), (54, 27, 'D0'), (54, 27, 'D1')],
         'L' : [(27,  0, 'A2'), (27,  0, 'A3'), (27,  0, 'D2'), (27,  0, 'D3'), (27,  0, 'D0'), (27,  0, 'D1')],
         'T' : [( 0, 27, 'A2'), ( 0, 27, 'A3'), ( 0, 27, 'D2'), ( 0, 27, 'D3'), (  0,27, 'D0'), ( 0, 27, 'D1')]},
        'GW2A-18C':
        {'R' : [(27, 55, 'A2'), (27, 55, 'A3'), (27, 55, 'D2'), (27, 55, 'D3'), (27, 55, 'D0'), (27, 55, 'D1')],
         'B' : [(54, 27, 'A2'), (54, 27, 'A3'), (54, 27, 'D2'), (54, 27, 'D3'), (54, 27, 'D0'), (54, 27, 'D1')],
         'L' : [(27,  0, 'A2'), (27,  0, 'A3'), (27,  0, 'D2'), (27,  0, 'D3'), (27,  0, 'D0'), (27,  0, 'D1')],
         'T' : [( 0, 27, 'A2'), ( 0, 27, 'A3'), ( 0, 27, 'D2'), ( 0, 27, 'D3'), (  0,27, 'D0'), ( 0, 27, 'D1')]},
        }
def fse_create_dhcen(dev, device, fse, dat: Datfile):
    if device not in _dhcen_ce:
        print(f'No DHCEN for {device} for now.')
        return
    for side, ces in _dhcen_ce[device].items():
        for idx, ce_wire in enumerate(ces):
            row, col, wire = ce_wire
            extra = dev.extra_func.setdefault((row, col), {})
            dhcen = extra.setdefault('dhcen', [])
            # use db.hclk_pips in order to find HCLK_IN cells
            for hclk_loc in _hclk_to_fclk[device][side]['hclk']:
                if idx < 4:
                    hclk_name = f'HCLK_IN{idx}'
                else:
                    hclk_name = f'HCLK_BANK_OUT{idx - 4}'
                if hclk_name in dev.hclk_pips[hclk_loc]:
                    hclkin = {'pip' : [f'X{hclk_loc[1]}Y{hclk_loc[0]}', hclk_name, next(iter(dev.hclk_pips[hclk_loc][hclk_name].keys())), side]}

            hclkin.update({ 'ce' : wire})
            dhcen.append(hclkin)

# DLLDLY
# from Gowin doc "DLLDLY is the clock delay module that adjusts the input clock according to the DLLSTEP"
# In practice the following peculiarities were discovered: the input for the
# clock cannot be arbitrary things, but only specialised pins of the chip and
# the delay line is cut in between the pin and the clock MUX.
#  { bel_loc : ([('io_loc', 'io_output_wire', (row, col, flag_wirea))], [(fuse_row, fuse_col)])

_dlldly = {
        'GW1N-1': {
            (10, 19) : {
                'fuse_bels': {(10, 0), (10, 19)},
                'ios' : [('X9Y10', 'IOBA', (10, 0, 'F1')), ('X10Y10', 'IOBA', (10, 0, 'F0'))],
                },
            },
        'GW1NZ-1': {
            ( 0, 19) : {
                'fuse_bels': {(0, 5)},
                'ios' : [('X9Y0', 'IOBA', (0, 19, 'F1')), ('X10Y0', 'IOBA', (0, 19, 'F0'))],
            },
            (10, 19) : {
                'fuse_bels' : {(5, 19)},
                'ios'  : [('X19Y4', 'IOBA', (5, 19, 'F0')), ('X19Y6', 'IOBA', (5, 19, 'F2'))],
            },
        }
 }

def fse_create_dlldly(dev, device):
    if device in _dlldly:
        for bel, fuse_ios in _dlldly[device].items():
            row, col = bel
            fuse_bels = fuse_ios['fuse_bels']
            ios = fuse_ios['ios']
            extra = dev.extra_func.setdefault((row, col), {})
            dlldly = extra.setdefault(f'dlldly', {})
            for idx in range(2):
                dlldly[idx] = {'io_loc': ios[idx][0], 'io_bel': ios[idx][1]}
                # FLAG output
                nodename = f'X{col}Y{row}/DLLDLY_FLAG{idx}'
                nodename = add_node(dev, nodename, "", row, col, f'DLLDLY_FLAG{idx}')
                add_node(dev, nodename, "", ios[idx][2][0], ios[idx][2][1], ios[idx][2][2])
                add_node(dev, f'{ios[idx][0]}/DLLDLY_IN', "TILE_CLK", row, col, f'DLLDLY_CLKIN{idx}')
                add_node(dev, f'{ios[idx][0]}/DLLDLY_OUT', "DLLDLY_O", row, col, f'DLLDLY_CLKOUT{idx}')

                # STEP wires
                wires = dlldly[idx].setdefault('in_wires', {})
                prefix = ["CB", "DC"][idx]
                for wire_idx in range(8):
                    wires[f'DLLSTEP{wire_idx}'] = f"{prefix[wire_idx // 4]}{(wire_idx + 4) % 8}"
                wires['DIR']   = ["A1", "B4"][idx]
                wires['LOADN'] = ["A0", "B7"][idx]
                wires['MOVE']  = ["B6", "B5"][idx]
                wires['CLKIN'] = f'DLLDLY_CLKIN{idx}'

                wires = dlldly[idx].setdefault('out_wires', {})
                wires['FLAG'] = f'DLLDLY_FLAG{idx}'
                wires['CLKOUT'] = f'DLLDLY_CLKOUT{idx}'
            dlldly_bels = extra.setdefault(f'dlldly_fusebels', set())
            dlldly_bels.update(fuse_bels)

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
                            # Himbaechel node
                            db.nodes.setdefault(w_src, ("PLL_O", set()))[1].add((row, col, w_src))
                    elif device in {'GW5A-25A'}:
                        if w_src.startswith('MPLL'):
                            db.nodes.setdefault(w_src, ("PLL_O", set()))[1].add((row, col, w_src))
                            db.nodes.setdefault(w_dst, ("PLL_O", set()))[1].add((row, col, w_dst))

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
    if device in {'GW5A-25A'}:
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
# columns in the new quadrant (even three clocks is enough, since the fourth
# becomes obvious).
# [3, 2, 1, 0] turned out to be the unwritten standard for all the chips studied.

# We're not done with that yet - what matters is how the columns of each
# quadrant end.
# For GW1N-1 [dat.grid.center_x, dat.grid.center_y] = [6, 10]
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
# 0, 11 - quadrant is located between these rows
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
# It also follows that for the Himbaechel clock wires should not be mixed
# together with any other  wires. At least I came to this conclusion and that
# is why the HCLK wires, which have the same numbers as the clock spines, are
# stored separately.

# dat.cmux_ins and 80 - here, the places of entry points into the clock
# system are stored in the form [row, col, wire], that is, in order to send a
# signal for propagation through the global clock network, you need to send it
# to this particular wire in this cell. In most cases it will not be possible
# to connect to this wire as they are basically outputs (IO output, PLL output
# etc).

# Let's look at the dat.cmux_ins fragment for GW1N-1. We know that this board
# has an external clock generator connected to the IOR5A pin and this is one of
# the PCLKR clock wires (R is for right here). We see that this is index 47,
# and index 48 belongs to another pin on the same side of the chip. If we
# consider the used fuses from the ['wire'][38] table on the simplest example,
# we will see that 47 corresponds to the PCLKR0 wire, whose index in the
# clknames table (wirenames.py) is 127.
# For lack of a better way, we assume that the indexes in the dat.cmux_ins
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
        'GW5A-25A': { 'tap_start': [[2, 1, 0, 3], [0, 3, 2, 1]], 'quads': {(10, 0, 19, 1, 0), (28, 19, 37, 2, 3)}},
        }

def get_clock_ins(device, dat: Datfile):
    if device in {'GW5A-25A'}:
        return {} # In this series, there is no way to directly use the GCLK pins bypassing HCLK.
    # pre 5a
    return {
            (i, dat.cmux_ins[i - 80][0] - 1, dat.cmux_ins[i - 80][1] - 1, dat.cmux_ins[i - 80][2])
              for i in range(wnames.clknumbers['PCLKT0'], wnames.clknumbers['PCLKR1'] + 1)
            }

def fse_create_clocks(dev, device, dat: Datfile, fse):
    if device not in _clock_data:
        print(f"No clocks for {device} for now.")
        return

    center_col = dat.grid.center_x - 1
    clkpin_wires = {}
    taps = {}
    # find center muxes
    for clk_idx, row, col, wire_idx in get_clock_ins(device, dat):
        if row != -2:
            # XXX GW1NR-9C has an interesting feature not found in any other
            # chip - the external pins for the clock are connected to the
            # central clock MUX not directly, but through auxiliary wires that
            # lead to the corner cells and only there the connection occurs.
            if device == 'GW1N-9C' and row == dev.rows - 1:
                add_node(dev, f'{wnames.clknames[clk_idx]}-9C', "GLOBAL_CLK", row, col, wnames.wirenames[wire_idx])
                if wnames.clknames[clk_idx][-1] == '1':
                    add_node(dev, f'{wnames.clknames[clk_idx]}-9C', "GLOBAL_CLK", row, dev.cols - 1, 'LWT6')
                else:
                    add_node(dev, f'{wnames.clknames[clk_idx]}-9C', "GLOBAL_CLK", row, 0, 'LWT6')
            elif (device == 'GW1NZ-1' and (row == 0 or col == dev.cols - 1)) or (device == 'GW1N-1' and row == dev.rows - 1):
                # Do not connect the IO output to the clock node because DLLDLY
                # may be located at these positions, which, if used, will be
                # the source for the clock. However, if DLLDLY is not used
                # (mostly), we need to have a way to connect them - for this we
                # add two PIPs - one to connect the IO output to the clock and
                # one to connect the IO output to the DLLDLY input.
                # Both are non-fuseable, but allow the router to work.
                add_node(dev, wnames.clknames[clk_idx], "GLOBAL_CLK", row, col, 'PCLK_DUMMY')
                dev.grid[row][col].pips['PCLK_DUMMY'] = {wnames.wirenames[wire_idx]: set(), 'DLLDLY_OUT': set()}
                add_node(dev, f'X{col}Y{row}/DLLDLY_OUT', "DLLDLY_O", row, col, 'DLLDLY_OUT')
                add_node(dev, f'X{col}Y{row}/DLLDLY_IN', "TILE_CLK", row, col, 'DLLDLY_IN')
                dev.grid[row][col].pips['DLLDLY_IN'] = {wnames.wirenames[wire_idx]: set()}
            else:
                add_node(dev, wnames.clknames[clk_idx], "GLOBAL_CLK", row, col, wnames.wirenames[wire_idx])
                add_buf_bel(dev, row, col, wnames.wirenames[wire_idx])


    spines = {f'SPINE{i}' for i in range(32)}
    hclk_srcs = {f'HCLK{i}_BANK_OUT{j}' for i in range(4) for j in range(2)}
    dcs_inputs = {f'P{i}{j}{k}' for i in range(1, 5) for j in range(6, 8) for k in "ABCD"}

    for row, rd in enumerate(dev.grid):
        for col, rc in enumerate(rd):
            for dest, srcs in rc.clock_pips.items():
                for src in srcs.keys():
                    if src in spines and not dest.startswith('GT'):
                        add_node(dev, src, "GLOBAL_CLK", row, col, src)
                if dest in spines or dest in dcs_inputs:
                    add_node(dev, dest, "GLOBAL_CLK", row, col, dest)
                    for src in { wire for wire in srcs.keys() if wire not in {'VCC', 'VSS'}}:
                        if src.startswith('PLL'):
                            add_node(dev, src, "PLL_O", row, col, src)
                        else:
                            add_node(dev, src, "GLOBAL_CLK", row, col, src)
                if device not in {'GW5A-25A'}:
                    if dest in {'HCLKMUX0', 'HCLKMUX1'}:
                        # this interbank communication between HCLKs
                        add_node(dev, dest, "GLOBAL_CLK", row, col, dest)
                        for src in {wire for wire in srcs.keys() if wire in hclk_srcs}:
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
                                dev.nodes.setdefault(f'SPINE{spine + 4}', ("GLOBAL_CLK", set()))[1].add((row, col, f'SPINE{spine + 4}'))
                        else:
                            dev.nodes.setdefault(node0_name, ("GLOBAL_CLK", set()))[1].add((row, col, 'GT00'))
                            dev.nodes.setdefault(node1_name, ("GLOBAL_CLK", set()))[1].add((row, col, 'GT10'))

    # According to the Gowin Clock User Guide, the DQCE primitives are located
    # between the "spine" wires (in our terminology) and the central MUX, which
    # selects the clock source for that spine. We detect cells with DQCE by
    # instantiating this primitive and connecting the CE input to the button -
    # in the images generated by the Gowin IDE, it is easy to trace the wires
    # from the button to the cell and pin being used.
    # It was found that the CE pin depends only on the "spine" number and does
    # not depend on the quadrant or chip. The cells used also do not depend on
    # the chip, but only on the cell type: here is the correspondence of the
    # types to the quadrants for which the corresponding DQCEs are responsible:
    #                          |
    #   quadrant 2   type 80   |   type 85  quadrant 1
    #  ------------------------+--------------------------
    #   quadrant 3   type 81   |   type 84  quadrant 4
    #                          |

    if device not in {'GW5A-25A'}:
        for q, ttyp in enumerate([85, 80, 81, 84]):
            # stop if chip has only 2 quadrants
            if q < 2 and device not in {'GW1N-9', 'GW1N-9C', 'GW2A-18', 'GW2A-18C'}:
                continue
            for row in range(dev.rows):
                for col in range(dev.cols):
                    if ttyp == fse['header']['grid'][61][row][col]:
                        break
                else:
                    continue
                break
            extra_func = dev.extra_func.setdefault((row, col), {})
            dqce_block = extra_func.setdefault('dqce', {})
            for j in range(6):
                dqce = dqce_block.setdefault(j, {})
                dqce[f'clkin'] = f'SPINE{q * 8 + j}'
                dqce[f'ce'] = ['A0', 'B0', 'C0', 'D0', 'A1', 'B1'][j]

    # As it turned out, the DCS are located in the same cells, but their
    # relationship with the quadrants is different.
    # By generating images where the button was connected to the clock
    # selection inputs (CLK0-3) as well as to the SELFORCE input, it was
    # possible to determine the correspondence of the wires in these cells.
    #                                   |
    #   quadrant 2, spine14 dcs type 80 | quadrant 1, spine 6 dcs type 85
    #               spine15 dcs type 81 |             spine 7 dcs type 84
    #  -------------------------------------------------------------------
    #   quadrant 3, spine22 dcs type 80 | quadrant 4, spine 30 dcs type 85
    #               spine23 dcs type 81 |             spine 31 dcs type 84
    #                                   |
    # At the moment we will organize the description of DCS as:
    # 'dcs':
    #        0 /* first DCS */ : its ports
    #        1 /* second DCS*/ : its ports
    # GW5A series:
    # Here, tracing the wires showed that there is no system in their
    # arrangement; the inputs of one DCS can be strictly in one cell, or they
    # can be in five different ones. And, as is traditional for this series,
    # fuses can be fragmented across many cells.
    # We will solve the fuse issue simply by going through all the cells and
    # installing them where we find them in gowin_pack.
    # We will trace the wires and compile them into a single table. The
    # location of the Bels is no longer important, so we will assign them to
    # the same place as in the previous series.
    # {(quandrant, dcs_idx): [(col, wire)]} // row is always 18
    gw5_dcs_inputs = {
            (0, 0) : [(48, 'D7'), (44, 'D4'), (45, 'D7'), (46, 'D7'), (47, 'D7')],
            (0, 1) : [(47, 'D2'), (47, 'D3'), (47, 'C3'), (47, 'B3'), (47, 'A3')],
            (1, 0) : [(48, 'D6'), (44, 'C3'), (45, 'D6'), (46, 'D6'), (47, 'D6')],
            (1, 1) : [(47, 'C1'), (47, 'C2'), (47, 'B2'), (47, 'A2'), (47, 'D1')],
            (2, 0) : [(48, 'C6'), (44, 'A1'), (45, 'C6'), (46, 'C6'), (47, 'C6')],
            (2, 1) : [(44, 'A5'), (47, 'A0'), (44, 'D5'), (44, 'C5'), (44, 'B5')],
            (3, 0) : [(48, 'C7'), (44, 'B2'), (45, 'C7'), (46, 'C7'), (47, 'C7')],
            (3, 1) : [(47, 'B0'), (47, 'B1'), (47, 'A1'), (47, 'D0'), (47, 'C0')],
    }
    for q, types in enumerate([(85, 84), (80, 81), (80, 81), (85, 84)]):
        # stop if chip has only 2 quadrants
        if q < 2 and device not in {'GW1N-9', 'GW1N-9C', 'GW2A-18', 'GW2A-18C', 'GW5A-25A'}:
            continue
        for j in range(2):
            for row in range(dev.rows):
                for col in range(dev.cols):
                    if types[j] == fse['header']['grid'][61][row][col]:
                        break
                else:
                    continue
                break
            extra_func = dev.extra_func.setdefault((row, col), {})
            dcs_block = extra_func.setdefault('dcs', {})
            dcs = dcs_block.setdefault(q // 2, {})
            spine_idx = f'SPINE{q * 8 + j + 6}'
            dcs['clkout'] = spine_idx
            dev.nodes.setdefault(spine_idx, ("GLOBAL_CLK", set()))[1].add((row, col, spine_idx))
            dcs['clk'] = []
            for port in "ABCD":
                wire_name = f'P{q + 1}{j + 6}{port}'
                dcs['clk'].append(wire_name)
                dev.nodes.setdefault(wire_name, ("GLOBAL_CLK", set()))[1].add((row, col, wire_name))
            if device in {'GW5A-25A'}:
                dcs['input_prefix'] = 'CLKIN'
                w_col, wire = gw5_dcs_inputs[(q, j)][0]
                if row == 18 and col == w_col:
                    dcs['selforce'] = wire
                else:
                    # not our cell, make an alias
                    dcs['selforce'] = f'DCS{q}{j}{wire}'
                    # Himbaechel node
                    dev.nodes.setdefault(f'X{col}Y{row}/DCS{q}{j}{wire}', ("DCS_I", {(row, col, dcs['selforce'])}))[1].add((row, w_col, wire))
                dcs['clksel'] = []
                for i, w_desc in enumerate(gw5_dcs_inputs[(q, j)][1:]):
                    w_col, wire = w_desc
                    if row == 18 and col == w_col:
                        dcs['clksel'].append(wire)
                    else:
                        # not our cell, make an alias
                        w_name = f'DCS{q}{j}{i}{wire}'
                        dcs['clksel'].append(w_name)
                        # Himbaechel node
                        dev.nodes.setdefault(f'X{col}Y{row}/{w_name}', ("DCS_I", {(row, col, w_name)}))[1].add((row, w_col, wire))
            else:
                if q < 2:
                    dcs['selforce'] = 'C2'
                    dcs['clksel'] = ['C1', 'D1', 'A2', 'B2']
                else:
                    dcs[f'selforce'] = 'D3'
                    dcs['clksel'] = ['D2', 'A3', 'B3', 'C3']

# Segmented wires are those that run along each column of the chip and have
# taps in each row about 4 cells wide. The height of the segment wires varies
# from chip to chip: from full chip height for GW1N-1 to two strips in GW1N-9
# and three strips in GW2A-18.
# The MUXes for the sources on these wires can switch between signals from
# "spines" (long horizontal wires up to half a chip in length) or from input
# points from the logic.
# These MUXes are placed on both ends of the segmented wire, which is very
# flexible but at the same time requires some care not to signal both ends of
# the wire.
# The coverage areas between segment wires i and i + 4 are the same, only the
# MUXes differ, so we create a pair of segments at once.

# tap_start = describes where in the 4-cell area the main wire column with index is located
# rows = top and bottom rows of segments
# top_wires = [(MUX wire for i segment, MUX wire for i + 4 segment), next_row]
# bottom_wires = [(MUX wire for i segment, MUX wire for i + 4 segment), next_row]
# top_gate_wires = [(MUX wire for i segment, MUX wire for i + 4 segment), next_row][2]
# bottom_gate_wires = [(MUX wire for i segment, MUX wire for i + 4 segment), next_row][2]
_segment_data = {
        'GW1N-1':  { 'tap_start':  [1, 0, 3, 2], 'rows': [(0, 10)],
                     'top_wires': [('LT02', 'LT13')], 'bottom_wires': [('LT02', 'LT13')],
                     'top_gate_wires':    [[('A6', 'A7')], [('B6', 'B7')]],
                     'bottom_gate_wires': [[('A6', 'A7')], [('B6', 'B7')]],
                     'reserved_wires': {(0, 17, 'A6'), (0, 18, 'A6'), (0, 17, 'A7'), (0, 18, 'A7'),
                                        (0, 17, 'B6'), (0, 18, 'B6'), (0, 17, 'B7'), (0, 18, 'B7')}},
        'GW1NZ-1': { 'tap_start':  [1, 0, 3, 2], 'rows': [(0, 10)],
                     'top_wires': [('LT02', 'LT13')], 'bottom_wires': [('LT02', 'LT13')],
                     'top_gate_wires':    [[('A6', 'A7')], [('B6', 'B7')]],
                     'bottom_gate_wires': [[('A6', 'A7')], [('B6', 'B7')]],
                     'reserved_wires': {(0, 17, 'A6'), (0, 18, 'A6'), (0, 17, 'A7'), (0, 18, 'A7'),
                                        (0, 17, 'B6'), (0, 18, 'B6'), (0, 17, 'B7'), (0, 18, 'B7')}},
        'GW1N-4':  { 'tap_start':  [2, 1, 0, 3], 'rows': [(0, 19)],
                     'top_wires': [('LT02', 'LT13')], 'bottom_wires': [('LT02', 'LT13')],
                     'top_gate_wires':    [[('A6', 'A7')], [('B6', 'B7')]],
                     'bottom_gate_wires': [[('A6', 'A7')], [('B6', 'B7')]],
                     'reserved_wires': {(0, 9, 'A6'), (0, 10, 'A6'), (0, 9, 'A7'), (0, 10, 'A7'),
                                        (0, 9, 'B6'), (0, 10, 'B6'), (0, 9, 'B7'), (0, 10, 'B7'),
                                        (0, 27, 'A6'), (0, 28, 'A6'), (0, 27, 'A7'), (0, 28, 'A7'),
                                        (0, 27, 'B6'), (0, 28, 'B6'), (0, 27, 'B7'), (0, 28, 'B7')}},
        'GW1NS-4': { 'tap_start':  [2, 1, 0, 3], 'rows': [(0, 19)],
                     'top_wires': [('LT02', 'LT13')], 'bottom_wires': [('LT02', 'LT13')],
                     'top_gate_wires':    [[('A6', 'A7')], [('B6', 'B7')]],
                     'bottom_gate_wires': [[('A6', 'A7')], [('B6', 'B7')]],
                     'reserved_wires': {(0, 27, 'A6'), (0, 36, 'A6'), (0, 27, 'A7'), (0, 36, 'A7'),
                                        (0, 27, 'B6'), (0, 36, 'B6'), (0, 27, 'B7'), (0, 36, 'B7')}},
        'GW1N-9':  { 'tap_start':  [3, 2, 1, 0], 'rows': [(0, 18), (19, 28)],
                     'top_wires': [('LT02', 'LT13'), ('LT00', 'LT10')],
                     'bottom_wires': [('LT20', 'LT30'), ('LT02', 'LT13')],
                     'top_gate_wires':    [[('A6', 'A7'), (None, None)], [('B6', 'B7'), None]],
                     'bottom_gate_wires': [[(None, 'B7'), (None, 'A7')], [None, None]],
                     'reserved_wires': {}},
        'GW1N-9C': { 'tap_start':  [3, 2, 1, 0], 'rows': [(0, 18), (19, 28)],
                     'top_wires': [('LT02', 'LT13'), ('LT00', 'LT10')],
                     'bottom_wires': [('LT20', 'LT30'), ('LT02', 'LT13')],
                     'top_gate_wires':    [[('A6', 'A7'), (None, None)], [('B6', 'B7'), None]],
                     'bottom_gate_wires': [[(None, 'B7'), ('A6', 'A7')], [None, None]],
                     'reserved_wires': {}},
        'GW2A-18': { 'tap_start':  [3, 2, 1, 0], 'rows': [(0, 18), (19, 36), (37, 54)],
                     'top_wires': [('LT02', 'LT13'), ('LT00', 'LT10'), ('LT00', 'LT10')],
                     'bottom_wires': [('LT20', 'LT30'), ('LT20', 'LT30'), ('LT02', 'LT13')],
                     'top_gate_wires':    [[('A6', 'A7'), (None, None), (None, None)], [('B6', 'B7'), None, None]],
                     'bottom_gate_wires': [[(None, 'B7'), (None, 'B7'), ('A6', 'A7')], [None, None, ('B6', 'B7')]],
                     'reserved_wires': {}},
        'GW2A-18C': { 'tap_start': [3, 2, 1, 0], 'rows': [(0, 18), (19, 36), (37, 54)],
                     'top_wires': [('LT02', 'LT13'), ('LT00', 'LT10'), ('LT00', 'LT10')],
                     'bottom_wires': [('LT20', 'LT30'), ('LT20', 'LT30'), ('LT02', 'LT13')],
                     'top_gate_wires':    [[('A6', 'A7'), (None, None), (None, None)], [('B6', 'B7'), None, None]],
                     'bottom_gate_wires': [[(None, 'B7'), (None, 'B7'), ('A6', 'A7')], [None, None, ('B6', 'B7')]],
                     'reserved_wires': {}},
        }
def create_segments(dev, device):
    if device not in _segment_data:
        return

    dev_desc = _segment_data[device]
    top_gate_row = dev_desc['rows'][0][0]
    for row_idx, tb_row in enumerate(dev_desc['rows']):
        t_row, b_row = tb_row
        for s_col in range(dev.cols):
            # new segment i
            seg_idx = dev_desc['tap_start'][s_col % 4]
            seg = dev.segments.setdefault((top_gate_row, s_col, seg_idx), {})
            # controlled area
            seg['min_x'] = max(0, s_col - 1)
            seg['min_y'] = t_row
            seg['max_x'] = min(dev.cols - 1, s_col + 2)
            if dev.cols - 1 - seg['max_x'] == 1:
                # The main wire of the segment is repeated every 4 cells, if
                # there is no space on the right side for the next wire, the
                # service area is extended to the very edge
                seg['max_x'] = dev.cols - 1
            seg['max_y'] = b_row
            # MUX's positions and wires
            seg['top_row'] = top_gate_row
            seg['bottom_row'] = b_row
            seg['top_wire'] = dev_desc['top_wires'][row_idx][0]
            seg['bottom_wire'] = dev_desc['bottom_wires'][row_idx][0]
            # gate wires
            seg['top_gate_wire'] = [dev_desc['top_gate_wires'][0][row_idx][0]]
            second_gate = dev_desc['top_gate_wires'][1][row_idx]
            seg['top_gate_wire'].append(second_gate)
            if second_gate:
                seg['top_gate_wire'][1] = second_gate[0]
            seg['bottom_gate_wire'] = [dev_desc['bottom_gate_wires'][0][row_idx][0]]
            second_gate = dev_desc['bottom_gate_wires'][1][row_idx]
            seg['bottom_gate_wire'].append(second_gate)
            if second_gate:
                seg['bottom_gate_wire'][1] = second_gate[0]
            # check reserved
            if (top_gate_row, s_col, seg['top_gate_wire'][0]) in dev_desc['reserved_wires']:
                seg['top_gate_wire'][0] = None
            if (top_gate_row, s_col, seg['top_gate_wire'][1]) in dev_desc['reserved_wires']:
                seg['top_gate_wire'][1] = None
            if (b_row, s_col, seg['bottom_gate_wire'][0]) in dev_desc['reserved_wires']:
                seg['bottom_gate_wire'][0] = None
            if (b_row, s_col, seg['bottom_gate_wire'][1]) in dev_desc['reserved_wires']:
                seg['bottom_gate_wire'][1] = None

            # new segment i + 1
            seg_idx += 4
            seg_1 = dev.segments.setdefault((top_gate_row, s_col, seg_idx), {})
            # controlled area
            seg_1['min_x'] = seg['min_x']
            seg_1['min_y'] = seg['min_y']
            seg_1['max_x'] = seg['max_x']
            seg_1['max_y'] = seg['max_y']
            # MUX's positions and wires
            seg_1['top_row']     = seg['top_row']
            seg_1['bottom_row']  = seg['bottom_row']
            seg_1['top_wire']    = dev_desc['top_wires'][row_idx][1]
            seg_1['bottom_wire'] = dev_desc['bottom_wires'][row_idx][1]
            # gate wires
            seg_1['top_gate_wire'] = [dev_desc['top_gate_wires'][0][row_idx][1]]
            second_gate = dev_desc['top_gate_wires'][1][row_idx]
            seg_1['top_gate_wire'].append(second_gate)
            if second_gate:
                seg_1['top_gate_wire'][1] = second_gate[1]
            seg_1['bottom_gate_wire'] = [dev_desc['bottom_gate_wires'][0][row_idx][1]]
            second_gate = dev_desc['bottom_gate_wires'][1][row_idx]
            seg_1['bottom_gate_wire'].append(second_gate)
            if second_gate:
                seg_1['bottom_gate_wire'][1] = second_gate[1]
            # check reserved
            if (top_gate_row, s_col, seg_1['top_gate_wire'][0]) in dev_desc['reserved_wires']:
                seg_1['top_gate_wire'][0] = None
            if (top_gate_row, s_col, seg_1['top_gate_wire'][1]) in dev_desc['reserved_wires']:
                seg_1['top_gate_wire'][1] = None
            if (b_row, s_col, seg_1['bottom_gate_wire'][0]) in dev_desc['reserved_wires']:
                seg_1['bottom_gate_wire'][0] = None
            if (b_row, s_col, seg_1['bottom_gate_wire'][1]) in dev_desc['reserved_wires']:
                seg_1['bottom_gate_wire'][1] = None

            # remove isolated segments (these are in the DSP area of -9, -9C, -18, -18C)
            if (not seg['top_gate_wire'][0] and not seg['top_gate_wire'][1]
                and not seg['bottom_gate_wire'][0] and not seg['bottom_gate_wire'][1]):
                del dev.segments[(top_gate_row, s_col, seg_idx - 4)]

            if (not seg_1['top_gate_wire'][0] and not seg_1['top_gate_wire'][1]
                and not seg_1['bottom_gate_wire'][0] and not seg_1['bottom_gate_wire'][1]):
                del dev.segments[(top_gate_row, s_col, seg_idx)]

        top_gate_row = b_row

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
def fse_create_simplio_rows(dev, dat: Datfile):
    for row, rd in enumerate(dat.grid.rows):
        if [r for r in rd if r in "Bb"]:
            if row > 0:
                row -= 1
            if row == dev.rows:
                row -= 1
            dev.simplio_rows.add(row)

def fse_create_tile_types(dev, dat: Datfile):
    type_chars = 'PCMIBD'
    for fn in type_chars:
        dev.tile_types[fn] = set()
    for row, rd in enumerate(dat.grid.rows):
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

def get_tile_types_by_func(dev, dat: Datfile, fse, fn):
    ttypes = set()
    fse_grid = fse['header']['grid'][61]
    for row, rd in enumerate(dat.grid.rows):
        for col, type_char in enumerate(rd):
            if type_char == fn:
                i = row
                if i > 0:
                    i -= 1
                if i == len(fse_grid):
                    i -= 1
                j = col
                if j > 0:
                    j -= 1
                if j == len(fse_grid[0]):
                    j -= 1
                ttypes.add(fse_grid[i][j])
    return ttypes

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
    elif device not in {'GW5A-25A', 'GW2A-18', 'GW2A-18C', 'GW1N-4'}:
        dev.diff_io_types.remove('TLVDS_IOBUF')

    if device in {'GW5A-25A'}:
        dev.diff_io_types.append('TLVDS_IBUF_ADC')

def fse_create_mipi(dev, device, dat: Datfile):
    # The MIPI OBUF is a slightly modified differential TBUF, such units are
    # located on the bottom or right side of the chip depending on the series.
    # We use the extra_func mechanism because these blocks do not depend on the
    # cell type, but only on the coordinates.
    # The same applies to MIPI_IBUF but here two neighbouring cells are used
    # per primitive.
    df = dev.extra_func
    wire_type = 'X0'
    if device in {'GW1N-9', 'GW1N-9C'}:
        for i in chain(range(1, 18, 2), range(20, 34, 2), range(38, 46, 2)):
            df.setdefault((dev.rows - 1, i), {})['mipi_obuf'] = {}
        for i in range(1, 44, 2):
            node_name = f'X{i}Y0/MIPIOL'
            add_node(dev, node_name, wire_type, 0, i, 'MIPIOL')
            add_node(dev, node_name, wire_type, 0, i + 1, wnames.wirenames[dat.portmap['IobufAOut']])
            df.setdefault((0, i), {})['mipi_ibuf'] = {'HSREN': wnames.wirenames[dat.portmap['IologicBIn'][40]]}
            # These two signals are noticed when MIPI input buffers are used. The
            # purpose is unclear, but will be repeated.
            node_name = f'X0Y0/MIPIEN0'
            add_node(dev, node_name, wire_type, 0, i, 'MIPIEN0')
            add_node(dev, node_name, wire_type, 0, 0, 'A4')
            node_name = f'X0Y0/MIPIEN1'
            add_node(dev, node_name, wire_type, 0, i, 'MIPIEN1')
            add_node(dev, node_name, wire_type, 0, 0, 'A5')
    elif device in {'GW1NS-4'}:
        for i in {1, 3, 5, 7, 10, 11, 14, 16}:
            df.setdefault((i, dev.cols - 1), {})['mipi_obuf'] = {}
        for i in chain(range(1, 9, 2), range(10, 17, 2), range(19, 26, 2), range(28, 35, 2)):
            node_name = f'X{i}Y0/MIPIOL'
            add_node(dev, node_name, wire_type, 0, i, 'MIPIOL')
            add_node(dev, node_name, wire_type, 0, i + 1, wnames.wirenames[dat.portmap['IobufAOut']])
            df.setdefault((0, i), {})['mipi_ibuf'] = {'HSREN': wnames.wirenames[dat.portmap['IologicBIn'][40]]}
            # These two signals are noticed when MIPI input buffers are used. The
            # purpose is unclear, but will be repeated.
            node_name = f'X37Y0/MIPIEN0'
            add_node(dev, node_name, wire_type, 0, i, 'MIPIEN0')
            add_node(dev, node_name, wire_type, 0, 0, 'D2')
            node_name = f'X37Y0/MIPIEN1'
            add_node(dev, node_name, wire_type, 0, i, 'MIPIEN1')
            add_node(dev, node_name, wire_type, 0, 0, 'D3')

def fse_create_i3c(dev, device, dat: Datfile):
    # The I3C_IOBUF is a slightly modified IOBUF, such units are
    # located on the bottom or right side of the chip depending on the series.
    # We use the extra_func mechanism because these blocks do not depend on the
    # cell type, but only on the coordinates.
    df = dev.extra_func
    wire_type = ''
    if device in {'GW1N-9', 'GW1N-9C'}:
        for i in range(1, dev.cols - 1):
            df.setdefault((0, i), {})['i3c_capable'] = {}
            df.setdefault((dev.rows - 1, i), {})['i3c_capable'] = {}
    elif device in {'GW1NS-4'}:
        for i in range(1, dev.cols - 1):
            df.setdefault((0, i), {})['i3c_capable'] = {}
        for i in range(1, dev.rows - 1):
            df.setdefault((i, dev.cols - 1), {})['i3c_capable'] = {}

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
              ('OSCA', 'GW5A-25A'):  ({}, {'OSCOUT': (19, 91, 'MPLL3CLKIN2'), 'OSCEN': (19, 90, 'SEL4')}),
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
def get_logic_clock_ins(device, dat: Datfile):
    if device in {'GW5A-25A'}:
        return {
                    (i, dat.gw5aStuff['CMuxTopIns'][i - 80][0] - 1,
                        dat.gw5aStuff['CMuxTopIns'][i - 80][1] - 1,
                        dat.gw5aStuff['CMuxTopIns'][i - 80][2])
                    for i in range(wnames.clknumbers['TRBDCLK0'], wnames.clknumbers['TRMDCLK1'] + 1)
                }
    # pre 5a
    return {
                (i, dat.cmux_ins[i - 80][0] - 1,
                    dat.cmux_ins[i - 80][1] - 1,
                    dat.cmux_ins[i - 80][2])
                for i in range(wnames.clknumbers['TRBDCLK0'], wnames.clknumbers['TRMDCLK1'] + 1)
            }

def fse_create_logic2clk(dev, device, dat: Datfile):
    for clkwire_idx, row, col, wire_idx in get_logic_clock_ins(device, dat):
        if row != -2:
            add_node(dev, wnames.clknames[clkwire_idx], "GLOBAL_CLK", row, col, wnames.wirenames[wire_idx])
            add_buf_bel(dev, row, col, wnames.wirenames[wire_idx])
            # Make list of the clock gates for nextpnr
            dev.extra_func.setdefault((row, col), {}).setdefault('clock_gates', []).append(wnames.wirenames[wire_idx])

def fse_create_osc(dev, device, fse):
    skip_nodes = False
    for row, rd in enumerate(dev.grid):
        for col, rc in enumerate(rd):
            if 51 in fse[rc.ttyp]['shortval']:
                # None of the supported chips, nor the planned TangMega138k,
                # have more than one OSC. However, in the GW25 series, the
                # fuses from Table 51 are found in several cells. The simplest
                # way to avoid creating duplicate nodes for OSC inputs and
                # outputs is to create them only in the first cell encountered.
                if skip_nodes:
                    dev.extra_func.setdefault((row, col), {}).update({'osc_fuses_only': {}})
                    continue
                osc_type = list(fse_osc(device, fse, rc.ttyp).keys())[0]
                dev.extra_func.setdefault((row, col), {}).update(
                        {'osc': {'type': osc_type}})
                _, aliases = _osc_ports[osc_type, device]
                for port, alias in aliases.items():
                    dev.nodes.setdefault(f'X{col}Y{row}/{port}', (port, {(row, col, port)}))[1].add(alias)
                    # Unlike previous series, GW5A has an OSC output as a clock
                    # wire, which means that, as a clock source output, it should
                    # be part of the clock MUX spread across the entire chip.
                    # Unfortunately, this is not the case—during trial
                    # compilations, a fuse was noticed for clock pip 520->211 and
                    # then 211->SPINE. This means that the OSC output is not a
                    # direct input to the clock MUX. So we are looking for all the
                    # intermediate wires and making them nodes in the hope that one
                    # of them will be picked up by the clock MUX.
                    if port == 'OSCOUT' and device in {'GW5A-25A'}:
                        a_row, a_col, a_wire = alias
                        for dest, srcs in dev.grid[a_row][a_col].clock_pips.items():
                            if a_wire in srcs:
                                add_node(dev, dest, "GLOBAL_CLK", a_row, a_col, dest)
                skip_nodes = True

def fse_create_gsr(dev, device):
    # Since, in the general case, there are several cells that have a
    # ['shortval'][20] table, in this case we do a test example with the GSR
    # primitive (Gowin Primitives User Guide.pdf - GSR), connect the GSRI input
    # to the button and see how the routing has changed in which of the
    # previously found cells.
    row, col = (0, 0)
    wire = 'C4'
    if device in {'GW2A-18', 'GW2A-18C'}:
        row, col = (27, 50)
    elif device in {'GW5A-25A'}:
        row, col = (28, 89)
        wire = 'LSR0'
    elif device in {'GW5AST-138C'}:
        row, col = (108, 165)
        wire = 'D7'
    dev.extra_func.setdefault((row, col), {}).update(
        {'gsr': {'wire': wire}})

def fse_create_bandgap(dev, device):
    # The cell and wire are found by a test compilation where the BGEN input is
    # connected to a button - such wires are easily traced in a binary image.
    if device in {'GW1NZ-1'}:
        dev.extra_func.setdefault((10, 18), {}).update(
            {'bandgap': {'wire': 'C1'}})

def fse_create_userflash(dev, device, dat):
    # dat[‘UfbIns’] and dat[‘UfbOuts’].
    # The outputs are exactly 32 by the number of bits and they are always
    # present, their positions correspond to bit indices - checked by
    # selectively connecting the outputs to LEDs.
    # The inputs depend on the Flash type - different types have different
    # inputs, e.g. XY or RCP addressing is used etc. During experimental
    # generation of images with input to button connection some inputs
    # description could not be found in the table, such inputs will be
    # specified here rigidly.
    # Flash types (see UG295-1.4.3E_Gowin User Flash User Guide.pdf)
    _flash_type = {'GW1N-1':  'FLASH96K',
                   'GW1NZ-1': 'FLASH64KZ',
                   'GW1N-4':  'FLASH256K', 'GW1NS-4': 'FLASH256K',
                   'GW1N-9':  'FLASH608K', 'GW1N-9C': 'FLASH608K'}
    if device not in _flash_type:
        return
    flash_type = _flash_type[device]
    ins_type = 'XY'
    if flash_type == 'FLASH96K':
        ins_type = 'RC'

    # userflash has neither its own cell type nor fuses, so it is logical to make it extra func.
    # use X0Y0 cell for convenience - a significant part of UserFlash pins are
    # located there, it saves from creating unnecessary nodes
    row, col = (0, 0)
    dev.extra_func.setdefault((row, col), {}).update(
        {'userflash': {'type': flash_type}})
    extra_func = dev.extra_func[(row, col)]['userflash']


    def make_port(r, c, wire, port, wire_type, pins):
        if r == -1 or c == -1:
            return
        bel = Bel()
        wire = wnames.wirenames[wire]
        bel.portmap[port] = wire
        if r - 1 != row or c - 1 != col :
            create_port_wire(dev, row, col, r - row - 1, c - col - 1, bel, 'USERFLASH', port, wire, wire_type)
        pins[port] = bel.portmap[port]

    # outputs
    outs = extra_func.setdefault('outs', {})
    for i, desc in enumerate(dat.compat_dict['UfbOuts']):
        port = f'DOUT{i}'
        r, c, wire = desc
        make_port(r, c, wire, port, 'FLASH_OUT', outs)

    # inputs
    ins = extra_func.setdefault('ins', {})
    # DIN first - we know there they are
    for i, desc in enumerate(dat.compat_dict['UfbIns'][58:]):
        port = f'DIN{i}'
        r, c, wire = desc
        make_port(r, c, wire, port, 'FLASH_IN', ins)

    if ins_type == 'RC':
        for i, desc in enumerate(dat.compat_dict['UfbIns'][21:27]):
            port = f'RA{i}'
            r, c, wire = desc
            make_port(r, c, wire, port, 'FLASH_IN', ins)
        for i, desc in enumerate(dat.compat_dict['UfbIns'][27:33]):
            port = f'CA{i}'
            r, c, wire = desc
            make_port(r, c, wire, port, 'FLASH_IN', ins)
        for i, desc in enumerate(dat.compat_dict['UfbIns'][33:39]):
            port = f'PA{i}'
            r, c, wire = desc
            make_port(r, c, wire, port, 'FLASH_IN', ins)
        for i, desc in enumerate(dat.compat_dict['UfbIns'][39:43]):
            port = f'MODE{i}'
            r, c, wire = desc
            make_port(r, c, wire, port, 'FLASH_IN', ins)
        for i, desc in enumerate(dat.compat_dict['UfbIns'][43:45]):
            port = f'SEQ{i}'
            r, c, wire = desc
            make_port(r, c, wire, port, 'FLASH_IN', ins)
        for i, desc in enumerate(dat.compat_dict['UfbIns'][45:50]):
            port = ['ACLK', 'PW', 'RESET', 'PE', 'OE'][i]
            r, c, wire = desc
            make_port(r, c, wire, port, 'FLASH_IN', ins)
        for i, desc in enumerate(dat.compat_dict['UfbIns'][50:52]):
            port = f'RMODE{i}'
            r, c, wire = desc
            make_port(r, c, wire, port, 'FLASH_IN', ins)
        for i, desc in enumerate(dat.compat_dict['UfbIns'][52:54]):
            port = f'WMODE{i}'
            r, c, wire = desc
            make_port(r, c, wire, port, 'FLASH_IN', ins)
        for i, desc in enumerate(dat.compat_dict['UfbIns'][54:56]):
            port = f'RBYTESEL{i}'
            r, c, wire = desc
            make_port(r, c, wire, port, 'FLASH_IN', ins)
        for i, desc in enumerate(dat.compat_dict['UfbIns'][56:58]):
            port = f'WBYTESEL{i}'
            r, c, wire = desc
            make_port(r, c, wire, port, 'FLASH_IN', ins)
    else:
        # GW1NS-4 has a direct connection of Flash with the built-in Cortex-M3
        # and some wires during test compilations showed connections different
        # from the table in the DAT file
        for i, desc in enumerate(dat.compat_dict['UfbIns'][:6]):
            port = ['XE', 'YE', 'SE', 'PROG', 'ERASE', 'NVSTR'][i]
            r, c, wire = desc
            if device == 'GW1NS-4' and port in {'XE', 'YE', 'SE'}:
                r, c, wire = {'XE':(15, 1, 28), 'YE': (15, 1, 0), 'SE':(14, 1, 31)}[port]
            make_port(r, c, wire, port, 'FLASH_IN', ins)
        for i, desc in enumerate(dat.compat_dict['UfbIns'][6:15]):
            port = f'XADR{i}'
            r, c, wire = desc
            if device == 'GW1NS-4' and i < 7:
                r, c, wire = (14, 1, 3 + 4 * i)
            make_port(r, c, wire, port, 'FLASH_IN', ins)
        for i, desc in enumerate(dat.compat_dict['UfbIns'][15:21]):
            port = f'YADR{i}'
            r, c, wire = desc
            if device == 'GW1NS-4' and i < 6:
                r, c, wire = (15, 1, 4 + 4 * i)
            make_port(r, c, wire, port, 'FLASH_IN', ins)

    # XXX INUSEN - is observed to be connected to the VSS when USERFLASH is used
    if flash_type != 'FLASH64KZ':
        ins['INUSEN'] = 'C0'

# Create a port and a wire, and if necessary, a Himbaechel node, but we
# don't need Bel itself — it will be created in nextpnr.
def make_port(dev, row, col, r, c, wire, bel_name, port, wire_type, pins):
    if r < 0 or c < 0:
        return
    bel = Bel()
    wire = wnames.wirenames[wire]
    bel.portmap[port] = wire
    if r - 1 != row or c - 1 != col :
        create_port_wire(dev, row, col, r - row - 1, c - col - 1, bel, bel_name, port, wire, wire_type)
    pins[port] = bel.portmap[port]

def fse_create_pincfg(dev, device, dat):
    if device not in {'GW5A-25A'}:
        return
    # place the bel where a change in routing has been experimentally observed
    # when the I2C pin function is disabled/enabled
    row, col = (9, 88)
    dev.extra_func.setdefault((row, col), {}).update({'pincfg': {}})
    extra_func = dev.extra_func[(row, col)]['pincfg']

    ins = extra_func.setdefault('ins', {})
    inputs = [('SSPI', 1), ('UNK0_VCC', 0), ('UNK1_VCC', 2), ('UNK2_VCC', 3), ('UNK3_VCC', 4), ('UNK4_VCC', 5), ]
    for port, idx in inputs:
        r, c, wire = dat.gw5aStuff['CibFabricNode'][idx]
        make_port(dev, row, col, r, c, wire, 'PINCFG', port, 'PINCFG_IN', ins)

    # special input (not in the DAT file)
    make_port(dev, row, col, 10, 89, 17, 'PINCFG', 'I2C', 'PINCFG_IN', ins)

def fse_create_emcu(dev, device, dat):
    # Mentions of the NS-2 series are excluded from the latest Gowin
    # documentation so that only one chip remains with the ARM processor
    if device != 'GW1NS-4':
        return

    # In (0, 0) is the CPU enabled/disabled flag, so place the CPU there
    row, col = (0, 0)
    dev.extra_func.setdefault((row, col), {}).update({'emcu': {}})
    extra_func = dev.extra_func[(row, col)]['emcu']

    # outputs
    outs = extra_func.setdefault('outs', {})
    single_wires = [('MTXHRESETN', 87), ('UART0TXDO', 32), ('UART1TXDO', 33),
                    ('UART0BAUDTICK', 34), ('UART1BAUDTICK', 35), ('INTMONITOR', 36),
                    ('SRAM0WREN0', 50), ('SRAM0WREN1', 51), ('SRAM0WREN2', 52), ('SRAM0WREN3', 53),
                    ('SRAM0CS', 86), ('TARGFLASH0HSEL', 88), ('TARGFLASH0HTRANS0', 118), ('TARGFLASH0HTRANS1', 119),
                    ('TARGEXP0HSEL', 127), ('TARGEXP0HTRANS0', 160), ('TARGEXP0HTRANS1', 161),
                    ('TARGEXP0HWRITE', 162),
                    ('TARGEXP0HSIZE0', 163), ('TARGEXP0HSIZE1', 164), ('TARGEXP0HSIZE2', 165),
                    ('TARGEXP0HBURST0', 166), ('TARGEXP0HBURST1', 167), ('TARGEXP0HBURST2', 168),
                    ('TARGEXP0HPROT0', 169), ('TARGEXP0HPROT1', 170),
                    ('TARGEXP0HPROT2', 171), ('TARGEXP0HPROT3', 172),
                    ('TARGEXP0MEMATTR0', 173), ('TARGEXP0MEMATTR1', 174),
                    ('TARGEXP0EXREQ', 175),
                    ('TARGEXP0HMASTER0', 176), ('TARGEXP0HMASTER1', 177),
                    ('TARGEXP0HMASTER2', 178), ('TARGEXP0HMASTER3', 179),
                    ('TARGEXP0HMASTLOCK', 212), ('TARGEXP0HREADYMUX', 213),
                    ('INITEXP0HREADY', 251), ('INITEXP0HRESP', 252), ('INITEXP0EXRESP', 253),
                    ('APBTARGEXP2PSEL', 257), ('APBTARGEXP2PENABLE', 258), ('APBTARGEXP2PWRITE', 271),
                    ('APBTARGEXP2PSTRB0', 304), ('APBTARGEXP2PSTRB1', 305),
                    ('APBTARGEXP2PSTRB2', 306), ('APBTARGEXP2PSTRB3', 307),
                    ('APBTARGEXP2PPROT0', 308), ('APBTARGEXP2PPROT1', 309), ('APBTARGEXP2PPROT2', 310),
                    ('DAPJTAGNSW', 313),
                    ('TPIUTRACEDATA0', 314), ('TPIUTRACEDATA1', 315),
                    ('TPIUTRACEDATA2', 316), ('TPIUTRACEDATA3', 317),
                    ]
    for port, idx in single_wires:
        r, c, wire = dat.compat_dict['EMcuOuts'][idx]
        make_port(dev, row, col, r, c, wire, 'EMCU', port, 'EMCU_OUT', outs)

    # gpio out - 16 output wires
    for i, desc in enumerate(dat.compat_dict['EMcuOuts'][0:16]):
        port = f'IOEXPOUTPUTO{i}'
        r, c, wire = desc
        make_port(dev, row, col, r, c, wire, 'EMCU', port, 'EMCU_OUT', outs)

    # gpio outputenable - 16 output wires
    for i, desc in enumerate(dat.compat_dict['EMcuOuts'][16:32]):
        port = f'IOEXPOUTPUTENO{i}'
        r, c, wire = desc
        make_port(dev, row, col, r, c, wire, 'EMCU', port, 'EMCU_OUT', outs)

    # ram addr- 13 output wires
    for i, desc in enumerate(dat.compat_dict['EMcuOuts'][37:50]):
        port = f'SRAM0ADDR{i}'
        r, c, wire = desc
        make_port(dev, row, col, r, c, wire, 'EMCU', port, 'EMCU_OUT', outs)

    # ram data- 32 output wires
    for i, desc in enumerate(dat.compat_dict['EMcuOuts'][54:86]):
        port = f'SRAM0WDATA{i}'
        r, c, wire = desc
        make_port(dev, row, col, r, c, wire, 'EMCU', port, 'EMCU_OUT', outs)

    # flash addr- 29 output wires
    for i, desc in enumerate(dat.compat_dict['EMcuOuts'][89:118]):
        port = f'TARGFLASH0HADDR{i}'
        r, c, wire = desc
        make_port(dev, row, col, r, c, wire, 'EMCU', port, 'EMCU_OUT', outs)

    # 32 output wires, unknown purpose
    for i, desc in enumerate(dat.compat_dict['EMcuOuts'][128:160]):
        port = f'TARGEXP0HADDR{i}'
        r, c, wire = desc
        make_port(dev, row, col, r, c, wire, 'EMCU', port, 'EMCU_OUT', outs)

    # 32 output wires, unknown purpose
    for i, desc in enumerate(dat.compat_dict['EMcuOuts'][180:212]):
        port = f'TARGEXP0HWDATA{i}'
        r, c, wire = desc
        make_port(dev, row, col, r, c, wire, 'EMCU', port, 'EMCU_OUT', outs)

    # 32 output wires, unknown purpose
    for i, desc in enumerate(dat.compat_dict['EMcuOuts'][219:251]):
        port = f'INITEXP0HRDATA{i}'
        r, c, wire = desc
        make_port(dev, row, col, r, c, wire, 'EMCU', port, 'EMCU_OUT', outs)

    # 12 output wires, unknown purpose
    for i, desc in enumerate(dat.compat_dict['EMcuOuts'][259:271]):
        port = f'APBTARGEXP2PADDR{i}'
        r, c, wire = desc
        make_port(dev, row, col, r, c, wire, 'EMCU', port, 'EMCU_OUT', outs)

    # 32 output wires, unknown purpose
    for i, desc in enumerate(dat.compat_dict['EMcuOuts'][272:304]):
        port = f'APBTARGEXP2PWDATA{i}'
        r, c, wire = desc
        make_port(dev, row, col, r, c, wire, 'EMCU', port, 'EMCU_OUT', outs)

    # inputs
    # funny thing - I have not been able to find ports PORESETN and SYSRESETN, they just
    # don't connect to the button. There is a suspicion that implicit
    # connection from GSR primitives is used, now it comes in handy.
    ins = extra_func.setdefault('ins', {})
    clock_wires = [('FCLK', 0), ('RTCSRCCLK', 3)]
    for port, idx in clock_wires:
        r, c, wire = dat.compat_dict['EMcuIns'][idx]
        make_port(dev, row, col, r, c, wire, 'EMCU', port, 'TILE_CLK', ins)

    single_wires = [('UART0RXDI', 20), ('UART1RXDI', 21),
                    ('TARGFLASH0HRESP', 89), ('TARGFLASH0HREADYOUT', 91),
                    ('TARGEXP0HRESP', 125), ('TARGEXP0HREADYOUT', 124), ('TARGEXP0EXRESP', 126),
                    ('TARGEXP0HRUSER0', 127), ('TARGEXP0HRUSER1', 128), ('TARGEXP0HRUSER2', 129),
                    ('INITEXP0HSEL', 130), ('INITEXP0HTRANS0', 163), ('INITEXP0HTRANS1', 164),
                    ('INITEXP0HWRITE', 165), ('INITEXP0HSIZE0', 166), ('INITEXP0HSIZE1', 167), ('INITEXP0HSIZE2', 168),
                    ('INITEXP0HBURST0', 169), ('INITEXP0HBURST1', 170), ('INITEXP0HBURST2', 171),
                    ('INITEXP0HPROT0', 172), ('INITEXP0HPROT1', 173), ('INITEXP0HPROT2', 174), ('INITEXP0HPROT3', 175),
                    ('INITEXP0MEMATTR0', 176), ('INITEXP0MEMATTR1', 177), ('INITEXP0EXREQ', 178),
                    ('INITEXP0HMASTER0', 179), ('INITEXP0HMASTER1', 180),
                    ('INITEXP0HMASTER2', 181), ('INITEXP0HMASTER3', 182),
                    ('INITEXP0HMASTLOCK', 215), ('INITEXP0HAUSER', 216),
                    ('INITEXP0HWUSER0', 217), ('INITEXP0HWUSER1', 218),
                    ('INITEXP0HWUSER2', 219), ('INITEXP0HWUSER3', 220),
                    ('APBTARGEXP2PREADY', 253), ('APBTARGEXP2PSLVERR', 254),
                    ('FLASHERR', 263), ('FLASHINT', 264),
                    ]
    for port, idx in single_wires:
        r, c, wire = dat.compat_dict['EMcuIns'][idx]
        make_port(dev, row, col, r, c, wire, 'EMCU', port, 'EMCU_IN', ins)

    # gpio inout - 16 input wires
    for i, desc in enumerate(dat.compat_dict['EMcuIns'][4:20]):
        port = f'IOEXPINPUTI{i}'
        r, c, wire = desc
        make_port(dev, row, col, r, c, wire, 'EMCU', port, 'EMCU_IN', ins)

    # read from ram - 32 input wires
    for i, desc in enumerate(dat.compat_dict['EMcuIns'][22:54]):
        port = f'SRAM0RDATA{i}'
        r, c, wire = desc
        make_port(dev, row, col, r, c, wire, 'EMCU', port, 'EMCU_IN', ins)

    # 32 input wires, unknown purpose
    for i, desc in enumerate(dat.compat_dict['EMcuIns'][92:124]):
        port = f'TARGEXP0HRDATA{i}'
        r, c, wire = desc
        make_port(dev, row, col, r, c, wire, 'EMCU', port, 'EMCU_IN', ins)

    # 32 input wires, unknown purpose
    for i, desc in enumerate(dat.compat_dict['EMcuIns'][131:163]):
        port = f'INITEXP0HADDR{i}'
        r, c, wire = desc
        make_port(dev, row, col, r, c, wire, 'EMCU', port, 'EMCU_IN', ins)

    # 32 input wires, unknown purpose
    for i, desc in enumerate(dat.compat_dict['EMcuIns'][183:215]):
        port = f'INITEXP0HWDATA{i}'
        r, c, wire = desc
        make_port(dev, row, col, r, c, wire, 'EMCU', port, 'EMCU_IN', ins)

    # 32 input wires, unknown purpose
    for i, desc in enumerate(dat.compat_dict['EMcuIns'][221:253]):
        port = f'APBTARGEXP2PRDATA{i}'
        r, c, wire = desc
        make_port(dev, row, col, r, c, wire, 'EMCU', port, 'EMCU_IN', ins)

    # 5 input wires connected to GND, may be GPINT
    for i, desc in enumerate(dat.compat_dict['EMcuIns'][265:270]):
        port = f'GPINT{i}'
        r, c, wire = desc
        make_port(dev, row, col, r, c, wire, 'EMCU', port, 'EMCU_IN', ins)


def fse_bram(fse, aux = False):
    bels = {}
    name = 'BSRAM'
    if aux:
        name = 'BSRAM_AUX'
    bels[name] = Bel()
    return bels

def fse_dsp(fse, aux = False):
    bels = {}
    if aux:
        bels['DSP_AUX0'] = Bel()
        bels['DSP_AUX1'] = Bel()
    else:
        # These are two macro DSPs, their purpose is to manage the control
        # signals CE, CLK and RESET, which seem to be allocated to different
        # subblocks from a common pool, the size of which reaches 4 possible
        # PIPs for each type of signal.
        # In other words, only the portmap that describes the pool is important here.
        bels['DSP'] = Bel()
        bels['DSP0'] = Bel()  # Macro 0
        bels['DSP1'] = Bel()  # Macro 1
        # Padd
        bels['PADD900'] = Bel()  # macro 0 padd9 0
        bels['PADD901'] = Bel()  # macro 0 padd9 1
        bels['PADD902'] = Bel()  # macro 0 padd9 2
        bels['PADD903'] = Bel()  # macro 0 padd9 3
        bels['PADD1800'] = Bel() # macro 0 padd18 0
        bels['PADD1801'] = Bel() # macro 0 padd18 1
        bels['PADD910'] = Bel()  # macro 1 padd9 0
        bels['PADD911'] = Bel()  # macro 1 padd9 1
        bels['PADD912'] = Bel()  # macro 1 padd9 2
        bels['PADD913'] = Bel()  # macro 1 padd9 3
        bels['PADD1810'] = Bel() # macro 1 padd18 0
        bels['PADD1811'] = Bel() # macro 1 padd18 1
        # mult
        bels['MULT9X900'] = Bel()   # macro 0 mult9x9 0
        bels['MULT9X901'] = Bel()   # macro 0 mult9x9 1
        bels['MULT9X902'] = Bel()   # macro 0 mult9x9 2
        bels['MULT9X903'] = Bel()   # macro 0 mult9x9 3
        bels['MULT18X1800'] = Bel() # macro 0 mult18x18 0
        bels['MULT18X1801'] = Bel() # macro 0 mult18x18 1
        bels['MULT9X910'] = Bel()   # macro 1 mult9x9 0
        bels['MULT9X911'] = Bel()   # macro 1 mult9x9 1
        bels['MULT9X912'] = Bel()   # macro 1 mult9x9 2
        bels['MULT9X913'] = Bel()   # macro 1 mult9x9 3
        bels['MULT18X1810'] = Bel() # macro 1 mult18x18 0
        bels['MULT18X1811'] = Bel() # macro 1 mult18x18 1
        # alu
        bels['ALU54D0'] = Bel()     # macro 0 ALU54D
        bels['ALU54D1'] = Bel()     # macro 1 ALU54D
        # multalu
        bels['MULTALU18X180'] = Bel()     # macro 0 multalu 18x18
        bels['MULTALU18X181'] = Bel()     # macro 1 multalu 18x18
        bels['MULTALU36X180'] = Bel()     # macro 0 multalu 36x18
        bels['MULTALU36X181'] = Bel()     # macro 1 multalu 36x18
        bels['MULTADDALU18X180'] = Bel()     # macro 0 multaddalu 18x18
        bels['MULTADDALU18X181'] = Bel()     # macro 1 multaddalu 18x18

        bels['MULT36X36'] = Bel()   # entire DSP mult36x36

    return bels

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

def set_chip_flags(dev, device):
    if device not in {"GW1NS-4", "GW1N-9"}:
        dev.chip_flags.append("HAS_SP32")
    if device in {'GW1N-1', 'GW1N-4', 'GW1NS-2', 'GW1N-9', 'GW2A-18'}:
        dev.chip_flags.append("NEED_SP_FIX")
    if device in {'GW1N-9C', 'GW2A-18C'}:
        dev.chip_flags.append("NEED_BSRAM_OUTREG_FIX")
    if device in {'GW1N-1', 'GW1NZ-1', 'GW1NS-2', 'GW1N-4', 'GW1NS-4', 'GW1N-9', 'GW1N-9C', 'GW2A-18', 'GW2A-18C'}:
        dev.chip_flags.append("NEED_BLKSEL_FIX")
    if device in {'GW1NZ-1'}:
        dev.chip_flags.append("HAS_BANDGAP")
    dev.chip_flags.append("HAS_PLL_HCLK")
    if device in {'GW2A-18', 'GW2A-18C'}:
        dev.chip_flags.append("HAS_CLKDIV_HCLK")
    if device in {'GW5A-25A'}:
        dev.chip_flags.append("HAS_PINCFG")
        dev.chip_flags.append("HAS_DFF67")
        dev.chip_flags.append("HAS_CIN_MUX")
        dev.chip_flags.append("NEED_BSRAM_RESET_FIX")
        dev.chip_flags.append("NEED_SDP_FIX")

    if device in {'GW5A-25A'}:
        dev.dcs_prefix = "CLKIN"

def from_fse(device, fse, dat: Datfile):
    wnames.select_wires(device)
    dev = Device()
    fse_create_simplio_rows(dev, dat)
    ttypes = {t for row in fse['header']['grid'][61] for t in row}
    tiles = {}
    bram_ttypes = get_tile_types_by_func(dev, dat, fse, 'B')
    bram_aux_ttypes = get_tile_types_by_func(dev, dat, fse, 'b')
    dsp_ttypes = get_tile_types_by_func(dev, dat, fse, 'D')
    dsp_aux_ttypes = get_tile_types_by_func(dev, dat, fse, 'd')
    pll_ttypes = get_tile_types_by_func(dev, dat, fse, 'P')
    pll_ttypes.update(get_tile_types_by_func(dev, dat, fse, 'p'))
    for ttyp in ttypes:
        w = fse[ttyp]['width']
        h = fse[ttyp]['height']
        tile = Tile(w, h, ttyp)
        tile.pips = fse_pips(fse, ttyp, device, 2, wnames.wirenames)
        tile.clock_pips = fse_pips(fse, ttyp, device, 38, wnames.clknames)
        tile.alonenode = fse_alonenode(fse, ttyp, device, 69)
        tile.alonenode_6 = fse_alonenode(fse, ttyp, device, 6)
        if 5 in fse[ttyp]['shortval']:
            tile.bels = fse_luts(fse, ttyp, device)
        elif 51 in fse[ttyp]['shortval']:
            tile.bels = fse_osc(device, fse, ttyp)
        elif ttyp in bram_ttypes:
            tile.bels = fse_bram(fse)
        elif ttyp in bram_aux_ttypes and device not in {'GW5A-25A'}:
            tile.bels = fse_bram(fse, True)
        elif ttyp in dsp_ttypes and device not in {'GW5A-25A'}:
            tile.bels = fse_dsp(fse)
        elif ttyp in dsp_aux_ttypes:
            tile.bels = fse_dsp(fse, True)
        elif ttyp in pll_ttypes:
            tile.bels = fse_pll(device, fse, ttyp)
        tile.bels.update(fse_iologic(device, fse, ttyp))
        tiles[ttyp] = tile

    fse_fill_logic_tables(dev, fse, device)
    dev.grid = [[tiles[ttyp] for ttyp in row] for row in fse['header']['grid'][61]]
    fse_create_clocks(dev, device, dat, fse)
    fse_create_pll_clock_aliases(dev, device)
    fse_create_bottom_io(dev, device)
    fse_create_tile_types(dev, dat)
    # No SSRAM in GW5A-25A
    if device in {'GW5A-25A'}:
        dev.tile_types.setdefault('C', set()).update(dev.tile_types['M'])
        dev.tile_types['P'] = set()
        dev.tile_types['M'] = set()
        # XXX
        dev.tile_types['D'] = set()

    # GW5 series have DFF6 and DFF7, so leave Q6 and Q7 as is
    if device not in {'GW5A-25A'}:
        create_vcc_pips(dev, tiles)
    create_default_pips(tiles)

    fse_create_diff_types(dev, device)
    fse_create_hclk_nodes(dev, device, fse, dat)
    fse_create_slot_plls(dev, device, fse, dat)
    fse_create_adc(dev, device, fse, dat)
    fse_create_mipi(dev, device, dat)
    fse_create_i3c(dev, device, dat)
    fse_create_io16(dev, device)
    fse_create_osc(dev, device, fse)
    fse_create_gsr(dev, device)
    fse_create_bandgap(dev, device)
    fse_create_userflash(dev, device, dat)
    fse_create_pincfg(dev, device, dat)
    fse_create_emcu(dev, device, dat)
    fse_create_logic2clk(dev, device, dat)
    fse_create_dhcen(dev, device, fse, dat)
    fse_create_dlldly(dev, device)
    create_segments(dev, device)
    disable_plls(dev, device)
    sync_extra_func(dev)
    set_chip_flags(dev, device)
    return dev

# get fuses for attr/val set using short/longval table
# returns a bit set
def get_table_fuses(attrs, table):
    bits = set()
    for key, fuses in table.items():
        # all 1/2/16 "features" must be present to be able to use a set of bits from the record
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

# get fuses for attr/val set using longfuses table for ttyp
# returns a bit set
def get_long_fuses(dev, ttyp, attrs, table_name):
    return get_table_fuses(attrs, dev.longfuses[ttyp][table_name])

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

# get fuses for attr/val set for bank use whatever table is preset in the cell: IOBA or IOBB
# returns a bit set
def get_bank_io_fuses(dev, ttyp, attrs):
    tablename = 'IOBA'
    if tablename not in dev.longval[ttyp]:
        tablename = 'IOBB'
        if tablename not in dev.longval[ttyp]:
            return set()
    return get_table_fuses(attrs, dev.longval[ttyp][tablename])

# add the attribute/value pair into an set, which is then passed to
# get_longval_fuses() and get_shortval_fuses()
def add_attr_val(dev, logic_table, attrs, attr, val):
    table = dev.logicinfo[logic_table]
    attrval = table.get((attr, val))
    if attrval:
        attrs.add(attrval)

def get_pins(device):
    if device not in {"GW1N-1", "GW1NZ-1", "GW1N-4", "GW1N-9", "GW1NR-9", "GW1N-9C", "GW1NR-9C", "GW1NSR-4C", "GW2A-18", "GW2A-18C", "GW2AR-18C", "GW5A-25A"}:
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
        pkgs, pins, bank_pins = get_pins("GW1NSR-4C")
        res = {}
        res.update(pkgs)
        res_bank_pins = {}
        res_bank_pins.update(bank_pins)
        return (res, {
            "GW1NS-4": pins,
            "GW1NSR-4C": pins, # XXX for nextpnr compatibility (remove)
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
    elif device =="GW5A-25A": # Fix me
        pkgs, pins, bank_pins = get_pins("GW5A-25A")
        res = {}
        res.update(pkgs)
        res_bank_pins = {}
        res_bank_pins.update(bank_pins)
        return (res, {
            "GW5A-25A": pins,
        }, res_bank_pins)
    else:
        raise Exception("unsupported device")

_adc_inputs = [(0, 'CLK'), (2, 'VSENCTL0'), (3, 'VSENCTL1'), (4, 'VSENCTL2'), (5, 'ADCMODE'),
               (6, 'DRSTN'), (7, 'ADCREQI'), (8, 'MDRP_CLK'), (10, 'MDRP_WDATA0'), (11, 'MDRP_WDATA1'),
               (12, 'MDRP_WDATA2'), (13, 'MDRP_WDATA3'), (14, 'MDRP_WDATA4'), (15, 'MDRP_WDATA5'),
               (16, 'MDRP_WDATA6'), (17, 'MDRP_WDATA7'), (18, 'MDRP_A_INC'), (20, 'MDRP_OPCODE0'),
               (21, 'MDRP_OPCODE1'), (22, 'ADCEN')];
_adc_outputs = [(0, 'ADCRDY'), (2, 'ADCVALUE0'), (3, 'ADCVALUE1'), (4, 'ADCVALUE2'), (5, 'ADCVALUE3'),
                (6, 'ADCVALUE4'), (7, 'ADCVALUE5'), (8, 'ADCVALUE6'), (9, 'ADCVALUE7'), (10, 'ADCVALUE8'),
                (11, 'ADCVALUE9'), (12, 'ADCVALUE10'), (13, 'ADCVALUE11'), (14, 'ADCVALUE12'),
                (15, 'ADCVALUE13'), (17, 'MDRP_RDATA0'), (18, 'MDRP_RDATA1'), (19, 'MDRP_RDATA2'),
                (20, 'MDRP_RDATA3'), (21, 'MDRP_RDATA4'), (22, 'MDRP_RDATA5'), (23, 'MDRP_RDATA6'),
                (24, 'MDRP_RDATA7')]
_pll_inputs = [(5, 'CLKFB'), (6, 'FBDSEL0'), (7, 'FBDSEL1'), (8, 'FBDSEL2'), (9, 'FBDSEL3'),
               (10, 'FBDSEL4'), (11, 'FBDSEL5'),
               (12, 'IDSEL0'), (13, 'IDSEL1'), (14, 'IDSEL2'), (15, 'IDSEL3'), (16, 'IDSEL4'),
               (17, 'IDSEL5'),
               (18, 'ODSEL0'), (19, 'ODSEL1'), (20, 'ODSEL2'), (21, 'ODSEL3'), (22, 'ODSEL4'),
               (23, 'ODSEL5'), (0, 'RESET'), (1, 'RESET_P'),
               (24, 'PSDA0'), (25, 'PSDA1'), (26, 'PSDA2'), (27, 'PSDA3'),
               (28, 'DUTYDA0'), (29, 'DUTYDA1'), (30, 'DUTYDA2'), (31, 'DUTYDA3'),
               (32, 'FDLY0'), (33, 'FDLY1'), (34, 'FDLY2'), (35, 'FDLY3')]
_plla_inputs = [(0, 'RESET'), (2, 'RESET_I'), (4, 'CLKIN'), (5, 'CLKFB'), (91, 'PSSEL0'),
                (92, 'PSSEL1'), (93, 'PSDIR'), (94, 'PSPULSE'), (100, 'PSSEL2'), (101, 'PLLPWD'),
                (102, 'RESET_O'), (191, 'SSCPOL'), (192, 'SSCON'), (193, 'SSCMDSEL0'),
                (194, 'SSCMDSEL1'), (195, 'SSCMDSEL2'), (196, 'SSCMDSEL3'), (197, 'SSCMDSEL4'),
                (198, 'SSCMDSEL5'), (199, 'SSCMDSEL6'), (200, 'SSCMDSEL_FRAC0'), (201, 'SSCMDSEL_FRAC1'),
                (202, 'SSCMDSEL_FRAC2'), (204, 'MDCLK'), (205, 'MDOPC0'), (206, 'MDOPC1'),
                (207, 'MDAINC'), (208, 'MDWDI0'), (209, 'MDWDI1'), (210, 'MDWDI2'), (211, 'MDWDI3'),
                (212, 'MDWDI4'), (213, 'MDWDI5'), (214, 'MDWDI6'), (215, 'MDWDI7'),]
_pll_outputs = [(0, 'CLKOUT'), (1, 'LOCK'), (2, 'CLKOUTP'), (3, 'CLKOUTD'), (4, 'CLKOUTD3')]
_plla_outputs = [(1, 'LOCK'), (10, 'CLKOUT0'), (11, 'CLKOUT1'), (12, 'CLKOUT2'), (13, 'CLKOUT3'),
                 (14, 'CLKOUT4'), (15, 'CLKOUT5'), (16, 'CLKOUT6'),
                 (24, 'MDRDO0'), (25, 'MDRDO1'), (26, 'MDRDO2'), (27, 'MDRDO3'), (28, 'MDRDO4'),
                 (29, 'MDRDO5'), (30, 'MDRDO6'), (31, 'MDRDO7'), ]
_iologic_inputs =  [(0, 'D'), (1, 'D0'), (2, 'D1'), (3, 'D2'), (4, 'D3'), (5, 'D4'),
                    (6, 'D5'), (7, 'D6'), (8, 'D7'), (9, 'D8'), (10, 'D9'), (11, 'D10'),
                    (12, 'D11'), (13, 'D12'), (14, 'D13'), (15, 'D14'), (16, 'D15'),
                    (17, 'CLK'), (18, 'ICLK'), (19, 'PCLK'), (20, 'FCLK'), (21, 'TCLK'),
                    (22, 'MCLK'), (23, 'SET'), (24, 'RESET'), (25, 'PRESET'), (26, 'CLEAR'),
                    (27, 'TX'), (28, 'TX0'), (29, 'TX1'), (30, 'TX2'), (31, 'TX3'),
                    (32, 'WADDR0'), (33, 'WADDR1'), (34, 'WADDR2'), (35, 'RADDR0'),
                    (36, 'RADDR1'), (37, 'RADDR2'), (38, 'CALIB'), (39, 'DI'), (40, 'SETN'),
                    (41, 'SDTAP'), (42, 'VALUE'), (42, 'CE'), (43, 'DASEL'), (44, 'DASEL0'), (45, 'DASEL1'),
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
_bsram_control_ins = ['CLK', 'OCE', 'CE', 'RESET', 'WRE']
_alusel = [[('CE0', 0), ('LSR2', 0), ('LSR0', 1), ('LSR1', 1), ('LSR2', 1), ('CE2', 2),  ('LSR2', 2)],
           [('CE0', 5), ('CE1', 5),  ('CE2', 5),  ('LSR2', 5), ('CE2', 6),  ('LSR2', 6), ('CE2', 7)]]
def get_pllout_global_name(row, col, wire, device):
    for name, loc in _pll_loc[device].items():
        if loc == (row, col, wire):
            return name
    raise Exception(f"bad PLL output {device} ({row}, {col}){wire}")

def need_create_multiple_nodes(device, name):
    if name.startswith("RPLLA") and device in {'GW2A-18', 'GW2A-18C'}:
        return True
    if name == "BSRAM" or name.startswith("MULT") or name.startswith("PADD") or name.startswith("ALU54D"):
        return True
    if name.startswith('IOB') and device in {'GW5A-25A'}:
        return True
    return False

# create simple port or the Himbaechel node
def create_port_wire(dev, row, col, row_off, col_off, bel, bel_name, port, wire, wire_type):
    # for aux cells create Himbaechel nodes
    if row_off or col_off:
        bel.portmap[port] = f'{bel_name}{port}{wire}'
        node_name = f'X{col}Y{row}/{bel_name}{port}{wire}'
        add_node(dev, node_name, wire_type, row, col, f'{bel_name}{port}{wire}')
        add_node(dev, node_name, wire_type, row+row_off, col+col_off, wire)
    else:
        bel.portmap[port] = wire

# The IO blocks in the GW5A family can (and in most cases will) be separated
# into different cells. This includes not only fuses, but also wires like IBUF
# output or OBUF input. But externally (as for example for specifying a pin in
# a CST file) they are in the same cell.
#
#For example:
#
# IOT3A is located in cell (0, 2) and IOT3B is located in cell (0, 3), but from
# the IDE point of view it is one cell IOT3 (0, 2).
#
# We solve this problem as follows: to minimize the logic in nextpnr, we place
# A and B in the same IOT3 cell and make himbaechel nodes for the wires so that
# B's ports are also seen in the IOT3 cell.
#
# This will allow nextpnr to do placement and routing, but doesn't account for
# the fact that the fuses for B need to be set in a different cell. To solve
# this, we add a descriptor field to each Bel that specifies the offsets to the
# cell where the fuses should be set.
# This breaks unpacking, but it is also solvable.

# By experimentally placing the IBUF IO by setting constraints in the CST file
# and then searching in which cell the bits were changed, the offsets depending
# on the cell type were determined.
_gw5_fuse_cell_offset = {
        'top': {
             50: (0, 0), 51: (0, 1), 242: (0, 0), 382: (0, 0), 383: (0, 1), 387: (0, 1),
            388: (0, 0), 389: (0, 1), 390: (0, 0), 395: (0, 1), 400: (0, 1), 403: (0, 0),
            410: (0, 0), 411: (0, 0), 420: (0, 0), 421: (0, 0), 422: (0, 1), 423: (0, 1),
            466: (0, 0)
            },
        'bottom': {
             48: (0, 0), 49: (0, 1), 247: (0, 0), 248: (0, 1), 251: (0, 1), 263: (0, 0),
             274: (0, 1), 393: (0, 0), 394: (0, 0), 396: (0, 0), 397: (0, 0), 405: (0, 1),
             407: (0, 0), 436: (0, 1), 437: (0,0), 438: (0, 1), 439: (0, 0),
            },
        'left': {
            57: (0, 0), 74: (1, 0), 243: (0, 0), 244: (1, 0), 257: (0, 0), 258: (0, 0),
            272: (0, 0), 384: (1, 0),
            },
        'right': {
            54: (0, 0), 220: (0, 0), 245: (0, 0), 246: (1, 0), 260: (0, 0), 385: (1, 0),
            391: (0, 0), 392: (0, 0), 399: (0, 0), 401: (0, 0), 419: (1, 0)
            }
}
def fill_GW5A_io_bels(dev):
    def fix_iobb(off):
        # for now fix B bel only
        if 'IOBB' in main_cell.bels:
            print(f'GW5 IO bels col:{col} {ttyp} -> {main_cell.ttyp}')
            main_cell.bels['IOBB'].fuse_cell_offset = off
        else:
            print(f'GW5 IO bels col:{col} skip {ttyp} -> {main_cell.ttyp}: no IOBB bel')

    # top
    for col, rc in enumerate(dev.grid[0]):
        ttyp = rc.ttyp
        if ttyp not in _gw5_fuse_cell_offset['top']:
            continue

        off = _gw5_fuse_cell_offset['top'][ttyp]
        if off != (0, 0):
            main_cell = dev.grid[0][col - off[1]]
            fix_iobb(off)

    # bottom
    for col, rc in enumerate(dev.grid[dev.rows - 1]):
        ttyp = rc.ttyp
        if ttyp not in _gw5_fuse_cell_offset['bottom']:
            continue

        off = _gw5_fuse_cell_offset['bottom'][ttyp]
        if off != (0, 0):
            main_cell = dev.grid[dev.rows - 1][col - off[1]]
            fix_iobb(off)

    # left
    for row in range(dev.rows):
        rc = dev.grid[row][0]
        ttyp = rc.ttyp
        if ttyp not in _gw5_fuse_cell_offset['left']:
            continue

        off = _gw5_fuse_cell_offset['left'][ttyp]
        if off != (0, 0):
            main_cell = dev.grid[row - off[0]][0]
            fix_iobb(off)

    # right
    for row in range(dev.rows):
        rc = dev.grid[row][dev.cols - 1]
        ttyp = rc.ttyp
        if ttyp not in _gw5_fuse_cell_offset['right']:
            continue

        off = _gw5_fuse_cell_offset['right'][ttyp]
        if off != (0, 0):
            main_cell = dev.grid[row - off[0]][dev.cols - 1]
            fix_iobb(off)

def create_GW5A_io_portmap(dat, dev, device, row, col, belname, bel, tile):
    pin = belname[-1]
    if pin == 'A' or not bel.fuse_cell_offset:
        inp = wnames.wirenames[dat.portmap[f'Iobuf{pin}Out']]
        bel.portmap['O'] = inp
        out = wnames.wirenames[dat.portmap[f'Iobuf{pin}In']]
        bel.portmap['I'] = out
        oe = wnames.wirenames[dat.portmap[f'Iobuf{pin}OE']]
        bel.portmap['OE'] = oe
        # XXX
        adcen = 'CE1'
        bel.portmap['ADCEN'] = adcen
    else:
        inp = wnames.wirenames[dat.portmap[f'Iobuf{pin}Out']]
        nodename = add_node(dev, f'X{col}Y{row}/IOBB_O', "IO_O", row + bel.fuse_cell_offset[0], col + bel.fuse_cell_offset[1], inp)
        nodename = add_node(dev, nodename, "IO_O", row, col, f'IOBB_{inp}')
        bel.portmap['O'] = f'IOBB_{inp}'
        out = wnames.wirenames[dat.portmap[f'Iobuf{pin}In']]
        nodename = add_node(dev, f'X{col}Y{row}/IOBB_I', "IO_I", row + bel.fuse_cell_offset[0], col + bel.fuse_cell_offset[1], out)
        nodename = add_node(dev, nodename, "IO_I", row, col, f'IOBB_{out}')
        bel.portmap['I'] = f'IOBB_{out}'
        oe = wnames.wirenames[dat.portmap[f'Iobuf{pin}OE']]
        nodename = add_node(dev, f'X{col}Y{row}/IOBB_OE', "IO_OE", row + bel.fuse_cell_offset[0], col + bel.fuse_cell_offset[1], oe)
        nodename = add_node(dev, nodename, "IO_OE", row, col, f'IOBB_{oe}')
        bel.portmap['OE'] = f'IOBB_{oe}'

def dat_portmap(dat, dev, device):
    wnames.select_wires(device)
    for row, row_dat in enumerate(dev.grid):
        for col, tile in enumerate(row_dat):
            for name, bel in tile.bels.items():
                if bel.portmap:
                    if not need_create_multiple_nodes(device, name):
                        continue
                if name.startswith("IOB"):
                    if is_GW5_family(device):
                        create_GW5A_io_portmap(dat, dev, device, row, col, name, bel, tile)
                        continue
                    if row in dev.simplio_rows:
                        idx = ord(name[-1]) - ord('A')
                        inp = wnames.wirenames[dat.portmap['IobufIns'][idx]]
                        bel.portmap['I'] = inp
                        out = wnames.wirenames[dat.portmap['IobufOuts'][idx]]
                        bel.portmap['O'] = out
                        oe = wnames.wirenames[dat.portmap['IobufOes'][idx]]
                        bel.portmap['OE'] = oe
                    else:
                        pin = name[-1]
                        inp = wnames.wirenames[dat.portmap[f'Iobuf{pin}Out']]
                        bel.portmap['O'] = inp
                        out = wnames.wirenames[dat.portmap[f'Iobuf{pin}In']]
                        bel.portmap['I'] = out
                        oe = wnames.wirenames[dat.portmap[f'Iobuf{pin}OE']]
                        bel.portmap['OE'] = oe
                        if row == dev.rows - 1:
                            # bottom io
                            bel.portmap['BOTTOM_IO_PORT_A'] = dev.bottom_io[0]
                            bel.portmap['BOTTOM_IO_PORT_B'] = dev.bottom_io[1]
                elif name.startswith("IOLOGIC"):
                    buf = name[-1]
                    for idx, nam in _iologic_inputs:
                        w_idx = dat.portmap[f'Iologic{buf}In'][idx]
                        if w_idx >= 0:
                            bel.portmap[nam] = wnames.wirenames[w_idx]
                        elif nam == 'FCLK':
                            # dummy Input, we'll make a special pips for it
                            bel.portmap[nam] = "FCLK"
                    # these inputs for IEM window selection
                    bel.portmap['WINSIZE0'] = {'A':"C6", 'B':"C7"}[buf]
                    bel.portmap['WINSIZE1'] = {'A':"D6", 'B':"D7"}[buf]
                    for idx, nam in _iologic_outputs:
                        w_idx = dat.portmap[f'Iologic{buf}Out'][idx]
                        if w_idx >= 0:
                            bel.portmap[nam] = wnames.wirenames[w_idx]
                elif name.startswith("OSER16"):
                    for idx, nam in _oser16_inputs:
                        w_idx = dat.portmap[f'IologicAIn'][idx]
                        if w_idx >= 0:
                            bel.portmap[nam] = wnames.wirenames[w_idx]
                        elif nam == 'FCLK':
                            # dummy Input, we'll make a special pips for it
                            bel.portmap[nam] = "FCLK"
                    for idx, nam in _oser16_outputs:
                        w_idx = dat.portmap[f'IologicAOut'][idx]
                        if w_idx >= 0:
                            bel.portmap[nam] = wnames.wirenames[w_idx]
                    bel.portmap.update(_oser16_fixed_inputs)
                elif name.startswith("IDES16"):
                    for idx, nam in _ides16_inputs:
                        w_idx = dat.portmap[f'IologicAIn'][idx]
                        if w_idx >= 0:
                            bel.portmap[nam] = wnames.wirenames[w_idx]
                        elif nam == 'FCLK':
                            # dummy Input, we'll make a special pips for it
                            bel.portmap[nam] = "FCLK"
                    bel.portmap.update(_ides16_fixed_outputs)
                elif name.startswith('PADD9'):
                    mac = int(name[-2])
                    idx = int(name[-1])
                    print("DSP_I: row:", row, "col:", col, "name:", name, "mac:", mac, "idx:", idx)
                    column = mac * 2 + (idx // 2)

                    for i in range(12):
                        off = dat.portmap['CtrlInDlt'][i][column]
                        wire_idx = dat.portmap['CtrlIn'][i][column]
                        if wire_idx < 0:
                            continue
                        wire = wnames.wirenames[wire_idx]
                        nam = ["CE", "CLK", "RESET"][i // 4] + str(i % 4)
                        # for aux cells create Himbaechel nodes
                        wire_type = 'DSP_I'
                        if wire.startswith('CLK') or wire.startswith('CE') or wire.startswith('LSR'):
                            wire_type = 'TILE_CLK'
                        create_port_wire(dev, row, col, 0, off, bel, name, nam, wire, wire_type)
                    # see PADD18
                    nam = 'ADDSUB'
                    wire, off = [[('CE2', 4), ('LSR2', 4)], [('CLK0', 5), ('CLK1', 8)]][mac][idx >> 1]
                    bel.portmap[nam] = f'{name}{nam}{wire}'
                    node_name = f'X{col}Y{row}/{name}{nam}{wire}'
                    add_node(dev, node_name, "DSP_I", row, col, f'{name}{nam}{wire}')
                    add_node(dev, node_name, "DSP_I", row, col + off, wire)

                    # from alu - we need input C as a constant 1
                    # input wire sequence: C0-53
                    # for padd9 0 use C0-8
                    # for padd9 1 use C9-17
                    # for padd9 2 use C27-35
                    # for padd9 3 use C36-44
                    padd_c_start = (idx // 2) * 27 + (idx & 1) * 9
                    padd_c_range = range(padd_c_start, padd_c_start + 9)
                    for i in range(len(dat.portmap['MdicIn'])):
                        off = dat.portmap['MdicInDlt'][i][mac]
                        wire_idx = dat.portmap['MdicIn'][i][mac]
                        if wire_idx < 0:
                            continue
                        wire = wnames.wirenames[wire_idx]
                        if i in padd_c_range:
                            nam = f'C{i - padd_c_start}'
                        else:
                            continue
                        create_port_wire(dev, row, col, 0, off, bel, name, nam, wire, "DSP_I")

                    # dat.portmap['PaddIn'] and dat.portmap['PaddInDlt'] indicate port offset in cells
                    # Each port in these tables has 4 elements - to describe
                    # the pre-adders, of which there are 4 per macro.  Of
                    # course, 2 columns per macro are not enough to describe 4
                    # pre-adds, so different lines are used for different
                    # pre-adds.
                    odd_idx = 0
                    for i in range(len(dat.portmap['PaddIn'])):
                        off = dat.portmap['PaddInDlt'][i][column]
                        wire_idx = dat.portmap['PaddIn'][i][column]
                        if wire_idx < 0:
                            continue
                        wire = wnames.wirenames[wire_idx]
                        # input wire sequence: A0-8, B0-8,
                        # unknown -1
                        # ASEL
                        #print("DSP_I: row:", row, "col:", col, "name:", name, "wire_idx:", wire_idx, "wire:", wire)
                        odd_idx = 9 * (idx & 1)
                        if i in range(odd_idx , 9 + odd_idx):
                            nam = f'A{i - odd_idx}'
                        elif i in range(18 + odd_idx, 27 + odd_idx):
                            nam = f'B{i - 18 - odd_idx}'
                        elif i == 72:
                            nam = 'ASEL'
                        else:
                            continue
                        create_port_wire(dev, row, col, 0, off, bel, name, nam, wire, "DSP_I")

                    # outputs The odd pre-adders, to my surprise, used wires
                    # for the output pins that were not mentioned in
                    # dat['PaddOut'], a similar sequence of wires was found in
                    # the tables dat['MultOut'], I don't like this, but for now
                    # let's leave it like that for lack of a better one.
                    if not odd_idx:
                        for i in range(len(dat.portmap['PaddOut'])):
                            off = dat.portmap['PaddOutDlt'][i][column]
                            wire_idx = dat.portmap['PaddOut'][i][column]
                            if wire_idx < 0:
                                continue
                            wire = wnames.wirenames[wire_idx]
                            # output wire sequence:
                            # unknown -1
                            # DOUT0-8
                            if i < 36:
                                raise Exception(f"{name} has unexpected wire {wire} at position {i}")
                            elif i < 9 + 36:
                                nam = f'DOUT{i - 36}'
                            else:
                                continue
                            create_port_wire(dev, row, col, 0, off, bel, name, nam, wire, "DSP_O")
                    else:
                        for i in range(36 + 18, 36 + 18 + 9):
                            off = dat.portmap['MultOutDlt'][i][column]
                            wire_idx = dat.portmap['MultOut'][i][column]
                            if wire_idx < 0:
                                continue
                            wire = wnames.wirenames[wire_idx]
                            # output wire sequence:
                            # unknown -1
                            # DOUT0-8
                            nam = f'DOUT{i - 36 - 18}'
                            create_port_wire(dev, row, col, 0, off, bel, name, nam, wire, "DSP_O")

                elif name.startswith('PADD18'):
                    mac = int(name[-2])
                    idx = int(name[-1])
                    column = mac * 2 + idx

                    for i in range(12):
                        off = dat.portmap['CtrlInDlt'][i][column]
                        wire_idx = dat.portmap['CtrlIn'][i][column]
                        if wire_idx < 0:
                            continue
                        wire = wnames.wirenames[wire_idx]
                        nam = ["CE", "CLK", "RESET"][i // 4] + str(i % 4)
                        create_port_wire(dev, row, col, 0, off, bel, name, nam, wire, wire_type)

                    # First experiments with PADD18 showed that, unlike the
                    # vendor-generated one, this primitive performs subtraction
                    # instead of addition. I didn’t find any difference in the
                    # functional fuses, so I started looking for wires that
                    # connect in the vendor’s version, but not in mine. These
                    # have been discovered. These ports are not listed in the
                    # documentation, so we will have to connect them in
                    # nextpnr.
                    nam = 'ADDSUB'
                    wire, off = [[('CE2', 4), ('LSR2', 4)], [('CLK0', 5), ('CLK1', 8)]][mac][idx]
                    create_port_wire(dev, row, col, 0, off, bel, name, nam, wire, "TILE_CLK")

                    # XXX from alu
                    # input wire sequence: C0-53, D0-53
                    # for padd18 0 use C0-17
                    # for padd18 1 use C27-44
                    padd_c_start = 27 * idx
                    padd_c_range = range(padd_c_start, padd_c_start + 18)
                    for i in range(len(dat.portmap['MdicIn'])):
                        off = dat.portmap['MdicInDlt'][i][mac]
                        wire_idx = dat.portmap['MdicIn'][i][mac]
                        if wire_idx < 0:
                            continue
                        wire = wnames.wirenames[wire_idx]
                        if i in padd_c_range:
                            nam = f'C{i - padd_c_start}'
                        else:
                            continue
                        create_port_wire(dev, row, col, 0, off, bel, name, nam, wire, "DSP_I")

                    # dat.portmap['PaddIn'] and dat.portmap['PaddInDlt'] indicate port offset in cells
                    # Each port in these tables has 4 elements - to describe
                    # all the pre-adders, of which there are 2 per macro.
                    for i in range(len(dat.portmap['PaddIn'])):
                        off = dat.portmap['PaddInDlt'][i][column]
                        wire_idx = dat.portmap['PaddIn'][i][column]
                        if wire_idx < 0:
                            continue
                        wire = wnames.wirenames[wire_idx]
                        # input wire sequence: A0-17, B0-17,
                        # unknown -1
                        # ASEL
                        if i < 18:
                            nam = f'A{i}'
                        elif i < 36:
                            nam = f'B{i - 18}'
                        elif i == 72:
                            nam = 'ASEL'
                        else:
                            continue
                        create_port_wire(dev, row, col, 0, off, bel, name, nam, wire, "DSP_I")
                    # outputs
                    for i in range(len(dat.portmap['PaddOut'])):
                        off = dat.portmap['PaddOutDlt'][i][column]
                        wire_idx = dat.portmap['PaddOut'][i][column]
                        if wire_idx < 0:
                            continue
                        wire = wnames.wirenames[wire_idx]
                        # output wire sequence:
                        # unknown -1
                        # DOUT0-17
                        if i < 36:
                            raise Exception(f"{name} has unexpected wire {wire} at position {i}")
                        else:
                            nam = f'DOUT{i - 36}'
                        create_port_wire(dev, row, col, 0, off, bel, name, nam, wire, "DSP_O")
                elif name.startswith('MULT9X9'):
                    mac = int(name[-2])
                    idx = int(name[-1])
                    column = mac * 2 + (idx // 2)
                    for i in range(12):
                        off = dat.portmap['CtrlInDlt'][i][column]
                        wire_idx = dat.portmap['CtrlIn'][i][column]
                        if wire_idx < 0:
                            continue
                        wire = wnames.wirenames[wire_idx]
                        nam = ["CE", "CLK", "RESET"][i // 4] + str(i % 4)
                        # for aux cells create Himbaechel nodes
                        wire_type = 'DSP_I'
                        if wire.startswith('CLK') or wire.startswith('CE') or wire.startswith('LSR'):
                            wire_type = 'TILE_CLK'
                        create_port_wire(dev, row, col, 0, off, bel, name, nam, wire, wire_type)

                    # dat.portmap['MultIn'] and dat.portmap['MultInDlt'] indicate port offset in cells
                    for i in range(len(dat.portmap['MultIn'])):
                        off = dat.portmap['MultInDlt'][i][column]
                        wire_idx = dat.portmap['MultIn'][i][column]
                        if wire_idx < 0:
                            continue
                        wire = wnames.wirenames[wire_idx]
                        # input wire sequence: A0-8, B0-8,
                        # unknown -1
                        # ASIGN, BSIGN, ASEL, BSEL
                        odd_idx = 9 * (idx & 1)
                        if i in range(odd_idx , 9 + odd_idx):
                            nam = f'A{i - odd_idx}'
                        elif i in range(18 + odd_idx, 27 + odd_idx):
                            nam = f'B{i - 18 - odd_idx}'
                        elif i in range(72, 76):
                            nam = ['ASIGN', 'BSIGN', 'ASEL', 'BSEL'][i - 72]
                        else:
                            continue
                        create_port_wire(dev, row, col, 0, off, bel, name, nam, wire, "DSP_I")

                    # outputs
                    for i in range(len(dat.portmap['MultOut'])):
                        off = dat.portmap['MultOutDlt'][i][column]
                        wire_idx = dat.portmap['MultOut'][i][column]
                        if wire_idx < 0:
                            continue
                        wire = wnames.wirenames[wire_idx]
                        # output wire sequence:
                        # unknown -1
                        # DOUT0-8
                        odd_idx = 36 + 18 * (idx & 1)
                        if i in range(odd_idx , 18 + odd_idx):
                            nam = f'DOUT{i - odd_idx}'
                        else:
                            continue
                        create_port_wire(dev, row, col, 0, off, bel, name, nam, wire, "DSP_O")

                elif name.startswith('MULT18X18'):
                    mac = int(name[-2])
                    idx = int(name[-1])
                    column = mac * 2 + idx
                    for i in range(12):
                        off = dat.portmap['CtrlInDlt'][i][column]
                        wire_idx = dat.portmap['CtrlIn'][i][column]
                        if wire_idx < 0:
                            continue
                        wire = wnames.wirenames[wire_idx]
                        nam = ["CE", "CLK", "RESET"][i // 4] + str(i % 4)
                        # for aux cells create Himbaechel nodes
                        wire_type = 'DSP_I'
                        if wire.startswith('CLK') or wire.startswith('CE') or wire.startswith('LSR'):
                            wire_type = 'TILE_CLK'
                        create_port_wire(dev, row, col, 0, off, bel, name, nam, wire, wire_type)

                    # dat.portmap['MultIn'] and dat.portmap['MultInDlt'] indicate port offset in cells
                    for i in range(len(dat.portmap['MultIn'])):
                        off = dat.portmap['MultInDlt'][i][column]
                        wire_idx = dat.portmap['MultIn'][i][column]
                        if wire_idx < 0:
                            continue
                        wire = wnames.wirenames[wire_idx]
                        # input wire sequence: A0-17, B0-17,
                        # unknown -1
                        # ASIGN, BSIGN, ASEL, BSEL
                        if i in range(18):
                            nam = f'A{i}'
                        elif i in range(18, 36):
                            nam = f'B{i - 18}'
                        elif i in range(72, 76):
                            nam = ['ASIGN', 'BSIGN', 'ASEL', 'BSEL'][i - 72]
                        else:
                            continue
                        create_port_wire(dev, row, col, 0, off, bel, name, nam, wire, "DSP_I")

                    # outputs
                    for i in range(len(dat.portmap['MultOut'])):
                        off = dat.portmap['MultOutDlt'][i][column]
                        wire_idx = dat.portmap['MultOut'][i][column]
                        if wire_idx < 0:
                            continue
                        wire = wnames.wirenames[wire_idx]
                        # output wire sequence:
                        # unknown -1
                        # DOUT0-35
                        if i in range(36 , 72):
                            nam = f'DOUT{i - 36}'
                        else:
                            continue
                        create_port_wire(dev, row, col, 0, off, bel, name, nam, wire, "DSP_O")
                elif name.startswith('ALU54D'):
                    mac = int(name[-1])
                    column = mac
                    for i in range(12):
                        off = dat.portmap['CtrlInDlt'][i][column * 2]
                        wire_idx = dat.portmap['CtrlIn'][i][column * 2]
                        if wire_idx < 0:
                            continue
                        wire = wnames.wirenames[wire_idx]
                        nam = ["CE", "CLK", "RESET"][i // 4] + str(i % 4)
                        # for aux cells create Himbaechel nodes
                        wire_type = 'DSP_I'
                        if wire.startswith('CLK') or wire.startswith('CE') or wire.startswith('LSR'):
                            wire_type = 'TILE_CLK'
                        create_port_wire(dev, row, col, 0, off, bel, name, nam, wire, wire_type)

                    for i in range(2):
                        off = dat.portmap['CtrlInDlt'][i + 12][column]
                        wire_idx = dat.portmap['CtrlIn'][i + 12][column]
                        if wire_idx < 0:
                            continue
                        wire = wnames.wirenames[wire_idx]
                        nam = f'ACCLOAD{i}'
                        # for aux cells create Himbaechel nodes
                        wire_type = 'DSP_I'
                        if wire.startswith('CLK') or wire.startswith('CE') or wire.startswith('LSR'):
                            wire_type = 'TILE_CLK'
                        create_port_wire(dev, row, col, 0, off, bel, name, nam, wire, wire_type)

                    # dat.portmap['AluIn'] and dat.portmap['AluInDlt'] indicate port offset in cells
                    for i in range(len(dat.portmap['AluIn'])):
                        off = dat.portmap['AluInDlt'][i][column]
                        wire_idx = dat.portmap['AluIn'][i][column]
                        if wire_idx < 0:
                            continue
                        wire = wnames.wirenames[wire_idx]
                        # input wire sequence: A0-53, B0-53, CASI0-54
                        # ASIGN, BSIGN
                        if i in range(54):
                            nam = f'A{i}'
                        elif i in range(54, 108):
                            nam = f'B{i - 54}'
                        elif i in range(163, 165):
                            nam = ['ASIGN', 'BSIGN'][i - 163]
                        else:
                            continue
                        create_port_wire(dev, row, col, 0, off, bel, name, nam, wire, "DSP_I")

                    # outputs
                    for i in range(len(dat.portmap['AluOut'])):
                        off = dat.portmap['AluOutDlt'][i][column]
                        wire_idx = dat.portmap['AluOut'][i][column]
                        if wire_idx < 0:
                            continue
                        wire = wnames.wirenames[wire_idx]
                        # output wire sequence:
                        # DOUT0-54
                        # unknown -1
                        if i > 53:
                            break
                        nam = f'DOUT{i}'
                        create_port_wire(dev, row, col, 0, off, bel, name, nam, wire, "DSP_O")

                elif name.startswith('MULT36X36'):
                    # 36x36 are assembled from 4 18x18 multipliers and two
                    # ALU54D.
                    # macro:          0       |       1
                    # mult18x18:   0     1    |   0       1
                    # A:  0-17    0-17        |  0-17
                    #    18-35          0-17  |          0-17
                    # -----------------------------------------------------
                    # B:  0-17    0-17  0-17  |
                    #    18-35                |  0-17    0-17
                    # The ALU54D outputs turned out to be the easiest to find.
                    # outputs
                    for i in range(72):
                        if i < 18:
                            column = 0
                            idx_off = 0
                        else:
                            column = 1
                            idx_off = -18
                        off = dat.portmap['AluOutDlt'][i + idx_off][column]
                        wire_idx = dat.portmap['AluOut'][i + idx_off][column]
                        if wire_idx < 0:
                            continue
                        wire = wnames.wirenames[wire_idx]
                        nam = f'DOUT{i}'
                        create_port_wire(dev, row, col, 0, off, bel, name, nam, wire, "DSP_O")
                    # In order to make 36x36 using 4 multiplications, we need
                    # to make sure that each multiplier receives its own unique
                    # combination of 18 bits A and 18 bits B. But this means
                    # that each port (A and B) of our MULT36X36 primitive must
                    # be connected to the ports of two multipliers at the same
                    # time. For simplicity, we add one more number to the end
                    # of the port name, that is, port A0 is represented as two
                    # A00 and A01. Of course, there are more beautiful
                    # solutions, but for now we will leave this one as simpler.
                    # A
                    for i in range(36):
                        if i < 18:
                            column = 0
                            idx_off = 0
                        else:
                            column = 1
                            idx_off = -18
                        off = dat.portmap['MultInDlt'][i + idx_off][column]
                        wire_idx = dat.portmap['MultIn'][i + idx_off][column]
                        if wire_idx < 0:
                            continue
                        wire = wnames.wirenames[wire_idx]
                        nam = f'A{i}0'
                        create_port_wire(dev, row, col, 0, off, bel, name, nam, wire, "DSP_I")

                        off = dat.portmap['MultInDlt'][i + idx_off][column + 2]
                        wire_idx = dat.portmap['MultIn'][i + idx_off][column + 2]
                        if wire_idx < 0:
                            continue
                        wire = wnames.wirenames[wire_idx]
                        nam = f'A{i}1'
                        create_port_wire(dev, row, col, 0, off, bel, name, nam, wire, "DSP_I")
                    # B
                    for i in range(36):
                        if i < 18:
                            column = 0
                            idx_off = 18
                        else:
                            column = 2
                            idx_off = 0
                        off = dat.portmap['MultInDlt'][i + idx_off][column]
                        wire_idx = dat.portmap['MultIn'][i + idx_off][column]
                        if wire_idx < 0:
                            continue
                        wire = wnames.wirenames[wire_idx]
                        nam = f'B{i}0'
                        create_port_wire(dev, row, col, 0, off, bel, name, nam, wire, "DSP_I")

                        off = dat.portmap['MultInDlt'][i + idx_off][column + 1]
                        wire_idx = dat.portmap['MultIn'][i + idx_off][column + 1]
                        if wire_idx < 0:
                            continue
                        wire = wnames.wirenames[wire_idx]
                        nam = f'B{i}1'
                        create_port_wire(dev, row, col, 0, off, bel, name, nam, wire, "DSP_I")
                    # We connect the sign wires only to MSB multipliers.
                    for column in range(2):
                        off = dat.portmap['MultInDlt'][72][column * 2 + 1]
                        wire_idx = dat.portmap['MultIn'][72][column * 2 + 1]
                        if wire_idx < 0:
                            continue
                        wire = wnames.wirenames[wire_idx]
                        nam = f'ASIGN{column}'
                        create_port_wire(dev, row, col, 0, off, bel, name, nam, wire, "DSP_I")

                        off = dat.portmap['MultInDlt'][73][column + 2]
                        wire_idx = dat.portmap['MultIn'][73][column + 2]
                        if wire_idx < 0:
                            continue
                        wire = wnames.wirenames[wire_idx]
                        nam = f'BSIGN{column}'
                        create_port_wire(dev, row, col, 0, off, bel, name, nam, wire, "DSP_I")

                        # and the register control wires
                        for i in range(12):
                            off = dat.portmap['CtrlInDlt'][i][column * 2]
                            wire_idx = dat.portmap['CtrlIn'][i][column * 2]
                            if wire_idx < 0:
                                continue
                            wire = wnames.wirenames[wire_idx]
                            nam = f'{["CE", "CLK", "RESET"][i // 4]}{i % 4}{column}'
                            # for aux cells create Himbaechel nodes
                            wire_type = 'DSP_I'
                            if wire.startswith('CLK') or wire.startswith('CE') or wire.startswith('LSR'):
                                wire_type = 'TILE_CLK'
                            create_port_wire(dev, row, col, 0, off, bel, name, nam, wire, wire_type)

                elif name.startswith('MULTALU18X18'):
                    mac = int(name[-1])
                    column = mac * 2

                    # Modes 0 and 1 of MULTALU18X18 use multiplier 1, and mode
                    # 2 uses multiplier 0. Now we don’t know which one will be
                    # used, so we indicate both options for A, B and their
                    # signs.
                    for opt in range(2):
                        # A
                        for i in range(18):
                            off = dat.portmap['MultInDlt'][i][column + opt]
                            wire_idx = dat.portmap['MultIn'][i][column + opt]
                            if wire_idx < 0:
                                continue
                            wire = wnames.wirenames[wire_idx]
                            nam = f'A{i}{opt}'
                            create_port_wire(dev, row, col, 0, off, bel, name, nam, wire, "DSP_I")

                        # B
                        for i in range(18):
                            off = dat.portmap['MultInDlt'][i + 18][column + opt]
                            wire_idx = dat.portmap['MultIn'][i + 18][column + opt]
                            if wire_idx < 0:
                                continue
                            wire = wnames.wirenames[wire_idx]
                            nam = f'B{i}{opt}'
                            create_port_wire(dev, row, col, 0, off, bel, name, nam, wire, "DSP_I")

                        # ASIGN, BSIGN
                        for sign_str, dat_off in [('ASIGN', 72), ('BSIGN', 73)]:
                            off = dat.portmap['MultInDlt'][dat_off][column + opt]
                            wire_idx = dat.portmap['MultIn'][dat_off][column + opt]
                            if wire_idx < 0:
                                continue
                            wire = wnames.wirenames[wire_idx]
                            nam = f'{sign_str}{opt}'
                            create_port_wire(dev, row, col, 0, off, bel, name, nam, wire, "DSP_I")

                    # C
                    for i in range(54):
                        off = dat.portmap['MdicInDlt'][i][mac]
                        wire_idx = dat.portmap['MdicIn'][i][mac]
                        if wire_idx < 0:
                            continue
                        wire = wnames.wirenames[wire_idx]
                        nam = f'C{i}'
                        create_port_wire(dev, row, col, 0, off, bel, name, nam, wire, "DSP_I")

                    # D
                    for i in range(54):
                        off = dat.portmap['AluInDlt'][i + 54][mac]
                        wire_idx = dat.portmap['AluIn'][i + 54][mac]
                        if wire_idx < 0:
                            continue
                        wire = wnames.wirenames[wire_idx]
                        nam = f'D{i}'
                        create_port_wire(dev, row, col, 0, off, bel, name, nam, wire, "DSP_I")

                    # DSIGN
                    off = dat.portmap['AluInDlt'][164][mac]
                    wire_idx = dat.portmap['AluIn'][164][mac]
                    if wire_idx < 0:
                        continue
                    wire = wnames.wirenames[wire_idx]
                    nam = f'DSIGN'
                    create_port_wire(dev, row, col, 0, off, bel, name, nam, wire, "DSP_I")


                    # ACCLOAD
                    for i in range(2):
                        off = dat.portmap['CtrlInDlt'][i + 12][mac]
                        wire_idx = dat.portmap['CtrlIn'][i + 12][mac]
                        if wire_idx < 0:
                            continue
                        wire = wnames.wirenames[wire_idx]
                        nam = f'ACCLOAD{i}'
                        # for aux cells create Himbaechel nodes
                        wire_type = 'DSP_I'
                        if wire.startswith('CLK') or wire.startswith('CE') or wire.startswith('LSR'):
                            wire_type = 'TILE_CLK'
                        create_port_wire(dev, row, col, 0, off, bel, name, nam, wire, wire_type)

                    # controls
                    for i in range(12):
                        off = dat.portmap['CtrlInDlt'][i][column]
                        wire_idx = dat.portmap['CtrlIn'][i][column]
                        if wire_idx < 0:
                            continue
                        wire = wnames.wirenames[wire_idx]
                        nam = f'{["CE", "CLK", "RESET"][i // 4]}{i % 4}'
                        # for aux cells create Himbaechel nodes
                        wire_type = 'DSP_I'
                        if wire.startswith('CLK') or wire.startswith('CE') or wire.startswith('LSR'):
                            wire_type = 'TILE_CLK'
                        create_port_wire(dev, row, col, 0, off, bel, name, nam, wire, wire_type)

                    # outputs
                    for i in range(54):
                        off = dat.portmap['AluOutDlt'][i][mac]
                        wire_idx = dat.portmap['AluOut'][i][mac]
                        if wire_idx < 0:
                            continue
                        wire = wnames.wirenames[wire_idx]
                        nam = f'DOUT{i}'
                        create_port_wire(dev, row, col, 0, off, bel, name, nam, wire, "DSP_O")

                elif name.startswith('MULTALU36X18'):
                    mac = int(name[-1])
                    column = mac * 2

                    b_in = 0
                    for opt in range(2):
                        # A is duplicated to both multipliers, but B is shared
                        # between B0 and B1. The signedness attribute for A is
                        # also duplicated, but only B1 has a sign. It's not
                        # visible here, but in nextpnr we'll probably connect
                        # BSIGN0 to GND

                        # A
                        for i in range(18):
                            off = dat.portmap['MultInDlt'][i][column + opt]
                            wire_idx = dat.portmap['MultIn'][i][column + opt]
                            if wire_idx < 0:
                                continue
                            wire = wnames.wirenames[wire_idx]
                            nam = f'A{i}{opt}'
                            create_port_wire(dev, row, col, 0, off, bel, name, nam, wire, "DSP_I")

                            # B
                            off = dat.portmap['MultInDlt'][i + 18][column + opt]
                            wire_idx = dat.portmap['MultIn'][i + 18][column + opt]
                            if wire_idx < 0:
                                continue
                            wire = wnames.wirenames[wire_idx]
                            nam = f'B{b_in + i}'
                            create_port_wire(dev, row, col, 0, off, bel, name, nam, wire, "DSP_I")
                        b_in += 18

                        # ASIGN, BSIGN
                        for sign_str, dat_off in [('ASIGN', 72), ('BSIGN', 73)]:
                            off = dat.portmap['MultInDlt'][dat_off][column + opt]
                            wire_idx = dat.portmap['MultIn'][dat_off][column + opt]
                            if wire_idx < 0:
                                continue
                            wire = wnames.wirenames[wire_idx]
                            nam = f'{sign_str}{opt}'
                            create_port_wire(dev, row, col, 0, off, bel, name, nam, wire, "DSP_I")


                    # C
                    for i in range(54):
                        off = dat.portmap['MdicInDlt'][i][mac]
                        wire_idx = dat.portmap['MdicIn'][i][mac]
                        if wire_idx < 0:
                            continue
                        wire = wnames.wirenames[wire_idx]
                        nam = f'C{i}'
                        create_port_wire(dev, row, col, 0, off, bel, name, nam, wire, "DSP_I")

                    # accload is formed by alusel wire
                    # Here we provide the wires, we will connect them in nextpnr
                    for i in range(7):
                        wire, off = _alusel[mac][i]
                        if wire_idx < 0:
                            continue
                        nam = f'ALUSEL{i}'
                        # for aux cells create Himbaechel nodes
                        wire_type = 'DSP_I'
                        if wire.startswith('CLK') or wire.startswith('CE') or wire.startswith('LSR'):
                            wire_type = 'TILE_CLK'
                        create_port_wire(dev, row, col, 0, off, bel, name, nam, wire, wire_type)

                    # controls
                    for i in range(12):
                        off = dat.portmap['CtrlInDlt'][i][column]
                        wire_idx = dat.portmap['CtrlIn'][i][column]
                        if wire_idx < 0:
                            continue
                        wire = wnames.wirenames[wire_idx]
                        nam = f'{["CE", "CLK", "RESET"][i // 4]}{i % 4}'
                        # for aux cells create Himbaechel nodes
                        wire_type = 'DSP_I'
                        if wire.startswith('CLK') or wire.startswith('CE') or wire.startswith('LSR'):
                            wire_type = 'TILE_CLK'
                        create_port_wire(dev, row, col, 0, off, bel, name, nam, wire, wire_type)

                    # outputs
                    for i in range(54):
                        off = dat.portmap['AluOutDlt'][i][mac]
                        wire_idx = dat.portmap['AluOut'][i][mac]
                        if wire_idx < 0:
                            continue
                        wire = wnames.wirenames[wire_idx]
                        nam = f'DOUT{i}'
                        create_port_wire(dev, row, col, 0, off, bel, name, nam, wire, "DSP_O")

                elif name.startswith('MULTADDALU18X18'):
                    mac = int(name[-1])
                    column = mac * 2

                    for opt in range(2):
                        # A
                        for i in range(18):
                            off = dat.portmap['MultInDlt'][i][column + opt]
                            wire_idx = dat.portmap['MultIn'][i][column + opt]
                            if wire_idx < 0:
                                continue
                            wire = wnames.wirenames[wire_idx]
                            nam = f'A{i}{opt}'
                            create_port_wire(dev, row, col, 0, off, bel, name, nam, wire, "DSP_I")

                            # B
                            off = dat.portmap['MultInDlt'][i + 18][column + opt]
                            wire_idx = dat.portmap['MultIn'][i + 18][column + opt]
                            if wire_idx < 0:
                                continue
                            wire = wnames.wirenames[wire_idx]
                            nam = f'B{i}{opt}'
                            create_port_wire(dev, row, col, 0, off, bel, name, nam, wire, "DSP_I")

                        # ASIGN, BSIGN
                        for sign_str, dat_off in [('ASIGN', 72), ('BSIGN', 73), ('ASEL', 74), ('BSEL', 75)]:
                            off = dat.portmap['MultInDlt'][dat_off][column + opt]
                            wire_idx = dat.portmap['MultIn'][dat_off][column + opt]
                            if wire_idx < 0:
                                continue
                            wire = wnames.wirenames[wire_idx]
                            nam = f'{sign_str}{opt}'
                            create_port_wire(dev, row, col, 0, off, bel, name, nam, wire, "DSP_I")


                    # C
                    for i in range(54):
                        off = dat.portmap['MdicInDlt'][i][mac]
                        wire_idx = dat.portmap['MdicIn'][i][mac]
                        if wire_idx < 0:
                            continue
                        wire = wnames.wirenames[wire_idx]
                        nam = f'C{i}'
                        create_port_wire(dev, row, col, 0, off, bel, name, nam, wire, "DSP_I")

                    # accload is formed by alusel wires
                    # Here we provide the wires, we will connect them in nextpnr
                    for i in range(7):
                        wire, off = _alusel[mac][i]
                        if wire_idx < 0:
                            continue
                        nam = f'ALUSEL{i}'
                        # for aux cells create Himbaechel nodes
                        wire_type = 'DSP_I'
                        if wire.startswith('CLK') or wire.startswith('CE') or wire.startswith('LSR'):
                            wire_type = 'TILE_CLK'
                        create_port_wire(dev, row, col, 0, off, bel, name, nam, wire, wire_type)

                    # controls
                    for i in range(12):
                        off = dat.portmap['CtrlInDlt'][i][column]
                        wire_idx = dat.portmap['CtrlIn'][i][column]
                        if wire_idx < 0:
                            continue
                        wire = wnames.wirenames[wire_idx]
                        nam = f'{["CE", "CLK", "RESET"][i // 4]}{i % 4}'
                        # for aux cells create Himbaechel nodes
                        wire_type = 'DSP_I'
                        if wire.startswith('CLK') or wire.startswith('CE') or wire.startswith('LSR'):
                            wire_type = 'TILE_CLK'
                        create_port_wire(dev, row, col, 0, off, bel, name, nam, wire, wire_type)

                    # outputs
                    for i in range(54):
                        off = dat.portmap['AluOutDlt'][i][mac]
                        wire_idx = dat.portmap['AluOut'][i][mac]
                        if wire_idx < 0:
                            continue
                        wire = wnames.wirenames[wire_idx]
                        nam = f'DOUT{i}'
                        create_port_wire(dev, row, col, 0, off, bel, name, nam, wire, "DSP_O")

                elif name == 'BSRAM':
                    # dat.portmap['BsramOutDlt'] and dat.portmap['BsramOutDlt'] indicate port offset in cells
                    for i in range(len(dat.portmap['BsramOut'])):
                        off = dat.portmap['BsramOutDlt'][i]
                        wire_idx = dat.portmap['BsramOut'][i]
                        if wire_idx < 0:
                            continue
                        wire = wnames.wirenames[wire_idx]
                        # outs sequence: DO0-35, DOA0-17, DOB0-17
                        if i < 36:
                            nam = f'DO{i}'
                        elif i < 54:
                            nam = f'DOA{i - 36}'
                        else:
                            nam = f'DOB{i - 36 - 18}'
                        create_port_wire(dev, row, col, 0, off, bel, "BSRAM", nam, wire, "BSRAM_O")

                    for i in range(len(dat.portmap['BsramIn']) + 6):
                        if i < 132:
                            off = dat.portmap['BsramInDlt'][i]
                            wire_idx = dat.portmap['BsramIn'][i]
                            if wire_idx < 0:
                                continue
                        elif i in range(132, 135):
                            nam = f'BLKSELA{i - 132}'
                            wire_idx = dat.portmap['BsramIn'][i - 132 + 15]
                            off = [0, 0, 2][i - 132]
                        else:
                            nam = f'BLKSELB{i - 135}'
                            wire_idx = wnames.wirenumbers[['CE2', 'LSR2', 'CE1'][i - 135]]
                            off = [1, 1, 2][i - 135]
                        wire = wnames.wirenames[wire_idx]
                        # helping the clock router
                        wire_type = 'BSRAM_I'
                        if wire.startswith('CLK') or wire.startswith('CE') or wire.startswith('LSR'):
                            wire_type = 'TILE_CLK'
                        # ins sequence: control(0-17), ADA0-13, AD0-13, DIA0-17,
                        # DI0-35, ADB0-13, DIB0-17, control(133-138)
                        # controls - A, B, '' like all controls for A (CLKA,), then for B (CLKB),
                        # then without modifier '' (CLK)
                        if i < 18:
                            if i < 15:
                                nam = _bsram_control_ins[i % 5] + ['A', 'B', ''][i // 5]
                            else:
                                nam = f'BLKSEL{i - 15}'
                        elif i < 32:
                            nam = f'ADA{i - 18}'
                        elif i < 46:
                            nam = f'AD{i - 32}'
                        elif i < 64:
                            nam = f'DIA{i - 46}'
                        elif i < 100:
                            nam = f'DI{i - 64}'
                        elif i < 114:
                            nam = f'ADB{i - 100}'
                        elif i < 132:
                            nam = f'DIB{i - 114}'
                        create_port_wire(dev, row, col, 0, off, bel, "BSRAM", nam, wire, wire_type)

                elif name == 'RPLLA':
                    # The PllInDlt table seems to indicate in which cell the
                    # inputs are actually located.
                    offx = 1
                    if device in {'GW1N-9C', 'GW1N-9', 'GW2A-18', 'GW2A-18C'}:
                        # two mirrored PLLs
                        if col > dat.grid.center_x - 1:
                            offx = -1
                    for idx, nam in _pll_inputs:
                        wire = wnames.wirenames[dat.portmap['PllIn'][idx]]
                        off = dat.portmap['PllInDlt'][idx] * offx
                        if device in {'GW1NS-2'}:
                            # NS-2 is a strange thingy
                            if nam in {'RESET', 'RESET_P', 'IDSEL1', 'IDSEL2', 'ODSEL5'}:
                                bel.portmap[nam] = f'rPLL{nam}{wire}'
                            else:
                                bel.portmap[nam] = wire
                        elif off == 0:
                            bel.portmap[nam] = wire
                        else:
                            # not our cell, make an alias
                            bel.portmap[nam] = f'rPLL{nam}{wire}'
                            # Himbaechel node
                            dev.nodes.setdefault(f'X{col}Y{row}/rPLL{nam}{wire}', ("PLL_I", {(row, col, f'rPLL{nam}{wire}')}))[1].add((row, col + off, wire))

                    for idx, nam in _pll_outputs:
                        wire = wnames.wirenames[dat.portmap['PllOut'][idx]]
                        off = dat.portmap['PllOutDlt'][idx] * offx
                        if off == 0 or device in {'GW1NS-2'}:
                            bel.portmap[nam] = wire
                        else:
                            # not our cell, make an alias
                            bel.portmap[nam] = f'rPLL{nam}{wire}'
                        # Himbaechel node
                        if nam != 'LOCK':
                            global_name = get_pllout_global_name(row, col + off, wire, device)
                        else:
                            global_name = f'X{col}Y{row}/rPLL{nam}{wire}'
                        dev.nodes.setdefault(global_name, ("PLL_O", set()))[1].update({(row, col, f'rPLL{nam}{wire}'), (row, col + off, wire)})
                    # clock input
                    nam = 'CLKIN'
                    wire = wnames.wirenames[dat.portmap['PllClkin'][1][0]]
                    off = dat.portmap['PllClkin'][1][1] * offx
                    if off == 0:
                        bel.portmap[nam] = wire
                    else:
                        # not our cell, make an alias
                        bel.portmap[nam] = f'rPLL{nam}{wire}'
                        # Himbaechel node
                        dev.nodes.setdefault(f'X{col}Y{row}/rPLL{nam}{wire}', ("PLL_I", {(row, col, f'rPLL{nam}{wire}')}))[1].add((row, col + off, wire))
                    # HCLK pips
                    hclk_pip_dsts = {'PLL_CLKIN', 'PLL_CLKFB'}
                    for dst in hclk_pip_dsts:
                        if (row, col) in dev.hclk_pips and dst in dev.hclk_pips[row, col]:
                            dev.hclk_pips[row, col][bel.portmap[dst[4:]]] = dev.hclk_pips[row, col].pop(dst)
                elif name == 'PLLVR':
                    pll_idx = 0
                    if col != 27:
                        pll_idx = 1
                    for idx, nam in _pll_inputs:
                        pin_row = dat.portmap[f'SpecPll{pll_idx}Ins'][idx * 3 + 0]
                        wire = wnames.wirenames[dat.portmap[f'SpecPll{pll_idx}Ins'][idx * 3 + 2]]
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
                            # Himbaechel node
                            dev.nodes.setdefault(f'X{col}Y{row}/PLLVR{nam}{wire}', ("PLL_I", {(row, col, f'PLLVR{nam}{wire}')}))[1].add((9, 37, wire))
                    for idx, nam in _pll_outputs:
                        wire = wnames.wirenames[dat.portmap[f'SpecPll{pll_idx}Outs'][idx * 3 + 2]]
                        bel.portmap[nam] = wire
                        # Himbaechel node
                        if nam != 'LOCK':
                            global_name = get_pllout_global_name(row, col, wire, device)
                        else:
                            global_name = f'X{col}Y{row}/PLLVR{nam}{wire}'
                        dev.nodes.setdefault(global_name, ("PLL_O", set()))[1].update({(row, col, f'PLLVR{nam}{wire}'), (row, col, wire)})
                    bel.portmap['CLKIN'] = wnames.wirenames[124];
                    reset = wnames.wirenames[dat.portmap[f'SpecPll{pll_idx}Ins'][0 + 2]]
                    # VREN pin is placed in another cell
                    if pll_idx == 0:
                        vren = 'D0'
                    else:
                        vren = 'B0'
                    bel.portmap['VREN'] = f'PLLVRV{vren}'
                    # Himbaechel node
                    dev.nodes.setdefault(f'X{col}Y{row}/PLLVRV{vren}', ("PLL_I", {(row, col, f'PLLVRV{vren}')}))[1].add((0, 37, vren))
                elif name.startswith('OSC'):
                    # local ports
                    local_ports, aliases = _osc_ports[name, device]
                    bel.portmap.update(local_ports)
                    for port, alias in aliases.items():
                        bel.portmap[port] = port
                        #dev.aliases[row, col, port] = alias

def tile_bitmap(dev, bitmap, empty=False):
    res = {}
    y = 0
    for idx, row in enumerate(dev.grid):
        x=0
        for jdx, td in enumerate(row):
            w = td.width
            h = td.height
            tile = [row[x:x+w] for row in bitmap[y:y+h]]
            if bitmatrix.any(tile) or empty:
                res[(idx, jdx)] = tile
            x+=w
        y+=h

    return res

def fuse_bitmap(db, bitmap):
    res = bitmatrix.zeros(db.height, db.width)
    y = 0
    for idx, row in enumerate(db.grid):
        x=0
        for jdx, td in enumerate(row):
            w = td.width
            h = td.height
            y0 = y
            for row in bitmap[(idx, jdx)]:
                x0 = x
                for val in row:
                    res[y0][x0] = val
                    x0 += 1
                y0 += 1
            x += w
        y += h

    return res

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

def fse_wire_delays(db, dev):
    wnames.select_wires(dev)
    for i in range(33): # A0-D7
        db.wire_delay[wnames.wirenames[i]] = "LUT_IN"
    for i in range(33, 40): # F0-F7
        db.wire_delay[wnames.wirenames[i]] = "LUT_OUT"
    for i in range(40, 48): # Q0-Q7
        db.wire_delay[wnames.wirenames[i]] = "FF_OUT"
    for i in range(48, 56): # OF0-OF7
        db.wire_delay[wnames.wirenames[i]] = "OF"
    for i in range(56, 64): # X01-X08
        db.wire_delay[wnames.wirenames[i]] = "X0"
    db.wire_delay[wnames.wirenames[64]] = "FX1" # N100
    db.wire_delay[wnames.wirenames[65]] = "FX1" # SN10
    db.wire_delay[wnames.wirenames[66]] = "FX1" # N100
    for i in range(67, 71): # N130-E100
        db.wire_delay[wnames.wirenames[i]] = "FX1"
    for i in range(71, 73): # EW10-EW20
        db.wire_delay[wnames.wirenames[i]] = "FX1"
    for i in range(73, 76): # E130-W130
        db.wire_delay[wnames.wirenames[i]] = "FX1"
    for i in range(76, 108): # N200-N270
        db.wire_delay[wnames.wirenames[i]] = "X2"
    for i in range(76, 108): # N200-W270
        db.wire_delay[wnames.wirenames[i]] = "X2"
    for i in range(108, 124): # N800-W830
        db.wire_delay[wnames.wirenames[i]] = "X8"
    for i in range(124, 127): # CLK0-CLK2
        db.wire_delay[wnames.wirenames[i]] = "X0CLK"
    for i in range(127, 130): # LSR0-LSR2
        db.wire_delay[wnames.wirenames[i]] = "X0CTL"
    for i in range(130, 133): # CE0-CE2
        db.wire_delay[wnames.wirenames[i]] = "X0CTL"
    for i in range(133, 141): # SEL0-SEL7
        db.wire_delay[wnames.wirenames[i]] = "SEL"
    for i in range(141, 149): # N101-W131
        db.wire_delay[wnames.wirenames[i]] = "FX1"
    for i in range(149, 181): # N201-W271
        db.wire_delay[wnames.wirenames[i]] = "X2"
    for i in range(181, 213): # N202-W272
        db.wire_delay[wnames.wirenames[i]] = "X2"
    for i in range(213, 229): # N804-W834
        db.wire_delay[wnames.wirenames[i]] = "X8"
    for i in range(229, 245): # N808-W838
        db.wire_delay[wnames.wirenames[i]] = "X8"
    for i in range(245, 253): # E110-N120
        db.wire_delay[wnames.wirenames[i]] = "FX1"
    for i in range(253, 261): # E111-N121
        db.wire_delay[wnames.wirenames[i]] = "FX1"
    for i in range(261, 269): # LB01-LB71
        db.wire_delay[wnames.wirenames[i]] = "LW_BRANCH"
    for i in range(269, 277): # GB00-GB70
        db.wire_delay[wnames.wirenames[i]] = "GCLK_BRANCH"
    db.wire_delay[wnames.wirenames[277]] = "VCC" # VSS
    db.wire_delay[wnames.wirenames[278]] = "VSS" # VCC
    for i in range(279, 285): # LT00-LT13
        db.wire_delay[wnames.wirenames[i]] = "LW_TAP"
    db.wire_delay[wnames.wirenames[285]] = "LW_TAP_0" # LT01
    db.wire_delay[wnames.wirenames[286]] = "LW_TAP_0" # LT04
    db.wire_delay[wnames.wirenames[287]] = "LW_BRANCH" # LTBO0
    db.wire_delay[wnames.wirenames[288]] = "LW_BRANCH" # LTBO1
    db.wire_delay[wnames.wirenames[289]] = "LW_SPAN" # SS00
    db.wire_delay[wnames.wirenames[290]] = "LW_SPAN" # SS40
    db.wire_delay[wnames.wirenames[291]] = "TAP_BRANCH_PCLK" # GT00
    db.wire_delay[wnames.wirenames[292]] = "TAP_BRANCH_PCLK" # GT10
    db.wire_delay[wnames.wirenames[293]] = "BRANCH_PCLK" # GBO0
    db.wire_delay[wnames.wirenames[294]] = "BRANCH_PCLK" # GBO1
    for i in range(295, 303): # DI0-DI7
        db.wire_delay[wnames.wirenames[i]] = "DI"
    for i in range(303, 309): # CIN0-CIN5
        db.wire_delay[wnames.wirenames[i]] = "CIN"
    for i in range(309, 314): # COUT0-COUT5
        db.wire_delay[wnames.wirenames[i]] = "COUT"
    for i in range(545, 553): # 5A needs these
        db.wire_delay[wnames.wirenames[i]] = "X8"
    for i in range(556, 564): # 5A needs these
        db.wire_delay[wnames.wirenames[i]] = "X8"
    for i in range(1001, 1049): # LWSPINE
        db.wire_delay[wnames.wirenames[i]] = "X8"
    # possibly LW wires for large chips, for now assign dummy value
    for i in range(1049, 1130):
        db.wire_delay[str(i)] = "X8"
    # clock wires
    #for i in range(261):
    #    db.wire_delay[wnames.clknames[i]] = "TAP_BRANCH_PCLK" # XXX
    for i in range(32):
        db.wire_delay[wnames.clknames[i]] = "SPINE_TAP_PCLK"
    for i in range(81, 105): # clock inputs (PLL outs)
        db.wire_delay[wnames.clknames[i]] = "CENT_SPINE_PCLK"
    for i in range(121, 129): # clock inputs (pins)
        db.wire_delay[wnames.clknames[i]] = "CENT_SPINE_PCLK"
    for i in range(129, 153): # clock inputs (logic->clock)
        db.wire_delay[wnames.clknames[i]] = "CENT_SPINE_PCLK"
    for i in range(1000, 1002): # HCLK bridge muxes
        db.wire_delay[wnames.clknames[i]] = "HclkHbrgMux"
    for i in range(1002, 1010): # HCLK
        db.wire_delay[wnames.clknames[i]] = "ISB" # XXX
    for i in range(2, 6): # HCLK ins
        db.wire_delay[wnames.hclknames[i]] = "HclkInMux"
    for i in range(4): # HCLK outs
        db.wire_delay[f'HCLK_OUT{i}'] = "HclkOutMux"
    for wire in {'DLLDLY_OUT', 'DLLDLY_CLKOUT', 'DLLDLY_CLKOUT0', 'DLLDLY_CLKOUT1'}:
        db.wire_delay[wire] = "ISB" # XXX
    if wire.startswith('MPLL'):
        db.wire_delay[wire] = "X0"
    # XXX for now
    for wire in chain(wnames.clknames.values(), wnames.wirenames.values(), wnames.hclknames.values()):
        if wire not in db.wire_delay:
            db.wire_delay[wire] = "X8"


# assign pads with plls
# for now use static table and store the bel name although it is always PLL without a number
# theoretically, we can determine which PLL pad belongs to from the list of
# functions, but for them we will have to write a special parser since the
# format is very diverse (example: RPLL1_T_IN, RPLL_C_IN, TPLL_T_IN2). And we
# will still need a table with the coordinates of the PLL itself.
_pll_pads = {
    'GW1N-1': { 'IOR5A' : (0, 17, 'CLKIN_T', 'PLL'),
                'IOR5B' : (0, 17, 'CLKIN_C', 'PLL'),
                'IOR4A' : (0, 17, 'FB_T', 'PLL'),
                'IOR4B' : (0, 17, 'FB_C', 'PLL') },
    'GW1NZ-1': { 'IOR5A' : (0, 17, 'CLKIN_T', 'PLL'),
                 'IOR5B' : (0, 17, 'CLKIN_C', 'PLL') },
    'GW1N-4': { 'IOL3A' : (0, 9, 'CLKIN_T', 'PLL'),
                'IOL3B' : (0, 9, 'CLKIN_C', 'PLL'),
                'IOL4A' : (0, 9, 'FB_T', 'PLL'),
                'IOL4B' : (0, 9, 'FB_C', 'PLL'),
                'IOR3A' : (0, 27, 'CLKIN_T', 'PLL'),
                'IOR3B' : (0, 27, 'CLKIN_C', 'PLL'),
                'IOR4A' : (0, 27, 'FB_T', 'PLL'),
                'IOR4B' : (0, 27, 'FB_C', 'PLL'), },
    'GW1NS-4': { 'IOR2A' : (0, 36, 'CLKIN_T', 'PLL'),
                 'IOR2B' : (0, 36, 'CLKIN_C', 'PLL'),
                 'IOT13A' : (0, 27, 'CLKIN_T', 'PLL'),
                 'IOT13B' : (0, 27, 'CLKIN_C', 'PLL'), },
    'GW1N-9': { 'IOL5A' : (9, 0, 'CLKIN_T', 'PLL'),
                'IOL5B' : (9, 0, 'CLKIN_C', 'PLL'),
                'IOR5A' : (9, 46, 'CLKIN_T', 'PLL'),
                'IOR5B' : (9, 46, 'CLKIN_C', 'PLL'),
                'IOR6A' : (9, 46, 'FB_T', 'PLL'),
                'IOR6B' : (9, 46, 'FB_C', 'PLL'), },
    'GW1N-9C': { 'IOL5A' : (9, 0, 'CLKIN_T', 'PLL'),
                 'IOL5B' : (9, 0, 'CLKIN_C', 'PLL'),
                 'IOR5A' : (9, 46, 'CLKIN_T', 'PLL'),
                 'IOR5B' : (9, 46, 'CLKIN_C', 'PLL'),
                 'IOR6A' : (9, 46, 'FB_T', 'PLL'),
                 'IOR6B' : (9, 46, 'FB_C', 'PLL'), },
    'GW1N-9C': { 'IOL5A' : (9, 0, 'CLKIN_T', 'PLL'),
                 'IOL5B' : (9, 0, 'CLKIN_C', 'PLL'),
                 'IOR5A' : (9, 46, 'CLKIN_T', 'PLL'),
                 'IOR5B' : (9, 46, 'CLKIN_C', 'PLL'),
                 'IOR6A' : (9, 46, 'FB_T', 'PLL'),
                 'IOR6B' : (9, 46, 'FB_C', 'PLL'), },
    'GW2A-18': { 'IOL7A'  : (9, 0, 'CLKIN_T', 'PLL'),
                 'IOL45A' : (45, 0, 'CLKIN_T', 'PLL'),
                 'IOL47A' : (45, 0, 'FB_T', 'PLL'),
                 'IOL47B' : (45, 0, 'FB_C', 'PLL'),
                 'IOR45A' : (45, 0, 'CLKIN_T', 'PLL'), },
    'GW2A-18C': { 'IOR7A'  : (9, 55, 'CLKIN_T', 'PLL'),
                  'IOR7B'  : (9, 55, 'CLKIN_C', 'PLL'),
                  'IOR8A'  : (9, 55, 'FB_T', 'PLL'),
                  'IOR8B'  : (9, 55, 'FN_C', 'PLL'),
                  'IOL7A'  : (9, 0, 'CLKIN_T', 'PLL'),
                  'IOL7B'  : (9, 0, 'CLKIN_C', 'PLL'),
                  'IOL45A' : (45, 0, 'CLKIN_T', 'PLL'),
                  'IOL45B' : (45, 0, 'CLKIN_C', 'PLL'),
                  'IOL47A' : (45, 0, 'FB_T', 'PLL'),
                  'IOL47B' : (45, 0, 'FB_C', 'PLL'),
                  'IOR45A' : (45, 55, 'CLKIN_T', 'PLL'),
                  'IOR45B' : (45, 55, 'CLKIN_C', 'PLL'),
                  'IOR47A' : (45, 55, 'FB_T', 'PLL'),
                  'IOR47B' : (45, 55, 'FB_C', 'PLL'), },
    'GW5A-25A': { 'IOT56B' : (0, 0, 'FB_C', 'PLL'),
                  'IOT58B' : (0, 0, 'FB_C', 'PLL'),
                  'IOT58A' : (0, 0, 'CLKIN_T', 'PLL'),
                  'IOT89A' : (0, 0, 'FB_T', 'PLL'),
                  'IOT56A' : (0, 0, 'CLKIN_T', 'PLL'),
                  'IOT91A' : (0, 0, 'CLKIN_T', 'PLL'),
                  'IOT91B' : (0, 0, 'FB_C', 'PLL'),
                  'IOT61A' : (0, 0, 'CLKIN_T', 'PLL'),
                  'IOT63A' : (0, 0, 'CLKIN_T', 'PLL'),
                  'IOL5B'  : (0, 0, 'FB_C', 'PLL'),
                  'IOL5A'  : (0, 0, 'CLKIN_T', 'PLL'),
                  'IOT1A'  : (0, 0, 'CLKIN_T', 'PLL'),
                  'IOL3B'  : (0, 0, 'FB_C', 'PLL'),
                  'IOR31A' : (0, 0, 'CLKIN_T', 'PLL'),
                  'IOR31B' : (0, 0, 'FB_C', 'PLL'),
                  'IOR33A' : (0, 0, 'CLKIN_T', 'PLL'),
                  'IOB89A' : (0, 0, 'CLKIN_T', 'PLL'),
                  'IOL14A' : (0, 0, 'CLKIN_T', 'PLL'),
                  'IOL3A'  : (0, 0, 'CLKIN_T', 'PLL'),
                  'IOR33B' : (0, 0, 'FB_C', 'PLL'),
                  'IOB31B' : (0, 0, 'FB_C', 'PLL'),
                  'IOB4B'  : (0, 0, 'FB_C', 'PLL'),
                  'IOB33A' : (0, 0, 'CLKIN_T', 'PLL'),
                  'IOB54B' : (0, 0, 'FB_C', 'PLL'),
                  'IOB12B' : (0, 0, 'CLKIN_C', 'PLL'), },
}
def pll_pads(dev, device, pad_locs):
    if device not in _pll_pads:
        return
    for loc, pll_data in _pll_pads[device].items():
        dev.pad_pll[loc] = pll_data

