import re
import os
import tempfile
import subprocess
from collections import deque
from itertools import chain, count
from random import shuffle, seed
from warnings import warn
from math import factorial
import numpy as np
from multiprocessing.dummy import Pool

import codegen
import bslib
import pindef
import fuse_h4x
import gowin_unpack
import chipdb

import sys, pdb

gowinhome = os.getenv("GOWINHOME")
if not gowinhome:
    raise "GOWINHOME not set"

device = os.getenv("DEVICE")
if not device:
    raise "DEVICE not set"

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
def dff(mod, cst, locations):
    for ttyp in range(12, 17):
        # iter causes the loop to not repeat the same locs per cls
        locs = iter(locations[ttyp])
        for cls in range(3):
            for loc, typ, port in zip(locs, dffmap.keys(), dffmap.values()):
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

def iob(mod, cst, loc):
    iobmap = {
        "IBUF": {"wires": ["O"], "inputs": ["I"]},
        "OBUF": {"wires": ["I"], "outputs": ["O"]},
        "TBUF": {"wires": ["I", "OEN"], "outputs": ["O"]},
        "IOBUF": {"wires": ["I", "O", "OEN"], "inouts": ["IO"]},
    }
    for typ, conn in iobmap.items():
        name = make_name(typ)
        iob = codegen.Primitive(typ, name)
        for port in chain.from_iterable(conn.values()):
            iob.portmap[port] = name+"_"+port

        for direction, wires in conn.items():
            wnames = [name+"_"+w for w in wires]
            getattr(mod, direction).update(wnames)
        mod.primitives[name] = iob



def read_posp(fname):
    cst_parser = re.compile(r"(\w+) CST_R(\d+)C(\d+)\[([0-3])\]\[([AB])\]")
    place_parser = re.compile(r"(\w+) PLACE_IO([TBLR])(\d+)\[([AB])\]")
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


def run_pnr(mod, constr):
    cfg = codegen.DeviceConfig({
        "JTAG regular_io": "false",
        "SSPI regular_io": "false",
        "MSPI regular_io": "false",
        "READY regular_io": "false",
        "DONE regular_io": "false",
        "RECONFIG_N regular_io": "false",
        "MODE regular_io": "false",
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

    opt = codegen.PnrOptions(["posp"])
            #"sdf", "oc", "ibs", "posp", "o",
            #"warning_all", "timing", "reg_not_in_iob"])

    pnr = codegen.Pnr()
    pnr.device = "GW1NR-9-QFN88-6"
    pnr.partnumber = "GW1NR-LV9QN88C6/I5"

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
            return bslib.read_bitstream(tmpdir+"/impl/pnr/top.fs")[0], \
                   list(read_posp(tmpdir+"/impl/pnr/top.posp"))
        except FileNotFoundError:
            print(tmpdir)
            input()
            return None

fuzzers = [dff]

if __name__ == "__main__":
    with open(gowinhome + "/IDE/share/device/GW1NR-9/GW1NR-9.fse", 'rb') as f:
        fse = fuse_h4x.readFse(f)

    db = chipdb.from_fse(fse)

    mod = codegen.Module()
    cst = codegen.Constraints()
    locations = {}
    for row, dat in enumerate(fse['header']['grid'][61]):
        for col, typ in enumerate(dat):
            locations.setdefault(typ, []).append((row, col))

    for fz in fuzzers:
        fz(mod, cst, locations)

    bitmap, posp = run_pnr(mod, cst)
    type_re = re.compile(r"inst\d+_([A-Z]+)_([A-Z]+)")
    #bitmap = bslib.read_bitstream("empty.fs")[0]
    #posp = []
    bm = gowin_unpack.tile_bitmap(fse, bitmap)
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

        tile = bm[idx]
        #for bitrow in tile:
        #    print(*bitrow, sep='')

        rows, cols = np.where(tile==1)
        loc = list(zip(rows, cols))
        print(cell_type, loc)

        if bel_type == "DUMMY":
            continue
        elif bel_type == "DFF":
            for i in range(2): # 2 DFF per CLS
                bel = db.grid[row][col].bels.setdefault(f"DFF{cls}", chipdb.Bel())
                bel.modes[cell_type] = loc
                bel.portmap = {
                    # D inputs hardwired to LUT F
                    'Q': chipdb.Wire(f"Q{cls*2+i}"),
                    'CLK': chipdb.Wire(f"CLK{cls}"),
                    'LSR': chipdb.Wire(f"LSR{cls}"), # set/reset
                    'CE': chipdb.Wire(f"CE{cls}"), # clock enable
                }
        else:
            raise ValueError(f"Type {bel_type} not handled")

    # corner tiles for bank enable
    print("### CORNER TILES ###")
    # TODO
