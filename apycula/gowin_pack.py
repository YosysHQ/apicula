import sys
import os
import re
import pickle
import numpy as np
import json
import argparse
import importlib.resources
from apycula import chipdb
from apycula import bslib
from apycula.wirenames import wirenames, wirenumbers

def get_bels(data):
    belre = re.compile(r"R(\d+)C(\d+)_(?:SLICE|IOB)(\w)")
    for cell in data['modules']['top']['cells'].values():
        bel = cell['attributes']['NEXTPNR_BEL']
        row, col, num = belre.match(bel).groups() 
        yield (cell['type'], int(row), int(col), num, cell['parameters'])

def get_pips(data):
    pipre = re.compile(r"R(\d+)C(\d+)_([^_]+)_([^_]+)")
    for net in data['modules']['top']['netnames'].values():
        routing = net['attributes']['ROUTING']
        pips = routing.split(';')[1::3]
        for pip in pips:
            res = pipre.fullmatch(pip) # ignore alias
            if res:
                row, col, src, dest = res.groups()
                yield int(row), int(col), src, dest
            elif pip:
                print("Invalid pip:", pip)

def infovaluemap(infovalue, start=2):
    return {tuple(iv[:start]):iv[start:] for iv in infovalue}

def place(db, tilemap, bels):
    for typ, row, col, num, attr in bels:
        tiledata = db.grid[row-1][col-1]
        tile = tilemap[(row-1, col-1)]
        if typ == "SLICE":
            lutmap = tiledata.bels[f'LUT{num}'].flags
            init = str(attr['INIT'])
            init = init*(16//len(init))
            for bitnum, lutbit in enumerate(init[::-1]):
                if lutbit == '0':
                    fuses = lutmap[bitnum]
                    for row, col in fuses:
                        tile[row][col] = 1

            if int(num) < 6:
                mode = str(attr['FF_TYPE']).strip('E')
                dffbits = tiledata.bels[f'DFF{num}'].modes[mode]
                for row, col in dffbits:
                    tile[row][col] = 1

        elif typ == "IOB":
            assert sum([int(v, 2) for v in attr.values()]) <= 1, "Complex IOB unsuported"
            iob = tiledata.bels[f'IOB{num}']
            if int(attr["INPUT_USED"], 2):
                bits = iob.modes['IBUF'] | iob.flags.get('IBUFC', set())
            elif int(attr["OUTPUT_USED"], 2):
                bits = iob.modes['OBUF'] | iob.flags.get('OBUFC', set())
            else:
                raise ValueError("IOB has no in or output")
            for r, c in bits:
                tile[r][c] = 1

            #bank enable
            if row == 1: # top bank
                brow = 0
                bcol = 0
            elif row == db.rows: # bottom bank
                brow = db.rows-1
                bcol = db.cols-1
            elif col == 1: # left bank
                brow = db.rows-1
                bcol = 0
            elif col == db.cols: # right bank
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
            if dest in tiledata.clock_pips:
                bits = tiledata.clock_pips[dest][src]
            else:
                bits = tiledata.pips[dest][src]
        except KeyError:
            print(src, dest, "not found in tile", row, col)
            breakpoint()
            continue
        for row, col in bits:
            tile[row][col] = 1

def header_footer(db, bs, compress):
    """
    Generate fs header and footer
    Currently limited to checksum with
    CRC_check and security_bit_enable set
    """
    bs = np.fliplr(bs)
    bs=np.packbits(bs)
    # configuration data checksum is computed on all
    # data in 16bit format
    bb = np.array(bs)

    res = int(bb[0::2].sum() * pow(2,8) + bb[1::2].sum())
    checksum = res & 0xffff
    db.cmd_hdr[0] = bytearray.fromhex(f"{checksum:04x}")

    if compress:
        # update line 0x10 with compress enable bit
        # rest (keys) is done in bslib.write_bitstream
        hdr10 = int.from_bytes(db.cmd_hdr[4], 'big') | (1 << 13)
        db.cmd_hdr[4] = bytearray.fromhex(f"{hdr10:016x}")

    # same task for line 2 in footer
    db.cmd_ftr[1] = bytearray.fromhex(f"{0x0A << 56 | checksum:016x}")

def main():
    parser = argparse.ArgumentParser(description='Unpack Gowin bitstream')
    parser.add_argument('netlist')
    parser.add_argument('-d', '--device', required=True)
    parser.add_argument('-o', '--output', default='pack.fs')
    parser.add_argument('-c', '--compress', default=False, action='store_true')
    parser.add_argument('--png')

    args = parser.parse_args()

    device = args.device
    # For tool integration it is allowed to pass a full part number
    m = re.match("GW1N([A-Z]*)-(LV|UV)([0-9])([A-Z]{2}[0-9]+)(C[0-9]/I[0-9])", device)
    if m:
        luts = m.group(3)
        device = f"GW1N-{luts}"

    with importlib.resources.open_binary("apycula", f"{device}.pickle") as f:
        db = pickle.load(f)
    with open(args.netlist) as f:
        pnr = json.load(f)
    tilemap = chipdb.tile_bitmap(db, db.template, empty=True)
    bels = get_bels(pnr)
    place(db, tilemap, bels)
    pips = get_pips(pnr)
    route(db, tilemap, pips)

    res = chipdb.fuse_bitmap(db, tilemap)
    header_footer(db, res, args.compress)
    if args.png:
        bslib.display(args.png, res)
    bslib.write_bitstream(args.output, res, db.cmd_hdr, db.cmd_ftr, args.compress)


if __name__ == '__main__':
    main()
