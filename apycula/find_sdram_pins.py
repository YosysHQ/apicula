#!/usr/bin/python3

import pickle
from multiprocessing.dummy import Pool

from apycula import codegen, tiled_fuzzer, gowin_unpack, chipdb

def run_script(pinName : str, idx=None):
    if idx == None:
        port = pinName
        idxName = pinName
    else:
        port = f"[{idx}:{idx}] {pinName}"
        idxName = f"{pinName}[{idx}]"

    mod = codegen.Module()
    cst = codegen.Constraints()

    name = "iobased"
    if pinName.startswith("IO"):
        mod.inouts.add(port)
        iob = codegen.Primitive("TBUF", name)
        iob.portmap["O"] = idxName
        iob.portmap["I"] = ""
        iob.portmap["OEN"] = ""
        mod.primitives[name] = iob
    elif pinName.startswith("O"):
        mod.outputs.add(port)
        iob = codegen.Primitive("OBUF", name)
        iob.portmap["O"] = idxName
        iob.portmap["I"] = ""
        mod.primitives[name] = iob
    elif pinName.startswith("I"):
        mod.inputs.add(port)
        iob = codegen.Primitive("IBUF", name)
        iob.portmap["I"] = idxName
        iob.portmap["O"] = ""
        mod.primitives[name] = iob
    else:
        raise ValueError(pinName)

    pnr_result = tiled_fuzzer.run_pnr(mod, cst, {})
    tiles = chipdb.tile_bitmap(db, pnr_result.bitmap)

    for (i, j), tile in tiles.items():
        bels, _, _ = gowin_unpack.parse_tile_(db, i, j, tile)
        iob_location = f"R{i}C{j}"
        print(iob_location, bels)
        if bels and ("IOBA" in bels or "IOBB" in bels):
            bel = next(iter(bels))
            belname = tiled_fuzzer.rc2tbrl(db, i+1, j+1, bel[-1])
            print(db.rows, db.cols)
            print(idxName, belname)
            return (idxName, i, j, bel[-1])
    
    raise Exception(f"No IOB found for {port}")

# these are all system in package variants with magic wire names connected interally
params = {
    "GW1N-9": [{
        "package": "QFN88",
        "device": "GW1NR-9",
        "partnumber": "GW1NR-UV9QN88C6/I5",
        "pins": [
            ["IO_sdram_dq", 16],
            ["O_sdram_clk", 0],
            ["O_sdram_cke", 0],
            ["O_sdram_cs_n", 0],
            ["O_sdram_cas_n", 0],
            ["O_sdram_ras_n", 0],
            ["O_sdram_wen_n", 0],
            ["O_sdram_addr", 12],
            ["O_sdram_dqm", 2],
            ["O_sdram_ba", 2]
        ],
    }],
}
# pin name, bus width

with open(f"{tiled_fuzzer.device}_stage2.pickle", 'rb') as f:
    db = pickle.load(f)

pool = Pool()

if tiled_fuzzer.device in params:
    devices = params[tiled_fuzzer.device]
    for device in devices:
        tiled_fuzzer.params = device
        pins = device["pins"]

        runs = []
        for pinName, pinBuswidth in pins:
            if (pinBuswidth == 0):
                runs.append((pinName, None))
            else:
                for pinIdx in range(0, pinBuswidth):
                    runs.append((pinName, pinIdx))

        print(runs)

        pinmap = pool.map(lambda params: run_script(*params), runs)

        db.sip_cst.setdefault(device["device"], {})[device["package"]] = pinmap

with open(f"{tiled_fuzzer.device}_stage3.pickle", 'wb') as f:
    pickle.dump(db, f)
