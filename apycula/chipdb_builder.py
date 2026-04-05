import re
import os
import copy
import argparse
import pickle
from pathlib import Path
from apycula import codegen
from apycula import pindef
from apycula import fse_parser
from apycula import wirenames as wnames
from apycula import dat_parser
from apycula import tm_parser
from apycula import chipdb
from apycula.chipdb import save_chipdb
from apycula import tracing
from apycula import gowin_unpack

DEVICE_PARAMS = {
    "GW1NS-4": {
        "package": "QFN48P",
        "device": "GW1NSR-4C",
        "partnumber": "GW1NSR-LV4CQN48PC7/I6",
    },
    "GW1N-9": {
        "package": "PBGA256",
        "device": "GW1N-9",
        "partnumber": "GW1N-LV9PG256C6/I5",
    },
    "GW1N-9C": {
        "package": "QFN88P",
        "device": "GW1NR-9C",
        "partnumber": "GW1NR-LV9QN88PC6/I5",
    },
    "GW1N-4": {
        "package": "PBGA256",
        "device": "GW1N-4",
        "partnumber": "GW1N-LV4PG256C6/I5",
    },
    "GW1N-1": {
        "package": "LQFP144",
        "device": "GW1N-1",
        "partnumber": "GW1N-LV1LQ144C6/I5",
    },
    "GW1NZ-1": {
        "package": "QFN48",
        "device": "GW1NZ-1",
        "partnumber": "GW1NZ-LV1QN48C6/I5",
    },
    "GW2A-18": {
        "package": "PBGA256",
        "device": "GW2A-18",
        "partnumber": "GW2A-LV18PG256C8/I7",
    },
    "GW2A-18C": {
        "package": "PBGA256S",
        "device": "GW2A-18C",
        "partnumber": "GW2A-LV18PG256SC8/I7", #"GW2AR-LV18PG256SC8/I7", "GW2AR-LV18QN88C8/I7"
    },
    "GW5A-25A": {
        "package": "MBGA121N",
        "device": "GW5A-25A",
        "partnumber": "GW5A-LV25MG121NES",
    },
    "GW5AST-138C": {
        "package": "PBGA484A",
        "device": "GW5AST-138C",
        "partnumber": "GW5AST-LV138PG484AC1/I0",
    },
}

