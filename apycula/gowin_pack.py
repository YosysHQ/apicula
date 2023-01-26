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

def extra_pll_bels(cell, row, col, num, cellname):
    # rPLL can occupy several cells, add them depending on the chip
    offx = 1;
    if device == 'GW1N-9C':
        if int(col) > 28:
            offx = -1
        for off in [1, 2, 3]:
            yield ('RPLLB', int(row), int(col) + offx * off, num,
                cell['parameters'], cell['attributes'], sanitize_name(cellname) + f'B{off}')
    elif device in {'GW1N-1', 'GW1NZ-1'}:
        for off in [1]:
            yield ('RPLLB', int(row), int(col) + offx * off, num,
                cell['parameters'], cell['attributes'], sanitize_name(cellname) + f'B{off}')

def get_bels(data):
    later = []
    belre = re.compile(r"R(\d+)C(\d+)_(?:GSR|SLICE|IOB|MUX2_LUT5|MUX2_LUT6|MUX2_LUT7|MUX2_LUT8|ODDR|OSC[ZFH]?|BUFS|RAMW|rPLL|PLLVR)(\w*)")
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
        cell_type = cell['type']
        if cell_type == 'rPLL':
            cell_type = 'RPLLA'
            yield from extra_pll_bels(cell, row, col, num, cellname)
        yield (cell_type, int(row), int(col), num,
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

# Permitted frequencies for chips
# { device : (max_in, max_out, min_out, max_vco, min_vco) }
_permitted_freqs = {
        "GW1N-1":  (400, 450, 3.125,  900,  400),
        "GW1NZ-1": (400, 400, 3.125,  800,  400),
        "GW1N-4":  (400, 500, 3.125,  1000, 400),
        "GW1NS-4": (400, 600, 4.6875, 1200, 600),
        "GW1N-9":  (400, 500, 3.125,  1000, 400),
        "GW1N-9C": (400, 600, 3.125,  1200, 400),
        "GW1NS-2": (400, 500, 3.125,  1200, 400),
        }
# input params are calculated as described in GOWIN doc (UG286-1.7E_Gowin Clock User Guide)
# fref = fclkin / idiv
# fvco = (odiv * fdiv * fclkin) / idiv
#
# returns (fclkin_idx, icp, r_idx)
# fclkin_idx - input frequency range index
# icp - charge current
# r_idx - resistor value index

# There are not many resistors so the whole frequency range is divided into
# 30MHz intervals and the number of this interval is one of the fuse sets. But
# the resistor itself is not directly dependent on the input frequency.
_freq_R = [(2.6, 65100.0), (3.87, 43800.0), (7.53, 22250.0), (14.35, 11800.0), (28.51, 5940.0), (57.01, 2970.0), (114.41, 1480), (206.34, 820.0)]
def calc_pll_pump(fref, fvco):
    fclkin_idx = int((fref - 1) // 30)
    if (fclkin_idx == 13 and fref <= 395) or (fclkin_idx == 14 and fref <= 430) or (fclkin_idx == 15 and fref <= 465) or fclkin_idx == 16:
        fclkin_idx = fclkin_idx - 1

    r_vals = [(fr[1], len(_freq_R) - 1 - idx) for idx, fr in enumerate(_freq_R) if fr[0] < fref]
    r_vals.reverse()

    # Find the resistor that provides the minimum current through the capacitor
    K0 = (497.5 - math.sqrt(247506.25 - (2675.4 - fvco) * 78.46)) / 39.23
    K1 = 4.8714 * K0 * K0 + 6.5257 * K0 + 142.67
    Kvco = 1000000.0 * K1
    Ndiv = fvco / fref
    C1 = 6.69244e-11

    for R1, r_idx in r_vals:
        Ic = (1.8769 / (R1 * R1 * Kvco * C1)) * 4.0 * Ndiv
        if Ic <= 0.00028:
            icp = int(Ic * 100000.0 + 0.5) * 10
            break

    return ((fclkin_idx + 1) * 16, icp, r_idx)

# add the default pll attributes according to the documentation
_default_pll_inattrs = {
            'FCLKIN'        : '100.00',
            'IDIV_SEL'      : '0',
            'DYN_IDIV_SEL'  : 'false',
            'FBDIV_SEL'     : '00000000000000000000000000000000',
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
            'IRSTEN': 'DISABLE',
            'SRSTEN': 'DISABLE',
            'PWDEN': 'ENABLE',
            'RSTEN': 'ENABLE',
            'FLDCOUNT': 16,
            'GMCGAIN': 0,
            'LPR': 'R4',
            'ICPSEL': 50,
}

# typ - PLL type (RPLL, etc)
def set_pll_attrs(db, typ, idx, attrs):
    pll_inattrs = add_pll_default_attrs(attrs)
    pll_attrs = _default_pll_internal_attrs.copy()

    if typ not in {'RPLL', 'PLLVR'}:
        raise Exception(f"PLL type {typ} is not supported for now")
    if typ == 'PLLVR':
        pll_attrs[['PLLVCC0', 'PLLVCC1'][idx]] = 'ENABLE'

    # parse attrs
    for attr, val in pll_inattrs.items():
        if attr in pll_attrs.keys():
            pll_attrs[attr] = val
        if attr == 'CLKOUTD_SRC':
            if val == 'CLKOUTP':
                pll_attrs['CLKOUTDIVSEL'] = 'CLKOUTPS'
            continue
        if attr == 'CLKOUTD3_SRC':
            if val == 'CLKOUTP':
                pll_attrs['CLKOUTDIV3SEL'] = 'CLKOUTPS'
            continue
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
            pll_attrs['SDIV'] = int(val, 2)
            continue
        if attr == 'ODIV_SEL':
            odiv = int(val, 2)
            pll_attrs['ODIV'] = odiv
            continue
        if attr == 'DYN_DA_EN':
            if val == 'true':
                pll_attrs['DPSEL'] = 'DYN'
                pll_attrs['DUTY'] = 0
                pll_attrs['PHASE'] = 0
                pll_attrs['PASEL'] = 'DISABLE'
                # steps in 50ps
                tmp_val = int(pll_inattrs['CLKOUT_DLY_STEP'], 2) * 50
                pll_attrs['OPDLY'] = tmp_val
                # XXX here is unclear according to the documentation only three
                # values are allowed: 0, 1 and 2, but there are 4 fuses (0, 50,
                # 75, 100). Find out what to do with 75
                tmp_val = int(pll_inattrs['CLKOUTP_DLY_STEP'], 2) * 50
                pll_attrs['OSDLY'] = tmp_val
            else:
                pll_attrs['OSDLY'] = 'DISABLE'
                pll_attrs['OPDLY'] = 'DISABLE'
                phase_val = int(pll_inattrs['PSDA_SEL'].strip(), 2)
                pll_attrs['PHASE'] = phase_val
                duty_val = int(pll_inattrs['DUTYDA_SEL'].strip(), 2)
                # XXX there are fuses for 15 variants (excluding 0) so for now
                # we will implement all of them, including those prohibited by
                # documentation 1 and 15
                if (phase_val + duty_val) < 16:
                    duty_val = phase_val + duty_val
                else:
                    duty_val = phase_val + duty_val - 16
                pll_attrs['DUTY'] = duty_val
            continue
        if attr == 'FCLKIN':
            fclkin = float(val)
            if fclkin < 3 or fclkin > _permitted_freqs[device][0]:
                print(f"The {fclkin}MHz frequency is outside the permissible range of 3-{_permitted_freqs[device][0]}MHz.")
                fclkin = 100.0
            continue

    # static vs dynamic
    if pll_inattrs['DYN_IDIV_SEL'] == 'false' and pll_inattrs['DYN_FBDIV_SEL'] == 'false' and pll_inattrs['DYN_ODIV_SEL'] == 'false':
        # static. We can immediately check the compatibility of the divisors
        clkout = fclkin * fbdiv / idiv
        if clkout <= _permitted_freqs[device][2] or clkout > _permitted_freqs[device][1]:
            raise Exception(f"CLKOUT = FCLKIN*(FBDIV_SEL+1)/(IDIV_SEL+1) = {clkout}MHz not in range {_permitted_freqs[device][2]} - {_permitted_freqs[device][1]}MHz")
        pfd = fclkin / idiv
        if pfd < 3.0 or pfd > _permitted_freqs[device][0]:
            raise Exception(f"PFD = FCLKIN/(IDIV_SEL+1) = {pfd}MHz not in range 3.0 - {_permitted_freqs[device][0]}MHz")
        fvco = odiv * fclkin * fbdiv / idiv
        if fvco < _permitted_freqs[device][4] or  fvco > _permitted_freqs[device][3]:
            raise Exception(f"VCO = FCLKIN*(FBDIV_SEL+1)*ODIV_SEL/(IDIV_SEL+1) = {fvco}MHz not in range {_permitted_freqs[device][4]} - {_permitted_freqs[device][3]}MHz")

    # pump
    fref = fclkin / idiv
    fvco = (odiv * fbdiv * fclkin) / idiv
    fclkin_idx, icp, r_idx = calc_pll_pump(fref, fvco)

    pll_attrs['FLDCOUNT'] = fclkin_idx
    pll_attrs['ICPSEL'] = int(icp)
    pll_attrs['LPR'] = f"R{r_idx}"

    fin_attrs = set()
    for attr, val in pll_attrs.items():
        if isinstance(val, str):
            val = pll_attrvals[val]
        add_attr_val(db, 'PLL', fin_attrs, pll_attrids[attr], val)
    #print(fin_attrs)
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
            pll_attrs = set_pll_attrs(db, 'RPLL', 0,  parms)
            bits = set()
            if 'PLL' in db.shortval[tiledata.ttyp].keys():
                bits = get_shortval_fuses(db, tiledata.ttyp, pll_attrs, 'PLL')
            #print(typ, bits)
            for r, c in bits:
                tile[r][c] = 1
        elif typ == 'PLLVR':
            idx = 0
            if col != 28:
                idx = 1
            pll_attrs = set_pll_attrs(db, 'PLLVR', idx, parms)
            bits = get_shortval_fuses(db, tiledata.ttyp, pll_attrs, 'PLL')
            #print(typ, bits)
            for r, c in bits:
                tile[r][c] = 1
            # only for 4C, we know exactly where CFG is
            cfg_type = 51
            bits = get_shortval_fuses(db, cfg_type, pll_attrs, 'PLL')
            cfg_tile = tilemap[(0, 37)]
            for r, c in bits:
                cfg_tile[r][c] = 1


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

# The vertical columns of long wires can receive a signal from either the upper
# or the lower end of the column.
# The default source is the top end of the column, but if optimum routing has
# resulted in the bottom end of the column being used, the top end must be
# electrically disconnected by setting special fuses.
def secure_long_wires(db, tilemap, row, col, src, dest):
    if device in {"GW1N-1"}:
        # the column runs across the entire height of the chip from the first to the last row
        check_row = db.rows
        fuse_row = 0
        if row == check_row and dest in {'LT02', 'LT13'}:
            tiledata = db.grid[fuse_row][col - 1]
            if dest in tiledata.alonenode_6.keys():
                tile = tilemap[(fuse_row, col - 1)]
                _, bits = tiledata.alonenode_6[dest]
                for row, col in bits:
                    tile[row][col] = 1


def route(db, tilemap, pips):
    for row, col, src, dest in pips:
        tiledata = db.grid[row-1][col-1]
        tile = tilemap[(row-1, col-1)]
        # short-circuit prevention
        secure_long_wires(db, tilemap, row, col, src, dest)

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
