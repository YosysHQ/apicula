import sys
import os
import re
import pickle
import itertools
import math
import numpy as np
import json
import argparse
import importlib.resources
from collections import namedtuple
from apycula import codegen
from apycula import chipdb
from apycula.chipdb import add_attr_val, get_shortval_fuses, get_longval_fuses
from apycula import attrids
from apycula.attrids import pll_attrids, pll_attrvals
from apycula import bslib
from apycula import attrids
from apycula.wirenames import wirenames, wirenumbers

device = ""

_verilog_name = re.compile(r"^[A-Za-z_0-9][A-Za-z_0-9$]*$")
def sanitize_name(name):
    retname = name
    if name[-3:] == '_LC':
        retname = name[:-3]
    elif name[-6:] == '_DFFLC':
        retname = name[:-6]
    elif name[-4:] == '$iob':
        retname = name[:-4]
    if _verilog_name.fullmatch(retname):
        return retname
    return f"\{retname} "

def get_bels(data):
    later = []
    belre = re.compile(r"R(\d+)C(\d+)_(?:GSR|SLICE|IOB|MUX2_LUT5|MUX2_LUT6|MUX2_LUT7|MUX2_LUT8|ODDR|OSC[ZFH]?|BUFS|RAMW|RPLL[AB])(\w*)")
    for cellname, cell in data['modules']['top']['cells'].items():
        if cell['type'].startswith('DUMMY_') :
            continue
        bel = cell['attributes']['NEXTPNR_BEL']
        if bel in {"VCC", "GND"}: continue
        bels = belre.match(bel)
        if not bels:
            raise Exception(f"Unknown bel:{bel}")
        row, col, num = bels.groups()
        # The differential buffer is pushed to the end of the queue for processing
        # because it does not have an independent iostd, but adjusts to the normal pins
        # in the bank, if any are found
        if 'DIFF' in cell['attributes'].keys():
            later.append((cellname, cell, row, col, num))
            continue
        yield (cell['type'], int(row), int(col), num,
                cell['parameters'], cell['attributes'], sanitize_name(cellname))

    # diff iobs
    for cellname, cell, row, col, num in later:
        yield (cell['type'], int(row), int(col), num,
                cell['parameters'], cell['attributes'], sanitize_name(cellname))

def get_pips(data):
    pipre = re.compile(r"R(\d+)C(\d+)_([^_]+)_([^_]+)")
    for net in data['modules']['top']['netnames'].values():
        routing = net['attributes']['ROUTING']
        pips = routing.split(';')[1::3]
        for pip in pips:
            res = pipre.fullmatch(pip) # ignore alias
            if res:
                row, col, src, dest = res.groups()
                yield int(row), int(col), src, dest
            elif pip and "DUMMY" not in pip:
                print("Invalid pip:", pip)

def infovaluemap(infovalue, start=2):
    return {tuple(iv[:start]):iv[start:] for iv in infovalue}

# add the default pll attributes according to the documentation
_default_pll_inattrs = {
            'FCLKIN'        : '100.00',
            'IDIV_SEL'      : '0',
            'DYN_IDIV_SEL'  : 'false',
            'FBDIV_SEL'     : '00000000000000000000000000000010', # XXX not as in doc
            'DYN_FBDIV_SEL' : 'false',
            'ODIV_SEL'      : '00000000000000000000000000001000',
            'DYN_ODIV_SEL'  : 'false',
            'PSDA_SEL'      : '0000 ', # XXX extra space for compatibility, but it will work with or without it in the future
            'DUTYDA_SEL'    : '1000 ', # ^^^
            'DYN_DA_EN'     : 'false',
            'CLKOUT_FT_DIR' : '1',
            'CLKOUT_DLY_STEP': '00000000000000000000000000000000',
            'CLKOUTP_FT_DIR': '1',
            'CLKOUTP_DLY_STEP': '00000000000000000000000000000000',
            'DYN_SDIV_SEL'  : '00000000000000000000000000000010',
            'CLKFB_SEL'     : 'internal',
            'CLKOUTD_SRC'   : 'CLKOUT',
            'CLKOUTD3_SRC'  : 'CLKOUT',
            'CLKOUT_BYPASS' : 'false',
            'CLKOUTP_BYPASS': 'false',
            'CLKOUTD_BYPASS': 'false',
            'DEVICE'        : 'GW1N-1'

        }

