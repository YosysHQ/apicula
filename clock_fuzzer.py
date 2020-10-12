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

def center_muxes(side):
    "Find which mux drives which spine, and maps their inputs to clock pins"
    crow = dat['center'][0]
    ccol = dat['center'][1]
    if side == "L": # GW1N-1 has 2 sides
        ct = crow-1, ccol-1
        dff_locs = [(2, 2+i) for i in range(len(true_pins))]
    elif side == "R":
        dff_locs = [(2, ccol+1+i) for i in range(8)]
        ct = crow-1, ccol
    elif side == "TL": # GW1N-9 has 4 quadrants
        ct = crow-1, ccol-2
        dff_locs = [(2, 2+i) for i in range(len(true_pins))]
    elif side == "TR":
        ct = crow-1, ccol+1
        dff_locs = [(2, ccol+1+i) for i in range(len(true_pins))]
    elif side == "BL":
        ct = crow-1, ccol-1
        dff_locs = [(crow+1, 2+i) for i in range(len(true_pins))]
    elif side == "BR":
        ct = crow-1, ccol
        dff_locs = [(crow+1, ccol+1+i) for i in range(len(true_pins))]
    else:
        raise ValueError("Wrong side")
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
        gb_destinations[f"SPINE{side}{i}"] = dest
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
    if tiled_fuzzer.device == "GW1N-1":
        lsrcs, ldests = center_muxes('L')
        true_pins.reverse()  # work around unfuzzed mux
        rsrcs, rdests = center_muxes('R')
        assert lsrcs == rsrcs
        srcs = rsrcs
        dsts = {**rdests, **ldests}
    elif tiled_fuzzer.device == "GW1N-9":
        tlsrcs, tldests = center_muxes('TL')
        trsrcs, trdests = center_muxes('TR')
        true_pins.reverse()  # work around unfuzzed mux
        blsrcs, bldests = center_muxes('BL')
        brsrcs, brdests = center_muxes('BR')
        srcs = {**trsrcs, **tlsrcs, **brsrcs, **blsrcs}
        dsts = {**trdests, **tldests, **brdests, **bldests}

    clks = taps()

    print(srcs)
    print(dsts)
    print(clks)
