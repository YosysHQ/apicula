import re
import os
import sys
import tempfile
import subprocess
from collections import deque, Counter, namedtuple
from itertools import chain, count, zip_longest
from functools import reduce
from random import shuffle, seed
from warnings import warn
from math import factorial
import numpy as np
from multiprocessing.dummy import Pool
import pickle
import json
from shutil import copytree

from apycula import codegen
from apycula import bslib
from apycula import pindef
from apycula import fuse_h4x
#TODO proper API
#from apycula import dat19_h4x
from apycula import tm_h4x
from apycula import chipdb

gowinhome = os.getenv("GOWINHOME")
if not gowinhome:
    raise Exception("GOWINHOME not set")

# XXX
# The indexes of the flag values depend on the device.
# So far I have not found where it is described in the tables
def recode_idx_gw1n1(idx):
    return idx

def recode_idx_gw1ns_2(idx):
    new_idx = idx + 1
    if idx >= 69:
        new_idx += 3
    if idx >= 80:
        new_idx += 1
    return new_idx

def recode_idx_gw1ns_4(idx):
    new_idx = idx
    if idx >= 48:
        new_idx -= 1
    if idx >= 55:
        new_idx -= 1
    if idx >= 70:
        new_idx -= 3
    return new_idx

def recode_idx_gw1n9(idx):
    new_idx = idx
    if idx >= 69:
        new_idx += 3
    return new_idx

def recode_idx_gw1n4(idx):
    new_idx  = idx
    if idx >= 48:
        new_idx -= 1
    if idx >= 55:
        new_idx -= 1
    if idx >= 70:
        new_idx -= 2
    return new_idx

def recode_idx_gw1nz_1(idx):
    new_idx = idx
    if idx >= 40:
        new_idx -= 10
    if idx >= 60:
        new_idx -= 2
    if idx >= 80:
        new_idx -= 6
    return new_idx

# device = os.getenv("DEVICE")
device = sys.argv[1]
params = {
    "GW1NS-2": {
        "package": "LQFP144",
        "device": "GW1NS-2C-LQFP144-5",
        "partnumber": "GW1NS-UX2CLQ144C5/I4",
        "recode_idx": recode_idx_gw1ns_2,
    },
    "GW1NS-4": {
        "package": "QFN48",
        "device": "GW1NSR-4C-QFN48-7",
        "partnumber": "GW1NSR-LV4CQN48PC7/I6",
        "recode_idx": recode_idx_gw1ns_4,
    },
    "GW1N-9": {
        "package": "PBGA256",
        "device": "GW1N-9-PBGA256-6",
        "partnumber": "GW1N-LV9PG256C6/I5",
        "recode_idx": recode_idx_gw1n9,
    },
    "GW1N-9C": {
        "package": "UBGA332",
        "device": "GW1N-9C-UBGA332-6",
        "partnumber": "GW1N-LV9UG332C6/I5",
        "recode_idx": recode_idx_gw1n9, # TODO: recheck
    },
    "GW1N-4": {
        "package": "PBGA256",
        "device": "GW1N-4-PBGA256-6",
        "partnumber": "GW1N-LV4PG256C6/I5",
        "recode_idx": recode_idx_gw1n4,
    },
    "GW1N-1": {
        "package": "LQFP144",
        "device": "GW1N-1-LQFP144-6",
        "partnumber": "GW1N-LV1LQ144C6/I5",
        "recode_idx": recode_idx_gw1n1,
    },
    "GW1NZ-1": {
        "package": "QFN48",
        "device": "GW1NZ-1-QFN48-6",
        "partnumber": "GW1NZ-LV1QN48C6/I5",
        "recode_idx": recode_idx_gw1nz_1, # TODO: check
    },
}[device]

name_idx = 0
def make_name(bel, typ):
    global name_idx
    name_idx += 1
    return f"inst{name_idx}_{bel}_{typ}"

# one fuzzer
Fuzzer = namedtuple('Fuzzer', [
    'ttyp',
    'mod',
    'cst',      # constraints
    'cfg',      # device config
    'iostd',    # io standard
    ])

