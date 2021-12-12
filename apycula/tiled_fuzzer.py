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

# device = os.getenv("DEVICE")
device = sys.argv[1]

params = {
    "GW1NS-2": {
        "package": "LQFP144",
        "device": "GW1NS-2C-LQ144-5",
        "partnumber": "GW1NS-UX2CLQ144C5/I4",
    },
    "GW1NS-4": {
        "package": "MBGA64",
        "device": "GW1NS-4C-MBGA64-6",
        "partnumber": "GW1NS-LV4CMG64C6/I5",
    },
    "GW1N-9": {
        "package": "PBGA256",
        "device": "GW1N-9-PBGA256-6",
        "partnumber": "GW1N-LV9PG256C6/I5",
    },
    "GW1N-4": {
        "package": "PBGA256",
        "device": "GW1N-4-PBGA256-6",
        "partnumber": "GW1N-LV4PG256C6/I5",
    },
    "GW1N-1": {
        "package": "LQFP144",
        "device": "GW1N-1-LQFP144-6",
        "partnumber": "GW1N-LV1LQ144C6/I5",
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

def is_illegal(pin, attr):
    if _illegal_combo.get((pin, attr)) == device:
        return True
    # GW1N-1, GW1NS-2, GW1N-4 and GW1N-9 allow single resisor only in banks 1/3
    if (attr == "SINGLE_RESISTOR") and (pin[2] in "BT"):
        return True
    return False

# take TBUF == IOBUF - O
iobmap = {
    "IBUF": {"wires": ["O"], "inputs": ["I"]},
    "OBUF": {"wires": ["I"], "outputs": ["O"]},
    "IOBUF": {"wires": ["I", "O", "OEN"], "inouts": ["IO"]},
}

iostd_drive = {
            ""            : ["4", "8", "12"],
            "LVTTL33"     : ["4", "8", "12", "16", "24"],
            "LVCMOS33"    : ["4", "8", "12", "16", "24"],
            "LVCMOS25"    : ["4", "8", "12", "16"],
            "LVCMOS18"    : ["4", "8", "12"],
            "LVCMOS15"    : ["4", "8"],
            "LVCMOS12"    : ["4", "8"],
            "SSTL25_I"    : ["8"],
            "SSTL25_II"   : ["8"],
            "SSTL33_I"    : ["8"],
            "SSTL33_II"   : ["8"],
            "SSTL18_I"    : ["8"],
            "SSTL18_II"   : ["8"],
            "SSTL15"      : ["8"],
            "HSTL18_I"    : ["8"],
            "HSTL18_II"   : ["8"],
            "HSTL15_I"    : ["8"],
            "PCI33"       : [],
        }
iostd_open_drain = {
            ""            : ["ON", "OFF"],
            "LVTTL33"     : ["ON", "OFF"],
            "LVCMOS33"    : ["ON", "OFF"],
            "LVCMOS25"    : ["ON", "OFF"],
            "LVCMOS18"    : ["ON", "OFF"],
            "LVCMOS15"    : ["ON", "OFF"],
            "LVCMOS12"    : ["ON", "OFF"],
            "SSTL25_I"    : [],
            "SSTL25_II"   : [],
            "SSTL33_I"    : [],
            "SSTL33_II"   : [],
            "SSTL18_I"    : [],
            "SSTL18_II"   : [],
            "SSTL15"      : [],
            "HSTL18_I"    : [],
            "HSTL18_II"   : [],
            "HSTL15_I"    : [],
            "PCI33"       : [],
        }
iostd_histeresis = {
            ""            : ["NONE", "H2L", "L2H", "HIGH"],
            "LVTTL33"     : ["NONE", "H2L", "L2H", "HIGH"],
            "LVCMOS33"    : ["NONE", "H2L", "L2H", "HIGH"],
            "LVCMOS25"    : ["NONE", "H2L", "L2H", "HIGH"],
            "LVCMOS18"    : ["NONE", "H2L", "L2H", "HIGH"],
            "LVCMOS15"    : ["NONE", "H2L", "L2H", "HIGH"],
            "LVCMOS12"    : ["NONE", "H2L", "L2H", "HIGH"],
            "SSTL25_I"    : [],
            "SSTL25_II"   : [],
            "SSTL33_I"    : [],
            "SSTL33_II"   : [],
            "SSTL18_I"    : [],
            "SSTL18_II"   : [],
            "SSTL15"      : [],
            "HSTL18_I"    : [],
            "HSTL18_II"   : [],
            "HSTL15_I"    : [],
            "PCI33"       : ["NONE", "H2L", "L2H", "HIGH"],
        }
iostd_pull_mode = {
            ""            : ["NONE", "UP", "DOWN", "KEEPER"],
            "LVTTL33"     : ["NONE", "UP", "DOWN", "KEEPER"],
            "LVCMOS33"    : ["NONE", "UP", "DOWN", "KEEPER"],
            "LVCMOS25"    : ["NONE", "UP", "DOWN", "KEEPER"],
            "LVCMOS18"    : ["NONE", "UP", "DOWN", "KEEPER"],
            "LVCMOS15"    : ["NONE", "UP", "DOWN", "KEEPER"],
            "LVCMOS12"    : ["NONE", "UP", "DOWN", "KEEPER"],
            "SSTL25_I"    : [],
            "SSTL25_II"   : [],
            "SSTL33_I"    : [],
            "SSTL33_II"   : [],
            "SSTL18_I"    : [],
            "SSTL18_II"   : [],
            "SSTL15"      : [],
            "HSTL18_I"    : [],
            "HSTL18_II"   : [],
            "HSTL15_I"    : [],
            "PCI33"       : [],
        }

iostandards = ["", "LVCMOS18", "LVCMOS33", "LVCMOS25", "LVCMOS15", "LVCMOS12",
      "SSTL25_I", "SSTL33_I", "SSTL15", "HSTL18_I", "PCI33"]

AttrValues = namedtuple('ModeAttr', [
    'allowed_modes',    # allowed modes for the attribute
    'values',           # values of the attribute
    'table',            # special values table
    ])

iobattrs = {
 "IO_TYPE"    : AttrValues(["IBUF", "OBUF", "IOBUF"], [""], None),
 "OPEN_DRAIN" : AttrValues([        "OBUF", "IOBUF"], None, iostd_open_drain),
 "HYSTERESIS" : AttrValues(["IBUF",         "IOBUF"], None, iostd_histeresis),
 "PULL_MODE"  : AttrValues(["IBUF", "OBUF", "IOBUF"], None, iostd_pull_mode),
 "SLEW_RATE"  : AttrValues([        "OBUF", "IOBUF"], ["SLOW", "FAST"], None),
 "DRIVE"      : AttrValues([        "OBUF", "IOBUF"], None, iostd_drive),
 "SINGLE_RESISTOR" : AttrValues(["IBUF", "IOBUF"], ["ON", "OFF"], None),
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
                    if iostd == "PCI33" and attr == "SINGLE_RESISTOR":
                        continue
                    attr_vals = attr_values.values
                    # drive is special
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
                            if is_illegal(loc, attr):
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
                side, numx, pin = info
                num = int(numx)
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
                if cell_type == "IOBUF":
                    loc -= route_bits(db, row, col)
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

    chipdb.dat_portmap(dat, db)
    chipdb.dat_aliases(dat, db)
    chipdb.diff2flag(db)
    chipdb.dff_clean(db)
    # XXX not used for IOB but...
    #chipdb.shared2flag(db)

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
