import re
import os
import sys
import tempfile
import subprocess
from collections import deque, Counter, namedtuple
from itertools import chain, count, zip_longest
from functools import reduce
from random import shuffle, seed
from warnings import warn
from math import factorial
import numpy as np
from multiprocessing.dummy import Pool
import pickle
import json
from shutil import copytree

from apycula import codegen
from apycula import bslib
from apycula import pindef
from apycula import fuse_h4x
from apycula.wirenames import wirenames, clknames, wirenumbers, clknumbers
#TODO proper API
#from apycula import dat19_h4x
from apycula import tm_h4x
from apycula import chipdb
from apycula import attrids

gowinhome = os.getenv("GOWINHOME")
if not gowinhome:
    raise Exception("GOWINHOME not set")

# device = os.getenv("DEVICE")
device = sys.argv[1]
params = {
    "GW1NS-2": {
        "package": "LQFP144",
        "device": "GW1NS-2C",
        "partnumber": "GW1NS-UX2CLQ144C5/I4",
    },
    "GW1NS-4": {
        "package": "QFN48",
        "device": "GW1NSR-4C",
        "partnumber": "GW1NSR-LV4CQN48PC7/I6",
    },
    "GW1N-9": {
        "package": "PBGA256",
        "device": "GW1N-9",
        "partnumber": "GW1N-LV9PG256C6/I5",
    },
    "GW1N-9C": {
        "package": "UBGA332",
        "device": "GW1N-9C",
        "partnumber": "GW1N-LV9UG332C6/I5",
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
        "device": "GW2AR-18C",
        "partnumber": "GW2AR-LV18PG256SC8/I7",
    },
}[device]

# utils
name_idx = 0
def make_name(bel, typ):
    global name_idx
    name_idx += 1
    return f"inst{name_idx}_{bel}_{typ}"

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

# Read the packer vendor log to identify problem with primitives/attributes
# returns dictionary {(primitive name, error code) : [full error text]}
_err_parser = re.compile("(\w+) +\(([\w\d]+)\).*'(inst[^\']+)\'.*")
def read_err_log(fname):
    errs = {}
    with open(fname, 'r') as f:
        for line in f:
            res = _err_parser.match(line)
            if res:
                line_type, code, name = res.groups()
                text = res.group(0)
                if line_type in ["Warning", "Error"]:
                    errs.setdefault((name, code), []).append(text)
    return errs

# Result of the vendor router-packer run
PnrResult = namedtuple('PnrResult', [
    'bitmap', 'hdr', 'ftr',
    'constrs',        # constraints
    'config',         # device config
    'attrs',          # port attributes
    'errs'            # parsed log file
    ])

def run_pnr(mod, constr, config):
    cfg = codegen.DeviceConfig({
        "use_jtag_as_gpio"      : config.get('jtag', "1"),
        "use_sspi_as_gpio"      : config.get('sspi', "1"),
        "use_mspi_as_gpio"      : config.get('mspi', "1"),
        "use_ready_as_gpio"     : config.get('ready', "1"),
        "use_done_as_gpio"      : config.get('done', "1"),
        "use_reconfign_as_gpio" : config.get('reconfig', "1"),
        "use_mode_as_gpio"      : config.get('mode', "1"),
        "use_i2c_as_gpio"       : config.get('i2c', "1"),
        "bit_crc_check"         : "1",
        "bit_compress"          : "0",
        "bit_encrypt"           : "0",
        "bit_security"          : "1",
        "bit_incl_bsram_init"   : "0",
        "loading_rate"          : "250/100",
        "spi_flash_addr"        : "0x00FFF000",
        "bit_format"            : "txt",
        "bg_programming"        : "off",
        "secure_mode"           : "0"})

    opt = codegen.PnrOptions({
        "gen_posp"          : "1",
        "gen_io_cst"        : "1",
        "gen_ibis"          : "1",
        "ireg_in_iob"       : "0",
        "oreg_in_iob"       : "0",
        "ioreg_in_iob"      : "0",
        "timing_driven"     : "0",
        "cst_warn_to_error" : "0"})
    #"show_all_warn" : "1",

    pnr = codegen.Pnr()
    pnr.device = params['device']
    pnr.partnumber = params['partnumber']
    pnr.opt = opt
    pnr.cfg = cfg

    with tempfile.TemporaryDirectory() as tmpdir:
        with open(tmpdir+"/top.v", "w") as f:
            mod.write(f)
        pnr.netlist = tmpdir+"/top.v"
        with open(tmpdir+"/top.cst", "w") as f:
            constr.write(f)
        pnr.cst = tmpdir+"/top.cst"
        with open(tmpdir+"/run.tcl", "w") as f:
            pnr.write(f)

        subprocess.run([gowinhome + "/IDE/bin/gw_sh", tmpdir+"/run.tcl"], cwd = tmpdir)
        #print(tmpdir); input()
        try:
            return PnrResult(
                    *bslib.read_bitstream(tmpdir+"/impl/pnr/top.fs"),
                    constr,
                    config, constr.attrs,
                    read_err_log(tmpdir+"/impl/pnr/top.log"))
        except FileNotFoundError:
            print(tmpdir)
            input()
            return None

