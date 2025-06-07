#!/usr/bin/python3

import pickle
from multiprocessing.dummy import Pool

from apycula import codegen, tiled_fuzzer, gowin_unpack, chipdb

def run_script(pinName : str, idx=None, iostd=None):
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
            return (idxName, i, j, bel[-1], iostd)

    raise Exception(f"No IOB found for {port}")

# these are all system in package variants with magic wire names connected interally
# pin names are obtained from litex-boards
# (pin name, bus width, iostd)
params = {
    "GW1N-9": [{
        "package": "QFN88",
        "device": "GW1NR-9",
        "partnumber": "GW1NR-UV9QN88C6/I5",
        "pins": [
            ("IO_sdram_dq", 16, "LVCMOS33"),
            ("O_sdram_clk", 0, "LVCMOS33"),
            ("O_sdram_cke", 0, "LVCMOS33"),
            ("O_sdram_cs_n", 0, "LVCMOS33"),
            ("O_sdram_cas_n", 0, "LVCMOS33"),
            ("O_sdram_ras_n", 0, "LVCMOS33"),
            ("O_sdram_wen_n", 0, "LVCMOS33"),
            ("O_sdram_addr", 12, "LVCMOS33"),
            ("O_sdram_dqm", 2, "LVCMOS33"),
            ("O_sdram_ba", 2, "LVCMOS33")
        ],
    }],
    "GW1N-9C": [{
        "package": "QFN88P",
        "device": "GW1NR-9C",
        "partnumber": "GW1NR-LV9QN88PC6/I5",
        "pins": [
            ("O_psram_ck", 2, None),
            ("O_psram_ck_n", 2, None),
            ("O_psram_cs_n", 2, None),
            ("O_psram_reset_n", 2, None),
            ("IO_psram_dq", 16, None),
            ("IO_psram_rwds", 2, None),
        ],
    }],
    "GW1NS-4": [{
        "package": "QFN48",#??
        "device": "GW1NSR-4C",
        "partnumber": "GW1NSR-LV4CQN48PC7/I6",
        "pins": [
            ("O_hpram_ck", 2, None),
            ("O_hpram_ck_n", 2, None),
            ("O_hpram_cs_n", 2, None),
            ("O_hpram_reset_n", 2, None),
            ("IO_hpram_dq", 16, None),
            ("IO_hpram_rwds", 2, None),
        ],
    }],
    "GW2A-18C": [{
        "package": "QFN88",
        "device": "GW2AR-18C",
        "partnumber": "GW2AR-LV18QN88C8/I7",
        "pins": [
            ("O_sdram_clk", 0, "LVCMOS33"),
            ("O_sdram_cke", 0, "LVCMOS33"),
            ("O_sdram_cs_n", 0, "LVCMOS33"),
            ("O_sdram_cas_n", 0, "LVCMOS33"),
            ("O_sdram_ras_n", 0, "LVCMOS33"),
            ("O_sdram_wen_n", 0, "LVCMOS33"),
            ("O_sdram_dqm", 4, "LVCMOS33"),
            ("O_sdram_addr", 11, "LVCMOS33"),
            ("O_sdram_ba", 2, "LVCMOS33"),
            ("IO_sdram_dq", 32, "LVCMOS33"),
        ]
    }],
}

with open(f"{tiled_fuzzer.device}_stage1.pickle", 'rb') as f:
    db = pickle.load(f)

pool = Pool()

if tiled_fuzzer.device in params:
    devices = params[tiled_fuzzer.device]
    for device in devices:
        tiled_fuzzer.params = device
        pins = device["pins"]

        runs = []
        for pinName, pinBuswidth, iostd in pins:
            if (pinBuswidth == 0):
                runs.append((pinName, None, iostd))
            else:
                for pinIdx in range(0, pinBuswidth):
                    runs.append((pinName, pinIdx, iostd))

        print(runs)

        pinmap = pool.map(lambda params: run_script(*params), runs)

        # check for duplicates
        seen = {}
        for pin in pinmap:
            wire = pin[0]
            bel = pin[1:4]
            if bel in seen:
                print("WARNING:", wire, "conflicts with", seen[bel], "at", bel)
            else:
                seen[bel] = wire

        db.sip_cst.setdefault(device["device"], {})[device["package"]] = pinmap

with open(f"{tiled_fuzzer.device}_stage2.pickle", 'wb') as f:
    pickle.dump(db, f)
