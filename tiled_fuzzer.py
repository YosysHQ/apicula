import re
import os
import tempfile
import subprocess
from collections import deque
from itertools import chain, count, zip_longest
from random import shuffle, seed
from warnings import warn
from math import factorial
import numpy as np
from multiprocessing.dummy import Pool
import pickle

import codegen
import bslib
import pindef
import fuse_h4x
#TODO proper API
#import dat19_h4x
import json
import chipdb

import sys, pdb

gowinhome = os.getenv("GOWINHOME")
if not gowinhome:
    raise Exception("GOWINHOME not set")

device = os.getenv("DEVICE")
if not device:
    raise Exception("DEVICE not set")

params = {
    "GW1NR-9": {
        "package": "QN881",
        "header": 1, # stupid note in excel
        "device": "GW1NR-9-QFN88-6",
        "partnumber": "GW1NR-LV9QN88C6/I5",
    },
    "GW1N-1": {
        "package": "QN48",
        "header": 0,
        "device": "GW1N-1-QFN48-6",
        "partnumber": "GW1N-LV1QN48C6/I5",
    },
}[device]

name_idx = 0
def make_name(bel, typ):
    global name_idx
    name_idx += 1
    return f"inst{name_idx}_{bel}_{typ}"


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
    for ttyp in range(12, 17): # for each tile type
        mod = codegen.Module()
        cst = codegen.Constraints()
        try:
            # get all tiles of this type
            # iter causes the loop to not repeat the same locs per cls
            locs = iter(locations[ttyp])
        except KeyError:
            continue

        for cls in range(3): # for each cls
            for typ, port in dffmap.items(): # for each bel type
                try:
                    loc = next(locs) # get the next unused tile
                except StopIteration:
                    yield ttyp, mod, cst
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
                cst.cells[lutname] = f"R{row}C{col}[{cls}]"
                cst.cells[name] = f"R{row}C{col}[{cls}]"
        yield ttyp, mod, cst

iobmap = {
    "IBUF": {"wires": ["O"], "inputs": ["I"]},
    "OBUF": {"wires": ["I"], "outputs": ["O"]},
    #"TBUF": {"wires": ["I", "OEN"], "outputs": ["O"]},
    "IOBUF": {"wires": ["I", "O", "OEN"], "inouts": ["IO"]},
}
def iob(locations):
    for ttyp, tiles in locations.items(): # for each tile of this type
        mod = codegen.Module()
        cst = codegen.Constraints()
        # get bels in this ttyp
        bels = {name[-1] for loc in tiles.values() for name in loc}
        locs = tiles.copy()
        for pin in bels: # [A, B, C, D, ...]
            for typ, conn in iobmap.items():
                # find the next location that has pin
                # or make a new module
                for tile, names in locs.items():
                    name = tile+pin
                    if name in names:
                        del locs[tile]
                        loc = name
                        break
                else: # no usable tiles
                    yield ttyp, mod, cst
                    locs = tiles.copy()
                    mod = codegen.Module()
                    cst = codegen.Constraints()
                    for tile, names in locs.items():
                        name = tile+pin
                        if name in names:
                            del locs[tile]
                            loc = name
                            break

                name = make_name("IOB", typ)
                iob = codegen.Primitive(typ, name)
                for port in chain.from_iterable(conn.values()):
                    iob.portmap[port] = name+"_"+port

                for direction, wires in conn.items():
                    wnames = [name+"_"+w for w in wires]
                    getattr(mod, direction).update(wnames)
                mod.primitives[name] = iob
                cst.ports[name] = loc

            yield ttyp, mod, cst


def read_posp(fname):
    cst_parser = re.compile(r"(\w+) CST_R(\d+)C(\d+)\[([0-3])\]\[([A-Z])\]")
    place_parser = re.compile(r"(\w+) (?:PLACE|CST)_IO([TBLR])(\d+)\[([A-Z])\]")
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


def run_pnr(mod, constr):
    cfg = codegen.DeviceConfig({
        "JTAG regular_io": "true",
        "SSPI regular_io": "true",
        "MSPI regular_io": "true",
        "READY regular_io": "true",
        "DONE regular_io": "true",
        "RECONFIG_N regular_io": "true",
        "MODE regular_io": "true",
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

    opt = codegen.PnrOptions(["posp", "warning_all"])
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
            return (*bslib.read_bitstream(tmpdir+"/impl/pnr/top.fs"), \
                   list(read_posp(tmpdir+"/impl/pnr/top.posp")))
        except FileNotFoundError:
            print(tmpdir)
            input()
            return None, None

if __name__ == "__main__":
    with open(f"{gowinhome}/IDE/share/device/{device}/{device}.fse", 'rb') as f:
        fse = fuse_h4x.readFse(f)

    with open(f"{device}.json") as f:
        dat = json.load(f)

    db = chipdb.from_fse(fse)

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

    modmap = {}
    cstmap = {}
    # Add fuzzers here
    fuzzers = chain(
        iob(pin_locations),
        dff(locations),
    )
    for ttyp, mod, cst in fuzzers:
        modmap.setdefault(ttyp, []).append(mod)
        cstmap.setdefault(ttyp, []).append(cst)

    modules = [sum(m, start=codegen.Module())
               for m in zip_longest(*modmap.values(), fillvalue=codegen.Module())]
    constrs = [sum(c, start=codegen.Constraints())
               for c in zip_longest(*cstmap.values(), fillvalue=codegen.Constraints())]

    type_re = re.compile(r"inst\d+_([A-Z]+)_([A-Z]+)")

    empty, hdr, ftr, posp = run_pnr(codegen.Module(), codegen.Constraints())
    db.cmd_hdr = hdr
    db.cmd_ftr = ftr
    db.template = empty
    p = Pool()
    pnr_res = p.map(lambda param: run_pnr(*param), zip(modules, constrs))

    for bitmap, hdr, ftr, posp in pnr_res:
        seen = {}
        diff = bitmap ^ empty
        bm = fuse_h4x.tile_bitmap(fse, diff)
        for cst_type, name, *info in posp:
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
            for bitrow in tile:
                print(*bitrow, sep='')

            rows, cols = np.where(tile==1)
            loc = set(zip(rows, cols))
            print(cell_type, loc)

            if bel_type == "DUMMY":
                continue
            elif bel_type == "DFF":
                for i in range(2): # 2 DFF per CLS
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
                    bel.modes[cell_type] = loc
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
            bel = db.grid[row][col].bels.setdefault("BANK", chipdb.Bel())
            #TODO fuzz modes
            bel.modes.setdefault("DEFAULT", set()).update(loc)

    chipdb.dat_portmap(dat, db)
    chipdb.dat_aliases(dat, db)
    chipdb.shared2flag(db)
    #TODO proper serialization format
    with open(f"{device}.pickle", 'wb') as f:
        pickle.dump(db, f)
