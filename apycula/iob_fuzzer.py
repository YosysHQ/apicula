import re
import os
import sys
import tempfile
import subprocess
from collections import deque, Counter, namedtuple
from itertools import chain, count, zip_longest
from functools import reduce, lru_cache
from random import shuffle, seed
from warnings import warn
from math import factorial
import numpy as np
from multiprocessing.dummy import Pool
import pickle
import json

from apycula import codegen
from apycula import bslib
from apycula import pindef
from apycula import fuse_h4x
#TODO proper API
#from apycula import dat19_h4x
from apycula import tm_h4x
from apycula import chipdb
from apycula import tiled_fuzzer

def dff(mod, cst, qwire, dwire, clock):
    "make a dff"
    name = tiled_fuzzer.make_name("DUMMY", "DFF")
    dff = codegen.Primitive("DFF", name)
    dff.portmap['CLK'] = clock
    dff.portmap['Q'] = qwire
    if dwire == None:
        dwire = name + "_D"
    dff.portmap['D'] = dwire
    mod.wires.update(dff.portmap.values())
    mod.primitives[name] = dff

Fuzzer = namedtuple('Fuzzer', [
    'ttyp',
    'mod',
    'cst',      # constraints
    'cfg',      # device config
    'iostd',    # io standard
    ])

iobmap = {
    "IBUF": {"wires": ["O"], "inputs": ["I"]},
    "OBUF": {"wires": ["I"], "outputs": ["O"]},
    "TBUF": {"wires": ["I", "OEN"], "outputs": ["O"]},
    "IOBUF": {"wires": ["I", "O", "OEN"], "inouts": ["IO"]},
}

iostandards = ["", "LVTTL33", "LVCMOS33", "LVCMOS25", "LVCMOS18", "LVCMOS15", "LVCMOS12",
               "SSTL25_I", "SSTL25_II", "SSTL33_I", "SSTL33_II", "SSTL18_I", "SSTL18_II",
               "SSTL15", "HSTL18_I", "HSTL18_II", "HSTL15_I", "PCI33"]

AttrValues = namedtuple('ModeAttr', [
    'bank_dependent',   # attribute dependent of bank flags/standards
    'allowed_modes',    # allowed modes for the attribute
    'values'            # values of the attribute
    ])

iobattrs = {
 # no attributes, default mode
 "NULL"       : AttrValues(False, ["IBUF", "OBUF", "IOBUF", "TBUF"], {"": [""]}),
 #
 "HYSTERESIS" : AttrValues(False, ["IBUF", "IOBUF"],
     { "": ["NONE", "H2L", "L2H", "HIGH"]}),
 "PULL_MODE"  : AttrValues(False, ["IBUF", "OBUF", "IOBUF", "TBUF"],
     { "": ["NONE", "UP", "DOWN", "KEEPER"]}),
 "SLEW_RATE"  : AttrValues(False, ["OBUF", "IOBUF", "TBUF"],
     { "": ["SLOW", "FAST"]}),
 "OPEN_DRAIN" : AttrValues(False, ["OBUF", "IOBUF", "TBUF"],
     { "": ["ON", "OFF"]}),
 # bank-dependent
 "DRIVE"      : AttrValues(True, ["OBUF", "IOBUF", "TBUF"],
     {  ""  : ["4", "8", "12", "16", "24"],
        "LVTTL33"  : ["4", "8", "12", "16", "24"],
        "LVCMOS33" : ["4", "8", "12", "16", "24"],
        "LVCMOS25" : ["4", "8", "12", "16"],
        "LVCMOS18" : ["4", "8", "12"],
        "LVCMOS15" : ["4", "8"],
        "LVCMOS12" : ["4", "8"],
        "SSTL25_I" : ["8"],
        "SSTL25_II": ["8"],
        "SSTL33_I" : ["8"],
        "SSTL33_II": ["8"],
        "SSTL18_I" : ["8"],
        "SSTL18_II": ["8"],
        "SSTL15"   : ["8"],
        "HSTL18_I" : ["8"],
        "HSTL18_II": ["8"],
        "HSTL15_I" : ["8"],
        "PCI33"    : [],
         }),
}

