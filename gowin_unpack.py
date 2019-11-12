import sys
import re
import numpy as np
from itertools import chain, count
import fuse_h4x as fse
import codegen
from bslib import read_bitstream
from wirenames import wirenames

import pdb


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

def fuse_lookup(d, ttyp, fuse):
    if fuse >= 0:
        num = d['header']['fuse'][1][fuse][ttyp]
        row = num // 100
        col = num % 100
        return row, col

def parse_tile(d, ttyp, tile):
    w = d[ttyp]['width']
    h = d[ttyp]['height']
    res = {}
    for start, table in [(2, 'shortval'), (2, 'wire'), (16, 'longval'),
                         (1, 'longfuse'), (0, 'const')]:
        if table in d[ttyp]: # skip missing entries
            for subtyp, tablerows in d[ttyp][table].items():
                items = {}
                for row in tablerows:
                    pos = row[0] > 0
                    coords = {(fuse_lookup(d, ttyp, f), pos) for f in row[start:] if f > 0}
                    idx = tuple(abs(attr) for attr in row[:start])
                    items.setdefault(idx, {}).update(coords)

                for idx, item in items.items():
                    test = [tile[loc[0]][loc[1]] == val
                            for loc, val in item.items()]
                    if all(test):
                        row = idx + tuple(item.keys())
                        res.setdefault(table, {}).setdefault(subtyp, []).append(row)

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
        data = [
            tiledata['wire'].get(2),
            tiledata['wire'].get(38),
            tiledata['wire'].get(48),
        ]
    except KeyError:
        return wires

    for table in data:
        if table:
            # put wires with more fuses later
            # so they overwrite smaller subsets
            table.sort(key=len)

            for w1, w2, *fuses in table:
                if w1 < 0:
                    #print('neg', wirenames[-w1], wirenames[w2], fuses)
                    excl.add((-w1, w2))
                elif w1 > 1000:
                    #print('1k1', wirenames[w1-1000], wirenames[w2], fuses)
                    wires.append((wirenames[w1-1000], wirenames[w2]))
                elif w2 > 1000:
                    #print('1k2', wirenames[w1], wirenames[w2-1000], fuses)
                    wires.append((wirenames[w1], wirenames[w2-1000]))
                elif (w1, w2) not in excl:
                    #print('pos', wirenames[w1], wirenames[w2], fuses)
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

def parse_dffs(tiledata):
    try:
        data = [
            tiledata['shortval'].get(25),
            tiledata['shortval'].get(26),
            tiledata['shortval'].get(27),
        ]
    except KeyError:
        return [None, None, None]

    fuses = [d and frozenset(f[0] for f in d) for d in data]
    print(fuses)

    dff_types = {
        frozenset([20, 21]): 'DFF',
        frozenset([21, 7]): 'DFFS',
        frozenset([20, 21, 7]): 'DFFR',
        frozenset([5, 21, 7]): 'DFFP',
        frozenset([5, 20, 21, 7]): 'DFFC',
        frozenset([3, 4, 20, 21]): 'DFFN',
        frozenset([3, 4, 21, 7]): 'DFFNS',
        frozenset([3, 4, 20, 21, 7]): 'DFFNR',
        frozenset([3, 4, 5, 21, 7]): 'DFFNP',
        frozenset([3, 4, 5, 20, 21, 7]): 'DFFNC',
    }
   
    return [dff_types.get(f) for f in fuses]

def parse_iob(tiledata):
    try:
        data = [
            tiledata['longval'].get(23),
            tiledata['longval'].get(24),
        ]
    except KeyError:
        return [None, None]

    fuses = [d and frozenset(f[0] for f in d) for d in data]
    print(fuses)

    iob_types = {
        frozenset([64, 47, 48, 49, 30]): 'IBUF',
        frozenset([3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 26, 30,
                   47, 48, 49, 61, 63, 64, 66, 67, 68, 81]): 'OBUF',
        # same as TBUF with unused input?
        frozenset([3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 47, 48, 49, 26, 30]): 'IOBUF',
    }
   
    return [iob_types.get(f) for f in fuses]

def wire2global(row, col, fse, name):
    width = len(fse['header']['grid'][61][0])
    height = len(fse['header']['grid'][61])
    if name.startswith("G") or name in {'VCC', 'VSS'}:
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
    uturnlut = {'N': 'S', 'S': 'N', 'E': 'W', 'W': 'E'}
    direction, wire, segment = m.groups()
    rootrow = row + dirlut[direction][0]*int(segment)
    rootcol = col + dirlut[direction][1]*int(segment)
    # wires wrap around the edges
    if rootrow < 1:
        rootrow = 1 - rootrow
        direction = uturnlut[direction]
    if rootcol < 1:
        rootcol = 1 - rootcol
        direction = uturnlut[direction]
    if rootrow > height:
        rootrow = 2*height+1 - rootrow
        direction = uturnlut[direction]
    if rootcol > width:
        rootcol = 2*width+1 - rootcol
        direction = uturnlut[direction]
    # map cross wires to their origin
    diaglut = {
        'E11': 'EW10',
        'W11': 'EW10',
        'E12': 'EW20',
        'W12': 'EW20',
        'S11': 'SN10',
        'N11': 'SN10',
        'S12': 'SN20',
        'N12': 'SN20',
    }
    name = diaglut.get(direction+wire, direction+wire)
    return f"R{rootrow}C{rootcol}_{name}"

