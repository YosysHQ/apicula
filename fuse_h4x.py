import sys
import numpy as np
from PIL import Image
import random
import pdb

def rint(f, w):
    val = int.from_bytes(f.read(w), 'little', signed=True)
    return val

def readFse(f):
    print("check", rint(f, 4))
    tiles = {}
    ttyp = rint(f, 4)
    tiles['header'] = readOneFile(f, ttyp)
    while True:
        ttyp = rint(f, 4)
        if ttyp == 0x9a1d85: break
        #print("tile type", ttyp)
        tiles[ttyp] = readOneFile(f, ttyp)
    return tiles

def readTable(f, size1, size2, w=2):
    return [[rint(f, w) for j in range(size2)]
                        for i in range(size1)]

def readOneFile(f, fuselength):
    tmap = {"height": rint(f, 4),
            "width": rint(f, 4)}
    tables = rint(f, 4)
    for i in range(tables):
        typ = rint(f, 4)
        size = rint(f, 4)
        #print("Table type", typ, "of size", size)
        if typ == 61:
            size2 = rint(f, 4)
            typn = "grid"
            t = readTable(f, size, size2, 4)
        elif typ == 1:
            typn = "fuse"
            t = readTable(f, size, fuselength, 2)
        elif typ in {7, 8, 9, 10, 0xb, 0xc, 0xd, 0xe, 0xf, 0x10,
                     0x27, 0x31, 0x34, 0x37, 0x39, 0x3b, 0x3e,
                     0x3f, 0x41, 0x43, 0x46, 0x48, 0x4a, 0x4c}:
            typn = "logicinfo"
            t = readTable(f, size, 3, 2)
        elif typ in {2, 0x26, 0x30}:
            typn = "wire"
            t = readTable(f, size, 8, 2)
        elif typ == 3:
            typn = "wiresearch"
            t = readTable(f, size, 3, 2)
        elif typ in {5, 0x11, 0x14, 0x15, 0x16, 0x19, 0x1a, 0x1b,
                     0x1c, 0x1d, 0x1e, 0x1f, 0x20, 0x21, 0x22, 0x23,
                     0x24, 0x32, 0x33, 0x38, 0x3c, 0x40, 0x42, 0x44,
                     0x47, 0x49, 0x4b, 0x4d}:
            typn = "shortval"
            t = readTable(f, size, 8, 2)
        elif typ in {6, 0x45}:
            typn = "alonenode"
            t = readTable(f, size, 15, 2)
        elif typ in {0x12, 0x13, 0x35, 0x36, 0x3a}:
            typn = "longfuse"
            t = readTable(f, size, 17, 2)
        elif typ in {0x17, 0x18, 0x25, 0x28, 0x29, 0x2a, 0x2b, 0x2c, 0x2d, 0x2e, 0x2f}:
            typn = "longval"
            t = readTable(f, size, 22, 2)
        elif typ == 4:
            typn = "const"
            t = readTable(f, size, 1, 2)
        else:
            raise ValueError("Unknown type at {}".format(hex(f.tell())))
        tmap.setdefault(typn, {})[typ] = t
    return tmap

def render_tile(d, ttyp):
    w = d[ttyp]['width']
    h = d[ttyp]['height']
    tile = np.zeros((h, w), np.uint8)#+(255-ttyp)
    for start, table in [(2, 'shortval'), (2, 'wire'), (16, 'longval'),
                         (1, 'longfuse'), (0, 'const')]:
        if table in d[ttyp]:
            for styp, sinfo in d[ttyp][table].items():
                for i in sinfo:
                    for fuse in i[start:]:
                        if fuse > 0:
                            num = d['header']['fuse'][1][fuse][ttyp]
                            row = num // 100
                            col = num % 100
                            if table == "wire":
                                if i[0] > 0:
                                    if tile[row][col] == 0:
                                        tile[row][col] = (styp + i[1]) % 256
                                    else:
                                        tile[row][col] = (tile[row][col] + (styp + i[1]) % 256) // 2
                            elif table == "shortval" and styp == 5:
                                assert tile[row][col] == 0
                                tile[row][col] = (styp + i[0]) % 256
                            else:
                                tile[row][col] = styp

    return tile


def render_bitmap(d):
    tiles = d['header']['grid'][61]
    width = sum([d[i]['width'] for i in tiles[0]])
    height = sum([d[i[0]]['height'] for i in tiles])
    bitmap = np.zeros((height, width), np.uint8)
    y = 0
    for row in tiles:
        x=0
        for typ in row:
            #if typ==12: pdb.set_trace()
            td = d[typ]
            w = td['width']
            h = td['height']
            #bitmap[y:y+h,x:x+w] += render_tile(d, typ)
            bitmap[y:y+h,x:x+w] = typ
            x+=w
        y+=h

    return bitmap

def display(fname, data):
    im = Image.frombytes(
            mode='P',
            size=data.shape[::-1],
            data=data)
    random.seed(123)
    im.putpalette(random.choices(range(256), k=3*256))
    im.save(fname)

def fuse_lookup(d, ttyp, fuse):
    if fuse >= 0:
        num = d['header']['fuse'][1][fuse][ttyp]
        row = num // 100
        col = num % 100
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
            #if typ==87: pdb.set_trace()
            td = d[typ]
            w = td['width']
            h = td['height']
            tile = bitmap[y:y+h,x:x+w]
            if tile.any() or empty:
                res[(idx, jdx, typ)] = tile
            x+=w
        y+=h

    return res

def fuse_bitmap(d, bitmap):
    tiles = d['header']['grid'][61]
    width = sum([d[i]['width'] for i in tiles[0]])
    height = sum([d[i[0]]['height'] for i in tiles])
    res = np.zeros((height, width), dtype=np.uint8)
    y = 0
    for idx, row in enumerate(tiles):
        x=0
        for jdx, typ in enumerate(row):
            td = d[typ]
            w = td['width']
            h = td['height']
            res[y:y+h,x:x+w] = bitmap[(idx, jdx, typ)]
            x+=w
        y+=h

    return res

if __name__ == "__main__":
    with open(sys.argv[1], 'rb') as f:
        d = readFse(f)
    bm = render_bitmap(d)
    display("fuse.png", bm)
    t = render_tile(d, 12)
    display("tile.png", t)

