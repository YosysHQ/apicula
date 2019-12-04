from dataclasses import dataclass, field
from typing import Dict, List, Set, Tuple, Union
import fuse_h4x as fuse
from wirenames import wirenames
import re

# represents a row, column coordinate
# can be either tiles or bits within tiles
Coord = Tuple[int, int]

@dataclass(frozen=True)
class Wire:
    """Represents a named wire
    driven at the specified relative offset"""
    name: str
    offset: Coord = (0, 0)

@dataclass
class Bel:
    """Respresents a Basic ELement
    with the specified modes mapped to bits
    and the specified portmap"""
    modes: Dict[Union[int, str], Set[Coord]] = field(default_factory=dict)
    portmap: Dict[str, Wire] = field(default_factory=dict)

@dataclass
class Tile:
    """Represents all the configurable features
    for this specific tile type"""
    width: int
    height: int
    # a mapping from source wire to bit coordinates
    pips: Dict[Tuple[Wire, Wire], Set[Coord]] = field(default_factory=dict)
    # a mapping from bel type to bel
    bels: Dict[str, Bel] = field(default_factory=dict)

@dataclass
class Device:
    # a grid of tiles
    grid: List[List[Tile]] = field(default_factory=list)

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

def id2wire(wid):
    name = wirenames[wid]
    m = re.match(r"([NESW])([128]\d)(\d)", name)
    if not m:
        # local/global wire
        return Wire(name)

    # inter-tile wire
    dirlut = {'N': (1, 0),
              'E': (0, -1),
              'S': (-1, 0),
              'W': (0, 1)}
    direction, wire, segment = m.groups()
    row = dirlut[direction][0]*int(segment)
    col = dirlut[direction][1]*int(segment)
    return Wire(f"{direction}{wire}", (row, col))

def unpad(fuses, pad=-1):
    try:
        return fuses[:fuses.index(pad)]
    except ValueError:
        return fuses

def fse_pips(fse, ttyp):
    pips = {}
    for srcid, destid, *fuses in fse[ttyp]['wire'][2]:
        fuses = {fuse.fuse_lookup(fse, ttyp, f) for f in unpad(fuses)}
        if srcid < 0:
            fuses = []
            srcid = -srcid
        if srcid > 1000:
            srcid -= 1000 # what does it mean?
        if destid > 1000:
            destid -= 1000 # what does it mean?
        src = id2wire(srcid)
        dest = id2wire(destid)
        pips[(src, dest)] = fuses

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
        bel.modes[bit] = {coord}

    # dicts are in insertion order
    for num, lut in enumerate(luts.values()):
        lut.portmap = {
            'F': Wire(f"F{num}"),
            'I0': Wire(f"A{num}"),
            'I1': Wire(f"B{num}"),
            'I2': Wire(f"C{num}"),
            'I3': Wire(f"D{num}"),
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
        tile.pips = fse_pips(fse, ttyp)
        tile.bels = fse_luts(fse, ttyp)
        tiles[ttyp] = tile

    dev.grid = [[tiles[ttyp] for ttyp in row] for row in fse['header']['grid'][61]]
    return dev
