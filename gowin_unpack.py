import sys
import os
import re
import random
import numpy as np
from itertools import chain, count
import pickle
import codegen
import chipdb
from bslib import read_bitstream
from wirenames import wirenames

device = os.getenv("DEVICE")
if not device:
    raise Exception("DEVICE not set")

def parse_tile(tiledata, tile):
    bels = {}
    for name, bel in tiledata.bels.items():
        for flag, bits in bel.flags.items():
            used_bits = {tile[row][col] for row, col in bits}
            if all(used_bits):
                bels.setdefault(name, set()).add(flag)
        mode_bits = {(row, col)
                     for row, col in bel.mode_bits
                     if tile[row][col] == 1}
        for mode, bits in bel.modes.items():
            if bits == mode_bits:
                bels.setdefault(name, set()).add(mode)

    pips = {}
    for dest, srcs in tiledata.pips.items():
        pip_bits = set().union(*srcs.values())
        used_bits = {(row, col)
                     for row, col in pip_bits
                     if tile[row][col] == 1}
        for src, bits in srcs.items():
            if bits == used_bits:
                pips[dest] = src

    return bels, pips


def wire2global(row, col, fse, name):
    width = len(fse['header']['grid'][61][0])
    height = len(fse['header']['grid'][61])
    if name.startswith("G") or name in {'VCC', 'VSS'}:
        # global wire
        return name

    m = re.match(r"([NESW])([128]\d)(\d)", name)
    if not m:
        # local wire
        return f"R{row}C{col}_{name}"

    # inter-tile wire
    dirlut = {'N': (1, 0),
              'E': (0, -1),
              'S': (-1, 0),
              'W': (0, 1)}
    uturnlut = {'N': 'S', 'S': 'N', 'E': 'W', 'W': 'E'}
    direction, wire, segment = m.groups()
    rootrow = row + dirlut[direction][0]*int(segment)
    rootcol = col + dirlut[direction][1]*int(segment)
    # wires wrap around the edges
    if rootrow < 1:
        rootrow = 1 - rootrow
        direction = uturnlut[direction]
    if rootcol < 1:
        rootcol = 1 - rootcol
        direction = uturnlut[direction]
    if rootrow > height:
        rootrow = 2*height+1 - rootrow
        direction = uturnlut[direction]
    if rootcol > width:
        rootcol = 2*width+1 - rootcol
        direction = uturnlut[direction]
    # map cross wires to their origin
    diaglut = {
        'E11': 'EW10',
        'W11': 'EW10',
        'E12': 'EW20',
        'W12': 'EW20',
        'S11': 'SN10',
        'N11': 'SN10',
        'S12': 'SN20',
        'N12': 'SN20',
    }
    name = diaglut.get(direction+wire, direction+wire)
    return f"R{rootrow}C{rootcol}_{name}"

