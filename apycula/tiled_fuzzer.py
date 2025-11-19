import re
import os
import sys
import tempfile
import subprocess
from pathlib import Path
from collections import deque, Counter, namedtuple
from itertools import chain, count, zip_longest
from functools import reduce
from random import shuffle, seed
from warnings import warn
from math import factorial
from multiprocessing.dummy import Pool
import pickle
from shutil import copytree

from apycula import codegen
from apycula import bslib
from apycula import pindef
from apycula import fuse_h4x
from apycula import wirenames as wnames
from apycula import dat19
from apycula import tm_h4x
from apycula import chipdb
from apycula import attrids

gowinhome = os.getenv("GOWINHOME")
if not gowinhome:
    raise Exception("GOWINHOME not set")
gowin_debug = os.getenv("GOWIN_DEBUG")

# device = os.getenv("DEVICE")
device = sys.argv[1]
params = {
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

def rc2tbrl(db, row, col, num):
    edge = 'T'
    idx = col
    if row == db.rows:
        edge = 'B'
    elif col == 1:
        edge = 'L'
        idx = row
    elif col == db.cols:
        edge = 'R'
        idx = row
    return f"IO{edge}{idx}{num}"

# Read the packer vendor log to identify problem with primitives/attributes
# returns dictionary {(primitive name, error code) : [full error text]}
_err_parser = re.compile(r"(\w+) +\(([\w\d]+)\).*'(inst[^\']+)\'.*")
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
    'bitmap', 'hdr', 'ftr', 'extra_slots',
    'constrs',        # constraints
    'config',         # device config
    'attrs',          # port attributes
    'errs',           # parsed log file
    'version',        # IDE version
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
        "bit_compress"          : "1",
        "bit_encrypt"           : "0",
        "bit_security"          : "1",
        "bit_incl_bsram_init"   : "0",
        #"loading_rate"          : "250/100",
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

        print(["/usr/bin/env", "LD_PRELOAD=" + gowinhome + "/Programmer/bin/libfontconfig.so.1", gowinhome + "/IDE/bin/gw_sh", tmpdir+"/run.tcl"])
        subprocess.run(["/usr/bin/env", "LD_PRELOAD=" + gowinhome + "/Programmer/bin/libfontconfig.so.1", gowinhome + "/IDE/bin/gw_sh", tmpdir+"/run.tcl"], cwd = tmpdir)
        #print(tmpdir); input()
        try:
            return PnrResult(
                    *bslib.read_bitstream(tmpdir+"/impl/pnr/top.fs"),
                    constr,
                    config, constr.attrs,
                    read_err_log(tmpdir+"/impl/pnr/top.log"),
                    bslib.read_bitstream_version(tmpdir+"/impl/pnr/top.fs"))
        except FileNotFoundError:
            print('ERROR', tmpdir)
            #input()
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
                is_diff, is_true_lvds, is_positive, adc_bus = diff_cap_info[bel_name]
            bel = iob_bels.setdefault(ttyp, {}).setdefault(f'IOB{bel_name[-1]}', chipdb.Bel())
            bel.simplified_iob = is_simplified
            bel.is_diff = is_diff
            bel.is_true_lvds = is_true_lvds
            bel.is_diff_p = is_positive

            #print(f"type:{ttyp} [{row}][{col}], IOB{bel_name[-1]}, diff:{is_diff}, true lvds:{is_true_lvds}, p:{is_positive}")
    for ttyp, bels in iob_bels.items():
        for row, col in locations[ttyp]:
            db.grid[row][col].bels.update(iob_bels[ttyp])

    # adc bus
    for pin, desc in diff_cap_info.items():
        _, _, _, adc_bus = desc
        if adc_bus:
            side, num = _tbrlre.match(pin).groups()
            row, col = tbrl2rc(fse, side, num)
            extra = db.extra_func.setdefault((row, col), {})
            extra.setdefault('adcio', {})['bus'] = adc_bus

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
        'GW1N-1'    : b'\x06\x00\x00\x00\x09\x00\x28\x1b',
        'GW1NZ-1'   : b'\x06\x00\x00\x00\x01\x00\x68\x1b',
        'GW1NS-2'   : b'\x06\x00\x00\x00\x03\x00\x08\x1b',
        'GW1N-4'    : b'\x06\x00\x00\x00\x01\x00\x38\x1b',
        'GW1NS-4'   : b'\x06\x00\x00\x00\x01\x00\x98\x1b',
        'GW1N-9'    : b'\x06\x00\x00\x00\x11\x00\x58\x1b',
        'GW1N-9C'   : b'\x06\x00\x00\x00\x11\x00\x48\x1b',
        'GW2A-18'   : b'\x06\x00\x00\x00\x00\x00\x08\x1b',
        'GW2A-18C'  : b'\x06\x00\x00\x00\x00\x00\x08\x1b',
        'GW5A-25A'  : b'\x06\x00\x00\x00\x00\x01\x28\x1b',
        }

