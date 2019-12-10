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


def wire2global(row, col, db, wire):
    if wire.name.startswith("G") or wire.name in {'VCC', 'VSS'}:
        # global wire
        return wire.name

    m = re.match(r"([NESW])([128]\d)", wire.name)
    if not m: # not an inter-tile wire
        return f"R{row}C{col}_{wire.name}"
    direction, num = m.groups()

    rootrow = row + wire.offset[0]
    rootcol = col + wire.offset[1]
    # wires wrap around the edges
    uturnlut = {'N': 'S', 'S': 'N', 'E': 'W', 'W': 'E'}
    if rootrow < 1:
        rootrow = 1 - rootrow
        direction = uturnlut[direction]
    if rootcol < 1:
        rootcol = 1 - rootcol
        direction = uturnlut[direction]
    if rootrow > db.rows:
        rootrow = 2*db.rows+1 - rootrow
        direction = uturnlut[direction]
    if rootcol > db.cols:
        rootcol = 2*db.cols+1 - rootcol
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
    name = diaglut.get(direction+num, direction+num)
    return f"R{rootrow}C{rootcol}_{name}"


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
iobmap = {
    "IBUF": {"wires": ["O"], "inputs": ["I"]},
    "OBUF": {"wires": ["I"], "outputs": ["O"]},
    "IOBUF": {"wires": ["I", "O", "OEN"], "inouts": ["IO"]},
}
def tile2verilog(dbrow, dbcol, bels, pips, mod, db):
    # db is 0-based, floorplanner is 1-based
    row = dbrow+1
    col = dbcol+1
    for dest, src in pips.items():
        srcg = wire2global(row, col, db, src)
        destg = wire2global(row, col, db, dest)
        mod.wires.update({srcg, destg})
        mod.assigns.append((destg, srcg))

    belre = re.compile(r"(IOB|LUT|DFF|BANK)(\w*)")
    for bel, flags in bels.items():
        typ, idx = belre.match(bel).groups()

        if typ == "LUT":
            val = sum(1<<f for f in flags)
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
        elif typ == "DFF":
            kind, = flags # DFF only have one flag
            idx = int(idx)
            port = dffmap[kind]
            name = f"R{row}C{col}_{typ}E_{idx}"
            dff = codegen.Primitive(kind+"E", name)
            dff.portmap['CLK'] = f"R{row}C{col}_CLK{idx//2}"
            dff.portmap['D'] = f"R{row}C{col}_F{idx}"
            dff.portmap['Q'] = f"R{row}C{col}_Q{idx}"
            dff.portmap['CE'] = f"R{row}C{col}_CE{idx//2}"
            if port:
                dff.portmap[port] = f"R{row}C{col}_LSR{idx//2}"
            mod.wires.update(dff.portmap.values())
            mod.primitives[name] = dff

        elif typ == "IOB":
            kind, = flags # IOB only have one flag
            portmap = db.grid[dbrow][dbcol].bels[bel].portmap
            name = f"R{row}C{col}_{kind}_{idx}"
            wires = set(iobmap[kind]['wires'])
            ports = set(chain.from_iterable(iobmap[kind].values())) - wires

            iob = codegen.Primitive(kind, name)

            for port in wires:
                wname = portmap[port].name
                iob.portmap[port] = f"R{row}C{col}_{wname}"

            for port in ports:
                iob.portmap[port] = f"R{row}C{col}_{port}{idx}"

            for wires in iobmap[kind]['wires']:
                wnames = [f"R{row}C{col}_{portmap[w].name}" for w in wires]
                mod.wires.update(wnames)
            for direction in ['inputs', 'outputs', 'inouts']:
                for wires in iobmap[kind].get(direction, []):
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
        print(idx)
        bels, pips = parse_tile(dbtile, t)
        print(bels)
        #print(pips)
        #for bitrow in t:
        #    print(*bitrow, sep='')
        #if idx == (8, 7):
        #    from fuse_h4x import *
        #    fse = readFse(open("/home/pepijn/bin/gowin/IDE/share/device/GW1N-1/GW1N-1.fse", 'rb'))
        #    breakpoint()
        tile2verilog(row, col, bels, pips, mod, db)
    with open("unpack.v", 'w') as f:
        mod.write(f)

