import sys
import random
import os
from apycula import bitmatrix

#gowinhome = os.getenv("GOWINHOME")
#if not gowinhome:
#    raise Exception("GOWINHOME not set")

# device = os.getenv("DEVICE")
device = sys.argv[1]

def rint(f, w):
    val = int.from_bytes(f.read(w), 'little', signed=True)
    return val

def readFse(f, device):
    print("check", rint(f, 4))
    tiles = {}
    ttyp = rint(f, 4)
    print(f"tile type:{ttyp}/{hex(ttyp)}")
    tiles['header'] = readOneFile(f, ttyp, device)
    while True:
        ttyp = rint(f, 4)
        if ttyp == 0x9a1d85: break
        print(f"tile type:{ttyp}/{hex(ttyp)}")
        tiles[ttyp] = readOneFile(f, ttyp, device)
    return tiles

def readTable(f, size1, size2, w=2):
    return [[rint(f, w) for j in range(size2)]
                        for i in range(size1)]

def readOneFile(f, tileType, device):
    tmap = {"height": rint(f, 4),
            "width": rint(f, 4)}
    tables = rint(f, 4)
    print("height: ", tmap["height"], "width: ", tmap["width"], "tables:", tables)

    #v1 = 0x1b8
    #v2 = 3
    #if (tileType < 0x400):
    #    if ((0x1b7 < tileType) or (tileType < 0)):
    #        print("Error: readOneFile 1")
    #else:
    #    if (2 < tileType + -0x400):
    #        print("Error: readOneFile 2")

    #    v2 = tileType + -0x400
    #    tileType = v1

    #v1 = tileType

    is5Series = device.lower().startswith("gw5a")

    for i in range(tables):
        typ = rint(f, 4)
        size = rint(f, 4)
        print(hex(f.tell()), " Table type", typ, "/", hex(typ), "of size", size)
        if typ == 61:
            size2 = rint(f, 4)
            typn = "grid"
            t = readTable(f, size, size2, 4)
        elif typ == 1:
            # Check if the device is 5 series as tile type 1 needs to be read differently
            typn = "fuse"
            if is5Series:
                t = readTable(f, size, 512, 2)
            else:
                t = readTable(f, size, 150, 2)
        elif typ in {0x02, 0x26, 0x30, 0x5a, 0x5b}:
            typn = "wire"
            if not is5Series: t = readTable(f, size, 8, 2)
            else: t = readTable(f, size, 9, 2)
        elif typ == 0x03:
            typn = "wiresearch"
            t = readTable(f, size, 3, 2)
        elif typ == 0x04:
            typn = "const"
            t = readTable(f, size, 1, 2)
        elif typ in {0x05, 0x11, 0x14, 0x15, 0x16, 0x19, 0x1a, 0x1b,
                     0x1c, 0x1d, 0x1e, 0x1f, 0x20, 0x21, 0x22, 0x23,
                     0x24, 0x32, 0x33, 0x38, 0x3c, 0x40, 0x42, 0x44,
                     0x47, 0x49, 0x4b, 0x4d, 0x4f, 0x50, 0x52, 0x54,
                     0x56, 0x58, 0x59, 0x5d, 0x5e, 0x5f, 0x60, 0x61,
                     0x62, 0x63, 0x64, 0x65, 0x66, 0x67, 0x68, 0x69,
                     0x6a, 0x6b, 0x6c, 0x6d, 0x6e, 0x6f, 0x70, 0x71,
                     0x72, 0x73, 0x74, 0x75, 0x76, 0x77, 0x78, 0x79,
                     0x7a, 0x7b, 0x7c, 0x7d, 0x7e, 0x7f, 0x80, 0x81,
                     0x82, 0x83, 0x84, 0x85, 0x88, 0x89, 0x8a}:
            typn = "shortval"
            t = readTable(f, size, 14, 2)
        elif typ in {6, 0x45}:
            typn = "alonenode"
            t = readTable(f, size, 15, 2)
        elif typ in {0x07, 0x08, 0x09, 0x0a, 0x0b, 0x0c, 0x0d, 0x0e,
                     0x0f, 0x10, 0x27, 0x31, 0x34, 0x37, 0x39, 0x3b,
                     0x3e, 0x3f, 0x41, 0x46, 0x48, 0x4a, 0x4c, 0x4e,
                     0x51, 0x53, 0x55, 0x57, 0x5c}:
            typn = "logicinfo"
            t = readTable(f, size, 3, 2)
        elif typ in {0x12, 0x13, 0x35, 0x36, 0x3a}:
            typn = "longfuse"
            t = readTable(f, size, 17, 2)
        elif typ in {0x17, 0x18, 0x25, 0x28, 0x29, 0x2a, 0x2b, 0x2c, 0x2d, 0x2e, 0x2f}:
            typn = "longval"
            t = readTable(f, size, 28, 2)
        elif typ == 0x43:
            if device in {'GW1N-1', 'GW1NZ-1', 'GW1N-9', 'GW1N-9C', 'GW1N-4', 'GW1NS-4',
                        'GW2A-18', 'GW2A-18C', 'GW5A-25A', 'GW5AS-25A'}:
                typn = "logicinfo"
                t = readTable(f, size, 3, 2)
            else: # GW5A-138B GW5AST-138B GW5AT-138 GW5AT-138B GW5AT-75B
                typn = "signedlogicinfo"
                t = readTable(f, size, 3, 2)
        elif typ in {0x86, 0x87}:
            typn = "signedlogicinfo"
            t = readTable(f, size, 6, 2)
        elif typ == 0x8b:
            typn = "drpfuse"
            t = readTable(f, size, 10, 2)
        else:
            raise ValueError("Unknown type {} at {}".format(hex(typ), hex(f.tell())))
        tmap.setdefault(typn, {})[typ] = t
    return tmap

