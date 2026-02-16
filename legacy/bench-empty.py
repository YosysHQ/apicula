import re
import os
import sys
import lzma
import tempfile
import subprocess
import importlib.resources
from collections import deque, Counter, namedtuple
from itertools import chain, count, zip_longest
from functools import reduce
from random import shuffle, seed
from warnings import warn
from math import factorial
from multiprocessing.dummy import Pool
import pickle
import json
from apycula.wirenames import wirenames, clknames
from PIL import Image, ImageDraw
from shutil import copytree

from apycula import bitmatrix
from apycula import attrids
from apycula import codegen
from apycula import bslib
from apycula import pindef
from apycula import fse_parser
from apycula import gowin_pack
import tiled_fuzzer
from apycula import codegen
from apycula import bslib
#TODO proper API
#from apycula import dat19_h4x
from apycula import tm_parser
from apycula import chipdb

gowinhome = os.getenv("GOWINHOME")
if not gowinhome:
    raise Exception("GOWINHOME not set")

# device = os.getenv("DEVICE")
device = sys.argv[1]

params = {
    "GW1NS-2": {
        "package": "LQFP144",
        "device": "GW1NS-2C",
        "partnumber": "GW1NS-UX2CLQ144C5/I4",
    },
    "GW1NS-4": {
        "package": "QFN48",
        "device": "GW1NSR-4C",
        "partnumber": "GW1NSR-LV4CQN48PC7/I6",
    },
    "GW1N-9": {
        "package": "PBGA256",
        "device": "GW1N-9",
        "partnumber": "GW1N-LV9PG256C6/I5",
    },
    "GW1N-9C": {
        "package": "UBGA332",
        "device": "GW1N-9C",
        "partnumber": "GW1N-LV9UG332C6/I5",
    },
    "GW1N-4": {
        "package": "PBGA256",
        "device": "GW1N-4",
        "partnumber": "GW1N-LV4PG256C6/I5",
    },
    "GW1N-1": {
        "package": "LQFP144",
        "device": "GW1N-1",
        "partnumber": "GW1N-LV1LQ144C6/I5",
    },
    "GW1NZ-1": {
        "package": "QFN48",
        "device": "GW1NZ-1",
        "partnumber": "GW1NZ-LV1QN48C6/I5",
    },
    "GW2A-18": {
        "package": "PBGA256",
        "device": "GW2A-18",
        "partnumber": "GW2A-LV18PG256C8/I7",
    },
    "GW2A-18C": {
        "package": "PBGA256S",
        "device": "GW2A-18C",
        "partnumber": "GW2A-LV18PG256SC8/I7", #"GW2AR-LV18PG256SC8/I7", "GW2AR-LV18QN88C8/I7"
    },
    "GW5A-25A": {
        "package": "MBGA121N",
        "device": "GW5A-25A",
        "partnumber": "GW5A-LV25MG121NC1/I0",
    },
    "GW1N-1P5C": {
        "package": "QFN48XF",
        "device": "GW1N-1P5C",
        "partnumber": "GW1N-UV1P5QN48XFC7/I6",
    },
    "GW5AST-138C": {
        "package": "PBGA484A",
        "device": "GW5AST-138C",
        "partnumber": "GW5AST-LV138PG484AC1/I0",
    },
}[device]

# collect all routing bits of the tile
_route_mem = {}
def route_bits(db, row, col):
    mem = _route_mem.get((row, col), None)
    if mem != None:
        return mem

    bits = set()
    for w in db[row, col].pips.values():
        for v in w.values():
            bits.update(v)
    for w in db[row, col].clock_pips.values():
        for v in w.values():
            bits.update(v)
    _route_mem.setdefault((row, col), bits)
    return bits

def get_fuse_num(ttyp, y, x):
    # bits YYXX
    if device.lower().startswith('gw5'):
        bits = y * 200 + x
    else:
        bits = y * 100 + x

    for i, fs in enumerate(fse['header']['fuse'][1]):
        if fs[ttyp] == bits:
            return i
    return -1