# generate bitsream header
def gen_hdr():
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

if __name__ == "__main__":
    with open(f"{gowinhome}/IDE/share/device/{params['device']}/{params['device']}.fse", 'rb') as f:
        fse = fuse_h4x.readFse(f, device)

    dat = dat19.Datfile(Path(f"{gowinhome}/IDE/share/device/{params['device']}/{params['device']}.dat"))

    if gowin_debug:
        with open(f"{device}-dat.pickle", 'wb') as f:
            pickle.dump(dat, f)

    with open(f"{gowinhome}/IDE/share/device/{params['device']}/{params['device']}.tm", 'rb') as f:
        tm = tm_h4x.read_tm(f, device)

    db = chipdb.from_fse(device, fse, dat)
    chipdb.set_banks(fse, db)
    db.timing = tm
    chipdb.fse_wire_delays(db, params['device'])
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
    db.cmd_hdr = gen_hdr()
    db.cmd_ftr = gen_ftr()

    # IOB
    diff_cap_info = pindef.get_diff_adc_cap_info(params['device'], params['package'], True)
    fse_iob(fse, db, pin_locations, diff_cap_info, locations);
    if chipdb.is_GW5_family(device):
        chipdb.fill_GW5A_io_bels(db)

    pad_locs = pindef.get_pll_pads_locs(params['device'], params['package'])
    chipdb.pll_pads(db, device, pad_locs)

    chipdb.dat_portmap(dat, db, device)
    chipdb.add_hclk_bels(dat, db, device)


    # XXX GW1NR-9 has interesting IOBA pins on the bottom side
    if device == 'GW1N-9' :
        loc = locations[52][0]
        bel = db.grid[loc[0]][loc[1]].bels['IOBA']
        bel.portmap['GW9_ALWAYS_LOW0'] = wnames.wirenames[dat.portmap['IologicAIn'][40]]
        bel.portmap['GW9_ALWAYS_LOW1'] = wnames.wirenames[dat.portmap['IologicAIn'][42]]

    # GSR
    if device in {'GW2A-18', 'GW2A-18C'}:
        db.grid[27][50].bels.setdefault('GSR', chipdb.Bel()).portmap['GSRI'] = 'C4';
    elif device in {'GW5A-25A'}:
        db.grid[27][88].bels.setdefault('GSR', chipdb.Bel()).portmap['GSRI'] = 'LSR0';
    elif device in {'GW5AST-138C'}:
        db.grid[108][165].bels.setdefault('GSR', chipdb.Bel()).portmap['GSRI'] = 'D7';
    elif device in {'GW1N-1', 'GW1N-4', 'GW1NS-4', 'GW1N-9', 'GW1N-9C', 'GW1NS-2', 'GW1NZ-1'}:
        db.grid[0][0].bels.setdefault('GSR', chipdb.Bel()).portmap['GSRI'] = 'C4';
    else:
        raise Exception(f"No GSR for {device}")


    #TODO proper serialization format
    with open(f"{device}_stage1.pickle", 'wb') as f:
        pickle.dump(db, f)
