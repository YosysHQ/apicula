import pickle
from apycula import chipdb
from apycula import codegen
from apycula import tiled_fuzzer
from apycula import tracing
from apycula import gowin_unpack

def find_pins(db, pnr:codegen.Pnr, trace_args):
    pnr_result = pnr.run_pnr()
    tiles = chipdb.tile_bitmap(db, pnr_result.bitmap)

    trace_starts = []
    for args in trace_args:
        iob, pin_name, pin_idx, direction = args
        iob_type = "IOB" + iob[-1]
        fuzz_io_row, fuzz_io_col, bel_idx = gowin_unpack.tbrl2rc(db, iob)
        fuzz_io_node = db.grid[fuzz_io_row][fuzz_io_col].bels[iob_type].portmap["O"]
        trace_starts.append((fuzz_io_row, fuzz_io_col, fuzz_io_node))

    dests = [x for x in tracing.get_io_nodes(db) if x not in trace_starts]
    pinout = {}

    all_paths = []
    for trace_start, args in zip(trace_starts, trace_args):
        iob, pin_name, pin_idx, direction = args
        sdram_idxName = pin_name if pin_idx is None else f"{pin_name}[{pin_idx}]"

        path_dict = tracing.get_path_dict(tiles, db, trace_start)
        paths = tracing.get_paths(path_dict, [trace_start], dests)
        all_paths.append(paths[0])
        possible_pins = list({path[-1] for path in paths})
        if len(possible_pins) > 1:
            print(f"WARNING: Multiple candidates found for {sdram_idxName}: {possible_pins}")
        if not possible_pins:
            print(f"WARNING: No candidate found for {sdram_idxName}")
        else:
            pin_node = possible_pins[0]  #pin : [row, col, wire]
            tbrl_pin = tracing.io_node_to_tbrl(db, pin_node)
            pinout[sdram_idxName] = (*pin_node[:2], tbrl_pin[-1])
    # all_paths = {k:v for k, v in enumerate(all_paths)}
    # # print(all_paths)
    # tracing.visualize_grid(all_paths, db.rows, db.cols, save_name="sdram_pinout.jpeg")

    return pinout

def run_script(db, pins, device, package, partnumber):
    sdram_pins = []
    pinout = []

    for pinName, pincount, iostd in pins:
        if pincount == 0:
            sdram_port = sdram_idxName = pinName
            sdram_pins.append((sdram_port, pinName, None, iostd))
        else:
            sdram_port = f"[{pincount-1}:0] {pinName}"
            for idx in range(pincount):
                sdram_pins.append((sdram_port, pinName, idx, iostd))

    #Use only pins without a special function to avoid placement errors
    all_pins = db.pinout[device][package]
    package_pins = [all_pins[k][0] for k in all_pins if not all_pins[k][1]]

    i = 0
    while i < len(sdram_pins):
        trace_args = []
        pnr = codegen.Pnr()
        pnr.cst = codegen.Constraints()
        pnr.netlist_type = "verilog"
        pnr.netlist = codegen.Module()
        pnr.device = device
        pnr.partnumber = partnumber

        for sdram_pin in sdram_pins:
            pnr.netlist.inouts.add(sdram_pin[0])

        for fuzz_pin, sdram_pin in zip(package_pins, sdram_pins[i:i+len(package_pins)]):
            sdram_port, sdram_pin_name, idx, iostd = sdram_pin
            sdram_idxName = sdram_pin_name if idx is None else f"{sdram_pin_name}[{idx}]"
            sdram_io_mod_name = f"{sdram_pin_name}_{idx}_iobased"

            suffix = f"_{idx}" if idx is not None else ""
            fuzz_input_wire = f"__{fuzz_pin}_input_{sdram_pin_name}{suffix}"
            fuzz_output_wire = f"__{fuzz_pin}_output_{sdram_pin_name}{suffix}"

            pnr.cst.ports[fuzz_input_wire] = fuzz_pin
            pnr.netlist.inputs.add(fuzz_input_wire)
            trace_args.append((fuzz_pin, sdram_pin_name, idx, "input"))
            iob = codegen.Primitive("TBUF", sdram_io_mod_name)
            iob.portmap["O"] = sdram_idxName
            iob.portmap["I"] = fuzz_input_wire
            iob.portmap["OEN"] = "1'b1"
            pnr.netlist.primitives[sdram_io_mod_name] = iob

        i += len(package_pins)

        iter_pinout = find_pins(db, pnr, trace_args)
        iter_pinout = [(k,*v,iostd) for k, v in iter_pinout.items()]
        pinout.extend(iter_pinout)

    # draw_map = {k:[(r,c)] for k, r, c, _, _ in pinout }
    # tracing.visualize_grid(draw_map, db.rows, db.cols, save_name="sdram_pinout.jpeg")
    return pinout

params = {
    "GW1NS-4": [{
        "package": "QFN48P",
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

if __name__ == "__main__":
    with open(f"{tiled_fuzzer.device}_stage1.pickle", 'rb') as f:
        db = pickle.load(f)

    if tiled_fuzzer.device in params:
        devices = params[tiled_fuzzer.device]
        for device_args in devices:
            tiled_fuzzer.params = device_args
            pinmap = run_script(db, device_args["pins"], device_args["device"], device_args["package"], device_args["partnumber"])
            db.sip_cst.setdefault(device_args["device"], {})[device_args["package"]] = pinmap

    # the reverse logicinfo does not make sense to store in the database
    db.rev_li = {}
    with open(f"{tiled_fuzzer.device}_stage2.pickle", 'wb') as f:
        pickle.dump(db, f)