def render_tile(d, ttyp, device):
    w = d[ttyp]['width']
    h = d[ttyp]['height']


    is5Series = device.lower().startswith("gw5a")

    #if is5Series:
    #    h = h * 2

    highestnum = 0

    tile = bitmatrix.zeros(h, w)#+(255-ttyp)
    for start, table in [(2, 'shortval'), (2, 'wire'), (16, 'longval'),
                         (1, 'longfuse'), (0, 'const')]:
        if table in d[ttyp]:
            for styp, sinfo in d[ttyp][table].items():
                for i in sinfo:
                    for fuse in i[start:]:
                        if fuse > 0:
                            if ttyp > 0x400: num = d['header']['fuse'][1][fuse][ttyp - 0x400]
                            else: num = d['header']['fuse'][1][fuse][ttyp]

                            if num > highestnum:
                                highestnum = num
                            row = num // 100
                            col = num % 100
                            if is5Series:
                                row = num // 200
                                col = num % 200

                            if row > h:
                                print("tile(r):", ttyp, "row:", row, "w:", w,"h:", h, "highest:", highestnum)

                            if col > w:
                                print("tile(w):", ttyp, "col:", col, "w:", w,"h:", h, "highest:", highestnum)

                            if table == "wire":
                                if i[0] > 0:
                                    if tile[row][col] == 0:
                                        tile[row][col] = (styp + i[1]) % 256
                                    else:
                                        tile[row][col] = (tile[row][col] + (styp + i[1]) % 256) // 2
                            elif table == "shortval" and styp == 5:
                                #assert tile[row][col] == 0
                                tile[row][col] = (styp + i[0]) % 256
                            else:
                                tile[row][col] = styp

    #print("tile:", ttyp, "w:", w,"h:", h, "highest:", highestnum)

    return tile


def render_bitmap(d, device):
    tiles = d['header']['grid'][61]
    width = sum([d[i]['width'] for i in tiles[0]])
    height = sum([d[i[0]]['height'] for i in tiles])

    is5Series = device.lower().startswith("gw5a")

    if is5Series:
        height = height * 2

    bitmap = bitmatrix.zeros(height, width)
    y = 0
    for row in tiles:
        x=0
        for typ in row:
            td = d[typ]
            w = td['width']
            h = td['height']
            #bitmap[y:y+h,x:x+w] += render_tile(d, typ)
            #bitmap[y:y+h,x:x+w] = typ
            rtile = render_tile(d, typ, device)
            y0 = y
            for row in rtile:
                x0 = x
                for val in row:
                    bitmap[y0][x0] += val
                    x0 += 1
                y0 += 1
            x+=w
        y+=h

    return bitmap

def display(fname, data):
    from PIL import Image
    import numpy as np
    data = np.array(data, dtype = np.uint16)
    im = Image.frombytes(
            mode='P',
            size=data.shape[::-1],
            data=data)
    random.seed(123)
    im.putpalette(random.choices(range(256), k=3*256))
    if fname:
        im.save(fname)
    return im

def fuse_lookup(d, ttyp, fuse, device):
    is5Series = device.lower().startswith("gw5a")

    w = d[ttyp]['width']
    h = d[ttyp]['height']

    if fuse >= 0:
        num = d['header']['fuse'][1][fuse][ttyp]
        row = num // 100
        col = num % 100
        if is5Series:
            row = num // 200
            col = num % 200

        if row > h:
            print("row too big", ttyp, row, h, col, w, num, h * w)
        if col > w:
            print("col too big", col, w)
        return row, col

def drpfuse_lookup(d, ttyp, fuse, device):
    if fuse >= 0:
        num = d['header']['drpfuse'][139][fuse][ttyp]
        row = num // 200
        col = num % 200
        return row, col

def tile_bitmap(d, bitmap, empty=False):
    tiles = d['header']['grid'][61]
    width = sum([d[i]['width'] for i in tiles[0]])
    height = sum([d[i[0]]['height'] for i in tiles])
    res = {}
    y = 0
    for idx, row in enumerate(tiles):
        x=0
        for jdx, typ in enumerate(row):
            td = d[typ]
            w = td['width']
            h = td['height']
            tile = [row[x:x+w] for row in bitmap[y:y+h]]
            if bitmatrix.any(tile) or empty:
                res[(idx, jdx, typ)] = tile
            x+=w
        y+=h

    return res

