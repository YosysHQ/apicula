import sys
import os
import re
import pickle
import json
import chipdb
import bslib
from wirenames import wirenames, wirenumbers

device = os.getenv("DEVICE")
if not device:
    raise Exception("DEVICE not set")

def get_bels(data):
    belre = re.compile(r"R(\d+)C(\d+)_(?:SLICE|IOB)(\w)")
    for cell in data['modules']['top']['cells'].values():
        bel = cell['attributes']['NEXTPNR_BEL']
        row, col, num = belre.match(bel).groups() 
        yield (cell['type'], int(row), int(col), num, cell['parameters'])

def get_pips(data):
    pipre = re.compile(r"R(\d+)C(\d+)_(\w+)_R(\d+)C(\d+)_(\w+);")
    for net in data['modules']['top']['netnames'].values():
        routing = net['attributes']['ROUTING']
        pips = pipre.findall(routing)
        for src_row, src_col, src, dest_row, dest_col, dest in pips:
            row = int(dest_row)
            col = int(dest_col)
            srow = int(src_row)
            scol = int(src_col)
            dest = chipdb.Wire(dest)
            src = chipdb.Wire(src, (srow-row, scol-col))
            yield int(dest_row), int(dest_col), src, dest

def infovaluemap(infovalue, start=2):
    return {tuple(iv[:start]):iv[start:] for iv in infovalue}

def place(db, tilemap, bels):
    for typ, row, col, num, attr in bels:
        tiledata = db.grid[row-1][col-1]
        tile = tilemap[(row-1, col-1)]
        if typ == "GENERIC_SLICE":
            lutmap = tiledata.bels[f'LUT{num}'].flags
            init = str(attr['INIT'])
            init = init*(16//len(init))
            for bitnum, lutbit in enumerate(init[::-1]):
                if lutbit == '0':
                    fuses = lutmap[bitnum]
                    for row, col in fuses:
                        tile[row][col] = 1

            #if attr["FF_USED"]: # Maybe it *always* needs the DFF
            if True:
                dffbits = tiledata.bels[f'DFF{num}'].modes['DFF']
                for row, col in dffbits:
                    tile[row][col] = 1

        elif typ == "GENERIC_IOB":
            assert sum(attr.values()) <= 1, "Complex IOB unsuported"
            iob = tiledata.bels[f'IOB{num}']
            if attr["INPUT_USED"]:
                bits = iob.modes['IBUF'] | iob.flags.get('IBUFC', set())
            elif attr["OUTPUT_USED"]:
                bits = iob.modes['OBUF'] | iob.flags.get('OBUFC', set())
            else:
                raise ValueError("IOB has no in or output")
            for row, col in bits:
                tile[row][col] = 1

            #bank enable
            if row == 1: # top bank
                bank = 0
                brow = 0
                bcol = 0
            elif row == db.rows: # bottom bank
                bank = 2
                brow = db.rows-1
                bcol = db.cols-1
            elif col == 1: # left bank
                bank = 3
                brow = db.rows-1
                bcol = 0
            elif col == db.cols: # right bank
                bank = 1
                brow = 0
                bcol = db.cols-1
            tiledata = db.grid[brow][bcol]
            tile = tilemap[(brow, bcol)]
            bits = tiledata.bels['BANK'].modes['DEFAULT']
            for row, col in bits:
                tile[row][col] = 1


def route(db, tilemap, pips):
    for row, col, src, dest in pips:
        tiledata = db.grid[row-1][col-1]
        tile = tilemap[(row-1, col-1)]

        try:
            bits = tiledata.pips[dest][src]
        except KeyError:
            print(src, dest, "not found in tile", row, col)
            continue
        for row, col in bits:
            tile[row][col] = 1

if __name__ == '__main__':
    with open(f"{device}.pickle", 'rb') as f:
        db = pickle.load(f)
    with open(sys.argv[1]) as f:
        pnr = json.load(f)
    tilemap = chipdb.tile_bitmap(db, db.template, empty=True)
    bels = get_bels(pnr)
    place(db, tilemap, bels)
    pips = get_pips(pnr)
    route(db, tilemap, pips)
    res = chipdb.fuse_bitmap(db, tilemap)
    bslib.display('pack.png', res)
    bslib.write_bitstream('pack.fs', res, db.cmd_hdr, db.cmd_ftr)