dffmap = {
    "DFF": None,
    "DFFN": None,
    "DFFS": "SET",
    "DFFR": "RESET",
    "DFFP": "PRESET",
    "DFFC": "CLEAR",
    "DFFNS": "SET",
    "DFFNR": "RESET",
    "DFFNP": "PRESET",
    "DFFNC": "CLEAR",
}
def dff(locations):
    for ttyp in range(12, 18): # for each tile type
        mod = codegen.Module()
        cst = codegen.Constraints()
        try:
            # get all tiles of this type
            # iter causes the loop to not repeat the same locs per cls
            locs = iter(locations[ttyp])
        except KeyError:
            continue

        for cls in range(3): # for each cls
            for side in ["A", "B"]:
                for typ, port in dffmap.items(): # for each bel type
                    try:
                        loc = next(locs) # get the next unused tile
                    except StopIteration:
                        yield Fuzzer(ttyp, mod, cst, {}, '')
                        locs = iter(locations[ttyp])
                        loc = next(locs)
                        mod = codegen.Module()
                        cst = codegen.Constraints()

                    lutname = make_name("DUMMY", "LUT4")
                    lut = codegen.Primitive("LUT4", lutname)
                    lut.params["INIT"] = "16'hffff"
                    lut.portmap['F'] = lutname+"_F"
                    lut.portmap['I0'] = lutname+"_I0"
                    lut.portmap['I1'] = lutname+"_I1"
                    lut.portmap['I2'] = lutname+"_I2"
                    lut.portmap['I3'] = lutname+"_I3"

                    mod.wires.update(lut.portmap.values())
                    mod.primitives[lutname] = lut
                    name = make_name("DFF", typ)
                    dff = codegen.Primitive(typ, name)
                    dff.portmap['CLK'] = name+"_CLK"
                    dff.portmap['D'] = lutname+"_F"
                    dff.portmap['Q'] = name+"_Q"
                    if port:
                        dff.portmap[port] = name+"_"+port
                    mod.wires.update(dff.portmap.values())
                    mod.primitives[name] = dff

                    row = loc[0]+1
                    col = loc[1]+1
                    cst.cells[lutname] = (row, col, cls, side)
                    cst.cells[name] = (row, col, cls, side)
        yield Fuzzer(ttyp, mod, cst, {}, '')

# illegal pin-attr combination for device
_illegal_combo = { ("IOR6A", "SLEW_RATE") : "GW1NS-2",
                   ("IOR6B", "SLEW_RATE") : "GW1NS-2"}

def is_illegal(iostd, pin, attr):
    if _illegal_combo.get((pin, attr)) == device:
        return True
    # GW1N-1, GW1NS-2, GW1N-4 and GW1N-9 allow single resisor only in banks 1/3
    if (attr == "SINGLE_RESISTOR") and (pin[2] in "BT"):
        return True
    # bottom pins GW1NS-4 (bank 3) support LVCMOS only
    if iostd != '' and device == 'GW1NS-4':
        if pin.startswith('IOB'):
            return not iostd.startswith('LVCMOS')
    return False

# take TBUF == IOBUF - O
iobmap = {
    "IBUF": {"wires": ["O"], "inputs": ["I"]},
    "OBUF": {"wires": ["I"], "outputs": ["O"]},
    "IOBUF": {"wires": ["I", "O", "OEN"], "inouts": ["IO"]},
}

iostd_open_drain = {
            ""        ,
            "LVCMOS33",
            "LVCMOS25",
            "LVCMOS18",
            "LVCMOS15",
            "LVCMOS12",
        }
iostd_histeresis = {
            ""        ,
            "LVCMOS33",
            "LVCMOS25",
            "LVCMOS18",
            "LVCMOS15",
            "LVCMOS12",
            "PCI33"   ,
        }

iostandards = ["", "LVCMOS18", "LVCMOS33", "LVCMOS25", "LVCMOS15",
      "SSTL25_I", "SSTL33_I", "SSTL15", "HSTL18_I", "PCI33"]

AttrValues = namedtuple('ModeAttr', [
    'allowed_modes',    # allowed modes for the attribute
    'values',           # values of the attribute
    'table',            # special values table
    ])

iobattrs = {
 "IO_TYPE"    : AttrValues(["IBUF", "OBUF", "IOBUF"], [""], None),
 #"SINGLE_RESISTOR" : AttrValues(["IBUF", "IOBUF"], ["ON", "OFF"], None),
}

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

# get fuse bits from longval table
# the key is automatically sorted and appended with zeros.
# If ignore_key_elem is set, the initial elements in the table record keys
# is ignored when searching.
def get_longval(fse, ttyp, table, key, ignore_key_elem = 0):
    bits = set()
    sorted_key = (sorted(key) + [0] * 16)[:16 - ignore_key_elem]
    for rec in fse[ttyp]['longval'][table]:
        k = rec[ignore_key_elem:16]
        if k == sorted_key:
            fuses = [f for f in rec[16:] if f != -1]
            for fuse in fuses:
                bits.update({fuse_h4x.fuse_lookup(fse, ttyp, fuse)})
            break
    return bits

