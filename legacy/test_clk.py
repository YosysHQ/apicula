import pickle
import os
import sys
import re

gowinhome = os.getenv("GOWINHOME")
if not gowinhome:
    raise Exception("GOWINHOME not set")

device = os.getenv("DEVICE")
if not device:
    raise Exception("DEVICE not set")

with open(f"{device}.pickle", 'rb') as f:
    db = pickle.load(f)

locre = re.compile(r"R(\d+)C(\d+)_(\w+)")

def route(row, col, gb):
    loc = f"R{row}C{col}_{gb}"
    if loc not in db.aliases: return
    print(loc)
    gbo = db.aliases[loc]
    print(gbo)
    lrow, lcol, pip = locre.match(gbo).groups()
    lrow = int(lrow)
    lcol = int(lcol)
    gt = db.grid[lrow-1][lcol-1].pips[pip]
    gt = list(gt.keys())[0]
    loc = f"R{lrow}C{lcol}_{gt}"
    print(loc)
    tap = db.aliases[loc]
    print(tap)
    trow, tcol, pip = locre.match(tap).groups()
    trow = int(trow)
    tcol = int(tcol)
    smux = db.grid[trow-1][tcol-1].clock_pips[pip]
    spine = "R1C1_NONE"
    for out in smux.keys():
        loc = f"R{trow}C{tcol}_{out}"
        if loc in db.aliases:
            spine = db.aliases[loc]
            break
    print(spine)
    srow, scol, pip = locre.match(spine).groups()
    srow = int(srow)
    scol = int(scol)
    cmux = db.grid[srow-1][scol-1].clock_pips[pip]
    iob = []
    for out in cmux.keys():
        loc = f"R{srow}C{scol}_{out}"
        if loc in db.aliases:
            iob.append(db.aliases[loc])

    print(iob[0])

errors = {}
for r in range(db.rows):
    for c in range(db.cols):
        for clk in range(8):
            gb = f"GB{clk}0"
            try:
                route(r+1, c+1, gb)
            except KeyError as e:
                errors.setdefault((r, c), []).append(e.args[0])
                print("Key error", e)

print("#"*(db.cols+2))
for r in range(db.rows):
    print('#', end='')
    for c in range(db.cols):
        if (r, c) in errors:
            print(len(errors[r, c]), end='')
        else:
            print(' ', end='')
    print("#")
print("#"*(db.cols+2))

print(errors)