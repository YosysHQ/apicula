import sys
import re
import json
import bslib
import fuse_h4x as fse
from wirenames import wirenumbers


cmd_hdr = [
    bytearray(b'\xb5\xb8'), # checksum
    bytearray(b'\xff\xff'), # NOP
    bytearray(b'\xa5\xc3'), # preamble
    bytearray(b'\x06\x00\x00\x00\x11\x00\x58\x1b'), # ID CODE check
    bytearray(b'\x10\x00\x00\x00\x00\x00\x00\x00'), # config register
    bytearray(b'\x51\x00\xff\xff\xff\xff\xff\xff'), # unknown
    bytearray(b'\x0b\x00\x00\x00'), # unknown
    bytearray(b'\xd2\x00\xff\xff\x00\xff\xf0\x00'), # SPI flash address
    bytearray(b'\x12\x00\x00\x00'), # init address?
    bytearray(b'\x3b\x80\x02\xc8'), # number of frames
]

cmd_ftr = [
    bytearray(b'\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\x34\x73'),
    bytearray(b'\x0a\x00\x00\x00\x00\x00\xb5\xb8'), # usercode
    bytearray(b'\xff\xff\xff\xff\xff\xff\xff\xff'),
    bytearray(b'\x08\x00\x00\x00'), # program done?
    bytearray(b'\xff\xff\xff\xff\xff\xff\xff\xff'),
    bytearray(b'\xff\xff')
]

def get_bels(data):
    belre = re.compile(r"R(\d+)C(\d+)_(?:SLICE|IOB)(\d)")
    for cell in data['modules']['top']['cells'].values():
        bel = cell['attributes']['NEXTPNR_BEL']
        row, col, num = belre.match(bel).groups() 
        yield (cell['type'], int(row), int(col), int(num), cell['parameters'])

def get_pips(data):
    pipre = re.compile(r"R(\d+)C(\d+)_(\w+)_(\w+);")
    for net in data['modules']['top']['netnames'].values():
        routing = net['attributes']['ROUTING']
        pips = pipre.findall(routing)
        for row, col, src, dest in pips:
            yield int(row), int(col), wirenumbers[src], wirenumbers[dest]

def infovaluemap(infovalue, start=2):
    return {tuple(iv[:start]):iv[start:] for iv in infovalue}

def place(fuse, tilemap, bels):
    for typ, row, col, num, attr in bels:
        ttyp = fuse['header']['grid'][61][row-1][col-1]
        tiledata = fuse[ttyp]
        tile = tilemap[(row-1, col-1, ttyp)]
        if typ == "GENERIC_SLICE":
            lutfuses = tiledata['shortval'][5]
            lutmap = infovaluemap(lutfuses)
            init = str(attr['INIT'])
            init = init*(16//len(init))
            for bitnum, lutbit in enumerate(init):
                if lutbit == '0':
                    fuses = lutmap[(num, bitnum)]
                    for f in fuses:
                        if f < 0: continue
                        row, col = fse.fuse_lookup(fuse, ttyp, f)
                        tile[row][col] = 1

            #if attr["FF_USED"]: # Maybe it *always* needs the DFF
            if True:
                table = 25 + num//2
                lutfuses = tiledata['shortval'][table]
                dffmap = infovaluemap(lutfuses)
                for feat in [-7, 20, 21]:
                    f = dffmap[(feat, 0)][0]
                    row, col = fse.fuse_lookup(fuse, ttyp, f)
                    tile[row][col] = 1
        elif typ == "GENERIC_IOB":
            assert sum(attr.values()) <= 1, "Complex IOB unsuported"
            table = 23 + num
            lutfuses = tiledata['longval'][table]
            iobmap = infovaluemap(lutfuses, 16)
            if attr["INPUT_USED"]:
                feats = [(48,)+(0,)*15, # logic type?
                         (-62, 12, 39, 48, 64)+(0,)*11]
            elif attr["OUTPUT_USED"]:
                feats = [(48,)+(0,)*15,
                         (26,)+(0,)*15,
                         (63,)+(0,)*15,
                         (3, 34, 39, 48)+(0,)*12,
                         (12, 32, 39, 48)+(0,)*12,
                         (12, 34, 39, 48)+(0,)*12]
            else:
                raise ValueError("IOB has no in or output")
            for feat in feats:
                fuses = iobmap[feat]
                for f in fuses:
                    if f < 0: break
                    row, col = fse.fuse_lookup(fuse, ttyp, f)
                    tile[row][col] = 1




if __name__ == '__main__':
    with open(sys.argv[1], 'rb') as f:
        fuse = fse.readFse(f)
    with open(sys.argv[2]) as f:
        pnr = json.load(f)
    empty = bslib.read_bitstream('empty.fs')
    tilemap = fse.tile_bitmap(fuse, empty, empty=True)
    bels = get_bels(pnr)
    place(fuse, tilemap, bels)
    res = fse.fuse_bitmap(fuse, tilemap)
    fse.display('pack.png', res)
    bslib.write_bitstream('pack.fs', res, cmd_hdr, cmd_ftr)
