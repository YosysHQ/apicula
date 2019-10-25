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

import sys, pdb

name_idx = 0
def make_name(typ):
    global name_idx
    name_idx += 1
    return f"my{typ}{name_idx}"


def dff(mod, cst):
    dffmap = {
        "DFFE": None,
        "DFFSE": "SET",
        "DFFRE": "RESET",
        "DFFPE": "PRESET",
        "DFFCE": "CLEAR",
        "DFFNSE": "SET",
        "DFFNRE": "RESET",
        "DFFNPE": "PRESET",
        "DFFNCE": "CLEAR",
    }
    col = 2
    for typ, port in dffmap.items():
        name = make_name(typ)
        #yield name
        dff = codegen.Primitive(typ, name)
        dff.portmap['CLK'] = name+"_CLK"
        dff.portmap['D'] = name+"_F"
        dff.portmap['Q'] = name+"_Q"
        dff.portmap['CE'] = name+"_CE"
        if port:
            dff.portmap[port] = name+"_"+port
        mod.wires.update(dff.portmap.values())
        mod.primitives[name] = dff
        cst.cells[name] = f"R2C{col}"
        col += 1

def iob(mod, cst):
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
        subprocess.run(["/home/pepijn/bin/gowin/IDE/bin/gw_sh", tmpdir+"/run.tcl"])
        print(tmpdir); input()
        try:
            return bslib.read_bitstream(tmpdir+"/impl/pnr/top.fs"), \
                   list(read_posp(tmpdir+"/impl/pnr/top.posp"))
        except FileNotFoundError:
            print(tmpdir)
            input()
            return None

fuzzers = [dff, iob]

if __name__ == "__main__":
    with open("/home/pepijn/bin/gowin/IDE/share/device/GW1NR-9/GW1NR-9.fse", 'rb') as f:
        fse = fuse_h4x.readFse(f)

    mod = codegen.Module()
    cst = codegen.Constraints()
    locations = {}
    for row, dat in enumerate(fse['header']['grid'][61]):
        for col, typ in enumerate(dat):
            locations.setdefault(typ, []).append((row, col, typ))

    for fz in fuzzers:
        fz(mod, cst)

    bitmap, posp = run_pnr(mod, cst)
    bm = gowin_unpack.tile_bitmap(fse, bitmap)
    for cst_type, name, *info in posp:
        if cst_type == "cst":
            row, col, cls, lut = info
            typ = fse['header']['grid'][61][row-1][col-1]
            idx = (row-1, col-1, typ)
            tile = bm[idx]
            print(name, idx)
            #td = gowin_unpack.parse_tile(fse, typ, tile)
            #print(td.keys())
            #print(gowin_unpack.parse_wires(td))
            #print(gowin_unpack.parse_luts(td))
            #for bitrow in tile:
            #    print(*bitrow, sep='')
            fuses = gowin_unpack.scan_fuses(fse, typ, tile)
            gowin_unpack.scan_tables(fse, typ, fuses)
        elif cst_type == "place":
            print(info)