def print_longval(ttyp, table, contains = None, must_all = False):
    "ttyp, num, contains = 0"
    for row in fse[ttyp]['longval'][table]:
        if contains == None:
            print(row)
        else:
            are_all = must_all
            for val in contains:
                if val in row[16:]:
                    are_all = True
                    if not must_all:
                        break
                else:
                    if must_all:
                        are_all = False
                        break
            if are_all:
                print(row)

def print_longval_key(ttyp, table, key, ignore_key_elem = 0, zeros = True):
    if zeros:
        sorted_key = (sorted(key) + [0] * 16)[:16 - ignore_key_elem]
        end = 16
    else:
        sorted_key = sorted(key)
        end = ignore_key_elem + len(sorted_key)
    for rec in fse[ttyp]['longval'][table]:
        k = rec[ignore_key_elem:end]
        if k == sorted_key:
            print(rec)

def print_alonenode(ttyp, contains = 0):
    "ttyp, contains = 0"
    for row in fse[ttyp]['alonenode'][69]:
        if contains == 0 or contains in row:
            print(row)

def get_wires_to(fse, ttyp, wiren, table = 2):
    for wr in [wire for wire in fse[ttyp]['wire'][table] if wire[1] == wiren]:
        print(wr)

def get_wires_from(fse, ttyp, wiren, table = 2):
    for wr in [wire for wire in fse[ttyp]['wire'][table] if wire[0] == wiren]:
        print(wr)

def get_grid_rc(fse, row, col):
    grow = 0
    h = fse[fse['header']['grid'][61][row][col]]['height']
    while row:
        grow += h
        h = fse[fse['header']['grid'][61][row][col]]['height']
        row -= 1
    gcol = 0
    w = fse[fse['header']['grid'][61][row][col]]['width']
    while col:
        gcol += w
        w = fse[fse['header']['grid'][61][row][col]]['width']
        col -= 1
    return (grow, gcol, h, w)

def pict(bm, name):
    im = bslib.display(None, bm)
    im_scaled = im.resize((im.width * 10, im.height * 10), Image.NEAREST)
    im_scaled.save(f"/home/rabbit/tmp/{name}")

def get_bits(bm):
    bits = set()
    rows, cols =bitmatrix.shape(bm)
    for row in range(rows):
        for col in range(cols):
            if bm[row][col] == 1:
                bits.update({(row, col)})
    return bits

def deep_bank_cmp(bel, ref_bel):
    keys = set(bel.bank_flags.keys())
    ref_keys = set(ref_bel.bank_flags.keys())
    if keys != ref_keys:
        print(f' keys diff:{keys ^ ref_keys}')
        return
    for key, val in bel.bank_flags.items():
        if val != ref_bel.bank_flags[key]:
            print(f' val diff: {key}:{val} vs {ref_bel.bank_flags[key]}')

def deep_io_cmp(bel, ref_bel, irow, icol, ibel):
    iostd_keys = set(bel.iob_flags.keys())
    ref_iostd_keys = set(ref_bel.iob_flags.keys())
    if iostd_keys != ref_iostd_keys:
        print(f' iostd diff:{iostd_keys ^ ref_iostd_keys}')
    for iostd_key, typ_rec in bel.iob_flags.items():
        ref_typ_rec = ref_bel.iob_flags[iostd_key]
        if set(typ_rec.keys()) != set(ref_typ_rec.keys()):
            print(f' type diff:{iostd_key} {set(typ_rec.keys()) ^ set(ref_typ_rec.keys())}')
            continue
        if typ_rec == ref_typ_rec:
            continue
        print(f' {iostd_key}')
        for typ_key, flag_rec in typ_rec.items():
            ref_flag_rec = ref_typ_rec[typ_key]
            if set(flag_rec.flags.keys()) != set(ref_flag_rec.flags.keys()):
                print(f'  flag diff:{iostd_key} {typ_key} {set(flag_rec.flags.keys()) ^ set(ref_flag_rec.flags.keys())}')
                continue
            if flag_rec == ref_flag_rec:
                continue;
            print(f'  {typ_key}')
            if flag_rec.encode_bits != ref_flag_rec.encode_bits:
                print(f'  encode diff:({irow}, {icol})[{ibel}] {iostd_key} {typ_key} {flag_rec.encode_bits ^ ref_flag_rec.encode_bits}')
            for flag_key, opt_rec in flag_rec.flags.items():
                ref_opt_rec = ref_flag_rec.flags[flag_key]
                if set(opt_rec.options.keys()) != set(ref_opt_rec.options.keys()):
                    print(f'   opt diff:{iostd_key} {typ_key} {flag_key} {set(opt_rec.options.keys()) ^ set(ref_opt_rec.options.keys())}')
                    continue
                if opt_rec == ref_opt_rec:
                    continue
                print(f'   {flag_key}')
                for opt_key, bits in opt_rec.options.items():
                    ref_bits = ref_opt_rec.options[opt_key]
                    if bits != ref_bits:
                        print(f'    bits diff:{iostd_key} {typ_key} {flag_key} {opt_key} {bits} vs {ref_bits}')


