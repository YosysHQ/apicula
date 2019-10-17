import sys
import numpy as np
import fuse_h4x as fse
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
            if frow == row and fcol == col:
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

    for w1, w2, *fuses in data:
        if w1 < 0:
            excl.add((-w1, w2))
        elif (w1, w2) not in excl:
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

if __name__ == "__main__":
    with open(sys.argv[1], 'rb') as f:
        d = fse.readFse(f)
    bitmap = read_bitstream(sys.argv[2])
    bitmap = np.fliplr(bitmap)
    bm = tile_bitmap(d, bitmap)
    for idx, t in bm.items():
        row, col, typ = idx
        #if typ != 14: continue
        print(idx)
        td = parse_tile(d, typ, t)
        print(td.keys())
        print(parse_wires(td))
        print(parse_luts(td))
        parse_wires(td)
        #for bitrow in t:
        #    print(*bitrow, sep='')
        #fuses = scan_fuses(d, typ, t)
        #scan_tables(d, typ, fuses)