def find_next_loc(pin, locs):
    # find the next location that has pin
    # or make a new module
    for tile, names in locs.items():
        name = tile+pin
        if name in names:
            del locs[tile]
            return name
    return None

_pnr_options = ["reg_not_in_iob"]
def iob(locations, corners):
    cnt = Counter() # keep track of how many runs are needed
    for iostd in iostandards:
        for ttyp, tiles in locations.items(): # for each tile of this type
            mod = codegen.Module()
            cst = codegen.Constraints()
            # get bels in this ttyp
            bels = {name[-1] for loc in tiles.values() for name in loc}
            locs = tiles.copy()
            for pin in bels: # [A, B, C, D, ...]
                for typ, conn in iobmap.items():
                    for attr, attr_values in iobattrs.items():  # each port attribute
                        # skip illegal atributes
                        if typ not in attr_values.allowed_modes:
                            continue
                        # skip bank independent values: they are generated only for empty iostd
                        if (iostd != "") ^ attr_values.bank_dependent:
                                continue

                        for attr_val in attr_values.values[iostd]:   # each value of the attribute
                            # find the next location that has pin
                            # or make a new module
                            loc = find_next_loc(pin, locs)
                            if (loc == None):
                                # no usable tiles
                                yield Fuzzer(ttyp, mod, cst, {"pnr_options": _pnr_options}, iostd)
                                if iostd == "":
                                    cnt[ttyp] += 1
                                locs = tiles.copy()
                                mod = codegen.Module()
                                cst = codegen.Constraints()
                                loc = find_next_loc(pin, locs)

                            name = tiled_fuzzer.make_name("IOB", typ)
                            iob = codegen.Primitive(typ, name)
                            for port in chain.from_iterable(conn.values()):
                                iob.portmap[port] = name+"_"+port

                            for direction, wires in conn.items():
                                wnames = [name+"_"+w for w in wires]
                                getattr(mod, direction).update(wnames)
                            mod.primitives[name] = iob
                            cst.ports[name] = loc
                            # complex iob. connect OEN and O in various ways
                            if typ == "IOBUF":
                                iob.portmap["OEN"] = name + "_O"
                            elif typ == "TBUF":
                                # TBUF doesn't like clockless triggers
                                dff(mod, cst, name + "_OEN", None, "FAKE_CLK")
                                mod.inputs.add("FAKE_CLK")
                            if attr != "NULL":
                                # port attribute value
                                cst.attrs[name] = {attr: attr_val}
                                # bank attribute
                                if iostd != "":
                                    cst.bank_attrs[name] = {"IO_TYPE": iostd}

            yield Fuzzer(ttyp, mod, cst, {"pnr_options": _pnr_options}, iostd)
            if iostd == "":
                cnt[ttyp] += 1

    # insert dummie in the corners to detect the bank enable bits
    runs = cnt.most_common(1)[0][1]
    for _ in range(runs):
        for ttyp in corners:
            mod = codegen.Module()
            cst = codegen.Constraints()
            cfg = {"pnr_options": _pnr_options}
            yield Fuzzer(ttyp, mod, cst, cfg, '')

# collect all routing and clock bits fo tile
_route_mem = {}
def route_bits(db, row, col):
    mem = _route_mem.get((row, col), None)
    if mem != None:
        return mem

    bits = set()
    for w in db.grid[row][col].pips.values():
        for v in w.values():
            bits.update(v)
    _route_mem.setdefault((row, col), bits)
    return bits

# module + constraints + config
DataForPnr = namedtuple('DataForPnr', ['modmap', 'cstmap', 'cfgmap'])