def add_pll_default_attrs(attrs):
    pll_inattrs = attrs.copy()
    for k, v in _default_pll_inattrs.items():
        if k in pll_inattrs.keys():
            continue
        pll_inattrs[k] = v
    return pll_inattrs

_default_pll_internal_attrs = {
            'INSEL': 'CLKIN1',
            'FBSEL': 'CLKFB3',
            'PLOCK': 'ENABLE',
            'FLOCK': 'ENABLE',
            'FLTOP': 'ENABLE',
            'GMCMODE': 15,
            'CLKOUTDIV3': 'ENABLE',
            'CLKOUTDIV': 'ENABLE',
            'CLKOUTPS': 'ENABLE',
            'PDN': 'ENABLE',
            'PASEL': 0,
            'IRSTEN': 'ENABLE',
            'SRSTEN': 'ENABLE',
            'PWDEN': 'ENABLE',
            'RSTEN': 'ENABLE',
            'FLDCOUNT': 16,
            'GMCGAIN': 0,
            'LPR': 'R4',
            'ICPSEL': 50,
}

# typ - PLL type (RPLL, etc)
def set_pll_attrs(db, typ, attrs):
    pll_inattrs = add_pll_default_attrs(attrs)
    pll_attrs = _default_pll_internal_attrs.copy()
    pll_attrs['IRSTEN'] = 'DISABLE'
    pll_attrs['SRSTEN'] = 'DISABLE'

    if typ not in ['RPLL']:
        raise Exception(f"PLL type {typ} is not supported for now")

    # parse attrs
    for attr, val in pll_inattrs.items():
        # XXX clock in and feedback in
        if attr == 'CLKOUTD_SRC':
            if val == 'CLKOUTP':
                pll_attrs['CLKOUTDIVSEL'] = 'CLKOUTPS'
            continue
        if attr == 'CLKOUTD3_SRC':
            if val == 'CLKOUTP':
                pll_attrs['CLKOUTDIV3SEL'] = 'CLKOUTPS'
            continue
        # XXX selin
        if attr == 'DYN_IDIV_SEL':
            if val == 'true':
                pll_attrs['IDIVSEL'] = 'DYN'
            continue
        if attr == 'DYN_FBDIV_SEL':
            if val == 'true':
                pll_attrs['FDIVSEL'] = 'DYN'
            continue
        if attr == 'DYN_ODIV_SEL':
            if val == 'true':
                pll_attrs['ODIVSEL'] = 'DYN'
            continue
        if attr == 'CLKOUT_BYPASS':
            if val == 'true':
                pll_attrs['BYPCK'] = 'BYPASS'
            continue
        if attr == 'CLKOUTP_BYPASS':
            if val == 'true':
                pll_attrs['BYPCKPS'] = 'BYPASS'
            continue
        if attr == 'CLKOUTD_BYPASS':
            if val == 'true':
                pll_attrs['BYPCKDIV'] = 'BYPASS'
            continue
        if attr == 'IDIV_SEL':
            idiv = 1 + int(val, 2)
            pll_attrs['IDIV'] = idiv
            continue
        if attr == 'FBDIV_SEL':
            fbdiv = 1 + int(val, 2)
            pll_attrs['FDIV'] = fbdiv
            continue
        if attr == 'DYN_SDIV_SEL':
            pll_attrs['SDIV'] = 2 + int(val, 2)
            continue
        if attr == 'ODIV_SEL':
            odiv = int(val, 2)
            pll_attrs['ODIV'] = odiv
            continue
        if attr == 'FCLKIN':
            fclkin = float(val)
            continue

    # XXX input is 24MHz only and output either 52MHz or 56MHz
    # XXX input is 27MHz only and output either 58.5MHz or 63MHz
    if device != "GW1N-1" and device != "GW1NZ-1":
        raise Exception(f"PLL is not supported")
    if (abs(fclkin - 24) > 0.01 and device == "GW1N-1") or (abs(fclkin - 27) > 0.01 and device == "GW1NZ-1"):
        raise Exception(f"PLL input frequency {fclkin} is not supported")
    if fbdiv == 13 and idiv == 6 and odiv == 8:
        pll_attrs['FLDCOUNT'] = 16
        pll_attrs['ICPSEL'] = 20
        pll_attrs['LPR'] = 6
    elif fbdiv == 7 and idiv == 3 and odiv == 8:
        pll_attrs['FLDCOUNT'] = 16
        pll_attrs['ICPSEL'] = 40
        pll_attrs['LPR'] = 5
    else:
        raise Exception(f"PLL parameters are not supported for now")

    fin_attrs = set()
    for attr, val in pll_attrs.items():
        if isinstance(val, str):
            val = pll_attrvals[val]
        add_attr_val(db, 'PLL', fin_attrs, pll_attrids[attr], val)
    return fin_attrs