def tile2verilog(row, col, td, mod, fse):
    # fse is 0-based, floorplanner is 1-based
    row += 1
    col += 1
    wires = parse_wires(td)
    for src, dest in wires:
        srcg = wire2global(row, col, fse, src)
        destg = wire2global(row, col, fse, dest)
        mod.wires.update({srcg, destg})
        mod.assigns.append((destg, srcg))

    luts = parse_luts(td)
    for idx, val in luts.items():
        name = f"R{row}C{col}_LUT4_{idx}"
        lut = codegen.Primitive("LUT4", name)
        lut.params["INIT"] = f"16'b{val:016b}"
        lut.portmap['F'] = f"R{row}C{col}_F{idx}"
        lut.portmap['I0'] = f"R{row}C{col}_A{idx}"
        lut.portmap['I1'] = f"R{row}C{col}_B{idx}"
        lut.portmap['I2'] = f"R{row}C{col}_C{idx}"
        lut.portmap['I3'] = f"R{row}C{col}_D{idx}"
        mod.wires.update(lut.portmap.values())
        mod.primitives[name] = lut

    dffs = parse_dffs(td)
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
    for idx, typ in enumerate(dffs):
        #print(idx, typ)
        if typ:
            port = dffmap[typ]
            lutidx = idx*2
            name = f"R{row}C{col}_{typ}E_{idx}_A"
            dff = codegen.Primitive(typ+"E", name)
            dff.portmap['CLK'] = f"R{row}C{col}_CLK{idx}"
            dff.portmap['D'] = f"R{row}C{col}_F{lutidx}"
            dff.portmap['Q'] = f"R{row}C{col}_Q{lutidx}"
            dff.portmap['CE'] = f"R{row}C{col}_CE{idx}"
            if port:
                dff.portmap[port] = f"R{row}C{col}_LSR{idx}"
            mod.wires.update(dff.portmap.values())
            mod.primitives[name] = dff

            lutidx = idx*2+1
            name = f"R{row}C{col}_{typ}E_{idx}_B"
            dff = codegen.Primitive(typ+"E", name)
            dff.portmap['CLK'] = f"R{row}C{col}_CLK{idx}"
            dff.portmap['D'] = f"R{row}C{col}_F{lutidx}"
            dff.portmap['Q'] = f"R{row}C{col}_Q{lutidx}"
            dff.portmap['CE'] = f"R{row}C{col}_CE{idx}"
            if port:
                dff.portmap[port] = f"R{row}C{col}_LSR{idx}"
            mod.wires.update(dff.portmap.values())
            mod.primitives[name] = dff

    iob = parse_iob(td)
    iobmap = {
        "IBUF": {"wires": ["O"], "inputs": ["I"]},
        "OBUF": {"wires": ["I"], "outputs": ["O"]},
        "TBUF": {"wires": ["I", "OEN"], "outputs": ["O"]},
        "IOBUF": {"wires": ["I", "O", "OEN"], "inouts": ["IO"]},
    }
    portmap = {
        ('I', 0): 'A0',
        ('OEN', 0): 'B0',
        ('O', 0): 'F6',
        ('I', 1): 'D1',
        ('OEN', 1): 'D5',
        ('O', 1): 'Q6',
    }
    for idx, typ in enumerate(iob):
        #print(idx, typ)
        if typ:
            name = f"R{row}C{col}_{typ}_{idx}"
            wires = set(iobmap[typ]['wires'])
            ports = set(chain.from_iterable(iobmap[typ].values())) - wires

            iob = codegen.Primitive(typ, name)

            for port in wires:
                wname = portmap[(port, idx)]
                iob.portmap[port] = f"R{row}C{col}_{wname}"

            for port in ports:
                iob.portmap[port] = f"R{row}C{col}_{port}{idx}"

            for wires in iobmap[typ]['wires']:
                wnames = [f"R{row}C{col}_{portmap[(w, idx)]}" for w in wires]
                mod.wires.update(wnames)
            for direction in ['inputs', 'outputs', 'inouts']:
                for wires in iobmap[typ].get(direction, []):
                    wnames = [f"R{row}C{col}_{w}{idx}" for w in wires]
                    getattr(mod, direction).update(wnames)

            mod.primitives[name] = iob

    gnd = codegen.Primitive("GND", "mygnd")
    gnd.portmap["G"] = "VSS"
    mod.primitives["mygnd"] = gnd
    vcc = codegen.Primitive("VCC", "myvcc")
    vcc.portmap["V"] = "VCC"
    mod.primitives["myvcc"] = vcc


if __name__ == "__main__":
    with open(f"{device}.pickle", 'rb') as f:
        db = pickle.load(f)
    bitmap = read_bitstream(sys.argv[1])[0]
    bm = chipdb.tile_bitmap(db, bitmap)
    mod = codegen.Module()
    for idx, t in bm.items():
        row, col = idx
        dbtile = db.grid[row][col]
        #if idx == (10, 9):
        #    from fuse_h4x import *
        #    fse = readFse(open("/home/pepijn/bin/gowin/IDE/share/device/GW1N-1/GW1N-1.fse", 'rb'))
        #    breakpoint()
        print(idx)
        bels, pips = parse_tile(dbtile, t)
        print(bels)
        #print(pips)
        #for bitrow in t:
        #    print(*bitrow, sep='')
        #tile2verilog(row, col, td, mod, d)
    with open("unpack.v", 'w') as f:
        mod.write(f)

