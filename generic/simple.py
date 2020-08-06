import sys
import os
import json
from itertools import chain
import re
import code
sys.path.append(os.path.join(sys.path[0], '..'))
from wirenames import wirenames
import pickle
import chipdb

device = os.getenv("DEVICE")
if not device:
    raise Exception("DEVICE not set")

with open(f"../{device}.pickle", 'rb') as f:
    db = pickle.load(f)


added_wires = set()
def addWire(row, col, wire):
    gname = chipdb.wire2global(row, col, db, wire)
    #print("wire", gname)
    if gname in added_wires:
        # print(f"Duplicate wire {gname}")
        return
    else:
        added_wires.add(gname)
        ctx.addWire(name=gname, type=wire, y=row, x=col)

belre = re.compile(r"(IOB|LUT|DFF|BANK|CFG)(\w*)")
for row, rowdata in enumerate(db.grid, 1):
    for col, tile in enumerate(rowdata, 1):
        # add wires
        wires = set(chain(tile.pips.keys(), *tile.pips.values()))
        for wire in wires:
            addWire(row, col, wire)
        # add aliasses
        # creat bels
        #print(row, col, ttyp)
        for name, bel in tile.bels.items():
            typ, idx = belre.match(name).groups()
            if typ == "DFF":
                z = int(idx)
                belname = f"R{row}C{col}_SLICE{z}"
                clkname = f"R{row}C{col}_CLK{z//2}"
                fname = f"R{row}C{col}_F{z}"
                qname = f"R{row}C{col}_Q{z}"
                #print("IOB", row, col, clkname, fname, qname)
                ctx.addBel(name=belname, type="GENERIC_SLICE", loc=Loc(col, row, z), gb=False)
                ctx.addBelInput(bel=belname, name="CLK", wire=clkname)
                for k, n in [('A', 'I[0]'), ('B', 'I[1]'),
                               ('C', 'I[2]'), ('D', 'I[3]')]:
                    inpname = f"R{row}C{col}_{k}{z}"
                    ctx.addBelInput(bel=belname, name=n, wire=inpname)
                ctx.addBelOutput(bel=belname, name="Q", wire=qname)
                ctx.addBelOutput(bel=belname, name="F", wire=fname)

            elif typ == "IOB":
                z = ord(idx)-ord('A')
                belname = f"R{row}C{col}_IOB{idx}"
                inp = bel.portmap['I']
                outp = bel.portmap['O']
                oe = bel.portmap['OE']
                iname = f"R{row}C{col}_{inp}"
                oname = f"R{row}C{col}_{outp}"
                oename = f"R{row}C{col}_{oe}"
                #print("IOB", row, col, iname, oname, oename)
                ctx.addBel(name=belname, type="GENERIC_IOB", loc=Loc(col, row, z), gb=False)
                ctx.addBelInput(bel=belname, name="I", wire=iname)
                ctx.addBelInput(bel=belname, name="EN", wire=oename)
                ctx.addBelOutput(bel=belname, name="O", wire=oname)


def addPip(row, col, srcname, destname):
    gsrcname = chipdb.wire2global(row, col, db, srcname)
    gdestname = chipdb.wire2global(row, col, db, destname)

    pipname = f"R{row}C{col}_{srcname}_{destname}"
    #print("pip", pipname, srcname, gsrcname, destname, gdestname)
    try:
        ctx.addPip(
            name=pipname, type=destname, srcWire=gsrcname, dstWire=gdestname,
            delay=ctx.getDelayFromNS(0.05), loc=Loc(col, row, 0))
    except IndexError:
        pass
        #print("Wire not found", gsrcname, gdestname)
    except AssertionError:
        pass
        #print("Wire already exists", gsrcname, gdestname)

def addAlias(row, col, srcname, destname):
    gsrcname = chipdb.wire2global(row, col, db, srcname)
    gdestname = chipdb.wire2global(row, col, db, destname)

    pipname = f"R{row}C{col}_{srcname}_{destname}"
    ##print("alias", pipname)
    ctx.addAlias(
        name=pipname, type=destname, srcWire=gsrcname, dstWire=gdestname,
        delay=ctx.getDelayFromNS(0.01))


for row, rowdata in enumerate(db.grid, 1):
    for col, tile in enumerate(rowdata, 1):
        for dest, srcs in tile.pips.items():
            for src in srcs.keys():
                addPip(row, col, src, dest)
        for dest, src in tile.aliases.items():
            addAlias(row, col, src, dest)

#code.interact(local=locals())