SDRAM_PARAMS = {
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

def tbrl2rc(fse, side, num):
    if side == 'T':
        row = 0
        col = int(num) - 1
    elif side == 'B':
        row = len(fse['header']['grid'][61])-1
        col = int(num) - 1
    elif side == 'L':
        row = int(num) - 1
        col = 0
    elif side == 'R':
        row = int(num) - 1
        col = len(fse['header']['grid'][61][0])-1
    return (row, col)

_tbrlre = re.compile(r"IO([TBRL])(\d+)")
def fse_iob(fse, db, diff_cap_info, locations, device):
    chipdb.set_corners_io(db, device)
    iob_bels = {}
    is_true_lvds = False
    is_positive = False
    for ttyp in fse.keys():
        if ttyp == 'header' or 'longval' not in fse[ttyp]:
            continue
        # crieate all IO bels
        bel_cnt = 0
        for idx, fuse_table_n in {'A':23, 'B':24, 'C':40, 'D':41, 'E':42, 'F':43, 'G':44, 'H':45, 'I':46, 'J':47}.items():
            if fuse_table_n in fse[ttyp]['longval']:
                bel_cnt += 1
                iob_bels.setdefault(ttyp, {}).setdefault(f'IOB{idx}', chipdb.Bel())
        if bel_cnt > 2:
            for bel in iob_bels[ttyp].values():
                bel.simplified_iob = True
    for ttyp, bels in iob_bels.items():
        first_cell = True
        for row, col in locations[ttyp]:
            if first_cell:
                for bel_name, bel in bels.items():
                    name = chipdb.rc2tbrl_0(db, row, col, bel_name[-1])
                    if name in diff_cap_info.keys():
                        is_diff, is_true_lvds, is_positive, adc_bus = diff_cap_info[name]
                        bel.is_diff = is_diff
                        bel.is_true_lvds = is_true_lvds
                        bel.is_diff_p = is_positive
                        first_cell = False

            db[row, col].bels.update(iob_bels[ttyp])

    # adc bus
    for pin, desc in diff_cap_info.items():
        _, _, _, adc_bus = desc
        if adc_bus:
            side, num = _tbrlre.match(pin).groups()
            row, col = tbrl2rc(fse, side, num)
            extra = db.extra_func.setdefault((row, col), {})
            extra.setdefault('adcio', {})['bus'] = adc_bus

    if device in {'GW5A-25A'}:
        # fix IOR3AB
        db[2, db.cols - 1].bels['IOBA'].is_diff = False
        db[2, db.cols - 1].bels['IOBA'].is_true_lvds = False
        db[2, db.cols - 1].bels['IOBB'] = copy.deepcopy(db[2, db.cols - 1].bels['IOBA'])

# generate bitstream footer
def gen_ftr():
    # first line with CRC(?) at the end
    line = bytearray(b'\xff'*20)
    line[-2] = 0x34
    line[-1] = 0x73
    ftr = [line]
    # bitmap CRC, filled in gowin_pack
    ftr.append(bytearray(b'\x0a\x00\x00\x00\x00\x00\x00\x00'))
    # noop
    ftr.append(bytearray(b'\xff'*8))
    # write done
    ftr.append(bytearray(b'\x08\x00\x00\x00'))
    # noop
    ftr.append(bytearray(b'\xff'*8))
    ftr.append(bytearray(b'\xff'*2))

    return ftr

# borrowed from https://github.com/trabucayre/openFPGALoader/blob/master/src/fsparser.cpp
_chip_id = {
        'GW1N-1'      : b'\x06\x00\x00\x00\x09\x00\x28\x1b',
        'GW1NZ-1'     : b'\x06\x00\x00\x00\x01\x00\x68\x1b',
        'GW1NS-2'     : b'\x06\x00\x00\x00\x03\x00\x08\x1b',
        'GW1N-4'      : b'\x06\x00\x00\x00\x01\x00\x38\x1b',
        'GW1NS-4'     : b'\x06\x00\x00\x00\x01\x00\x98\x1b',
        'GW1N-9'      : b'\x06\x00\x00\x00\x11\x00\x58\x1b',
        'GW1N-9C'     : b'\x06\x00\x00\x00\x11\x00\x48\x1b',
        'GW2A-18'     : b'\x06\x00\x00\x00\x00\x00\x08\x1b',
        'GW2A-18C'    : b'\x06\x00\x00\x00\x00\x00\x08\x1b',
        'GW5A-25A'    : b'\x06\x00\x00\x00\x00\x01\x28\x1b',
        'GW5AST-138C' : b'\x06\x00\x00\x00\x00\x01\x08\x1b',
        }

# generate bitsream header
def gen_hdr(device, params):
    hdr = [bytearray(b'\xff'*20)]
    hdr.append(bytearray(b'\xff'*2))
    # magic
    hdr.append(bytearray(b'\xa5\xc3'))
    # chip id
    hdr.append(bytearray(_chip_id[device]))
    # flags?
    hdr.append(bytearray(b'\x10\x00\x00\x00\x00\xae\x00\x00'))
    if params['device'] in {'GW5A-25A'}:
        hdr.append(bytearray(b'\x62\x00\x00\x00\x00\x00\x00\x40'))
    # compression keys
    hdr.append(bytearray(b'\x51\x00\xff\xff\xff\xff\xff\xff'))
    # something about the Security Bit
    hdr.append(bytearray(b'\x0b\x00\x00\x00'))
    # SPI address = 0
    hdr.append(bytearray(b'\xd2\x00\xff\xff\x00\x00\x00\x00'))
    # unknown
    hdr.append(bytearray(b'\x12\x00\x00\x00'))
    # number of rows, is filled in gowin_pack
    hdr.append(bytearray(b'\x3b\x80\x00\x00'))

    return hdr

# --- SDRAM pin discovery (absorbed from find_sdram_pins.py) ---

def find_pins(db, pnr, trace_args):
    pnr_result = pnr.run_pnr()
    tiles = chipdb.tile_bitmap(db, pnr_result.bitmap)

    trace_starts = []
    for args in trace_args:
        iob, pin_name, pin_idx, direction = args
        iob_type = "IOB" + iob[-1]
        fuzz_io_row, fuzz_io_col, bel_idx = gowin_unpack.tbrl2rc(db, iob)
        fuzz_io_node = db[fuzz_io_row, fuzz_io_col].bels[iob_type].portmap["O"]
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

    return pinout

def run_sdram_script(db, pins, device, package, partnumber):
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

    return pinout

# --- Main builder ---

def main():
    parser = argparse.ArgumentParser(description='Build chip database from Gowin vendor files')
    parser.add_argument('device', choices=DEVICE_PARAMS.keys())
    parser.add_argument('--skip-sdram', action='store_true',
                        help='Skip SDRAM pin discovery')
    parser.add_argument('-o', '--output',
                        help='Output path (default: apycula/{device}.msgpack.xz)')
    args = parser.parse_args()

    device = args.device
    params = DEVICE_PARAMS[device]

    gowinhome = os.getenv("GOWINHOME")
    if not gowinhome:
        raise Exception("GOWINHOME not set")
    gowin_debug = os.getenv("GOWIN_DEBUG")

    with open(f"{gowinhome}/IDE/share/device/{params['device']}/{params['device']}.fse", 'rb') as f:
        fse = fse_parser.read_fse(f, device)

    dat = dat_parser.Datfile(Path(f"{gowinhome}/IDE/share/device/{params['device']}/{params['device']}.dat"))

    if params['device'] == "GW5AST-138C":
        dat.patch_grid_bram_138()

    if gowin_debug:
        with open(f"{device}-dat.pickle", 'wb') as f:
            pickle.dump(dat, f)

    with open(f"{gowinhome}/IDE/share/device/{params['device']}/{params['device']}.tm", 'rb') as f:
        tm = tm_parser.read_tm(f, device)

    db = chipdb.from_fse(device, fse, dat)
    chipdb.set_banks(fse, dat, db)
    db.timing = tm
    chipdb.fse_wire_delays(db, params['device'])
    db.packages, db.pinout, _ = chipdb.json_pinout(device)

    corners = [
        (0, 0, fse['header']['grid'][61][0][0]),
        (0, db.cols-1, fse['header']['grid'][61][0][-1]),
        (db.rows-1, db.cols-1, fse['header']['grid'][61][-1][-1]),
        (db.rows-1, 0, fse['header']['grid'][61][-1][0]),
    ]

    locations = {}
    for row, row_dat in enumerate(fse['header']['grid'][61]):
        for col, typ in enumerate(row_dat):
            locations.setdefault(typ, []).append((row, col))

    pin_names = pindef.get_locs(params['device'], params['package'], True)
    edges = {'T': fse['header']['grid'][61][0],
             'B': fse['header']['grid'][61][-1],
             'L': [row[0] for row in fse['header']['grid'][61]],
             'R': [row[-1] for row in fse['header']['grid'][61]]}
    pin_locations = {}
    pin_re = re.compile(r"IO([TBRL])(\d+)([A-Z])")
    for name in pin_names:
        side, num, pin = pin_re.match(name).groups()
        ttyp = edges[side][int(num)-1]
        ttyp_pins = pin_locations.setdefault(ttyp, {})
        ttyp_pins.setdefault(name[:-1], set()).add(name)

    # fill header/footer by hand
    db.cmd_hdr = gen_hdr(device, params)
    db.cmd_ftr = gen_ftr()

    # IOB
    diff_cap_info = pindef.get_diff_adc_cap_info(params['device'], params['package'], True)
    fse_iob(fse, db, diff_cap_info, locations, device)
    if chipdb.is_GW5_family(device):
        chipdb.fill_GW5A_io_bels(db)
    chipdb.dat_fill_io_cfgs(db, dat, device, db.pinout[params['device']][params['package']])

    pad_locs = pindef.get_pll_pads_locs(params['device'], params['package'])
    chipdb.pll_pads(db, device, pad_locs)

    chipdb.dat_portmap(dat, db, device)
    chipdb.add_hclk_bels(dat, db, device)


    # XXX GW1NR-9 has interesting IOBA pins on the bottom side
    if device == 'GW1N-9' :
        loc = locations[52][0]
        bel = db[loc[0], loc[1]].bels['IOBA']
        bel.portmap['GW9_ALWAYS_LOW0'] = wnames.wirenames[dat.portmap['IologicAIn'][40]]
        bel.portmap['GW9_ALWAYS_LOW1'] = wnames.wirenames[dat.portmap['IologicAIn'][42]]

    # GSR
    if device in {'GW2A-18', 'GW2A-18C'}:
        db[27, 50].bels.setdefault('GSR', chipdb.Bel()).portmap['GSRI'] = 'C4'
    elif device in {'GW5A-25A'}:
        db[27, 88].bels.setdefault('GSR', chipdb.Bel()).portmap['GSRI'] = 'LSR0'
    elif device in {'GW5AST-138C'}:
        db[108, 165].bels.setdefault('GSR', chipdb.Bel()).portmap['GSRI'] = 'D7'
    elif device in {'GW1N-1', 'GW1N-4', 'GW1NS-4', 'GW1N-9', 'GW1N-9C', 'GW1NS-2', 'GW1NZ-1'}:
        db[0, 0].bels.setdefault('GSR', chipdb.Bel()).portmap['GSRI'] = 'C4'
    else:
        raise Exception(f"No GSR for {device}")

    # SDRAM pin discovery (previously find_sdram_pins.py stage 2)
    if not args.skip_sdram and device in SDRAM_PARAMS:
        for device_args in SDRAM_PARAMS[device]:
            pinmap = run_sdram_script(db, device_args["pins"], device_args["device"], device_args["package"], device_args["partnumber"])
            db.sip_cst.setdefault(device_args["device"], {})[device_args["package"]] = pinmap

    # the reverse logicinfo does not make sense to store in the database
    db.rev_li = {}

    # Save output
    output = args.output or f"apycula/{device}.msgpack.xz"
    save_chipdb(db, output)

if __name__ == "__main__":
    main()
