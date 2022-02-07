from multiprocessing.dummy import Pool
from PIL import Image
import numpy as np
import pickle
import json
import re
from apycula import tiled_fuzzer
from apycula import codegen
from apycula import pindef
from apycula import bslib
from apycula import chipdb
from apycula import fuse_h4x
from apycula import gowin_unpack
from apycula.wirenames import wirenames

def dff(mod, cst, row, col, clk=None):
    "make a dff with optional clock"
    name = tiled_fuzzer.make_name("DFF", "DFF")
    dff = codegen.Primitive("DFF", name)
    dff.portmap['CLK'] = clk if clk else name+"_CLK"
    dff.portmap['D'] = name+"_D"
    dff.portmap['Q'] = name+"_Q"
    mod.wires.update(dff.portmap.values())
    mod.primitives[name] = dff
    cst.cells[name] = (row, col, 0, 'A') # f"R{row}C{col}"
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

with open(f"{tiled_fuzzer.device}_stage1.pickle", 'rb') as f:
    db = pickle.load(f)

# init pindef
pindef.all_packages(tiled_fuzzer.device)

clock_pins = pindef.get_clock_locs(
        tiled_fuzzer.device,
        tiled_fuzzer.params['package'])
# pins appear to be differential with T/C denoting true/complementary
true_pins = [p[0] for p in clock_pins if "GCLKT" in p[1]]

pool = Pool()

def quadrants():
    mod = codegen.Module()
    cst = codegen.Constraints()
    ibuf(mod, cst, true_pins[2], clk="myclk")
    pnr = tiled_fuzzer.run_pnr(mod, cst, {})

    modules = []
    constrs = []
    idxes = []
    for i in range(2, db.cols):
        for j in [2, db.rows-3]: # avoid bram
            if "DFF0" not in db.grid[j-1][i-1].bels:
                print(i, j)
                continue
            mod = codegen.Module()
            cst = codegen.Constraints()

            ibuf(mod, cst, true_pins[0], clk="myclk")
            dff(mod, cst, j, i, clk="myclk")

            modules.append(mod)
            constrs.append(cst)
            idxes.append((j, i))

    for i in [2, db.cols-2]:
        for j in range(2, db.rows):
            if "DFF0" not in db.grid[j-1][i-1].bels:
                print(i, j)
                continue
            mod = codegen.Module()
            cst = codegen.Constraints()

            ibuf(mod, cst, true_pins[0], clk="myclk")
            dff(mod, cst, j, i, clk="myclk")

            modules.append(mod)
            constrs.append(cst)
            idxes.append((j, i))

    pnr_res = pool.map(lambda param: tiled_fuzzer.run_pnr(*param, {}), zip(modules, constrs))

    res = {}
    for (row, col), (mybs, *_) in zip(idxes, pnr_res):
        sweep_tiles = fuse_h4x.tile_bitmap(fse, mybs^pnr.bitmap)

        # find which tap was used
        taps = [r for (r, c, typ), t in sweep_tiles.items() if typ in {13, 14, 15, 16, 18, 19}]

        # find which center tile was used
        t8x = [(r, c) for (r, c, typ), t in sweep_tiles.items() if typ >= 80 and typ < 90]
        rows, cols, _ = res.setdefault(t8x[0], (set(), set(), taps[0]))
        rows.add(row-1)
        cols.add(col-1)

    return res

def center_muxes(ct, rows, cols):
    "Find which mux drives which spine, and maps their inputs to clock pins"

    fr = min(rows)
    dff_locs = [(fr+1, c+1) for c in cols][:len(true_pins)]

    mod = codegen.Module()
    cst = codegen.Constraints()

    ibufs = [ibuf(mod, cst, p) for p in true_pins]
    dffs = [dff(mod, cst, row, col) for row, col in dff_locs]

    pnr = tiled_fuzzer.run_pnr(mod, cst, {})

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

    gb_sources = {}
    gb_destinations = {}
    src_seen = set()
    dst_seen = set()

    base = pnr.bitmap
    for i, (bs_sweep, *_) in enumerate(pnr_res):
        pin = true_pins[i]
        new = base ^ bs_sweep
        tiles = chipdb.tile_bitmap(db, new)

        try:
            _, _, clk_pips = gowin_unpack.parse_tile_(db, ct[0], ct[1], tiles[ct], noalias=True)
            dest, = set(clk_pips.keys()) - dst_seen
            dst_seen.add(dest)
            src, = set(clk_pips.values()) - src_seen
            src_seen.add(src)
        except ValueError:
            # it seems this uses a dynamically configurable mux routed to VCC/VSS
            continue
        print(i, pin, src, dest)
        gb_destinations[(ct[1], i)] = dest
        gb_sources[src] = pin

    return gb_sources, gb_destinations

