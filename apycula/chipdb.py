from dataclasses import dataclass, field
from typing import Dict, List, Set, Tuple, Union, ByteString
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

# IOB flag descriptor
# bitmask and possible values
@dataclass
class IOBFlag:
    mask: Set[Coord] = field(default_factory = set)
    options: Dict[str, Set[Coord]] = field(default_factory = dict)

# IOB mode descriptor
# bits and flags
# encode bits include all default flag values
@dataclass
class IOBMode:
    encode_bits: Set[Coord] = field(default_factory = set)
    decode_bits: Set[Coord] = field(default_factory = set)
    flags: Dict[str, IOBFlag] = field(default_factory = dict)

@dataclass
class Bel:
    """Respresents a Basic ELement
    with the specified modes mapped to bits
    and the specified portmap"""
    # there can be zero or more flags
    flags: Dict[Union[int, str], Set[Coord]] = field(default_factory=dict)
    # { iostd: { mode : IOBMode}}
    iob_flags: Dict[str, Dict[str, IOBMode]] = field(default_factory=dict)
    lvcmos121518_bits: Set[Coord] = field(default_factory = set)
    # this Bel is IOBUF and needs routing to become IBUF or OBUF
    simplified_iob: bool = field(default = False)
    # banks
    bank_mask: Set[Coord] = field(default_factory=set)
    bank_flags: Dict[str, Set[Coord]] = field(default_factory=dict)
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
    # a mapping from dest, source wire to bit coordinates
    pips: Dict[str, Dict[str, Set[Coord]]] = field(default_factory=dict)
    clock_pips: Dict[str, Dict[str, Set[Coord]]] = field(default_factory=dict)
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
    pinout: Dict[str, Dict[str, Dict[str, str]]] = field(default_factory=dict)
    pin_bank: Dict[str, int] = field(default_factory = dict)
    cmd_hdr: List[ByteString] = field(default_factory=list)
    cmd_ftr: List[ByteString] = field(default_factory=list)
    template: np.ndarray = None
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

    @property
    def corners(self):
        # { (row, col) : bank# }
        return {
            (0, 0) : 0,
            (0, self.cols - 1) : 1,
            (self.rows - 1, self.cols - 1) : 2,
            (self.rows - 1, 0) : 3}

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

# add the ALU mode
# new_mode_bits: string like "0110000010011010"
def add_alu_mode(base_mode, modes, lut, new_alu_mode, new_mode_bits):
    alu_mode = modes.setdefault(new_alu_mode, set())
    alu_mode.update(base_mode)
    for i, bit in enumerate(new_mode_bits):
        if bit == '0':
            alu_mode.update(lut.flags[15 - i])

# also make ALUs and shadow RAM
def fse_luts(fse, ttyp):
    try:
        data = fse[ttyp]['shortval'][5]
    except KeyError:
        return {}

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
        data = fse[ttyp]['shortval'][28]
        bel = luts.setdefault(f"RAM16", Bel())
        mode = bel.modes.setdefault("0", set())
        for key0, key1, *fuses in data:
            if key0 == 2 and key1 == 0:
                for f in (f for f in fuses if f != -1):
                    coord = fuse.fuse_lookup(fse, ttyp, f)
                    mode.update({coord})
                break
        bel.flags.update({k:v for (k, v) in luts["LUT0"].flags.items()})
        bel.flags.update({k+16:v for (k, v) in luts["LUT1"].flags.items()})
        bel.flags.update({k+32:v for (k, v) in luts["LUT2"].flags.items()})
        bel.flags.update({k+48:v for (k, v) in luts["LUT3"].flags.items()})
        bel.portmap = {
            'DI': ("A5", "B5", "C5", "D5"),
            'CLK': "CLK2",
            'WRE': "LSR2",
            'WAD': ("A4", "B4", "C4", "D4"),
            'RAD': tuple(tuple(f"{j}{i}" for i in range(4)) for j in ["A", "B", "C", "D"]),
            'DO': ("F0", "F1", "F2", "F3"),
        }
    return luts


