import sys
import importlib.resources
import pickle
import argparse
import re
from contextlib import contextmanager
from collections import Counter
from apycula import chipdb

class Bba(object):
    
    def __init__(self, file):
        self.file = file
        self.block_idx = Counter()

    def __getattr__(self, attr):
        def write_value(val):
            self.file.write(f"{attr} {val}\n")
        return write_value

    def str(self, val, sep="|"):
        self.file.write(f"str {sep}{val}{sep}\n")
    
    @contextmanager
    def block(self, prefix="block"):
        idx = self.block_idx[prefix]
        self.block_idx.update([prefix])
        name = f"{prefix}_{idx}"
        self.push(name)
        self.label(name)
        try:
            yield name
        finally:
            self.pop(name)

constids = ['']
ids = []
def id_string(s):
    try:
        return constids.index(s)
    except ValueError:
        pass
    try:
        return len(constids)+ids.index(s)
    except ValueError:
        ids.append(s)
        return len(constids)+len(ids)-1

def id_strings(b):
    with b.block('idstrings') as  blk:
        for s in ids:
            b.str(s)
    b.u16(len(constids))
    b.u16(len(ids))
    b.ref(blk)

def write_pips(b, pips):
    num = 0
    with b.block("pips") as blk:
        for dest, srcs in pips.items():
            for src in srcs:
                num += 1
                b.u16(id_string(dest))
                b.u16(id_string(src))
    b.u32(num)
    b.ref(blk)

def write_bels(b, bels):
    with b.block("bels") as blk:
        for typ, bel in bels.items():
            b.u16(id_string(typ))
            with b.block("portmap") as port_blk:
                for dest, src in bel.portmap.items():
                    b.u16(id_string(dest))
                    b.u16(id_string(src))
            b.u16(len(bel.portmap))
            b.ref(port_blk)


    b.u32(len(bels))
    b.ref(blk)

def write_aliases(b, aliases):
    with b.block('aliases') as blk:
        for dest, src in aliases.items():
            b.u16(id_string(dest))
            b.u16(id_string(src))
    b.u32(len(aliases))
    b.ref(blk)

def write_tile(b, tile):
    with b.block('tile') as blk:
        write_bels(b, tile.bels)
        write_pips(b, tile.pips)
        write_pips(b, tile.clock_pips)
        write_aliases(b, tile.aliases)
        return blk

def write_grid(b, grid):
    tiles = {}
    with b.block('grid') as grid_block:
        for row in grid:
            for tile in row:
                if id(tile) in tiles:
                    b.ref(tiles[id(tile)])
                else:
                    blk = write_tile(b, tile)
                    tiles[id(tile)] = blk
                    b.ref(blk)
    b.ref(grid_block)


def write_global_aliases(b, db):
    with b.block('aliases') as blk:
        aliases = sorted(db.aliases.items(),
            key=lambda i: (i[0][0], i[0][1], id_string(i[0][2])))
        for (drow, dcol, dest), (srow, scol, src) in aliases:
            b.u16(drow)
            b.u16(dcol)
            b.u16(id_string(dest))
            b.u16(srow)
            b.u16(scol)
            b.u16(id_string(src))
    b.u32(len(db.aliases))
    b.ref(blk)

def write_timing(b, timing):
    with b.block('timing') as blk:
        for speed, groups in timing.items():
            b.u32(id_string(speed))
            with b.block('timing_group') as tg:
                for group, types in groups.items():
                    b.u32(id_string(group))
                    with b.block('timing_types') as tt:
                        for name, items in types.items():
                            try:
                                items[0] # QUACKING THE DUCK
                                b.u32(id_string(name))
                                for item in items:
                                    b.u32(int(item*1000))
                            except TypeError:
                                pass
                    b.u32(len(types))
                    b.ref(tt)
            b.u32(len(groups))
            b.ref(tg)
    b.u32(len(timing))
    b.ref(blk)

pin_re = re.compile(r"IO([TBRL])(\d+)([A-Z])")
def iob2bel(db, name):
    banks = {'T': [(1, n) for n in range(1, db.cols)],
            'B': [(db.rows, n) for n in range(1, db.cols)],
            'L': [(n, 1) for n in range(1, db.rows)],
            'R': [(n, db.cols) for n in range(1, db.rows)]}
    side, num, pin = pin_re.match(name).groups()
    row, col = banks[side][int(num)-1]
    return f"R{row}C{col}_IOB{pin}"

def write_pinout(b, db):
    with b.block("variants") as blk:
        for device, pkgs in db.pinout.items():
            b.u32(id_string(device))
            with b.block("packages") as pkgblk:
                for pkg, pins in pkgs.items():
                    b.u32(id_string(pkg))
                    with b.block("pins") as pinblk:
                        for num, loc in pins.items():
                            b.u16(id_string(num))
                            b.u16(id_string(iob2bel(db, loc)))
                    b.u32(len(pins))
                    b.ref(pinblk)
            b.u32(len(pkgs))
            b.ref(pkgblk)
    b.u32(len(db.pinout))
    b.ref(blk)

def write_chipdb(db, f, device):
    cdev=device.replace('-', '_')
    b = Bba(f)
    b.pre('#include "nextpnr.h"')
    b.pre('#include "embed.h"')
    b.pre('NEXTPNR_NAMESPACE_BEGIN')
    with b.block(f'chipdb_{cdev}') as blk:
        b.str(device)
        b.u32(0) # version
        b.u16(db.rows)
        b.u16(db.cols)
        write_grid(b, db.grid)
        write_global_aliases(b, db)
        write_timing(b, db.timing)
        write_pinout(b, db)
        id_strings(b)
    b.post(f'EmbeddedFile chipdb_file_{cdev}("gowin/chipdb-{device}.bin", {blk});')
    b.post('NEXTPNR_NAMESPACE_END')

def read_constids(f):
    xre = re.compile(r"X\((.*)\)")
    for line in f:
        m = xre.match(line)
        if m:
            constids.append(m.group(1))
    return ids


def main():
    parser = argparse.ArgumentParser(description='Make Gowin BBA')
    parser.add_argument('-d', '--device', required=True)
    parser.add_argument('-i', '--constids', type=argparse.FileType('r'), default=sys.stdin)
    parser.add_argument('-o', '--output', type=argparse.FileType('w'), default=sys.stdout)

    args = parser.parse_args()
    read_constids(args.constids)
    with importlib.resources.open_binary("apycula", f"{args.device}.pickle") as f:
        db = pickle.load(f)
    write_chipdb(db, args.output, args.device)

if __name__ == "__main__":
    main()
