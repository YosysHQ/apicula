from dataclasses import dataclass
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
        "package": "LQ144",
        "header": 0,
        "device": "GW1NS-2C-LQ144-5",
        "partnumber": "GW1NS-UX2CLQ144C5/I4",
    },
    "GW1N-9": {
        "package": "PG256",
        "header": 0,
        "device": "GW1N-9-PBGA256-6",
        "partnumber": "GW1N-LV9PG256C6/I5",
    },
    "GW1N-4": {
        "package": "PG256",
        "header": 0,
        "device": "GW1N-4-PBGA256-6",
        "partnumber": "GW1N-LV4PG256C6/I5",
    },
    "GW1N-1": {
        "package": "LQ144",
        "header": 1, # stupid note in excel
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
                    cst.cells[lutname] = f"R{row}C{col}[{cls}][{side}]"
                    cst.cells[name] = f"R{row}C{col}[{cls}][{side}]"
        yield Fuzzer(ttyp, mod, cst, {}, '')

iobmap = {
    "IBUF": {"wires": ["O"], "inputs": ["I"]},
    "OBUF": {"wires": ["I"], "outputs": ["O"]},
    #"TBUF": {"wires": ["I", "OEN"], "outputs": ["O"]},
    "IOBUF": {"wires": ["I", "O", "OEN"], "inouts": ["IO"]},
}

iostandards = ["", "LVCMOS33", "LVCMOS18"]

AttrValues = namedtuple('ModeAttr', [
    'bank_dependent',   # attribute dependent of bank flags/standards
    'allowed_modes',    # allowed modes for the attribute
    'values'            # values of the attribute
    ])

iobattrs = {
 "HYSTERESIS" : AttrValues(False, ["IBUF", "IOBUF"],                ["NONE", "H2L", "L2H", "HIGH"]),
 "PULL_MODE"  : AttrValues(False, ["IBUF", "OBUF", "IOBUF", "TBUF"],["NONE", "UP", "DOWN", "KEEPER"]),
 "SLEW_RATE"  : AttrValues(False, ["OBUF", "IOBUF", "TBUF"],        ["SLOW", "FAST"]),
 "OPEN_DRAIN" : AttrValues(False, ["OBUF", "IOBUF", "TBUF"],        ["ON", "OFF"]),
 # bank-dependent
 "DRIVE"      : AttrValues(True, ["OBUF", "IOBUF", "TBUF"],        ["4", "8", "12", "16", "24"]),
 # no attributes, default mode
 "NULL"       : AttrValues(False, ["IBUF", "OBUF", "IOBUF", "TBUF"], [""]),
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

                        for attr_val in attr_values.values:         # each value of the attribute
                            # find the next location that has pin
                            # or make a new module
                            loc = find_next_loc(pin, locs)
                            if (loc == None):
                                # no usable tiles
                                yield Fuzzer(ttyp, mod, cst, {}, iostd)
                                if iostd == "":
                                    cnt[ttyp] += 1
                                locs = tiles.copy()
                                mod = codegen.Module()
                                cst = codegen.Constraints()
                                loc = find_next_loc(pin, locs)

                            name = make_name("IOB", typ)
                            iob = codegen.Primitive(typ, name)
                            for port in chain.from_iterable(conn.values()):
                                iob.portmap[port] = name+"_"+port

                            for direction, wires in conn.items():
                                wnames = [name+"_"+w for w in wires]
                                getattr(mod, direction).update(wnames)
                            mod.primitives[name] = iob
                            cst.ports[name] = loc
                            if attr != "NULL":
                                # port attribute value
                                cst.attrs[name] = {attr: attr_val}
                                # bank attribute
                                if iostd != "":
                                    cst.bank_attrs[name] = {"IO_TYPE": iostd}

            yield Fuzzer(ttyp, mod, cst, {}, iostd)
            if iostd == "":
                cnt[ttyp] += 1

    # insert dummie in the corners to detect the bank enable bits
    runs = cnt.most_common(1)[0][1]
    for _ in range(runs):
        for ttyp in corners:
            mod = codegen.Module()
            cst = codegen.Constraints()
            cfg = {}
            yield Fuzzer(ttyp, mod, cst, cfg, '')

dualmode_pins = {'jtag', 'sspi', 'mspi', 'ready', 'done', 'reconfig', 'mode'}
def dualmode(ttyp):
    for pin in dualmode_pins:
        mod = codegen.Module()
        cst = codegen.Constraints()
        cfg = {pin: 'false'}
        yield Fuzzer(ttyp, mod, cst, cfg, '')

def read_posp(fname):
    cst_parser = re.compile(r"([^ ]+) (?:PLACE|CST)_R(\d+)C(\d+)\[([0-3])\]\[([A-Z])\]")
    place_parser = re.compile(r"([^ ]+) (?:PLACE|CST)_IO([TBLR])(\d+)\[([A-Z])\]")
    with open(fname, 'r') as f:
        for line in f:
            cst = cst_parser.match(line)
            place = place_parser.match(line)
            if cst:
                name, row, col, cls, lut = cst.groups()
                yield "cst", name, int(row), int(col), int(cls), lut
            elif place:
                name, side, num, pin = place.groups()
                yield "place", name, side, int(num), pin
            elif line.strip() and not line.startswith('//'):
                raise Exception(line)

# Read the packer vendor log to identify problem with primitives/attributes
# One line of error log with contains primitive name like inst1_IOB_IBUF
LogLine = namedtuple('LogLine', [
    'line_type',    # line type: Info, Warning, Error
    'code',         # error/message code like (CT1108)
    'prim_name',    # name of primitive
    'text'          # full text of the line
    ])

# check if the primitive caused the warning/error
def primitive_caused_err(name, err_code, log):
    flt = filter(lambda el: el.prim_name == name and el.code == err_code, log)
    return next(flt, None) != None

def read_err_log(fname):
    err_parser = re.compile("(\w+) +\(([\w\d]+)\).*'(inst[^\']+)\'.*")
    errs = list()
    with open(fname, 'r') as f:
        for line in f:
            res = err_parser.match(line)
            if res:
                line_type, code, prim_name = res.groups()
                text = res.group(0)
                ll = LogLine(line_type, code, prim_name, text)
                errs.append(ll)
    return errs

# Result of the vendor router-packer run
PnrResult = namedtuple('PnrResult', [
    'bitmap', 'hdr', 'ftr',
    'posp',           # parsed Post-Place file
    'config',         # device config
    'attrs',          # port attributes
    'bank_attrs',     # per bank attributes
    'errs'            # parsed log file
    ])

def run_pnr(mod, constr, config):
    cfg = codegen.DeviceConfig({
        "JTAG regular_io": config.get('jtag', "true"),
        "SSPI regular_io": config.get('sspi', "true"),
        "MSPI regular_io": config.get('mspi', "true"),
        "READY regular_io": config.get('ready', "true"),
        "DONE regular_io": config.get('done', "true"),
        "RECONFIG_N regular_io": config.get('reconfig', "true"),
        "MODE regular_io": config.get('mode', "true"),
        "CRC_check": "true",
        "compress": "false",
        "encryption": "false",
        "security_bit_enable": "true",
        "bsram_init_fuse_print": "true",
        "download_speed": "250/100",
        "spi_flash_address": "0x00FFF000",
        "format": "txt",
        "background_programming": "false",
        "secure_mode": "false"})

    opt = codegen.PnrOptions(["posp", "warning_all", "oc", "ibs"])
            #"sdf", "oc", "ibs", "posp", "o",
            #"warning_all", "timing", "reg_not_in_iob"])

    pnr = codegen.Pnr()
    pnr.device = params['device']
    pnr.partnumber = params['partnumber']

    with tempfile.TemporaryDirectory() as tmpdir:
        pnr.outdir = tmpdir
        with open(tmpdir+"/top.v", "w") as f:
            mod.write(f)
        pnr.netlist = tmpdir+"/top.v"
        with open(tmpdir+"/top.cst", "w") as f:
            constr.write(f)
        pnr.cst = tmpdir+"/top.cst"
        with open(tmpdir+"/device.cfg", "w") as f:
            cfg.write(f)
        pnr.cfg = tmpdir+"/device.cfg"
        with open(tmpdir+"/pnr.cfg", "w") as f:
            opt.write(f)
        pnr.opt = tmpdir+"/pnr.cfg"
        with open(tmpdir+"/run.tcl", "w") as f:
            pnr.write(f)

        subprocess.run([gowinhome + "/IDE/bin/gw_sh", tmpdir+"/run.tcl"])
        #print(tmpdir); input()
        try:
            return PnrResult(
                    *bslib.read_bitstream(tmpdir+"/impl/pnr/top.fs"),
                    list(read_posp(tmpdir+"/impl/pnr/top.posp")),
                    config, constr.attrs, constr.bank_attrs,
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
    db.pinout = chipdb.xls_pinout(device)

    locations = {}
    for row, row_dat in enumerate(fse['header']['grid'][61]):
        for col, typ in enumerate(row_dat):
            locations.setdefault(typ, []).append((row, col))

    pin_names = pindef.get_locs(device, params['package'], True, params['header'])
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
    pnr_res = p.map(lambda param: run_pnr(*param), zip(modules, constrs, configs))

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
                if primitive_caused_err(name, "CT1108", pnr.errs): # skip bad primitives
                    continue
                    #input("Bad attribute ex")
                    #raise Exception(f"Bad attribute (CT1108):{name}")

                bel = db.grid[row][col].bels.setdefault(f"IOB{pin}", chipdb.Bel())
                pnr_attrs = pnr.attrs.get(name)
                if pnr_attrs != None:
                    mod_attr = list(pnr_attrs)[0]
                    mod_attr_val = pnr_attrs[mod_attr]
                    if list(pnr.bank_attrs): # all bank attrs are equal
                        mod_attr = pnr.bank_attrs[name]["IO_TYPE"] + chipdb.bank_attr_sep + mod_attr
                    bel.modes[f"{cell_type}&{mod_attr}={mod_attr_val}"] = loc;
                else:
                    bel.modes[f"{cell_type}_DEFAULT"] = loc;
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

            try:
                flag, = dualmode_pins.intersection(pnr.config)
                bel = db.grid[row][col].bels.setdefault("CFG", chipdb.Bel())
                bel.flags.setdefault(flag.upper(), set()).update(loc)
            except ValueError:
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