# diff boards have diff key indexes
def recode_key(key):
    return set(map(params['recode_idx'], key))

# IOB from tables
# (code, {option values}, is cmos-like mode, GW1N-4 aliases)
_iostd_codes = {
    # XXX default LVCMOS18
    ""            : ( 66, {'4', '8', '12'}, True, {'4': None, '8': 51, '12': 53}),
    "LVCMOS33"    : ( 68, {'4', '8', '12', '16', '24'}, True, {'4': 48, '8': None, '12': 50, '16': 51, '24': 53}),
    "LVCMOS25"    : ( 67, {'4', '8', '12', '16'}, True, {'4': None, '8': 50, '12': 51, '16': 53}),
    "LVCMOS18"    : ( 66, {'4', '8', '12'}, True, {'4': None, '8': 51, '12': 53}),
    "LVCMOS15"    : ( 65, {'4', '8'}, True, {'4': 50, '8': 53}),
    "LVCMOS12"    : ( 64, {'4', '8'}, True, {'4': 50, '8': 53}),
    "SSTL25_I"    : ( 71, {'8'}, False, {'8': 50}),
    "SSTL25_II"   : ( 71, {'8'}, False, {'8': 50}),
    "SSTL33_I"    : ( -1, {'8'}, False, {'8': None}),
    "SSTL33_II"   : ( -1, {'8'}, False, {'8': None}),
    "SSTL18_I"    : ( 72, {'8'}, False, {'8': 51}),
    "SSTL18_II"   : ( 72, {'8'}, False, {'8': 51}),
    "SSTL15"      : ( 74, {'8'}, False, {'8': 51}),
    "HSTL18_I"    : ( 72, {'8'}, False, {'8': 53}),
    "HSTL18_II"   : ( 72, {'8'}, False, {'8': 53}),
    "HSTL15_I"    : ( 74, {'8'}, False, {'8': 51}),
    "PCI33"       : ( 69, {'4', '8'}, False, {'4':48, '8': None}),
    }

# PULL_MODE
_pin_mode_longval = {'A':23, 'B':24, 'C':40, 'D':41, 'E':42, 'F':43, 'G':44, 'H':45, 'I':46, 'J':47}
_pull_mode_iob = ["IBUF", "OBUF", "IOBUF"]
_tbrlre = re.compile(r"IO([TBRL])(\d+)")
_pull_mode_idx = { 'UP' : -1, 'NONE' : 45, 'KEEPER' : 44, 'DOWN' : 43}
def fse_pull_mode(fse, db, pin_locations):
    for ttyp, tiles in pin_locations.items():
        pin_loc = list(tiles.keys())[0]
        side, num = _tbrlre.match(pin_loc).groups()
        row, col = tbrl2rc(fse, side, num)
        bels = {name[-1] for loc in tiles.values() for name in loc}
        for bel_idx in bels:
            bel = db.grid[row][col].bels.setdefault(f"IOB{bel_idx}", chipdb.Bel())
            for iostd, b_iostd in bel.iob_flags.items():
                for io_mode in _pull_mode_iob:
                    b_mode = b_iostd.setdefault(io_mode, chipdb.IOBMode())
                    b_attr = b_mode.flags.setdefault('PULL_MODE', chipdb.IOBFlag())
                    for opt_name, val in _pull_mode_idx.items():
                        if val == -1:
                            loc = set()
                        else:
                            loc = get_longval(fse, ttyp, _pin_mode_longval[bel_idx], recode_key({val}))
                        b_attr.options[opt_name] = loc

# LVCMOS12/15/18 fuse
def get_12_15_18_bits(fse, ttyp, pin):
    return get_longval(fse, ttyp, _pin_mode_longval[pin], recode_key({66}))

# SLEW_RATE
_slew_rate_iob = [        "OBUF", "IOBUF"]
_slew_rate_idx = { 'SLOW' : -1, 'FAST' : 42}
def fse_slew_rate(fse, db, pin_locations):
    for ttyp, tiles in pin_locations.items():
        pin_loc = list(tiles.keys())[0]
        side, num = _tbrlre.match(pin_loc).groups()
        row, col = tbrl2rc(fse, side, num)
        bels = {name[-1] for loc in tiles.values() for name in loc}
        for bel_idx in bels:
            bel = db.grid[row][col].bels.setdefault(f"IOB{bel_idx}", chipdb.Bel())
            for iostd, b_iostd in bel.iob_flags.items():
                for io_mode in _slew_rate_iob:
                    b_mode  = b_iostd.setdefault(io_mode, chipdb.IOBMode())
                    b_attr = b_mode.flags.setdefault('SLEW_RATE', chipdb.IOBFlag())
                    for opt_name, val in _slew_rate_idx.items():
                        if val == -1:
                            loc = set()
                        else:
                            loc = get_longval(fse, ttyp, _pin_mode_longval[bel_idx], recode_key({val}))
                        b_attr.options[opt_name] = loc

