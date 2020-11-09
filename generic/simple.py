import sys
import os
from itertools import chain
import re
import code
import pickle
import importlib.resources
sys.path.append(os.path.join(sys.path[0], '..'))
from apycula import chipdb
from apycula.wirenames import wirenames

device = os.getenv("DEVICE")
if not device:
    raise Exception("DEVICE not set")

with importlib.resources.open_binary("apycula", f"{device}.pickle") as f:
    db = pickle.load(f)

timing_class = "C6/I5" # TODO parameterize
timing = db.timing[timing_class]

def addWire(row, col, wire):
    gname = chipdb.wire2global(row, col, db, wire)
    #print("wire", gname)
    try:
        ctx.addWire(name=gname, type=wire, y=row, x=col)
    except AssertionError:
        pass
        #print("duplicate wire")

belre = re.compile(r"(IOB|LUT|DFF|BANK|CFG)(\w*)")
for row, rowdata in enumerate(db.grid, 1):
    for col, tile in enumerate(rowdata, 1):
        # add wires
        wires = set(chain(
            tile.pips.keys(),
            tile.clock_pips.keys(),
            *tile.pips.values(),
            *tile.clock_pips.values(),
            ))
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


wlens = {0: 'X0', 1: 'FX1', 2: 'X2', 8: 'X8'}
def wiredelay(wire):
    m = re.match(r"[NESWX]+([0128])", wire)
    if m:
        wlen = int(m.groups()[0])
        name = wlens.get(wlen)
        return ctx.getDelayFromNS(max(timing['wire'][name]))
    elif wire.startswith("UNK"):
        return ctx.getDelayFromNS(max(timing['glbsrc']['PIO_CENT_PCLK']))
    elif wire.startswith("SPINE"):
        return ctx.getDelayFromNS(max(timing['glbsrc']['CENT_SPINE_PCLK']))
    elif wire.startswith("GT"):
        return ctx.getDelayFromNS(max(timing['glbsrc']['SPINE_TAP_PCLK']))
    elif wire.startswith("GBO"):
        return ctx.getDelayFromNS(max(timing['glbsrc']['TAP_BRANCH_PCLK']))
    elif wire.startswith("GB"):
        return ctx.getDelayFromNS(max(timing['glbsrc']['BRANCH_PCLK']))
    else: # no known delay
        return ctx.getDelayFromNS(0)



def addPip(row, col, srcname, destname):
    gsrcname = chipdb.wire2global(row, col, db, srcname)
    gdestname = chipdb.wire2global(row, col, db, destname)

    pipname = f"R{row}C{col}_{srcname}_{destname}"
    #print("pip", pipname, srcname, gsrcname, destname, gdestname)
    try:
        # delay is crude fudge from vendor critical path
        ctx.addPip(
            name=pipname, type=destname, srcWire=gsrcname, dstWire=gdestname,
            delay=wiredelay(destname), loc=Loc(col, row, 0))
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
    #print("alias", pipname)
    ctx.addPip(
        name=pipname+"_ALIAS", type=destname, srcWire=gsrcname, dstWire=gdestname,
        delay=ctx.getDelayFromNS(0), loc=Loc(col, row, 0))


for row, rowdata in enumerate(db.grid, 1):
    for col, tile in enumerate(rowdata, 1):
        for dest, srcs in tile.pips.items():
            for src in srcs.keys():
                addPip(row, col, src, dest)
        for dest, srcs in tile.clock_pips.items():
            for src in srcs.keys():
                addPip(row, col, src, dest)
        for dest, src in tile.aliases.items():
            addAlias(row, col, src, dest)

for (row, col, pip), (srow, scol, spip) in db.aliases.items():
    dest = f"R{row+1}C{col+1}_{pip}"
    src = f"R{srow+1}C{scol+1}_{spip}"
    name = f"{src}_{dest}_ALIAS"
    ctx.addPip(
        name=name, type=dest, srcWire=src, dstWire=dest,
        delay=ctx.getDelayFromNS(0), loc=Loc(row+1, col+1, 0))

# too low numbers will result in slow routing iterations
# too high numbers will result in more iterations
ctx.setDelayScaling(0.1, 0.7)

#code.interact(local=locals())
