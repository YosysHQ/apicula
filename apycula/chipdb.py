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
            if srcid >= 1000:
                srcid -= 1000 # what does it mean?
            if destid >= 1000:
                destid -= 1000 # what does it mean?
            src = wn.get(srcid, srcid)
            dest = wn.get(destid, destid)
            pips.setdefault(dest, {})[src] = fuses

    return pips

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
    if device == "GW1N-1":
        header = 1
        start = 5
    elif device == "GW1N-4":
        header = 0
        start = 7
    elif device == "GW1N-9":
        header = 0
        start = 7
    elif device == "GW1NR-9":
        header = 1
        start = 7
    elif device == "GW1NS-2":
        header = 0
        start = 7
    elif device == "GW1NS-2C":
        header = 0
        start = 7
    else:
        raise Exception("unsupported device")
    pkgs = pindef.all_packages(device, start, header)
    res = {}
    for pkg in pkgs:
        res[pkg] = pindef.get_pin_locs(device, pkg, pindef.VeryTrue, header)
    return res

def xls_pinout(family):
    if family == "GW1N-1":
        return {
            "GW1N-1": get_pins("GW1N-1"),
        }
    elif family == "GW1N-9":
        return {
            "GW1N-9": get_pins("GW1N-9"),
            "GW1NR-9": get_pins("GW1NR-9"),
        }
    elif family == "GW1N-4":
        return {
            "GW1N-4": get_pins("GW1N-4"),
        }
    elif family == "GW1NS-2":
        return {
            "GW1NS-2": get_pins("GW1NS-2"),
            "GW1NS-2C": get_pins("GW1NS-2C"),
        }
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
                    # If for a given mode all possible values of one flag
                    # contain some bit, then this bit is "noise" --- this bit
                    # belongs to the default value of another flag. Remove.
                    for iostd, iostd_rec in bel.iob_flags.items():
                        for mode, mode_rec in iostd_rec.items():
                            mode_rec.decode_bits = mode_rec.encode_bits.copy()
                            for flag, flag_rec in mode_rec.flags.items():
                                noise_bits = set()
                                for bits in flag_rec.options.values():
                                    if noise_bits:
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
                    noise_bits = set()
                    for bits in bel.bank_flags.values():
                        if noise_bits:
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
        # XXX do something with this 'A'
        bank = db.pin_bank[loc2pin_name(db, row, col) + 'A']
    return bank

