import random
from apycula import bitmatrix
from apycula.fse_formats import DEVICE_FORMATS, TABLE_KINDS

# Row width in 16-bit words; fuse and wire widths depend on the device.
ROW_WIDTHS = {"wiresearch": 3, "const": 1, "shortval": 14, "alonenode": 15, "logicinfo": 3,
              "signedlogicinfo": 3, "longfuse": 17, "longval": 28, "drpfuse": 10}

def device_format(device):
    """(fuse row width, wire row width, kind of table 0x43) for a device."""
    if device in DEVICE_FORMATS:
        return DEVICE_FORMATS[device]
    # These GW1N devices are not named in the extracted vendor table.
    if device.startswith("GW1N"):
        return 150, 8, "logicinfo"
    raise ValueError(f"No .fse format known for device {device}")


def read_int(f, w):
    val = int.from_bytes(f.read(w), 'little', signed=True)
    return val

def read_fse(f, device):
    print("check", read_int(f, 4))
    tiles = {}
    ttyp = read_int(f, 4)
    #print(f"tile type:{ttyp}/{hex(ttyp)}")
    tiles['header'] = read_one_file(f, ttyp, device)
    while True:
        ttyp = read_int(f, 4)
        if ttyp == 0x9a1d85: break
        #print(f"tile type:{ttyp}/{hex(ttyp)}")
        tiles[ttyp] = read_one_file(f, ttyp, device)
    return tiles

def read_table(f, size1, size2, w=2):
    return [[read_int(f, w) for j in range(size2)]
                        for i in range(size1)]

def read_one_file(f, tile_type, device):
    tmap = {"height": read_int(f, 4),
            "width": read_int(f, 4)}
    tables = read_int(f, 4)
    #print("height: ", tmap["height"], "width: ", tmap["width"], "tables:", tables)

    fuse_row, wire_row, table_0x43 = device_format(device)
    row_widths = dict(ROW_WIDTHS, fuse=fuse_row, wire=wire_row)

    for i in range(tables):
        typ = read_int(f, 4)
        size = read_int(f, 4)
        #print(hex(f.tell()), " Table type", typ, "/", hex(typ), "of size", size)
        typn = table_0x43 if typ == 0x43 else TABLE_KINDS.get(typ)
        if typn is None:
            raise ValueError("Unknown type {} at {}".format(hex(typ), hex(f.tell())))
        if typn == "grid":
            size2 = read_int(f, 4)
            t = read_table(f, size, size2, 4)
        else:
            t = read_table(f, size, row_widths[typn], 2)
        tmap.setdefault(typn, {})[typ] = t
    return tmap

def render_tile(d, ttyp, device):
    w = d[ttyp]['width']
    h = d[ttyp]['height']


    is_5_series = device.lower().startswith("gw5a")

    #if is_5_series:
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
                            if is_5_series:
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

    is_5_series = device.lower().startswith("gw5a")

    if is_5_series:
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
    is_5_series = device.lower().startswith("gw5a")

    w = d[ttyp]['width']
    h = d[ttyp]['height']

    if fuse >= 0:
        num = d['header']['fuse'][1][fuse][ttyp]
        row = num // 100
        col = num % 100
        if is_5_series:
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
    is_5_series = device.lower().startswith("gw5a")

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
            #if is_5_series:
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
                    #print(f"fuses {row_fuses} found in {tname}({ttyp}): {row}")
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