# DRIVE
_drive_iob = [        "OBUF", "IOBUF"]
_drive_idx = {'4': {48}, '8': {50}, '12': {51}, '16': {52}, '24': {54}}
_drive_key = {56}
def fse_drive(fse, db, pin_locations):
    for ttyp, tiles in pin_locations.items():
        pin_loc = list(tiles.keys())[0]
        side, num = _tbrlre.match(pin_loc).groups()
        row, col = tbrl2rc(fse, side, num)
        bels = {name[-1] for loc in tiles.values() for name in loc}
        for bel_idx in bels:
            bel = db.grid[row][col].bels.setdefault(f"IOB{bel_idx}", chipdb.Bel())
            for iostd, b_iostd in bel.iob_flags.items():
                for io_mode in _drive_iob:
                    b_mode = b_iostd.setdefault(io_mode, chipdb.IOBMode())
                    b_attr = b_mode.flags.setdefault('DRIVE', chipdb.IOBFlag())
                    for opt_name, val in _drive_idx.items():
                        iostd_key, iostd_vals, iostd_cmos, gw1n4_aliases = _iostd_codes[iostd]
                        if opt_name not in iostd_vals:
                            continue
                        # XXX
                        if iostd_key == -1 or (iostd == "PCI33" and opt_name == '8'):
                            loc = set()
                        else:
                            if device in ['GW1N-4', 'GW1NS-4']:
                                opt_key = gw1n4_aliases[opt_name]
                                if opt_key:
                                    val = _drive_key.union({opt_key})
                                    loc = get_longval(fse, ttyp, _pin_mode_longval[bel_idx],
                                            recode_key(val), 1)
                                else:
                                    loc = set()
                            else:
                                val = {iostd_key}.union(_drive_key)
                                if iostd_cmos:
                                    val = val.union(_drive_idx[opt_name])
                                loc = get_longval(fse, ttyp, _pin_mode_longval[bel_idx],
                                        recode_key(val), 1)
                        b_attr.options[opt_name] = loc

# OPEN_DRAIN
_open_drain_iob = [        "OBUF", "IOBUF"]
_open_drain_key = {"ON": {55, 70}, "NOISE": {55, 72}}
_open_drain_gw1n4_key = {"ON": {49, 54}, "NOISE": {51, 54}}
def fse_open_drain(fse, db, pin_locations):
    for ttyp, tiles in pin_locations.items():
        pin_loc = list(tiles.keys())[0]
        side, num = _tbrlre.match(pin_loc).groups()
        row, col = tbrl2rc(fse, side, num)
        bels = {name[-1] for loc in tiles.values() for name in loc}
        for bel_idx in bels:
            bel = db.grid[row][col].bels.setdefault(f"IOB{bel_idx}", chipdb.Bel())
            for iostd, b_iostd in bel.iob_flags.items():
                if iostd not in iostd_open_drain:
                    continue
                # XXX presumably OPEN_DRAIN is another DRIVE mode, strange as it may sound.
                # Three fuses are used: ON=100, i.e. one is set and the other two are cleared,
                # OFF=xxx (xxx != 100)
                # These are the same fuses that are used for DRIVE and in the future you can
                # come up with a smarter way to find them.
                # XXX Below is a very shamanic method of determining the fuses,
                iostd33_key, _, _, gw1n4_aliases = _iostd_codes["LVCMOS33"]
                if device in ['GW1N-4', 'GW1NS-4']:
                    cur16ma_key = _drive_key.union({gw1n4_aliases["16"]})
                    keys = _open_drain_gw1n4_key
                else:
                    cur16ma_key = {iostd33_key}.union(_drive_key).union(_drive_idx["16"])
                    keys = _open_drain_key
                # ON fuse is simple
                on_fuse = get_longval(fse, ttyp, _pin_mode_longval[bel_idx],
                        recode_key(keys['ON']), 1)
                # the mask to clear is diff between 16mA fuses of LVCMOS33 standard and
                # some key
                cur16ma_fuse = get_longval(fse, ttyp, _pin_mode_longval[bel_idx],
                        recode_key(cur16ma_key), 1)
                noise_fuse = get_longval(fse, ttyp, _pin_mode_longval[bel_idx],
                        recode_key(keys['NOISE']), 1)
                clear_mask = cur16ma_fuse - noise_fuse - on_fuse;
                for io_mode in _open_drain_iob:
                    b_mode = b_iostd.setdefault(io_mode, chipdb.IOBMode())
                    b_attr = b_mode.flags.setdefault('OPEN_DRAIN', chipdb.IOBFlag())
                    # bits of this attribute are the same as the DRIVE bits
                    # so make a flag mask here, also never use OFF when encoding, only ON
                    b_attr.mask = clear_mask.union(on_fuse)
                    b_attr.options["OFF"] = set()
                    b_attr.options["ON"] = on_fuse.copy()
                    #print(b_attr.options)