def taps(rows, cols):
    "Find which colunm is driven by which tap"
    # conver to sorted list of 1-indexed vendor constraints
    rows = [row+1 for row in sorted(rows)]
    cols = [col+1 for col in sorted(cols)]

    modules = []
    constrs = []
    locs = []

    # use a different row for each clock
    # row by row, column by column, hook up the clock to the dff
    # in the old IDE row 1 always used clock 1 and so forth
    for col in cols:
        for gclk, row in enumerate(rows[:len(true_pins)]):
            mod = codegen.Module()
            cst = codegen.Constraints()

            clks = [ibuf(mod, cst, p) for p in true_pins]
            for i, clk in zip(rows, clks):
                flop = dff(mod, cst, i, col)
                if i <= row:
                    mod.assigns.append((flop, clk))

            modules.append(mod)
            constrs.append(cst)
            locs.append((gclk, col-1))

    pnr_res = pool.map(lambda param: tiled_fuzzer.run_pnr(*param, {}), zip(modules, constrs))

    last_dffcol = None
    seen_primary_taps = set()
    seen_secondary_taps = set()
    seen_spines = set()
    clks = {}
    for (gclk, dff_col), (sweep_bs, *_) in zip(locs, pnr_res):
        sweep_tiles = chipdb.tile_bitmap(db, sweep_bs)
        if dff_col != last_dffcol:
            seen_primary_taps = set()
            seen_secondary_taps = set()
            seen_spines = set()
            last_dffcol = dff_col

        tap = None
        print("#"*80)
        print("gclk", gclk, "dff_col", dff_col)
        for loc, tile in sweep_tiles.items():
            row, col = loc
            _, _, clk_pips = gowin_unpack.parse_tile_(db, row, col, tile, noalias=True)
            spines   = set(s for s in clk_pips.keys() if s.startswith("SPINE"))
            new_spines = spines - seen_spines
            seen_spines.update(spines)
            print(clk_pips.keys())
            if "GT00" in clk_pips and col not in seen_primary_taps:
                tap = col
                seen_primary_taps.add(col)
            if "GT10" in clk_pips and col not in seen_secondary_taps:
                tap = col
                seen_secondary_taps.add(col)
            print("loc", row, col, "tap", tap, "new spines", new_spines)
        # if tap == None: breakpoint()
        clks.setdefault(gclk, {}).setdefault(tap, set()).add(dff_col)
        print(clks)

    return clks

pin_re = re.compile(r"IO([TBRL])(\d+)([A-Z])")
banks = {'T': [(0, n) for n in range(db.cols)],
         'B': [(db.rows-1, n) for n in range(db.cols)],
         'L': [(n, 0) for n in range(db.rows)],
         'R': [(n, db.cols-1) for n in range(db.rows)]}
def pin2loc(name):
    side, num, pin = pin_re.match(name).groups()
    return banks[side][int(num)-1], "IOB"+pin

def pin_aliases(quads, srcs):
    aliases = {}
    for ct in quads.keys():
        for mux, pin in srcs.items():
            (row, col), bel = pin2loc(pin)
            iob = db.grid[row][col].bels[bel]
            iob_out = iob.portmap['O']
            aliases[ct[0], ct[1], mux] = row, col, iob_out
    return aliases

def spine_aliases(quads, dests, clks):
    aliases = {}
    for ct, (_, _, spine_row) in quads.items():
        for clk, taps in clks[ct].items():
            for tap in taps.keys():
                try:
                    dest = dests[ct[1], clk]
                except KeyError:
                    continue
                if 'UNK' not in dest: # these have an unknown function
                    aliases[spine_row, tap, dest] = ct[0], ct[1], dest
    return aliases

def tap_aliases(quads):
    aliases = {}
    for _, (rows, cols, spine_row) in quads.items():
        for col in cols:
            for row in rows:
                for src in ["GT00", "GT10"]:
                    if row != spine_row:
                        aliases[row, col, src] = spine_row, col, src

    return aliases

def branch_aliases(quads, clks):
    aliases = {}
    for ct, (rows, _, _) in quads.items():
        for clk, taps in clks[ct].items():
            if clk < 4:
                src = "GBO0"
            else:
                src = "GBO1"
            for tap, branch_cols in taps.items():
                for row in rows:
                    for col in branch_cols:
                        aliases[row, col, f"GB{clk}0"] = row, tap, src

    return aliases

if __name__ == "__main__":
    quads = quadrants()

    srcs = {}
    dests = {}
    clks = {}
    for ct, (rows, cols, _) in quads.items():
        # I reverse the pins here because
        # the 8th mux is not fuzzed presently
        true_pins.reverse()
        qsrcs, qdests = center_muxes(ct, rows, cols)
        srcs.update(qsrcs)
        dests.update(qdests)

        clks[ct] = taps(rows, cols)

    for _, cols, _ in quads.values():
        # col 0 contains a tap, but not a dff
        if 1 in cols:
            cols.add(0)

    print("    quads =", quads)
    print("    srcs =", srcs)
    print("    dests =", dests)
    print("    clks =", clks)

    pa = pin_aliases(quads, srcs)
    sa = spine_aliases(quads, dests, clks)
    ta = tap_aliases(quads)
    ba = branch_aliases(quads, clks)

    # print(pa)
    # print(sa)
    # print(ta)
    # print(ba)

    db.aliases.update(pa)
    db.aliases.update(sa)
    db.aliases.update(ta)
    db.aliases.update(ba)

    with open(f"{tiled_fuzzer.device}_stage2.pickle", 'wb') as f:
        pickle.dump(db, f)