if __name__ == "__main__":
    with open(f"{tiled_fuzzer.gowinhome}/IDE/share/device/{tiled_fuzzer.device}/{tiled_fuzzer.device}.fse", 'rb') as f:
        fse = fuse_h4x.readFse(f)

    with open(f"{tiled_fuzzer.device}.json") as f:
        dat = json.load(f)

    with open(f"{tiled_fuzzer.gowinhome}/IDE/share/device/{tiled_fuzzer.device}/{tiled_fuzzer.device}.tm", 'rb') as f:
        tm = tm_h4x.read_tm(f, tiled_fuzzer.device)

    with open(f"{tiled_fuzzer.device}_stage1.pickle", 'rb') as f:
        db = pickle.load(f)

    locations = {}
    for row, row_dat in enumerate(fse['header']['grid'][61]):
        for col, typ in enumerate(row_dat):
            locations.setdefault(typ, []).append((row, col))

    pin_names = pindef.get_locs(tiled_fuzzer.device, tiled_fuzzer.params['package'],
                                True, tiled_fuzzer.params['header'])
    #pin_names = ["IOL6B", "IOR6B"]
    #pin_names = ["IOB7A"]
    banks = {'T': fse['header']['grid'][61][0],
             'B': fse['header']['grid'][61][-1],
             'L': [row[0] for row in fse['header']['grid'][61]],
             'R': [row[-1] for row in fse['header']['grid'][61]]}
    pin_locations = {}
    pin_re = re.compile(r"IO([TBRL])(\d+)([A-Z])")
    for name in pin_names:
        side, num, pin = pin_re.match(name).groups()
        ttyp = banks[side][int(num)-1]
        ttyp_pins = pin_locations.setdefault(ttyp, {})
        ttyp_pins.setdefault(name[:-1], set()).add(name)

    # Add fuzzers here
    fuzzers = chain(
        iob(pin_locations, [
            fse['header']['grid'][61][0][0],
            fse['header']['grid'][61][-1][0],
            fse['header']['grid'][61][0][-1],
            fse['header']['grid'][61][-1][-1],
        ]),
    )

    # Only combine modules with the same IO standard
    pnr_data = {}
    for fuzzer in fuzzers:
        pnr_data.setdefault(fuzzer.iostd, DataForPnr({}, {}, {}))
        pnr_data[fuzzer.iostd].modmap.setdefault(fuzzer.ttyp, []).append(fuzzer.mod)
        pnr_data[fuzzer.iostd].cstmap.setdefault(fuzzer.ttyp, []).append(fuzzer.cst)
        pnr_data[fuzzer.iostd].cfgmap.setdefault(fuzzer.ttyp, []).append(fuzzer.cfg)

    modules = []
    constrs = []
    configs = []
    for data in pnr_data.values():
        modules += [reduce(lambda a, b: a+b, m, codegen.Module())
                    for m in zip_longest(*data.modmap.values(), fillvalue=codegen.Module())]
        constrs += [reduce(lambda a, b: a+b, c, codegen.Constraints())
                    for c in zip_longest(*data.cstmap.values(), fillvalue=codegen.Constraints())]
        configs += [reduce(lambda a, b: {**a, **b}, c, {})
                    for c in zip_longest(*data.cfgmap.values(), fillvalue={})]

    type_re = re.compile(r"inst\d+_([A-Z]+)_([A-Z]+)")

    pnr_empty = tiled_fuzzer.run_pnr(codegen.Module(), codegen.Constraints(),
                                     {"pnr_options": _pnr_options})
    db.cmd_hdr = pnr_empty.hdr
    db.cmd_ftr = pnr_empty.ftr
    db.template = pnr_empty.bitmap
    p = Pool()
    pnr_res = p.imap_unordered(lambda param: tiled_fuzzer.run_pnr(*param),
                                               zip(modules, constrs, configs), 5)

    for pnr in pnr_res:
        seen = {}
        diff = pnr.bitmap ^ pnr_empty.bitmap
        bm = fuse_h4x.tile_bitmap(fse, diff)
        for cst_type, name, *info in pnr.posp:
            bel_type, cell_type = type_re.match(name).groups()
            if cst_type == "cst":
                row, col, cls, lut = info
                print(name, row, col, cls, lut)
                row = row-1
                col = col-1
            elif cst_type == "place":
                side, num, pin = info
                if side == 'T':
                    row = 0
                    col = num-1
                elif side == 'B':
                    row = len(fse['header']['grid'][61])-1
                    col = num-1
                elif side == 'L':
                    row = num-1
                    col = 0
                elif side == 'R':
                    row = num-1
                    col = len(fse['header']['grid'][61][0])-1
                print(name, row, col, side, num, pin)

            typ = fse['header']['grid'][61][row][col]
            idx = (row, col, typ)

            # verify integrity
            if bel_type != "DUMMY":
                if (row, col) in seen:
                    oldname = seen[(row, col)]
                    raise Exception(f"Location {idx} used by {oldname} and {name}")
                else:
                    seen[(row, col)] = name

            tile = bm[idx]
            #for bitrow in tile:
            #    print(*bitrow, sep='')

            rows, cols = np.where(tile==1)
            loc = set(zip(rows, cols))
            #print(cell_type, loc)

            if bel_type == "DUMMY":
                continue
            elif bel_type == "IOB":
                if tiled_fuzzer.primitive_caused_err(name, "CT1108", pnr.errs): # skip bad primitives
                    raise Exception(f"Bad attribute (CT1108):{name}")

                bel = db.grid[row][col].bels.setdefault(f"IOB{pin}", chipdb.Bel())
                if cell_type in ["IOBUF", "TBUF"]:
                    loc -= route_bits(db, row, col)
                pnr_attrs = pnr.attrs.get(name)
                if pnr_attrs != None:
                    mod_attr = list(pnr_attrs)[0]
                    mod_attr_val = pnr_attrs[mod_attr]
                    if list(pnr.bank_attrs): # all bank attrs are equal
                        mod_attr = pnr.bank_attrs[name]["IO_TYPE"] + chipdb.bank_attr_sep + mod_attr
                    bel.modes[f"{cell_type}&{mod_attr}={mod_attr_val}"] = loc;
                else:
                    bel.modes[f"{cell_type}"] = loc;
                # portmap is set from dat file

            else:
                raise ValueError(f"Type {bel_type} not handled")

        # corner tiles for bank enable
        print("### CORNER TILES ###")
        # TODO
        corners = [
            (0, 0, fse['header']['grid'][61][0][0]),
            (0, db.cols-1, fse['header']['grid'][61][0][-1]),
            (db.rows-1, 0, fse['header']['grid'][61][-1][0]),
            (db.rows-1, db.cols-1, fse['header']['grid'][61][-1][-1]),
        ]
        for idx in corners:
            row, col, typ = idx
            try:
                tile = bm[idx]
            except KeyError:
                continue
            rows, cols = np.where(tile==1)
            loc = set(zip(rows, cols))
            print(idx, loc)

            mode = "DEFAULT"
            bel = db.grid[row][col].bels.setdefault("BANK", chipdb.Bel())
            bel.modes.setdefault(mode, set()).update(loc)

            # fuzz bank modes
            bank_attrs = list(pnr.bank_attrs.values())
            if bank_attrs:
                for mod_attr, mod_attr_val in bank_attrs[0].items():
                    bel.modes["BANK&{}={}".format(mod_attr, mod_attr_val)] = loc;

    chipdb.dat_portmap(dat, db)
    chipdb.dat_aliases(dat, db)
    chipdb.diff2flag(db)
    chipdb.shared2flag(db)

    db.grid[0][0].bels['CFG'].flags['UNK0'] = {(3, 1)}
    db.grid[0][0].bels['CFG'].flags['UNK1'] = {(3, 2)}


    #TODO proper serialization format
    with open(f"{tiled_fuzzer.device}_stage2.pickle", 'wb') as f:
        pickle.dump(db, f)