def tbrl2rc(fse, side, num):
    if side == 'T':
        row = 0
        col = int(num) - 1
    elif side == 'B':
        row = len(fse['header']['grid'][61])-1
        col = int(num) - 1
    elif side == 'L':
        row = int(num) - 1
        col = 0
    elif side == 'R':
        row = int(num) - 1
        col = len(fse['header']['grid'][61][0])-1
    return (row, col)

def attrs2log(attrs, pos):
    for name, p in attrs[0].items():
        if p == pos:
            return f'{pos}:{attrs[1][name]}:{name}'

def st(tiletyp, fuses):
    res = []
    sorted_res = []
    for tname, tables in fse[tiletyp].items():
        if tname in {"width", "height"}: continue
        for ttyp, table in tables.items():
            for row in table:
                row_fuses = fuses.intersection(row)
                if row_fuses:
                    #print(f"fuses {row_fuses} found in {tname}({ttyp}): {row}")
                    sorted_res.append((row_fuses, tname, ttyp, row))
                    res.append(row)
    for rd in sorted(sorted_res, key = lambda x: ord(x[1][0]) * 100000 + x[2] * 100 + len(x[0])):
        print(f"fuses {sorted(rd[0])} found in {rd[1]}({rd[2]}): {rd[3]}")
    return

def find_node(name):
    for node_key, node_rec in db.nodes.items():
        for node in node_rec[1]:
            if node[2] == name:
                print('*', node_key, node_rec)

def find_nodes_row(row):
    for node_key, node_rec in db.nodes.items():
        for node in node_rec[1]:
            if node[0] == row:
                print('*', node_key, node_rec)

def find_nodes_row(row, name):
    for node_key, node_rec in db.nodes.items():
        for node in node_rec[1]:
            if node[0] == row and node[2] == name:
                print(node)