def from_fse(fse):
    dev = Device()
    ttypes = {t for row in fse['header']['grid'][61] for t in row}
    tiles = {}
    for ttyp in ttypes:
        w = fse[ttyp]['width']
        h = fse[ttyp]['height']
        tile = Tile(w, h)
        tile.pips = fse_pips(fse, ttyp, 2, wirenames)
        tile.clock_pips = fse_pips(fse, ttyp, 38, clknames)
        tile.bels = fse_luts(fse, ttyp)
        tiles[ttyp] = tile

    dev.grid = [[tiles[ttyp] for ttyp in row] for row in fse['header']['grid'][61]]
    return dev

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


def dat_portmap(dat, dev):
    for row in dev.grid:
        for tile in row:
            for name, bel in tile.bels.items():
                if bel.portmap: continue
                if name.startswith("IOB"):
                    if len(tile.bels) > 2:
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

def dff_clean(dev):
    """ Clean DFF mode bits: fuzzer captures a bit of the neighboring trigger."""
    seen_bels = []
    for idx, row in enumerate(dev.grid):
        for jdx, td in enumerate(row):
            for name, bel in td.bels.items():
                if name[0:3] == "DFF":
                    if bel in seen_bels:
                        continue
                    seen_bels.append(bel)
                    # find extra bit
                    extra_bits = None
                    for bits in bel.modes.values():
                        if extra_bits != None:
                            extra_bits &= bits
                        else:
                            extra_bits = bits.copy()
                    # remove it
                    for mode, bits in bel.modes.items():
                        bits -= extra_bits

def get_route_bits(db, row, col):
    """ All routing bits for the cell """
    bits = set()
    for w in db.grid[row][col].pips.values():
        for v in w.values():
            bits.update(v)
    return bits

def diff2flag(dev):
    """ Minimize bits for flag values and calc flag bitmask"""
    seen_bels = []
    for idx, row in enumerate(dev.grid):
        for jdx, td in enumerate(row):
            for name, bel in td.bels.items():
                if name[0:3] == "IOB":
                    if not bel.iob_flags or bel in seen_bels:
                        continue
                    seen_bels.append(bel)
                    # get routing bits for cell
                    rbits = get_route_bits(dev, idx, jdx)
                    # If for a given mode all possible values of one flag
                    # contain some bit, then this bit is "noise" --- this bit
                    # belongs to the default value of another flag. Remove.
                    for iostd, iostd_rec in bel.iob_flags.items():
                        for mode, mode_rec in iostd_rec.items():
                            # if encoding has routing
                            r_encoding = mode_rec.encode_bits & rbits
                            mode_rec.encode_bits -= rbits
                            if r_encoding and mode != 'IOBUF':
                                bel.simplified_iob = True
                            mode_rec.decode_bits = mode_rec.encode_bits.copy()
                            for flag, flag_rec in mode_rec.flags.items():
                                noise_bits = None
                                for bits in flag_rec.options.values():
                                    if noise_bits != None:
                                        noise_bits &= bits
                                    else:
                                        noise_bits = bits.copy()
                                # remove noise
                                for bits in flag_rec.options.values():
                                    bits -= noise_bits
                                    flag_rec.mask |= bits
                            # decode bits don't include flags
                            for _, flag_rec in mode_rec.flags.items():
                                mode_rec.decode_bits -= flag_rec.mask
                elif name == "BANK":
                    noise_bits = None
                    for bits in bel.bank_flags.values():
                        if noise_bits != None:
                            noise_bits &= bits
                        else:
                            noise_bits = bits.copy()
                    mask = set()
                    for bits in bel.bank_flags.values():
                        bits -= noise_bits
                        mask |= bits
                    bel.bank_mask = mask
                    bel.modes['ENABLE'] -= mask
                else:
                    continue

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
    """ returns bank index 0...n
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

