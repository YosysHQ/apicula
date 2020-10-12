import tiled_fuzzer
import codegen
import pindef
import bslib
import chipdb
import fuse_h4x
import gowin_unpack
from wirenames import wirenames
from multiprocessing.dummy import Pool
from PIL import Image
import numpy as np
import pickle
import json

def dff(mod, cst, row, col, clk=None):
    "make a dff with optional clock"
    name = tiled_fuzzer.make_name("DFF", "DFF")
    dff = codegen.Primitive("DFF", name)
    dff.portmap['CLK'] = clk if clk else name+"_CLK"
    dff.portmap['D'] = name+"_D"
    dff.portmap['Q'] = name+"_Q"
    mod.wires.update(dff.portmap.values())
    mod.primitives[name] = dff
    cst.cells[name] = f"R{row}C{col}"
    return dff.portmap['CLK']

def ibuf(mod, cst, loc, clk=None):
    "make an ibuf with optional clock"
    name = tiled_fuzzer.make_name("IOB", "IBUF")
    iob = codegen.Primitive("IBUF", name)
    iob.portmap["I"] = name+"_I"
    iob.portmap["O"] = clk if clk else name+"_O"

    mod.wires.update([iob.portmap["O"]])
    mod.inputs.update([iob.portmap["I"]])
    mod.primitives[name] = iob
    cst.ports[name] = loc
    return iob.portmap["O"]

with open(f"{tiled_fuzzer.gowinhome}/IDE/share/device/{tiled_fuzzer.device}/{tiled_fuzzer.device}.fse", 'rb') as f:
    fse = fuse_h4x.readFse(f)

with open(f"{tiled_fuzzer.device}.json") as f:
    dat = json.load(f)

with open(f"{tiled_fuzzer.device}.pickle", 'rb') as f:
    db = pickle.load(f)


clock_pins = pindef.get_clock_locs(
        tiled_fuzzer.device,
        tiled_fuzzer.params['package'],
        header=tiled_fuzzer.params['header'])
# pins appear to be differential with T/C denoting true/complementary
true_pins = [p[0] for p in clock_pins if "GCLKT" in p[1]]

pool = Pool()

def quadrants():
    mod = codegen.Module()
    cst = codegen.Constraints()
    ibuf(mod, cst, true_pins[2], clk="myclk")
    base_bs, _, _, _, _ = tiled_fuzzer.run_pnr(mod, cst, {})

    width = len(db.grid[0])
    height = len(db.grid)
    modules = []
    constrs = []
    idxes = []
    for i in range(2, width):
        for j in [2, height-3]: # avoid bram
            if "DFF0" not in db.grid[j-1][i-1].bels:
                print(i, j)
                continue
            mod = codegen.Module()
            cst = codegen.Constraints()

            ibuf(mod, cst, true_pins[0], clk="myclk")
            dff(mod, cst, j, i, clk="myclk")

            modules.append(mod)
            constrs.append(cst)
            idxes.append((i, j))

    for i in [2, width-2]:
        for j in range(2, height):
            if "DFF0" not in db.grid[j-1][i-1].bels:
                print(i, j)
                continue
            mod = codegen.Module()
            cst = codegen.Constraints()

            ibuf(mod, cst, true_pins[0], clk="myclk")
            dff(mod, cst, j, i, clk="myclk")

            modules.append(mod)
            constrs.append(cst)
            idxes.append((i, j))

    pnr_res = pool.map(lambda param: tiled_fuzzer.run_pnr(*param, {}), zip(modules, constrs))

    res = {}
    for (row, col), (mybs, *_) in zip(idxes, pnr_res):
        sweep_tiles = fuse_h4x.tile_bitmap(fse, mybs^base_bs)
        t8x = [(r, c) for (r, c, typ), t in sweep_tiles.items() if typ >= 80 and typ < 90]
        rows, cols = res.setdefault(t8x[0], (set(), set()))
        rows.add(row)
        cols.add(col)

    return res