# HYSTERESIS
_hysteresis_iob = [ "IBUF",          "IOBUF"]
_hysteresis_idx = { 'NONE': -1, 'HIGH': {57, 85}, 'H2L': {58, 85}, 'L2H': {59, 85}}
def fse_hysteresis(fse, db, pin_locations):
    for ttyp, tiles in pin_locations.items():
        pin_loc = list(tiles.keys())[0]
        side, num = _tbrlre.match(pin_loc).groups()
        row, col = tbrl2rc(fse, side, num)
        bels = {name[-1] for loc in tiles.values() for name in loc}
        for bel_idx in bels:
            bel = db.grid[row][col].bels.setdefault(f"IOB{bel_idx}", chipdb.Bel())
            for iostd, b_iostd in bel.iob_flags.items():
                if iostd not in iostd_histeresis:
                    continue
                for io_mode in _hysteresis_iob:
                    b_mode  = b_iostd.setdefault(io_mode, chipdb.IOBMode())
                    b_attr = b_mode.flags.setdefault('HYSTERESIS', chipdb.IOBFlag())
                    for opt_name, val in _hysteresis_idx.items():
                        if val == -1:
                            loc = set()
                        else:
                            loc = get_longval(fse, ttyp, _pin_mode_longval[bel_idx],
                                    recode_key(val), 1)
                        b_attr.options[opt_name] = loc

# IOB fuzzer
def find_next_loc(pin, locs):
    # find the next location that has pin
    # or make a new module
    for tile, names in locs.items():
        name = tile+pin
        if name in names:
            del locs[tile]
            return name
    return None

def iob(locations):
    for iostd in iostandards:
        for ttyp, tiles in locations.items(): # for each tile of this type
            locs = tiles.copy()
            mod = codegen.Module()
            cst = codegen.Constraints()
            # get bels in this ttyp
            bels = {name[-1] for loc in tiles.values() for name in loc}
            for pin in bels: # [A, B, C, D, ...]
                for attr, attr_values in iobattrs.items():  # each IOB attribute
                    # XXX remove
                    if iostd == "PCI33" and attr == "SINGLE_RESISTOR":
                        continue
                    attr_vals = attr_values.values
                    if attr_vals == None:
                        attr_vals = attr_values.table[iostd]
                    for attr_val in attr_vals:   # each value of the attribute
                        for typ, conn in iobmap.items():
                            # skip illegal atributesa for mode
                            if typ not in attr_values.allowed_modes:
                                continue
                            # find the next location that has pin
                            # or make a new module
                            loc = find_next_loc(pin, locs)
                            if (loc == None):
                                yield Fuzzer(ttyp, mod, cst, {}, iostd)
                                locs = tiles.copy()
                                mod = codegen.Module()
                                cst = codegen.Constraints()
                                loc = find_next_loc(pin, locs)

                            # special pins
                            if is_illegal(iostd, loc, attr):
                                continue
                            name = make_name("IOB", typ)
                            iob = codegen.Primitive(typ, name)
                            for port in chain.from_iterable(conn.values()):
                                iob.portmap[port] = name+"_"+port

                            for direction, wires in conn.items():
                                wnames = [name+"_"+w for w in wires]
                                getattr(mod, direction).update(wnames)
                            mod.primitives[name] = iob
                            cst.ports[name] = loc
                            # complex iob. connect OEN and O
                            if typ == "IOBUF":
                                iob.portmap["OEN"] = name + "_O"
                            if attr_val:
                                # port attribute value
                                cst.attrs[name] = {attr: attr_val}
                            if iostd:
                                cst.attrs.setdefault(name, {}).update({"IO_TYPE": iostd})
            yield Fuzzer(ttyp, mod, cst, {}, iostd)