_tbrlre = re.compile(r"IO([TBRL])(\d+)")
def fse_iob(fse, db, pin_locations, diff_cap_info, locations):
    iob_bels = {}
    is_true_lvds = False
    is_positive = False
    for ttyp, tiles in pin_locations.items():
        # tiles are unique, so one is enough but we need A&B pins
        for tile, bels in tiles.items():
            if len(bels) >= 2:
                break
        # crate all IO bels
        is_simplified = len(bels) > 2
        side, num = _tbrlre.match(tile).groups()
        row, col = tbrl2rc(fse, side, num)
        for bel_name in bels:
            is_diff = False
            if bel_name in diff_cap_info.keys():
                is_diff, is_true_lvds, is_positive = diff_cap_info[bel_name]
            bel = iob_bels.setdefault(ttyp, {}).setdefault(f'IOB{bel_name[-1]}', chipdb.Bel())
            bel.simplified_iob = is_simplified
            bel.is_diff = is_diff
            bel.is_true_lvds = is_true_lvds
            bel.is_diff_p = is_positive
            print(f"type:{ttyp} [{row}][{col}], IOB{bel_name[-1]}, diff:{is_diff}, true lvds:{is_true_lvds}, p:{is_positive}")
    for ttyp, bels in iob_bels.items():
        for row, col in locations[ttyp]:
            db.grid[row][col].bels.update(iob_bels[ttyp])


if __name__ == "__main__":
    with open(f"{gowinhome}/IDE/share/device/{device}/{device}.fse", 'rb') as f:
        fse = fuse_h4x.readFse(f)

    with open(f"{device}.json") as f:
        dat = json.load(f)

    with open(f"{gowinhome}/IDE/share/device/{device}/{device}.tm", 'rb') as f:
        tm = tm_h4x.read_tm(f, device)

    db = chipdb.from_fse(device, fse, dat)
    chipdb.set_banks(fse, db)
    db.timing = tm
    db.packages, db.pinout, db.pin_bank = chipdb.json_pinout(device)

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

    pin_names = pindef.get_locs(device, params['package'], True)
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

    pnr_empty = run_pnr(codegen.Module(), codegen.Constraints(), {})
    db.cmd_hdr = pnr_empty.hdr
    db.cmd_ftr = pnr_empty.ftr
    db.template = pnr_empty.bitmap

    # IOB
    diff_cap_info = pindef.get_diff_cap_info(device, params['package'], True)
    fse_iob(fse, db, pin_locations, diff_cap_info, locations);

    chipdb.dat_portmap(dat, db, device)

    # XXX GW1NR-9 has interesting IOBA pins on the bottom side
    if device == 'GW1N-9' :
        loc = locations[52][0]
        bel = db.grid[loc[0]][loc[1]].bels['IOBA']
        bel.portmap['GW9_ALWAYS_LOW0'] = wirenames[dat[f'IologicAIn'][40]]
        bel.portmap['GW9_ALWAYS_LOW1'] = wirenames[dat[f'IologicAIn'][42]]
    chipdb.dat_aliases(dat, db)

    # GSR
    if device in {'GW2A-18', 'GW2A-18C'}:
        db.grid[27][50].bels.setdefault('GSR', chipdb.Bel()).portmap['GSRI'] = 'C4';
    elif device in {'GW1N-1', 'GW1N-4', 'GW1NS-4', 'GW1N-9', 'GW1N-9C', 'GW1NS-2', 'GW1NZ-1'}:
        db.grid[0][0].bels.setdefault('GSR', chipdb.Bel()).portmap['GSRI'] = 'C4';
    else:
        raise Exception(f"No GSR for {device}")


    #TODO proper serialization format
    with open(f"{device}_stage1.pickle", 'wb') as f:
        pickle.dump(db, f)