iostd_alias = {
        "HSTL18_II"  : "HSTL18_I",
        "SSTL18_I"   : "HSTL18_I",
        "SSTL18_II"  : "HSTL18_I",
        "HSTL15_I"   : "SSTL15",
        "SSTL25_II"  : "SSTL25_I",
        "SSTL33_II"  : "SSTL33_I",
        "LVTTL33"    : "LVCMOS33",
        }
# For each bank, remember the Bels used, mark whether Outs were among them and the standard.
class BankDesc:
    def __init__(self, iostd, inputs_only, bels_tiles, true_lvds_drive):
        self.iostd = iostd
        self.inputs_only = inputs_only
        self.bels_tiles = bels_tiles
        self.true_lvds_drive = true_lvds_drive

_banks = {}
_sides = "AB"
def place(db, tilemap, bels, cst, args):
    for typ, row, col, num, parms, attrs, cellname in bels:
        tiledata = db.grid[row-1][col-1]
        tile = tilemap[(row-1, col-1)]
        if typ == "GSR":
            pass
        elif typ.startswith('MUX2_'):
            pass
        elif typ == "BUFS":
            # fuses must be reset in order to activate so remove them
            bits2zero = set()
            for fuses in [fuses for fuses in parms.keys() if fuses in {'L', 'R'}]:
                bits2zero.update(tiledata.bels[f'BUFS{num}'].flags[fuses])
            for r, c in bits2zero:
                tile[r][c] = 0

        elif typ in {'OSC', 'OSCZ', 'OSCF', 'OSCH'}:
            divisor = int(parms['FREQ_DIV'], 2)
            if divisor % 2 == 1:
                raise Exception(f"Divisor of {typ} must be even")
            divisor //= 2
            if divisor in tiledata.bels[typ].modes:
                bits = tiledata.bels[typ].modes[divisor]
                for r, c in bits:
                    tile[r][c] = 1
        elif typ == "SLICE":
            lutmap = tiledata.bels[f'LUT{num}'].flags

            if 'ALU_MODE' in parms.keys():
                alu_bel = tiledata.bels[f"ALU{num}"]
                mode = str(parms['ALU_MODE'])
                for r_c in lutmap.values():
                    for r, c in r_c:
                        tile[r][c] = 0
                if mode in alu_bel.modes.keys():
                    bits = alu_bel.modes[mode]
                else:
                    bits = alu_bel.modes[str(int(mode, 2))]
                for r, c in bits:
                    tile[r][c] = 1
            else:
                init = str(parms['INIT'])
                init = init*(16//len(init))
                for bitnum, lutbit in enumerate(init[::-1]):
                    if lutbit == '0':
                        fuses = lutmap[bitnum]
                        for brow, bcol in fuses:
                            tile[brow][bcol] = 1

            if int(num) < 6:
                mode = str(parms['FF_TYPE']).strip('E')
                dffbits = tiledata.bels[f'DFF{num}'].modes[mode]
                for brow, bcol in dffbits:
                    tile[brow][bcol] = 1
            # XXX skip power
            if not cellname.startswith('\$PACKER'):
                cst.cells[cellname] = (row, col, int(num) // 2, _sides[int(num) % 2])
        elif typ[:3] == "IOB":
            # skip B for true lvds
            if 'DIFF' in attrs.keys():
                if attrs['DIFF_TYPE'] == 'TLVDS_OBUF' and attrs['DIFF'] == 'N':
                    continue
            edge = 'T'
            idx = col;
            if row == db.rows:
                edge = 'B'
            elif col == 1:
                edge = 'L'
                idx = row
            elif col == db.cols:
                edge = 'R'
                idx = row
            cst.ports[cellname] = f"IO{edge}{idx}{num}"
            iob = tiledata.bels[f'IOB{num}']
            if 'DIFF' in attrs.keys():
                mode = attrs['DIFF_TYPE']
            else:
                if int(parms["ENABLE_USED"], 2) and int(parms["OUTPUT_USED"], 2):
                    # TBUF = IOBUF - O
                    mode = "IOBUF"
                elif int(parms["INPUT_USED"], 2):
                    mode = "IBUF"
                elif int(parms["OUTPUT_USED"], 2):
                    mode = "OBUF"
                else:
                    raise ValueError("IOB has no in or output")

            pinless_io = False
            try:
                bank = chipdb.loc2bank(db, row - 1, col - 1)
                iostd = _banks.setdefault(bank, BankDesc(None, True, [], None)).iostd
            except KeyError:
                if not args.allow_pinless_io:
                    raise Exception(f"IO{edge}{idx}{num} is not allowed for a given package")
                pinless_io = True
                iostd = None

            # find io standard
            for flag in attrs.keys():
                flag_name_val = flag.split("=")
                if len(flag_name_val) < 2:
                    continue
                if flag[0] != chipdb.mode_attr_sep:
                    continue
                if flag_name_val[0] == chipdb.mode_attr_sep + "IO_TYPE":
                    if iostd and iostd != flag_name_val[1]:
                        raise Exception(f"Different I/O modes for the same bank {bank} were specified: {iostd} and {flag_name_val[1]}")
                    iostd = iostd_alias.get(flag_name_val[1], flag_name_val[1])

            # first used pin sets bank's iostd
            # XXX default io standard may be board-dependent!
            if not iostd:
                if 'DIFF' in attrs.keys():
                    iostd = "LVCMOS25"
                else:
                    iostd = "LVCMOS18"
            if not pinless_io:
                _banks[bank].iostd = iostd
                if mode == 'IBUF':
                    _banks[bank].bels_tiles.append((iob, tile))
                else:
                    _banks[bank].inputs_only = False

            if 'DIFF' in attrs.keys():
                _banks[bank].true_lvds_drive = "3.5"
            cst.attrs.setdefault(cellname, {}).update({"IO_TYPE": iostd})

            # collect flag bits
            if iostd not in iob.iob_flags.keys():
                print(f"Warning: {iostd} isn't allowed for IO{edge}{idx}{num}. Set LVCMOS18 instead.")
                iostd = 'LVCMOS18'
            if mode not in iob.iob_flags[iostd].keys() :
                    raise Exception(f"IO{edge}{idx}{num}. {mode} is not allowed for a given io standard {iostd}")
            bits = iob.iob_flags[iostd][mode].encode_bits.copy()
            # XXX OPEN_DRAIN must be after DRIVE
            attrs_keys = attrs.keys()
            if 'DIFF' not in attrs_keys:
                if 'OPEN_DRAIN=ON' in attrs_keys:
                    attrs_keys = itertools.chain(attrs_keys, ['OPEN_DRAIN=ON'])
                for flag in attrs.keys():
                    flag_name_val = flag.split("=")
                    if len(flag_name_val) < 2:
                        continue
                    if flag[0] != chipdb.mode_attr_sep:
                        continue
                    if flag_name_val[0] == chipdb.mode_attr_sep + "IO_TYPE":
                        continue
                    # skip OPEN_DRAIN=OFF can't clear by mask and OFF is the default
                    if flag_name_val[0] == chipdb.mode_attr_sep + "OPEN_DRAIN" \
                            and flag_name_val[1] == 'OFF':
                                continue
                    # set flag
                    mode_desc = iob.iob_flags[iostd][mode]
                    try:
                       flag_desc = mode_desc.flags[flag_name_val[0][1:]]
                       flag_bits = flag_desc.options[flag_name_val[1]]
                    except KeyError:
                        raise Exception(
                                f"Incorrect attribute {flag[1:]} (iostd:\"{iostd}\", mode:{mode})")
                    bits -= flag_desc.mask
                    bits.update(flag_bits)
                    cst.attrs[cellname].update({flag_name_val[0][1:] : flag_name_val[1]})
            for r, c in bits:
                tile[r][c] = 1

            if pinless_io:
                return
        elif typ == "ODDR":
            bel = tiledata.bels[f'ODDR{num}']
            bits = bel.modes['ENABLE'].copy()
            if int(attrs["IOBUF"], 2):
                bits.update(bel.flags['IOBUF'])
            for r, c in bits:
                tile[r][c] = 1
        elif typ == "RAMW":
            bel = tiledata.bels['RAM16']
            bits = bel.modes['0']
            #print(typ, bits)
            for r, c in bits:
                tile[r][c] = 1
        elif typ.startswith('RPLL'):
            pll_attrs = set_pll_attrs(db, 'RPLL', parms)
            bits = get_shortval_fuses(db, tiledata.ttyp, pll_attrs, 'PLL')
            #print(typ, bits)
            for r, c in bits:
                tile[r][c] = 1

        else:
            print("unknown type", typ)

    # If the entire bank has only inputs, the LVCMOS12/15/18 bit is set
    # in each IBUF regardless of the actual I/O standard.
    for bank, bank_desc in _banks.items():
        #bank enable
        brow, bcol = db.bank_tiles[bank]
        tiledata = db.grid[brow][bcol]
        btile = tilemap[(brow, bcol)]
        bank_bel = tiledata.bels['BANK' + bank]
        bits = bank_bel.modes['ENABLE'].copy()
        iostd = bank_desc.iostd
        if bank_desc.inputs_only:
            if bank_desc.iostd in {'LVCMOS33', 'LVCMOS25'}:
                for bel, tile in bank_desc.bels_tiles:
                    for row, col in bel.lvcmos121518_bits:
                        tile[row][col] = 1
            iostd = bank_bel.bank_input_only_modes[bank_desc.iostd]
        # iostd flag
        bits |= bank_bel.bank_flags[iostd]
        if bank_desc.true_lvds_drive:
            # XXX set drive
            comb_mode = f'LVDS25#{iostd}'
            if comb_mode not in bank_bel.bank_flags.keys():
                    raise Exception(
                            f'Incorrect iostd "{iostd}" for bank with "LVDS25" pin')
            bits |= bank_bel.bank_flags[comb_mode]
        for row, col in bits:
            btile[row][col] = 1

def route(db, tilemap, pips):
    for row, col, src, dest in pips:
        tiledata = db.grid[row-1][col-1]
        tile = tilemap[(row-1, col-1)]

        try:
            if dest in tiledata.clock_pips:
                bits = tiledata.clock_pips[dest][src]
            else:
                bits = tiledata.pips[dest][src]
        except KeyError:
            print(src, dest, "not found in tile", row, col)
            breakpoint()
            continue
        for row, col in bits:
            tile[row][col] = 1

def header_footer(db, bs, compress):
    """
    Generate fs header and footer
    Currently limited to checksum with
    CRC_check and security_bit_enable set
    """
    bs = np.fliplr(bs)
    bs=np.packbits(bs)
    # configuration data checksum is computed on all
    # data in 16bit format
    bb = np.array(bs)

    res = int(bb[0::2].sum() * pow(2,8) + bb[1::2].sum())
    checksum = res & 0xffff

    if compress:
        # update line 0x10 with compress enable bit
        # rest (keys) is done in bslib.write_bitstream
        hdr10 = int.from_bytes(db.cmd_hdr[4], 'big') | (1 << 13)
        db.cmd_hdr[4] = bytearray.fromhex(f"{hdr10:016x}")

    # set the checksum
    db.cmd_ftr[1] = bytearray.fromhex(f"{0x0A << 56 | checksum:016x}")

def dualmode_pins(db, tilemap, args):
    bits = set()
    if args.jtag_as_gpio:
        bits.update(db.grid[0][0].bels['CFG'].flags['JTAG'])
    if args.sspi_as_gpio:
        bits.update(db.grid[0][0].bels['CFG'].flags['SSPI'])
    if args.mspi_as_gpio:
        bits.update(db.grid[0][0].bels['CFG'].flags['MSPI'])
    if args.ready_as_gpio:
        bits.update(db.grid[0][0].bels['CFG'].flags['READY'])
    if args.done_as_gpio:
        bits.update(db.grid[0][0].bels['CFG'].flags['DONE'])
    if args.reconfign_as_gpio:
        bits.update(db.grid[0][0].bels['CFG'].flags['RECONFIG'])
    if bits:
        tile = tilemap[(0, 0)]
        for row, col in bits:
            tile[row][col] = 1

def main():
    global device
    pil_available = True
    try:
        from PIL import Image
    except ImportError:
        pil_available = False
    parser = argparse.ArgumentParser(description='Pack Gowin bitstream')
    parser.add_argument('netlist')
    parser.add_argument('-d', '--device', required=True)
    parser.add_argument('-o', '--output', default='pack.fs')
    parser.add_argument('-c', '--compress', default=False, action='store_true')
    parser.add_argument('-s', '--cst', default = None)
    parser.add_argument('--allow_pinless_io', action = 'store_true')
    parser.add_argument('--jtag_as_gpio', action = 'store_true')
    parser.add_argument('--sspi_as_gpio', action = 'store_true')
    parser.add_argument('--mspi_as_gpio', action = 'store_true')
    parser.add_argument('--ready_as_gpio', action = 'store_true')
    parser.add_argument('--done_as_gpio', action = 'store_true')
    parser.add_argument('--reconfign_as_gpio', action = 'store_true')
    if pil_available:
        parser.add_argument('--png')

    args = parser.parse_args()
    device = args.device
    # For tool integration it is allowed to pass a full part number
    m = re.match("GW1N(S|Z)?[A-Z]*-(LV|UV|UX)([0-9])C?([A-Z]{2}[0-9]+P?)(C[0-9]/I[0-9])", device)
    if m:
        mods = m.group(1) or ""
        luts = m.group(3)
        device = f"GW1N{mods}-{luts}"

    with importlib.resources.open_binary("apycula", f"{device}.pickle") as f:
        db = pickle.load(f)
    with open(args.netlist) as f:
        pnr = json.load(f)

    tilemap = chipdb.tile_bitmap(db, db.template, empty=True)
    cst = codegen.Constraints()
    bels = get_bels(pnr)
    place(db, tilemap, bels, cst, args)
    pips = get_pips(pnr)
    route(db, tilemap, pips)
    dualmode_pins(db, tilemap, args)
    res = chipdb.fuse_bitmap(db, tilemap)
    header_footer(db, res, args.compress)
    if pil_available and args.png:
        bslib.display(args.png, res)
    bslib.write_bitstream(args.output, res, db.cmd_hdr, db.cmd_ftr, args.compress)
    if args.cst:
        with open(args.cst, "w") as f:
                cst.write(f)

if __name__ == '__main__':
    main()
