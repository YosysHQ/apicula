import sys
import os
import json
from itertools import chain
import re
import code
sys.path.append(os.path.join(sys.path[0], '..'))
from wirenames import wirenames
import fuse_h4x as fuse

gowinhome = os.getenv("GOWINHOME")
if not gowinhome:
    raise "GOWINHOME not set"

with open("../dat.json") as f:
    data = json.load(f)

with open(gowinhome+'/IDE/share/device/GW1NR-9/GW1NR-9.fse', 'rb') as f:
    fse = fuse.readFse(f)

grid = fse['header']['grid'][61]
width = len(grid[0])
height = len(grid)

def wire2global(row, col, height, width, name):
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
    return f"R{rootrow}C{rootcol}_{direction}{wire}"

def addWire(row, col, num):
    try:
        name = wirenames[num]
    except KeyError:
        return
    gname = wire2global(row, col, height, width, name)
    print("wire", gname)
    try:
        ctx.addWire(name=gname, type=name, y=row, x=col)
    except AssertionError:
        pass
        print("duplicate wire")

for row, rowdata in enumerate(grid, 1):
    for col, ttyp in enumerate(rowdata, 1):
        # add wires
        wires = {abs(w) for fs in fse[ttyp]['wire'][2] for w in fs[:2]}
        for wire in wires:
            addWire(row, col, wire)
        # add aliasses
        # creat bels
        print(row, col, ttyp)
        if ttyp in {12, 13, 14, 15, 16, 17}:
            for z in range(6): # TODO 3rd CLS has no DFF, add constraint
                belname = f"R{row}C{col}_SLICE{z}"
                clkname = f"R{row}C{col}_CLK{z//2}"
                fname = f"R{row}C{col}_F{z}"
                qname = f"R{row}C{col}_Q{z}"
                print("IOB", row, col, clkname, fname, qname)
                ctx.addBel(name=belname, type="GENERIC_SLICE", loc=Loc(col, row, z), gb=False)
                ctx.addBelInput(bel=belname, name="CLK", wire=clkname)
                for k, n in [('A', 'I[0]'), ('B', 'I[1]'),
                               ('C', 'I[2]'), ('D', 'I[3]')]:
                    inpname = f"R{row}C{col}_{k}{z}"
                    ctx.addBelInput(bel=belname, name=n, wire=inpname)
                ctx.addBelOutput(bel=belname, name="Q", wire=qname)
                ctx.addBelOutput(bel=belname, name="F", wire=fname)

        elif ttyp in {52, 53, 58, 63, 64, 65, 66}:
            for z, side in enumerate(['A', 'B']):
                belname = f"R{row}C{col}_IOB{z}"
                inp = wirenames[data[f"Iobuf{side}In"]]
                outp = wirenames[data[f"Iobuf{side}Out"]]
                oe = wirenames[data[f"Iobuf{side}OE"]]
                iname = f"R{row}C{col}_{inp}"
                oname = f"R{row}C{col}_{outp}"
                oename = f"R{row}C{col}_{oe}"
                print("IOB", row, col, iname, oname, oename)
                ctx.addBel(name=belname, type="GENERIC_IOB", loc=Loc(col, row, z), gb=False)
                ctx.addBelInput(bel=belname, name="I", wire=iname)
                ctx.addBelInput(bel=belname, name="EN", wire=oename)
                ctx.addBelOutput(bel=belname, name="O", wire=oname)


def addPip(row, col, srcnum, destnum):
    try:
        srcname = wirenames[srcnum]
        gsrcname = wire2global(row, col, height, width, srcname)

        destname = wirenames[destnum]
        gdestname = wire2global(row, col, height, width, destname)
    except KeyError:
        return

    pipname = f"R{row}C{col}_{srcname}_{destname}"
    print("pip", pipname, srcname, gsrcname, destname, gdestname)
    try:
        ctx.addPip(
            name=pipname, type=destname, srcWire=gsrcname, dstWire=gdestname,
            delay=ctx.getDelayFromNS(0.05), loc=Loc(col, row, 0))
    except IndexError:
        pass
        print("Wire not found", gsrcname, gdestname)
    except AssertionError:
        pass
        print("Wire already exists", gsrcname, gdestname)

def addAlias(row, col, srcnum, destnum):
    srcname = wirenames[srcnum]
    gsrcname = wire2global(row, col, height, width, srcname)

    destname = wirenames[destnum]
    gdestname = wire2global(row, col, height, width, destname)

    pipname = f"R{row}C{col}_{srcname}_{destname}"
    #print("alias", pipname)
    ctx.addAlias(
        name=pipname, type=destname, srcWire=gsrcname, dstWire=gdestname,
        delay=ctx.getDelayFromNS(0.01))

for row, rowdata in enumerate(grid, 1):
    for col, ttyp in enumerate(rowdata, 1):
        for dest, srcs in zip(data['X11s'], data['X11Ins']):
            addAlias(row, col, srcs[0], dest)
        for src, dest, *fuses in fse[ttyp]['wire'][2]:
            addPip(row, col, abs(src), abs(dest))

#code.interact(local=locals())