if __name__ == "__main__":
    with open(f"{gowinhome}/IDE/share/device/{params['device']}/{params['device']}.fse", 'rb') as f:
        fse = fse_parser.read_fse(f, device)

    with open(f"{gowinhome}/IDE/share/device/{params['device']}/{params['device']}.tm", 'rb') as f:
        tm = tm_parser.read_tm(f, device)

    with open(f"/home/rabbit/src/apicula/{device}-dat.pickle", "rb") as f:
        dat = pickle.load(f)

    db = chipdb.load_chipdb(f"/home/rabbit/src/apicula/apycula/{device}.msgpack.xz")

    if len(sys.argv) > 2:
        img = bslib.read_bitstream(f'{sys.argv[2]}')[0]
        bm = chipdb.tile_bitmap(db, img, True)
    else:
        import ipdb; ipdb.set_trace()

    #for ri, rr in dat['CiuBdConnection'].items():
    #    print(ri, rr)

    """
    seen = set()
    for row in fse['header']['grid'][61]:
        for ttyp in row:
            if ttyp not in seen:
                seen.add(ttyp)
                src = set()
                for rrow in fse[ttyp]['wire'][2]:
                    if rrow[0] in {289, 290}:
                        src.add(rrow[0])
                if src:
                    print(ttyp, src)
    """

    row3 = db.rows - 1
    col3 = db.cols - 1
    row3 = 0
    col3 = 0
    import ipdb; ipdb.set_trace()
    # cmp images
    if len(sys.argv) > 3:
        fuses = set()
        sec_img = bslib.read_bitstream(f'{sys.argv[3]}')[0]
        sec_bm = chipdb.tile_bitmap(db, sec_img)
        diff = bitmatrix.xor(img, sec_img)
        diff_tiles = fse_parser.tile_bitmap(fse, diff)
        sec_tiles = fse_parser.tile_bitmap(fse, sec_img)
        print(diff_tiles.keys())
        ttyp = fse['header']['grid'][61][row3][col3]
        # first tiles wo same
        first_tiles = set()
        for ft in fse_parser.tile_bitmap(fse, img):
            if ft in diff_tiles:
                first_tiles.update({ft})
        print('first tiles:', sorted(first_tiles))
        #print(fse_parser.parse_tile(fse, 49, fse_parser.tile_bitmap(fse, img)[(19, 37, 49)]))
        #print(fse_parser.parse_tile(fse, 49, fse_parser.tile_bitmap(fse, sec_img)[(19, 37, 49)]))
        print('first bits:', sorted(get_bits(fse_parser.tile_bitmap(fse, img, True)[(row3, col3, ttyp)])))
        fuses = set()
        for df in get_bits(fse_parser.tile_bitmap(fse, img, True)[(row3, col3, ttyp)]):
            fuses.update({get_fuse_num(ttyp, df[0], df[1])})
        print('first fuses:', sorted(fuses))
        if (row3, col3, ttyp) in fse_parser.tile_bitmap(fse, sec_img).keys():
            print('second bits:', sorted(get_bits(fse_parser.tile_bitmap(fse, sec_img)[(row3, col3, ttyp)])))
        rbits = route_bits(db, row3, col3)
        fuses = set()
        func_fuses = set()
        for df in get_bits(diff_tiles[(row3, col3, ttyp)]):
            fuses.update({get_fuse_num(ttyp, df[0], df[1])})
            if df not in rbits:
                func_fuses.update({get_fuse_num(ttyp, df[0], df[1])})
        print("=====================================")
        print("all diff:", sorted(fuses))
        print("func diff:", sorted(func_fuses))
        print("=====================================")

    row = row3
    col = col3
    ttyp = fse['header']['grid'][61][row][col]
    consts = set()
    if 'const' in fse[ttyp].keys():
        consts = {item for sublist in fse[ttyp]['const'][4] for item in sublist}
    print("consts:", consts)

    rbits = route_bits(db, row, col)
    r, c = bitmatrix.nonzero(bm[(row, col)])
    tile = set(zip(r, c))
    bits = tile# - rbits
    fuses = set()
    for df in sorted(bits):
        fs = get_fuse_num(ttyp, df[0], df[1])
        if fs not in consts:
            fuses.update({fs})
    print("all first bits:")
    #print(sorted(bits))
    print(sorted(fuses))
    all_fuses = fuses.copy()
    fuses = set()
    for df in sorted(bits):
        if df in rbits:
            fuses.update({get_fuse_num(ttyp, df[0], df[1])})
    print('route:', sorted(fuses))
    print('func:', sorted(all_fuses - fuses))


    if (row3, col3, ttyp) in fse_parser.tile_bitmap(fse, sec_img).keys():
        rbits = route_bits(db, row, col)
        r, c = bitmatrix.nonzero(sec_bm[(row, col)])
        tile = set(zip(r, c))
        bits = tile# - rbits
        fuses = set()
        for df in sorted(bits):
            fs = get_fuse_num(ttyp, df[0], df[1])
            if fs not in consts:
                fuses.update({fs})
        print("all second bits:")
        #print(sorted(bits))
        print(sorted(fuses))
        all_fuses = fuses.copy()
        fuses = set()
        for df in sorted(bits):
            if df in rbits:
                fuses.update({get_fuse_num(ttyp, df[0], df[1])})
        print('route:', sorted(fuses))
        print('func:', sorted(all_fuses - fuses))
    print(row, col, ttyp)

    import ipdb; ipdb.set_trace()