# collect all routing bits of the tile
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

dualmode_pins = {'jtag', 'sspi', 'mspi', 'ready', 'done', 'reconfig', 'mode', 'i2c'}
def dualmode(ttyp):
    for pin in dualmode_pins:
        mod = codegen.Module()
        cst = codegen.Constraints()
        cfg = {pin: "0"}
        # modules with different ttyp can be combined, so in theory it could happen
        # that there is an IOB in the module, which claims the dual-purpose pin.
        # P&R will not be able to place it and the fuzzling result will be misleading.
        # Non-optimal: prohibit combining with anything.
        yield Fuzzer(ttyp, mod, cst, cfg, 'dual_mode_fuzzing')

# read vendor .posp log
_cst_parser = re.compile(r"([^ ]+) (?:PLACE|CST)_R(\d+)C(\d+)\[([0-3])\]\[([A-Z])\]")
_place_parser = re.compile(r"([^ ]+) (?:PLACE|CST)_IO([TBLR])(\d+)\[([A-Z])\]")
def read_posp(fname):
    with open(fname, 'r') as f:
        for line in f:
            cst = _cst_parser.match(line)
            place = _place_parser.match(line)
            if cst:
                name, row, col, cls, lut = cst.groups()
                yield "cst", name, int(row), int(col), int(cls), lut
            elif place:
                name, side, num, pin = place.groups()
                yield "place", name, side, int(num), pin
            elif line.strip() and not line.startswith('//'):
                raise Exception(line)

# Read the packer vendor log to identify problem with primitives/attributes
# returns dictionary {(primitive name, error code) : [full error text]}
_err_parser = re.compile("(\w+) +\(([\w\d]+)\).*'(inst[^\']+)\'.*")
def read_err_log(fname):
    errs = {}
    with open(fname, 'r') as f:
        for line in f:
            res = _err_parser.match(line)
            if res:
                line_type, code, name = res.groups()
                text = res.group(0)
                if line_type in ["Warning", "Error"]:
                    errs.setdefault((name, code), []).append(text)
    return errs

# check if the primitive caused the warning/error
def primitive_caused_err(name, err_code, log):
    return (name, err_code) in log

# Result of the vendor router-packer run
PnrResult = namedtuple('PnrResult', [
    'bitmap', 'hdr', 'ftr',
    'constrs',        # constraints
    'config',         # device config
    'attrs',          # port attributes
    'errs'            # parsed log file
    ])

def run_pnr(mod, constr, config):
    cfg = codegen.DeviceConfig({
        "use_jtag_as_gpio"      : config.get('jtag', "1"),
        "use_sspi_as_gpio"      : config.get('sspi', "1"),
        "use_mspi_as_gpio"      : config.get('mspi', "1"),
        "use_ready_as_gpio"     : config.get('ready', "1"),
        "use_done_as_gpio"      : config.get('done', "1"),
        "use_reconfign_as_gpio" : config.get('reconfig', "1"),
        "use_mode_as_gpio"      : config.get('mode', "1"),
        "use_i2c_as_gpio"       : config.get('i2c', "1"),
        "bit_crc_check"         : "1",
        "bit_compress"          : "0",
        "bit_encrypt"           : "0",
        "bit_security"          : "1",
        "bit_incl_bsram_init"   : "0",
        "loading_rate"          : "250/100",
        "spi_flash_addr"        : "0x00FFF000",
        "bit_format"            : "txt",
        "bg_programming"        : "off",
        "secure_mode"           : "0"})

    opt = codegen.PnrOptions({
        "gen_posp"          : "1",
        "gen_io_cst"        : "1",
        "gen_ibis"          : "1",
        "ireg_in_iob"       : "0",
        "oreg_in_iob"       : "0",
        "ioreg_in_iob"      : "0",
        "timing_driven"     : "0",
        "cst_warn_to_error" : "0"})
    #"show_all_warn" : "1",

    pnr = codegen.Pnr()
    pnr.device = device
    pnr.partnumber = params['partnumber']
    pnr.opt = opt
    pnr.cfg = cfg

    with tempfile.TemporaryDirectory() as tmpdir:
        with open(tmpdir+"/top.v", "w") as f:
            mod.write(f)
        pnr.netlist = tmpdir+"/top.v"
        with open(tmpdir+"/top.cst", "w") as f:
            constr.write(f)
        pnr.cst = tmpdir+"/top.cst"
        with open(tmpdir+"/run.tcl", "w") as f:
            pnr.write(f)

        subprocess.run([gowinhome + "/IDE/bin/gw_sh", tmpdir+"/run.tcl"], cwd = tmpdir)
        #print(tmpdir); input()
        try:
            return PnrResult(
                    *bslib.read_bitstream(tmpdir+"/impl/pnr/top.fs"),
                    constr,
                    config, constr.attrs,
                    read_err_log(tmpdir+"/impl/pnr/top.log"))
        except FileNotFoundError:
            print(tmpdir)
            input()
            return None