def center_muxes(ct, rows, cols):
    "Find which mux drives which spine, and maps their inputs to clock pins"

    fr = min(rows)
    dff_locs = [(c, fr) for c in cols][:len(true_pins)]

    mod = codegen.Module()
    cst = codegen.Constraints()

    ibufs = [ibuf(mod, cst, p) for p in true_pins]
    dffs = [dff(mod, cst, row, col) for row, col in dff_locs]

    bs, _, _, _, _ = tiled_fuzzer.run_pnr(mod, cst, {})

    gb_sources = {}
    gb_destinations = {}

    modules = []
    constrs = []
    for i, pin in enumerate(true_pins):
        mod = codegen.Module()
        cst = codegen.Constraints()
        ibufs = [ibuf(mod, cst, p) for p in true_pins]
        dffs = [dff(mod, cst, row, col) for row, col in dff_locs]
        mod.assigns = list(zip(dffs, ibufs))[:i+1]

        modules.append(mod)
        constrs.append(cst)

    pnr_res = pool.map(lambda param: tiled_fuzzer.run_pnr(*param, {}), zip(modules, constrs))

    base = bs
    for i, (bs_sweep, *_) in enumerate(pnr_res):
        pin = true_pins[i]
        new = base ^ bs_sweep
        base = bs_sweep
        tiles = chipdb.tile_bitmap(db, new)

        try:
            db_tile = db.grid[ct[0]][ct[1]]
            _, _, clk_pips = gowin_unpack.parse_tile_(db_tile, tiles[ct], default=False)
            dest = list(clk_pips.keys())[0]
            src = list(clk_pips.values())[0]
        except (KeyError, IndexError):
            # it seems this uses a dynamically configurable mux routed to VCC/VSS
            continue
        print(i, pin, src, dest)
        gb_destinations[f"SPINE_{ct[1]}_{i}"] = dest
        gb_sources[src] = pin

    return gb_sources, gb_destinations

def taps():
    "Find which colunm is driven by which tap"
    width = len(db.grid[0])
    mod = codegen.Module()
    cst = codegen.Constraints()

    clks = [ibuf(mod, cst, p) for p in true_pins]

    offset = 2
    for i in range(len(true_pins)):
        for j in range(2, width):
            while "DFF0" not in db.grid[i-1+offset][j-1].bels:
                offset += 1
            flop = dff(mod, cst, i+offset, j)

    bs_base, _, _, _, _ = tiled_fuzzer.run_pnr(mod, cst, {})

    modules = []
    constrs = []
    for pin_nr in range(len(true_pins)):
        for col in range(2, width):
            mod = codegen.Module()
            cst = codegen.Constraints()

            clks = [ibuf(mod, cst, p) for p in true_pins]
            offset = 2
            for i, clk in enumerate(clks):
                for j in range(2, width):
                    while "DFF0" not in db.grid[i-1+offset][j-1].bels:
                        offset += 1
                    flop = dff(mod, cst, i+offset, j)
                    if i < pin_nr:
                        mod.assigns.append((flop, clk))
                    elif i == pin_nr and j == col:
                        mod.assigns.append((flop, clk))

            modules.append(mod)
            constrs.append(cst)

    pnr_res = pool.imap(lambda param: tiled_fuzzer.run_pnr(*param, {}), zip(modules, constrs))

    offset = 0
    clks = {}
    complete_taps = set()
    for idx, (sweep_bs, *_) in enumerate(pnr_res):
        sweep_tiles = chipdb.tile_bitmap(db, sweep_bs^bs_base)

        dffs = set()
        tap = None
        gclk = idx//(width-2)
        if idx and idx%(width-2)==0:
            complete_taps.update(clks[gclk-1].keys())
        if gclk == 4: # secondary taps
            complete_taps = set()
        while "DFF0" not in db.grid[gclk+1+offset][2].bels:
            offset += 1
        # print("#"*80)
        for loc, tile in sweep_tiles.items():
            row, col = loc
            dbtile = db.grid[row][col]
            _, pips, clk_pips = gowin_unpack.parse_tile_(dbtile, tile)
            # print(row, idx//(width-2), clk_pips)
            #if row <= gclk: continue
            if row > gclk+offset and (pips['CLK0'].startswith("GB") or pips['CLK1'].startswith("GB")):
                # print("branch", col)
                dffs.add(col)
            if ("GT00" in clk_pips and gclk < 4) or \
            ("GT10" in clk_pips and gclk >= 4):
                # print("tap", col)
                if col not in complete_taps:
                    tap = col
        clks.setdefault(gclk, {}).setdefault(tap, set()).update(dffs)
        #print(complete_taps, clks)
        #if not tap: break

    return clks

if __name__ == "__main__":
    quads = quadrants()

    srcs = {}
    dests = {}
    for ct, (rows, cols) in quads.items():
        # I reverse the pins here because
        # the 8th mux is not fuzzed presently
        true_pins.reverse()
        qsrcs, qdests = center_muxes(ct, rows, cols)
        srcs.update(qsrcs)
        dests.update(qdests)

    clks = taps()

    print(quads)
    print(srcs)
    print(dests)
    print(clks)