def tile2verilog(row, col, td, mod, fse):
    # fse is 0-based, floorplanner is 1-based
    row += 1
    col += 1
    wires = parse_wires(td)
    for src, dest in wires:
        srcg = wire2global(row, col, fse, src)
        destg = wire2global(row, col, fse, dest)
        mod.wires.update({srcg, destg})
        mod.assigns.append((destg, srcg))

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

    dffs = parse_dffs(td)
    dffmap = {
        "DFF": None,
        "DFFS": "SET",
        "DFFR": "RESET",
        "DFFP": "PRESET",
        "DFFC": "CLEAR",
        "DFFNS": "SET",
        "DFFNR": "RESET",
        "DFFNP": "PRESET",
        "DFFNC": "CLEAR",
    }
    for idx, typ in enumerate(dffs):
        #print(idx, typ)
        if typ:
            port = dffmap[typ]
            lutidx = idx*2
            name = f"R{row}C{col}_{typ}E_{idx}_A"
            dff = codegen.Primitive(typ+"E", name)
            dff.portmap['CLK'] = f"R{row}C{col}_CLK{idx}"
            dff.portmap['D'] = f"R{row}C{col}_F{lutidx}"
            dff.portmap['Q'] = f"R{row}C{col}_Q{lutidx}"
            dff.portmap['CE'] = f"R{row}C{col}_CE{idx}"
            if port:
                dff.portmap[port] = f"R{row}C{col}_LSR{idx}"
            mod.wires.update(dff.portmap.values())
            mod.primitives[name] = dff

            lutidx = idx*2+1
            name = f"R{row}C{col}_{typ}E_{idx}_B"
            dff = codegen.Primitive(typ+"E", name)
            dff.portmap['CLK'] = f"R{row}C{col}_CLK{idx}"
            dff.portmap['D'] = f"R{row}C{col}_F{lutidx}"
            dff.portmap['Q'] = f"R{row}C{col}_Q{lutidx}"
            dff.portmap['CE'] = f"R{row}C{col}_CE{idx}"
            if port:
                dff.portmap[port] = f"R{row}C{col}_LSR{idx}"
            mod.wires.update(dff.portmap.values())
            mod.primitives[name] = dff

    iob = parse_iob(td)
    iobmap = {
        "IBUF": {"wires": ["O"], "inputs": ["I"]},
        "OBUF": {"wires": ["I"], "outputs": ["O"]},
        "TBUF": {"wires": ["I", "OEN"], "outputs": ["O"]},
        "IOBUF": {"wires": ["I", "O", "OEN"], "inouts": ["IO"]},
    }
    portmap = {
        ('I', 0): 'A0',
        ('OEN', 0): 'B0',
        ('O', 0): 'F6',
        ('I', 1): 'D1',
        ('OEN', 1): 'D5',
        ('O', 1): 'Q6',
    }
    for idx, typ in enumerate(iob):
        #print(idx, typ)
        if typ:
            name = f"R{row}C{col}_{typ}_{idx}"
            wires = set(iobmap[typ]['wires'])
            ports = set(chain.from_iterable(iobmap[typ].values())) - wires

            iob = codegen.Primitive(typ, name)

            for port in wires:
                wname = portmap[(port, idx)]
                iob.portmap[port] = f"R{row}C{col}_{wname}"

            for port in ports:
                iob.portmap[port] = f"R{row}C{col}_{port}{idx}"

            for wires in iobmap[typ]['wires']:
                wnames = [f"R{row}C{col}_{portmap[(w, idx)]}" for w in wires]
                mod.wires.update(wnames)
            for direction in ['inputs', 'outputs', 'inouts']:
                for wires in iobmap[typ].get(direction, []):
                    wnames = [f"R{row}C{col}_{w}{idx}" for w in wires]
                    getattr(mod, direction).update(wnames)

            mod.primitives[name] = iob

    gnd = codegen.Primitive("GND", "mygnd")
    gnd.portmap["G"] = "VSS"
    mod.primitives["mygnd"] = gnd
    vcc = codegen.Primitive("VCC", "myvcc")
    vcc.portmap["V"] = "VCC"
    mod.primitives["myvcc"] = vcc


if __name__ == "__main__":
    with open(sys.argv[1], 'rb') as f:
        d = fse.readFse(f)
    bitmap = read_bitstream(sys.argv[2])
    bm = tile_bitmap(d, bitmap)
    mod = codegen.Module()
    for idx, t in bm.items():
        row, col, typ = idx
        #if typ != 17: continue
        print(idx)
        td = parse_tile(d, typ, t)
        print(td.keys())
        #print(parse_wires(td))
        #print(parse_luts(td))
        print(parse_iob(td))
        #for bitrow in t:
        #    print(*bitrow, sep='')
        #fuses = scan_fuses(d, typ, t)
        #scan_tables(d, typ, fuses)
        tile2verilog(row, col, td, mod, d)
    with open("unpack.v", 'w') as f:
        mod.write(f)