# module + constraints + config
DataForPnr = namedtuple('DataForPnr', ['modmap', 'cstmap', 'cfgmap'])

if __name__ == "__main__":
    with open(f"{gowinhome}/IDE/share/device/{device}/{device}.fse", 'rb') as f:
        fse = fuse_h4x.readFse(f)

    with open(f"{device}.json") as f:
        dat = json.load(f)

    with open(f"{gowinhome}/IDE/share/device/{device}/{device}.tm", 'rb') as f:
        tm = tm_h4x.read_tm(f, device)

    db = chipdb.from_fse(fse)
    db.timing = tm
    db.packages, db.pinout, db.pin_bank = chipdb.json_pinout(device)

    corners = [
        (0, 0, fse['header']['grid'][61][0][0]),
        (0, db.cols-1, fse['header']['grid'][61][0][-1]),
        (db.rows-1, 0, fse['header']['grid'][61][-1][0]),
        (db.rows-1, db.cols-1, fse['header']['grid'][61][-1][-1]),
    ]

    locations = {}
    for row, row_dat in enumerate(fse['header']['grid'][61]):
        for col, typ in enumerate(row_dat):
            locations.setdefault(typ, []).append((row, col))

    pin_names = pindef.get_locs(device, params['package'], True)
    edges = {'T': fse['header']['grid'][61][0],
             'B': fse['header']['grid'][61][-1],
             'L': [row[0] for row in fse['header']['grid'][61]],
             'R': [row[-1] for row in fse['header']['grid'][61]]}
    pin_locations = {}
    pin_re = re.compile(r"IO([TBRL])(\d+)([A-Z])")
    for name in pin_names:
        side, num, pin = pin_re.match(name).groups()
        ttyp = edges[side][int(num)-1]
        ttyp_pins = pin_locations.setdefault(ttyp, {})
        ttyp_pins.setdefault(name[:-1], set()).add(name)

    # Add fuzzers here
    fuzzers = chain(
        iob(pin_locations),
        dff(locations),
        dualmode(fse['header']['grid'][61][0][0]),
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

    pnr_empty = run_pnr(codegen.Module(), codegen.Constraints(), {})
    db.cmd_hdr = pnr_empty.hdr
    db.cmd_ftr = pnr_empty.ftr
    db.template = pnr_empty.bitmap

    p = Pool()
    pnr_res = p.imap_unordered(lambda param: run_pnr(*param), zip(modules, constrs, configs), 4)
    for pnr in pnr_res:
        seen = {}
        diff = pnr.bitmap ^ pnr_empty.bitmap
        bm = fuse_h4x.tile_bitmap(fse, diff)
        placement = chain(
           [("cst", name, info) for name, info in pnr.constrs.cells.items()],
           [("place", name, pin_re.match(info).groups()) for name, info in pnr.constrs.ports.items()]
           )
        for cst_type, name, info in placement:
            if primitive_caused_err(name, "CT1108", pnr.errs) or \
                primitive_caused_err(name, "CT1117", pnr.errs) or \
                primitive_caused_err(name, "PR2016", pnr.errs) or \
                primitive_caused_err(name, "PR2017", pnr.errs) or \
                primitive_caused_err(name, "CT1005", pnr.errs):
                  raise Exception(f"Placement conflict (PR201[67]):{name} or CT1108/CT1117")

            bel_type, cell_type = type_re.match(name).groups()
            if cst_type == "cst":
                row, col, cls, lut = info
                print(name, row, col, cls, lut)
                row = row-1
                col = col-1
            elif cst_type == "place":
                side, num, pin = info
                row, col = tbrl2rc(fse, side, num)
                print(name, row, col, side, num, pin)

            typ = fse['header']['grid'][61][row][col]
            idx = (row, col, typ)

            # verify integrity
            if bel_type not in ["DUMMY", "IOB"]:
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
            elif bel_type == "DFF":
                i = ord(lut)-ord("A")
                bel = db.grid[row][col].bels.setdefault(f"DFF{cls*2+i}", chipdb.Bel())
                bel.modes[cell_type] = loc
                bel.portmap = {
                    # D inputs hardwired to LUT F
                    'Q': f"Q{cls*2+i}",
                    'CLK': f"CLK{cls}",
                    'LSR': f"LSR{cls}", # set/reset
                    'CE': f"CE{cls}", # clock enable
                }
            elif bel_type == "IOB":
                bel = db.grid[row][col].bels.setdefault(f"IOB{pin}", chipdb.Bel())
                bel.lvcmos121518_bits = get_12_15_18_bits(fse, typ, pin)
                pnr_attrs = pnr.attrs.get(name)
                if pnr_attrs:
                    # first get iostd
                    iostd = pnr_attrs.get("IO_TYPE")
                    # default iostd and some attr
                    if iostd == None:
                        rec_iostd = ""
                        rec_attr = list(pnr_attrs)[0]
                        rec_val  = pnr_attrs[rec_attr]
                        # add flag record
                        b_iostd  = bel.iob_flags.setdefault(rec_iostd, {})
                        b_mode   = b_iostd.setdefault(cell_type, chipdb.IOBMode())
                        b_attr   = b_mode.flags.setdefault(rec_attr, chipdb.IOBFlag())
                        b_attr.options[rec_val] = loc
                    elif len(pnr_attrs) == 1:
                        # only IO_TYPE
                        # set mode bits
                        b_iostd  = bel.iob_flags.setdefault(iostd, {})
                        b_mode   = b_iostd.setdefault(cell_type, chipdb.IOBMode())
                        if cell_type == "IBUF" and iostd in {'LVCMOS25', 'LVCMOS33'}:
                            loc -= bel.lvcmos121518_bits
                        b_mode.encode_bits = loc
                    else:
                        # IO_TYPE and some attr
                        pnr_attrs.pop(iostd, None)
                        rec_iostd = iostd
                        rec_attr = list(pnr_attrs)[0]
                        rec_val  = pnr_attrs[rec_attr]
                        # add flag record
                        b_iostd  = bel.iob_flags.setdefault(rec_iostd, {})
                        b_mode   = b_iostd.setdefault(cell_type, chipdb.IOBMode())
                        b_attr   = b_mode.flags.setdefault(rec_attr, chipdb.IOBFlag())
                        b_attr.options[rec_val] = loc
                else:
                    # set mode bits
                    b_iostd  = bel.iob_flags.setdefault('', {})
                    b_mode   = b_iostd.setdefault(cell_type, chipdb.IOBMode())
                    b_mode.encode_bits = loc
            else:
                raise ValueError(f"Type {bel_type} not handled")

        # corner tiles for bank enable
        print("### CORNER TILES ###")
        for idx in corners:
            row, col, typ = idx
            try:
                tile = bm[idx]
            except KeyError:
                continue
            rows, cols = np.where(tile==1)
            loc = set(zip(rows, cols))
            print(idx, loc)

            try:
                flag, = dualmode_pins.intersection(pnr.config)
                bel = db.grid[row][col].bels.setdefault("CFG", chipdb.Bel())
                bel.flags.setdefault(flag.upper(), set()).update(loc)
            except ValueError:
                bel = db.grid[row][col].bels.setdefault("BANK", chipdb.Bel())
                # in one file all iostd are same
                iostd = ''
                if pnr.attrs:
                    iostd = pnr.attrs[next(iter(pnr.attrs))].get('IO_TYPE', '')
                if iostd:
                    bel.bank_flags[iostd] = loc;
                else:
                    bel.modes["ENABLE"] = loc

    # Fill the IOB encodings from fse tables
    fse_pull_mode(fse, db, pin_locations)
    fse_slew_rate(fse, db, pin_locations)
    fse_hysteresis(fse, db, pin_locations)
    fse_drive(fse, db, pin_locations)

    chipdb.dat_portmap(dat, db)
    chipdb.dat_aliases(dat, db)
    chipdb.diff2flag(db)

    # must be after diff2flags in order to make clean mask for OPEN_DRAIN
    fse_open_drain(fse, db, pin_locations)
    chipdb.dff_clean(db)

    db.grid[0][0].bels['CFG'].flags['UNK0'] = {(3, 1)}
    db.grid[0][0].bels['CFG'].flags['UNK1'] = {(3, 2)}

    # set template dual-mode pins to HW mode
    for pin in dualmode_pins:
        try:
            loc, = db.grid[0][0].bels['CFG'].flags[pin.upper()]
        except KeyError:
            continue
        db.template[loc] = 0

    #TODO proper serialization format
    with open(f"{device}_stage1.pickle", 'wb') as f:
        pickle.dump(db, f)