def fuse_bitmap(d, bitmap):
    tiles = d['header']['grid'][61]
    width = sum([d[i]['width'] for i in tiles[0]])
    height = sum([d[i[0]]['height'] for i in tiles])
    res = bitmatrix.zeros(height, width)
    y = 0
    for idx, row in enumerate(tiles):
        x=0
        for jdx, typ in enumerate(row):
            td = d[typ]
            w = td['width']
            h = td['height']
            y0 = y
            for row in bitmap[(idx, jdx, typ)]:
                x0 = x
                for val in row:
                    res[y0][x0] = val
                    x0 += 1
                y0 += 1
            x+=w
        y+=h

    return res

def parse_tile(d, ttyp, tile, device):
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
                    coords = {(fuse_lookup(d, ttyp, f, device), pos) for f in row[start:] if f > 0}
                    idx = tuple(abs(attr) for attr in row[:start])
                    items.setdefault(idx, {}).update(coords)

                #print(items)
                for idx, item in items.items():
                    test = [tile[loc[0]][loc[1]] == val
                            for loc, val in item.items()]
                    if all(test):
                        row = idx + tuple(item.keys())
                        res.setdefault(table, {}).setdefault(subtyp, []).append(row)

    return res

def parse_tile_exact(d, ttyp, tile, device, fuse_loc=True):
    w = d[ttyp]['width']
    h = d[ttyp]['height']
    res = {}
    for start, table in [(2, 'shortval'), (2, 'wire'), (16, 'longval'),
                         (1, 'longfuse'), (0, 'const')]:
        if table in d[ttyp]: # skip missing entries
            for subtyp, tablerows in d[ttyp][table].items():
                pos_items, neg_items = {}, {}
                active_rows = []
                for row in tablerows:
                    if row[0] > 0:
                        row_fuses  = [fuse for fuse in row[start:] if fuse >= 0]
                        locs = [fuse_lookup(d,ttyp, fuse, device) for fuse in row_fuses]
                        test = [tile[loc[0]][loc[1]] == 1 for loc in locs]
                        if all(test):
                            full_row = row[:start]
                            full_row.extend(row_fuses)
                            active_rows.append(full_row)

                # report fuse locations
                if (active_rows):
                    exact_cover = exact_table_cover(active_rows, start, table)
                    if fuse_loc:
                        for cover_row in exact_cover:
                            cover_row[start:] = [fuse_lookup(d, ttyp, fuse, device) for fuse in cover_row[start:]]

                    res.setdefault(table, {})[subtyp] = exact_cover
    return res


def exact_table_cover(t_rows, start, table=None):
    try:
        import xcover
    except:
        raise ModuleNotFoundError ("The xcover package needs to be installed to use the exact_cover function.\
                                    \nYou may install it via pip: `pip install xcover`")

    row_fuses = [set ([fuse for fuse in row[start:] if fuse!=-1]) for row in t_rows]
    primary = set()
    for row in row_fuses:
        primary.update(row)
    secondary = set()

    # Enforce that every destination node has a single source
    if table == 'wire':
        for id, row in enumerate(t_rows):
            # Casting the wire_id to a string ensures that it doesn't conflict with fuse_ids
            row_fuses[id].add(str(row[1]))
            secondary.add(str(row[1]))

    g = xcover.covers(row_fuses, primary=primary, secondary=secondary, colored=False)
    if g:
        for r in g:
            #g is an iterator, so this is just a hack to return the first solution.
            #A future commit might introduce a heuristic for determining what solution is most plausible
            #where there are multiple solutions
            return [t_rows[idx] for idx in r]
    else:
        return []

def scan_fuses(d, ttyp, tile, device):
    is5Series = device.lower().startswith("gw5a")

    w = d[ttyp]['width']
    h = d[ttyp]['height']
    fuses = []
    rows, cols = bitmatrix.nonzero(tile)
    for row, col in zip(rows, cols):
        # ripe for optimization
        for fnum, fuse in enumerate(d['header']['fuse'][1]):
            num = fuse[ttyp]
            frow = num // 100
            fcol = num % 100
            #if is5Series:
            #    frow = num // w
            #    fcol = num % w
            #    print("GO FLUFFY")

            if frow == row and fcol == col and fnum > 100:
                fuses.append(fnum)
    return set(fuses)

def scan_tables(d, tiletyp, fuses):
    res = []
    for tname, tables in d[tiletyp].items():
        if tname in {"width", "height"}: continue
        for ttyp, table in tables.items():
            for row in table:
                row_fuses = fuses.intersection(row)
                if row_fuses:
                    print(f"fuses {row_fuses} found in {tname}({ttyp}): {row}")
                    res.append(row)
    return res

def reduce_rows(rows, fuses, start=16, tries=1000):
    rowmap = {frozenset(iv[:iv.index(0)]): frozenset(iv[start:(list(iv)+[-1]).index(-1)]) for iv in rows}
    features = {i for s in rowmap.keys() for i in s}
    for _ in range(tries):
        feat = random.sample(features, 1)[0]
        features.remove(feat)
        rem_fuses = set()
        for k, v in rowmap.items():
            if k & features:
                rem_fuses.update(v)
        if rem_fuses != fuses:
            features.add(feat)
    return features

