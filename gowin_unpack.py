import sys
import re
import numpy as np
import fuse_h4x as fse
import codegen
from bslib import read_bitstream
from wirenames import wirenames


def tile_bitmap(d, bitmap):
    tiles = d['header']['grid'][61]
    width = sum([d[i]['width'] for i in tiles[0]])
    height = sum([d[i[0]]['height'] for i in tiles])
    res = {}
    y = 0
    for idx, row in enumerate(tiles):
        x=0
        for jdx, typ in enumerate(row):
            #if typ==12: pdb.set_trace()
            td = d[typ]
            w = td['width']
            h = td['height']
            tile = bitmap[y:y+h,x:x+w]
            if tile.any():
                res[(idx, jdx, typ)] = tile
            x+=w
        y+=h

    return res

def parse_tile(d, ttyp, tile):
    w = d[ttyp]['width']
    h = d[ttyp]['height']
    res = {}
    for start, table in [(2, 'shortval'), (2, 'wire'), (16, 'longval'),
                         (1, 'longfuse'), (0, 'const')]:
        if table in d[ttyp]:
            for styp, sinfo in d[ttyp][table].items():
                for i in sinfo:
                    fusebits = []
                    for fuse in i[start:]:
                        if fuse >= 0:
                            num = d['header']['fuse'][1][fuse][ttyp]
                            row = num // 100
                            col = num % 100
                            bit = tile[row][col]
                            fusebits.append(bit==1)
                    if all(fusebits):
                        res.setdefault(table, {}).setdefault(styp, []).append(tuple(i[:]))

    return res

def scan_fuses(d, ttyp, tile):
    w = d[ttyp]['width']
    h = d[ttyp]['height']
    fuses = []
    rows, cols = np.where(tile==1)
    for row, col in zip(rows, cols):
        # ripe for optimization
        for fnum, fuse in enumerate(d['header']['fuse'][1]):
            num = fuse[ttyp]
            frow = num // 100
            fcol = num % 100
            if frow == row and fcol == col and fnum > 100:
                fuses.append(fnum)
    return set(fuses)

def scan_tables(d, tiletyp, fuses):
    for tname, tables in d[tiletyp].items():
        if tname in {"width", "height"}: continue
        for ttyp, table in tables.items():
            for row in table:
                row_fuses = fuses.intersection(row)
                if row_fuses:
                    print(f"fuses {row_fuses} found in {tname}({ttyp}): {row}")

def parse_wires(tiledata):
    excl = set()
    wires = []
    try:
        data = tiledata['wire'][2]
    except KeyError:
        return wires

    # put wires with more fuses later
    # so they overwrite smaller subsets
    data.sort(key=lambda l: [w > 0 for w in l[2:]])

    for w1, w2, *fuses in data:
        if w1 < 0:
            print('neg', wirenames[-w1], wirenames[w2], fuses)
            excl.add((-w1, w2))
        elif (w1, w2) not in excl:
            print('pos', wirenames[w1], wirenames[w2], fuses)
            wires.append((wirenames[w1], wirenames[w2]))
    return wires

def parse_luts(tiledata):
    excl = set()
    luts = {}
    try:
        data = tiledata['shortval'][5]
    except KeyError:
        return luts

    for lut, bit, *fuses in data:
        luts[lut] = luts.get(lut, 0xffff) & ~(1<<bit)

    return luts

def wire2global(row, col, name):
    if name.startswith("GB") or name in {'VCC', 'VSS'}:
        # global wire
        return name

    m = re.match(r"([NESW])([128]\d)(\d)", name)
    if not m:
        # local wire
        return f"R{row}C{col}_{name}"

    # inter-tile wire
    dirlut = {'N': (1, 0),
              'E': (0, -1),
              'S': (-1, 0),
              'W': (0, 1)}
    direction, wire, segment = m.groups()
    rootrow = row + dirlut[direction][0]*int(segment)
    rootcol = col + dirlut[direction][1]*int(segment)
    return f"R{rootrow}C{rootcol}_{direction}{wire}"

def tile2verilog(row, col, td, mod):
    wires = parse_wires(td)
    for src, dest in wires:
        srcg = wire2global(row, col, src)
        destg = wire2global(row, col, dest)
        mod.wires.update({srcg, destg})
        mod.assigns[destg] = srcg

    luts = parse_luts(td)
    for idx, val in luts.items():
        name = f"R{row}C{col}_LUT4_{idx}"
        lut = codegen.Primitive("LUT4", name)
        lut.params["INIT"] = f"16'b{val:016b}"
        lut.portmap['F'] = f"R{row}C{col}_F{idx}"
        lut.portmap['I0'] = f"R{row}C{col}_A{idx}"
        lut.portmap['I1'] = f"R{row}C{col}_B{idx}"
        lut.portmap['I2'] = f"R{row}C{col}_C{idx}"
        lut.portmap['I3'] = f"R{row}C{col}_D{idx}"
        mod.wires.update(lut.portmap.values())
        mod.primitives[name] = lut


if __name__ == "__main__":
    with open(sys.argv[1], 'rb') as f:
        d = fse.readFse(f)
    bitmap = read_bitstream(sys.argv[2])
    bitmap = np.fliplr(bitmap)
    bm = tile_bitmap(d, bitmap)
    mod = codegen.Module()
    for idx, t in bm.items():
        row, col, typ = idx
        if typ != 17: continue
        print(idx)
        td = parse_tile(d, typ, t)
        print(td.keys())
        print(parse_wires(td))
        print(parse_luts(td))
        parse_wires(td)
        for bitrow in t:
            print(*bitrow, sep='')
        fuses = scan_fuses(d, typ, t)
        scan_tables(d, typ, fuses)
        tile2verilog(row, col, td, mod)
    with open("unpack.v", 'w') as f:
        mod.write(f)

