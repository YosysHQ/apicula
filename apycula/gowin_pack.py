import sys
import os
import re
import pickle
import gzip
import itertools
import math
import json
import argparse
import importlib.resources
from collections import namedtuple
from contextlib import closing
from apycula import codegen
from apycula import chipdb
from apycula.chipdb import add_attr_val, get_shortval_fuses, get_longval_fuses, get_bank_fuses
from apycula import attrids
from apycula import bslib
from apycula import bitmatrix
from apycula.wirenames import wirenames, wirenumbers

device = ""
pnr = None
is_himbaechel = False
has_bsram_init = False
bsram_init_map = None

# Sometimes it is convenient to know where a port is connected to enable
# special fuses for VCC/VSS cases.

# This is not the optimal place for it - resources for routing are taken anyway
# and it should be done in nextpnr (as well as at yosys level to identify
# inverters since we can invert inputs without LUT in many cases), but for now
# let it be here to work out the mechanisms.
# Do not use for IOBs - their wires may be disconnected by IOLOGIC
_vcc_net = []
_gnd_net = []

def is_gnd_net(wire):
    return wire in _gnd_net

def is_vcc_net(wire):
    return wire in _vcc_net

def is_connected(wire, connections):
    return len(connections[wire]) != 0

### IOB
def iob_is_gnd_net(flags, wire):
    return flags.get(f'NET_{wire}', False) == 'GND'

def iob_is_vcc_net(flags, wire):
    return flags.get(f'NET_{wire}', False) == 'VCC'

def iob_is_connected(flags, wire):
    return f'NET_{wire}' in flags

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
    offx = 1
    if device in {'GW1N-9C', 'GW1N-9', 'GW2A-18', 'GW2A-18C'}:
        if int(col) > 28:
            offx = -1
        for off in [1, 2, 3]:
            yield ('RPLLB', int(row), int(col) + offx * off, num,
                cell['parameters'], cell['attributes'], sanitize_name(cellname) + f'B{off}', cell)
    elif device in {'GW1N-1', 'GW1NZ-1', 'GW1N-4'}:
        for off in [1]:
            yield ('RPLLB', int(row), int(col) + offx * off, num,
                cell['parameters'], cell['attributes'], sanitize_name(cellname) + f'B{off}', cell)

def extra_bsram_bels(cell, row, col, num, cellname):
    for off in [1, 2]:
        yield ('BSRAM_AUX', int(row), int(col) + off, num,
            cell['parameters'], cell['attributes'], sanitize_name(cellname) + f'AUX{off}', cell)

def extra_dsp_bels(cell, row, col, num, cellname):
    for off in range(1,9):
        yield ('DSP_AUX', int(row), int(col) + off, num,
            cell['parameters'], cell['attributes'], sanitize_name(cellname) + f'AUX{off}', cell)

# Explanation of what comes from and magic numbers. The process is this: you
# create a file with one primitive from the BSRAM family. In my case pROM. You
# give it a completely zero initialization. You generate an image. You specify
# one single unit bit at address 0 in the initialization. You generate an
# image. You compare. You sweep away garbage like CRC.
# Repeat 16 times.
# The 16th bit did not show much, but it allowed us to discover the meaning of
# the logicinfo table [39] - this is the location of a bit in the chip
# depending on its location in a 16-bit word.
# Next, we set the bits at address 2 (the next 16 bits) and compare. The result
# is unexpected: the bits no longer end up where we expect, but a certain pattern
# is present - bits 4 and 5 radically change the position of the bits in the
# chip, we take this into account.
# We repeat for bits up to the 13th --- since this is the maximum address in one SRAM block.
def store_bsram_init_val(db, row, col, typ, parms, attrs):
    global bsram_init_map
    global has_bsram_init
    if typ == 'BSRAM_AUX' or 'INIT_RAM_00' not in parms:
        return

    subtype = attrs['BSRAM_SUBTYPE']
    if not has_bsram_init:
        has_bsram_init = True
        # 256 * bsram rows * chip bit width
        bsram_init_map = bitmatrix.zeros(256 * len(db.simplio_rows), bitmatrix.shape(db.template)[1])
    # 3 BSRAM cells have width 3 * 60
    loc_map = bitmatrix.zeros(256, 3 * 60)
    #print("mapping")
    if not subtype.strip():
        width = 256
    elif subtype in {'X9'}:
        width = 288
    else:
        raise Exception(f"Init for {subtype} is not supported")

    def get_bits(init_data):
        bit_no = 0
        ptr = -1
        while ptr >= -width:
            if bit_no == 8 or bit_no == 17:
                if width == 288:
                    yield (init_data[ptr], bit_no, lambda x: x)
                    ptr -= 1
                else:
                    yield ('0', bit_no, lambda x: x)
                bit_no = (bit_no + 1) % 18
            else:
                yield (init_data[ptr], bit_no, lambda x: x + 1)
                ptr -= 1
                bit_no = (bit_no + 1) % 18

    addr = -1
    for init_row in range(0x40):
        init_data = parms[f'INIT_RAM_{init_row:02X}']
        #print(init_data)
        for ptr_bit_inc in get_bits(init_data):
            addr = ptr_bit_inc[2](addr)
            if ptr_bit_inc[0] == '0':
                continue
            logic_line = ptr_bit_inc[1] * 4 + (addr >> 12)
            bit = db.logicinfo['BSRAM_INIT'][logic_line][0] - 1
            quad = {0x30: 0xc0, 0x20: 0x40, 0x10: 0x80, 0x00: 0x0}[addr & 0x30]
            map_row = quad + ((addr >> 6) & 0x3f)
            #print(f'map_row:{map_row}, addr: {addr}, bit {ptr_bit_inc[1]}, bit:{bit}')
            loc_map[map_row][bit] = 1

    # now put one cell init data into global place
    height = 256
    y = 0
    for brow in db.simplio_rows:
        if row == brow:
            break
        y += height
    x = 0
    for jdx in range(col):
        x += db.grid[0][jdx].width
    loc_map = bitmatrix.flipud(loc_map)
    for row in loc_map:
        x0 = x
        for val in row:
            bsram_init_map[y][x0] = val
            x0 += 1
        y += 1

_bsram_cell_types = {'DP', 'SDP', 'SP', 'ROM'}
_dsp_cell_types = {'ALU54D', 'MULT36X36', 'MULTALU36X18', 'MULTADDALU18X18', 'MULTALU18X18', 'MULT18X18', 'MULT9X9', 'PADD18', 'PADD9'}
def get_bels(data):
    later = []
    if is_himbaechel:
        belre = re.compile(r"X(\d+)Y(\d+)/(?:GSR|LUT|DFF|IOB|MUX|ALU|ODDR|OSC[ZFHWO]?|BUF[GS]|RAM16SDP4|RAM16SDP2|RAM16SDP1|PLL|IOLOGIC|BSRAM|ALU|MULTALU18X18|MULTALU36X18|MULTADDALU18X18|MULT36X36|MULT18X18|MULT9X9|PADD18|PADD9)(\w*)")
    else:
        belre = re.compile(r"R(\d+)C(\d+)_(?:GSR|SLICE|IOB|MUX2_LUT5|MUX2_LUT6|MUX2_LUT7|MUX2_LUT8|ODDR|OSC[ZFHWO]?|BUFS|RAMW|rPLL|PLLVR|IOLOGIC)(\w*)")

    for cellname, cell in data['modules']['top']['cells'].items():
        if cell['type'].startswith('DUMMY_') or cell['type'] in {'OSER16', 'IDES16'} or 'NEXTPNR_BEL' not in cell['attributes']:
            continue
        bel = cell['attributes']['NEXTPNR_BEL']
        if bel in {"VCC", "GND"}: continue
        if is_himbaechel and bel[-4:] in {'/GND', '/VCC'}:
            continue

        bels = belre.match(bel)
        if not bels:
            raise Exception(f"Unknown bel:{bel}")
        row, col, num = bels.groups()
        if is_himbaechel:
            col_ = col
            col = str(int(row) + 1)
            row = str(int(col_) + 1)

        # The differential buffer is pushed to the end of the queue for processing
        # because it does not have an independent iostd, but adjusts to the normal pins
        # in the bank, if any are found
        if 'DIFF' in cell['attributes']:
            later.append((cellname, cell, row, col, num))
            continue
        cell_type = cell['type']
        if cell_type == 'rPLL':
            cell_type = 'RPLLA'
            yield from extra_pll_bels(cell, row, col, num, cellname)
        if cell_type in _bsram_cell_types:
            yield from extra_bsram_bels(cell, row, col, num, cellname)
        if cell_type in _dsp_cell_types:
            yield from extra_dsp_bels(cell, row, col, num, cellname)
        yield (cell_type, int(row), int(col), num,
                cell['parameters'], cell['attributes'], sanitize_name(cellname), cell)

    # diff iobs
    for cellname, cell, row, col, num in later:
        yield (cell['type'], int(row), int(col), num,
                cell['parameters'], cell['attributes'], sanitize_name(cellname), cell)

_pip_bels = []
def get_pips(data):
    if is_himbaechel:
        pipre = re.compile(r"X(\d+)Y(\d+)/([\w_]+)/([\w_]+)")
    else:
        pipre = re.compile(r"R(\d+)C(\d+)_([^_]+)_([^_]+)")
    for net in data['modules']['top']['netnames'].values():
        routing = net['attributes']['ROUTING']
        pips = routing.split(';')[1::3]
        for pip in pips:
            res = pipre.fullmatch(pip) # ignore alias
            if res:
                row, col, src, dest = res.groups()
                if is_himbaechel:
                    # XD - input of the DFF
                    if src.startswith('XD'):
                        if dest.startswith('F'):
                            continue
                        # pass-though LUT
                        num = dest[1]
                        init = {'A': '1010101010101010', 'B': '1100110011001100',
                                'C': '1111000011110000', 'D': '1111111100000000'}[dest[0]]
                        _pip_bels.append(("LUT4", int(col) + 1, int(row) + 1, num, {"INIT": init}, {}, f'$PACKER_PASS_LUT_{len(_pip_bels)}', None))
                        continue
                    yield int(col) + 1, int(row) + 1, dest, src
                else:
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
        "GW2A-18": (400, 600, 3.125,  1200, 400), # XXX check it
        "GW2A-18C": (400, 600, 3.125,  1200, 400), # XXX check it
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
_freq_R = [[(2.6, 65100.0), (3.87, 43800.0), (7.53, 22250.0), (14.35, 11800.0), (28.51, 5940.0), (57.01, 2970.0), (114.41, 1480), (206.34, 820.0)], [(2.4, 69410.0), (3.53, 47150.0), (6.82, 24430.0), (12.93, 12880.0), (25.7, 6480.0), (51.4, 3240.0), (102.81, 1620), (187.13, 890.0)]]
def calc_pll_pump(fref, fvco):
    fclkin_idx = int((fref - 1) // 30)
    if (fclkin_idx == 13 and fref <= 395) or (fclkin_idx == 14 and fref <= 430) or (fclkin_idx == 15 and fref <= 465) or fclkin_idx == 16:
        fclkin_idx = fclkin_idx - 1

    if device not in {'GW2A-18', 'GW2A-18C'}:
        freq_Ri = _freq_R[0]
    else:
        freq_Ri = _freq_R[1]
    r_vals = [(fr[1], len(freq_Ri) - 1 - idx) for idx, fr in enumerate(freq_Ri) if fr[0] < fref]
    r_vals.reverse()

    # Find the resistor that provides the minimum current through the capacitor
    if device not in {'GW2A-18', 'GW2A-18C'}:
        K0 = (497.5 - math.sqrt(247506.25 - (2675.4 - fvco) * 78.46)) / 39.23
        K1 = 4.8714 * K0 * K0 + 6.5257 * K0 + 142.67
    else:
        K0 = (-28.938 + math.sqrt(837.407844 - (385.07 - fvco) * 0.9892)) / 0.4846
        K1 = 0.1942 * K0 * K0 - 13.173 * K0 + 518.86
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


def add_pll_default_attrs(attrs):
    pll_inattrs = attrs.copy()
    for k, v in _default_pll_inattrs.items():
        if k in pll_inattrs:
            continue
        pll_inattrs[k] = v
    return pll_inattrs


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
        if attr in pll_attrs:
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
            val = attrids.pll_attrvals[val]
        add_attr_val(db, 'PLL', fin_attrs, attrids.pll_attrids[attr], val)
    return fin_attrs

_bsram_bit_widths = { 1: '1', 2: '2', 4: '4', 8: '9', 9: '9', 16: '16', 18: '16', 32: 'X36', 36: 'X36'}
def set_bsram_attrs(db, typ, params):
    bsram_attrs = {}
    bsram_attrs['MODE'] = 'ENABLE'
    bsram_attrs['GSR'] = 'DISABLE'

    for parm, val in params.items():
        if parm == 'BIT_WIDTH':
            val = int(val, 2)
            if val in _bsram_bit_widths:
                if typ not in {'ROM'}:
                    if val in {16, 18}: # XXX no dynamic byte enable
                        bsram_attrs[f'{typ}A_BEHB'] = 'DISABLE'
                        bsram_attrs[f'{typ}A_BELB'] = 'DISABLE'
                    elif val in {32, 36}: # XXX no dynamic byte enable
                        bsram_attrs[f'{typ}A_BEHB'] = 'DISABLE'
                        bsram_attrs[f'{typ}A_BELB'] = 'DISABLE'
                        bsram_attrs[f'{typ}B_BEHB'] = 'DISABLE'
                        bsram_attrs[f'{typ}B_BELB'] = 'DISABLE'
                if val not in {32, 36}:
                    bsram_attrs[f'{typ}A_DATA_WIDTH'] = _bsram_bit_widths[val]
                    bsram_attrs[f'{typ}B_DATA_WIDTH'] = _bsram_bit_widths[val]
                elif typ != 'SP':
                    bsram_attrs['DBLWA'] = _bsram_bit_widths[val]
                    bsram_attrs['DBLWB'] = _bsram_bit_widths[val]
            else:
                raise Exception(f"BSRAM width of {val} isn't supported for now")
        elif parm == 'BIT_WIDTH_0':
            val = int(val, 2)
            if val in _bsram_bit_widths:
                if val not in {32, 36}:
                    bsram_attrs[f'{typ}A_DATA_WIDTH'] = _bsram_bit_widths[val]
                else:
                    bsram_attrs['DBLWA'] = _bsram_bit_widths[val]
                if val in {16, 18, 32, 36}: # XXX no dynamic byte enable
                    bsram_attrs[f'{typ}A_BEHB'] = 'DISABLE'
                    bsram_attrs[f'{typ}A_BELB'] = 'DISABLE'
            else:
                raise Exception(f"BSRAM width of {val} isn't supported for now")
        elif parm == 'BIT_WIDTH_1':
            val = int(val, 2)
            if val in _bsram_bit_widths:
                if val not in {32, 36}:
                    bsram_attrs[f'{typ}B_DATA_WIDTH'] = _bsram_bit_widths[val]
                else:
                    bsram_attrs['DBLWB'] = _bsram_bit_widths[val]
                if val in {16, 18, 32, 36}: # XXX no dynamic byte enable
                    bsram_attrs[f'{typ}B_BEHB'] = 'DISABLE'
                    bsram_attrs[f'{typ}B_BELB'] = 'DISABLE'
            else:
                raise Exception(f"BSRAM width of {val} isn't supported for now")
        elif parm == 'BLK_SEL':
            for i in range(3):
                if val[-1 - i] == '0':
                    bsram_attrs[f'CSA_{i}'] = 'SET'
                    bsram_attrs[f'CSB_{i}'] = 'SET'
        elif parm == 'BLK_SEL_0':
            for i in range(3):
                if val[-1 - i] == '0':
                    bsram_attrs[f'CSA_{i}'] = 'SET'
        elif parm == 'BLK_SEL_1':
            for i in range(3):
                if val[-1 - i] == '0':
                    bsram_attrs[f'CSB_{i}'] = 'SET'
        elif parm == 'READ_MODE0':
            val = int(val, 2)
            if val == 1:
                bsram_attrs[f'{typ}A_REGMODE'] = 'OUTREG'
        elif parm == 'READ_MODE1':
            val = int(val, 2)
            if val == 1:
                bsram_attrs[f'{typ}B_REGMODE'] = 'OUTREG'
        elif parm == 'READ_MODE':
            val = int(val, 2)
            if val == 1:
                bsram_attrs[f'{typ}A_REGMODE'] = 'OUTREG'
                bsram_attrs[f'{typ}B_REGMODE'] = 'OUTREG'
        elif parm == 'RESET_MODE':
            if val == 'ASYNC':
                bsram_attrs[f'OUTREG_ASYNC'] = 'RESET'
        elif parm == 'WRITE_MODE0':
            val = int(val, 2)
            if val == 1:
                bsram_attrs[f'{typ}A_MODE'] = 'WT'
            elif val == 2:
                bsram_attrs[f'{typ}A_MODE'] = 'RBW'
        elif parm == 'WRITE_MODE1':
            val = int(val, 2)
            if val == 1:
                bsram_attrs[f'{typ}B_MODE'] = 'WT'
            elif val == 2:
                bsram_attrs[f'{typ}B_MODE'] = 'RBW'
        elif parm == 'WRITE_MODE':
            val = int(val, 2)
            if val == 1:
                bsram_attrs[f'{typ}A_MODE'] = 'WT'
                bsram_attrs[f'{typ}B_MODE'] = 'WT'
            elif val == 2:
                bsram_attrs[f'{typ}A_MODE'] = 'RBW'
                bsram_attrs[f'{typ}B_MODE'] = 'RBW'
    fin_attrs = set()
    for attr, val in bsram_attrs.items():
        if isinstance(val, str):
            val = attrids.bsram_attrvals[val]
        add_attr_val(db, 'BSRAM', fin_attrs, attrids.bsram_attrids[attr], val)
    return fin_attrs

# MULTALU18X18
_ABLH = [('A', 'L'), ('A', 'H'), ('B', 'L'), ('B', 'H')]
_01LH = [(0, 'L'), (1, 'H')]
def set_multalu18x18_attrs(db, typ, params, num, attrs, dsp_attrs, mac):
    ce_val = 'UNKNOWN'
    if int(attrs['CE'], 2):
        ce_val = f"CEIN{int(attrs['CE'], 2)}"
    clk_val = 'UNKNOWN'
    if int(attrs['CLK'], 2):
        clk_val = f"CLKIN{int(attrs['CLK'], 2)}"
    reset_val = 'UNKNOWN'
    if int(attrs['RESET'], 2):
        reset_val = f"RSTIN{int(attrs['RESET'], 2)}"

    # The mode determines which multiplier is used, and this in turn selects
    # the registers and pins used. We rely on nextpnr so that MULTALU18X18_MODE
    # is from the set {0, 1, 2}
    mode = int(params['MULTALU18X18_MODE'], 2)
    mode_01 = 0
    if mode != 2:
        mode_01 = 1

    accload = attrs['NET_ACCLOAD']

    dsp_attrs["RCISEL_3"] = "1"
    if mode_01:
        dsp_attrs["RCISEL_1"] = "1"

    dsp_attrs['OR2CIB_EN0L_0'] = "ENABLE"
    dsp_attrs['OR2CIB_EN0H_1'] = "ENABLE"
    dsp_attrs['OR2CIB_EN1L_2'] = "ENABLE"
    dsp_attrs['OR2CIB_EN1H_3'] = "ENABLE"

    if 'B_ADD_SUB' in params:
        if int(params['B_ADD_SUB'], 2) == 1:
            dsp_attrs['OPCD_7'] = "1"

    dsp_attrs['ALU_EN'] = "ENABLE"
    dsp_attrs['OPCD_5'] = "1"
    dsp_attrs['OPCD_9'] = "1"
    for i in {5, 6}:
        dsp_attrs[f'CINBY_{i}'] = "ENABLE"
        dsp_attrs[f'CINNS_{i}'] = "ENABLE"
        dsp_attrs[f'CPRBY_{i}'] = "ENABLE"
        dsp_attrs[f'CPRNS_{i}'] = "ENABLE"

    if "USE_CASCADE_IN" in attrs:
        dsp_attrs['CSGIN_EXT'] = "ENABLE"
        dsp_attrs['CSIGN_PRE'] = "ENABLE"
    if "USE_CASCADE_OUT" in attrs:
        dsp_attrs['OR2CASCADE_EN'] = "ENABLE"

    if mode_01:
        dsp_attrs['OPCD_2'] = "1"
        if accload == "VCC":
            dsp_attrs['OR2CASCADE_EN'] = "ENABLE"
        elif accload == "GND":
            dsp_attrs['OPCD_0'] = "1"
            dsp_attrs['OPCD_1'] = "1"
        else:
            dsp_attrs['OPCDDYN_0'] = "ENABLE"
            dsp_attrs['OPCDDYN_1'] = "ENABLE"
            dsp_attrs['OR2CASCADE_EN'] = "ENABLE"
            dsp_attrs['OPCDDYN_INV_0'] = "ENABLE"
            dsp_attrs['OPCDDYN_INV_1'] = "ENABLE"
        if mode == 0:
            dsp_attrs['OPCD_4'] = "1"
            if 'C_ADD_SUB' in params:
                if int(params['C_ADD_SUB'], 2) == 1:
                    dsp_attrs['OPCD_8'] = "1"
    else:
        dsp_attrs['OPCD_0'] = "1"
        dsp_attrs['OPCD_3'] = "1"

    for parm, val in params.items():
        if parm == 'AREG':
            if val == '0':
                for i, h in _01LH:
                    dsp_attrs[f'IRBY_IREG{mode_01}A{h}_{4 * mode_01 + i}']  = "ENABLE"
                    dsp_attrs[f'IRNS_IREG{mode_01}A{h}_{4 * mode_01 + i}']  = "ENABLE"
            else:
                for h in "LH":
                    dsp_attrs[f'CE{h}MUX_REGMA{mode_01}']  = ce_val
                    dsp_attrs[f'CLK{h}MUX_REGMA{mode_01}'] = clk_val
                    dsp_attrs[f'RST{h}MUX_REGMA{mode_01}'] = reset_val
                if 'MULT_RESET_MODE' in params:
                    if params['MULT_RESET_MODE'] == 'SYNC':
                        for h in "LH":
                            dsp_attrs[f'RSTGEN{h}MUX_REGMA{mode_01}'] = 'SYNC'
        if parm == 'BREG':
            if val == '0':
                for i, h in _01LH:
                    dsp_attrs[f'IRBY_IREG{mode_01}B{h}_{4 * mode_01 + 2 + i}']  = "ENABLE"
                    dsp_attrs[f'IRNS_IREG{mode_01}B{h}_{4 * mode_01 + 2 + i}']  = "ENABLE"
            else:
                for h in "LH":
                    dsp_attrs[f'CE{h}MUX_REGMB{mode_01}']  = ce_val
                    dsp_attrs[f'CLK{h}MUX_REGMB{mode_01}'] = clk_val
                    dsp_attrs[f'RST{h}MUX_REGMB{mode_01}'] = reset_val
                if 'MULT_RESET_MODE' in params:
                    if params['MULT_RESET_MODE'] == 'SYNC':
                        for h in "LH":
                            dsp_attrs[f'RSTGEN{h}MUX_REGMB{mode_01}'] = 'SYNC'
        if parm == 'CREG' and mode_01:
            if val == '0':
                for i, h in _01LH:
                    dsp_attrs[f'CIR_BYP{h}_{i}'] = "1"
            else:
                for h in "LH":
                    dsp_attrs[f'CE{h}MUX_CREG']  = ce_val
                    dsp_attrs[f'CLK{h}MUX_CREG'] = clk_val
                    dsp_attrs[f'RST{h}MUX_CREG'] = reset_val
                if 'MULT_RESET_MODE' in params:
                    if params['MULT_RESET_MODE'] == 'SYNC':
                        for h in "LH":
                            dsp_attrs[f'RSTGEN{h}MUX_REGC0'] = 'SYNC'
        if parm == 'DREG' and not mode_01:
            if val == '0':
                dsp_attrs['CIR_BYPH_1'] = "1"
                ii = 4
                for i, h in _ABLH:
                    dsp_attrs[f'IRBY_IREG1{i}{h}_{ii}'] = "ENABLE"
                    dsp_attrs[f'IRNS_IREG1{i}{h}_{ii}'] = "ENABLE"
                    ii += 1
            else:
                dsp_attrs['CEHMUX_CREG']  = ce_val
                dsp_attrs['CLKHMUX_CREG'] = clk_val
                dsp_attrs['RSTHMUX_CREG'] = reset_val
                for i, h in _ABLH:
                    dsp_attrs[f'CE{h}MUX_REGM{i}1']  = ce_val
                    dsp_attrs[f'CLK{h}MUX_REGM{i}1'] = clk_val
                    dsp_attrs[f'RST{h}MUX_REGM{i}1'] = reset_val
                if 'MULT_RESET_MODE' in params:
                    if params['MULT_RESET_MODE'] == 'SYNC':
                        dsp_attrs['RSTGENHMUX_REGC0'] = 'SYNC'
                        for i, h in _ABLH:
                            dsp_attrs[f'RSTGEN{h}MUX_REGM{i}1'] = 'SYNC'
        if parm == 'ASIGN_REG':
            if val == '0':
                dsp_attrs[f'CINNS_{3 * mode_01}'] = "ENABLE"
                dsp_attrs[f'CINBY_{3 * mode_01}'] = "ENABLE"
            else:
                dsp_attrs[f'CEMUX_ASIGN{mode_01}1']  = ce_val
                dsp_attrs[f'CLKMUX_ASIGN{mode_01}1'] = clk_val
                dsp_attrs[f'RSTMUX_ASIGN{mode_01}1'] = reset_val
                if 'MULT_RESET_MODE' in params:
                    if params['MULT_RESET_MODE'] == 'SYNC':
                        dsp_attrs[f'RSTGENMUX_ASIGN{mode_01}1'] = 'SYNC'
        if parm == 'BSIGN_REG':
            if val == '0':
                dsp_attrs[f'CINNS_{1 + 3 * mode_01}'] = "ENABLE"
                dsp_attrs[f'CINBY_{1 + 3 * mode_01}'] = "ENABLE"
            else:
                dsp_attrs[f'CEMUX_BSIGN{mode_01}1']  = ce_val
                dsp_attrs[f'CLKMUX_BSIGN{mode_01}1'] = clk_val
                dsp_attrs[f'RSTMUX_BSIGN{mode_01}1'] = reset_val
                if 'MULT_RESET_MODE' in params:
                    if params['MULT_RESET_MODE'] == 'SYNC':
                        dsp_attrs[f'RSTGENMUX_BSIGN{mode_01}1'] = 'SYNC'
        if parm == 'DSIGN_REG' and not mode_01:
            if val == '0':
                dsp_attrs['CINNS_4'] = "ENABLE"
                dsp_attrs['CINBY_4'] = "ENABLE"
            else:
                dsp_attrs['CEMUX_BSIGN11']  = ce_val
                dsp_attrs['CLKMUX_BSIGN11'] = clk_val
                dsp_attrs['RSTMUX_BSIGN11'] = reset_val
                if 'MULT_RESET_MODE' in params:
                    if params['MULT_RESET_MODE'] == 'SYNC':
                        dsp_attrs['RSTGENMUX_BSIGN11'] = 'SYNC'
            if 'PIPE_REG' in params:
                if params['PIPE_REG'] == '0':
                    dsp_attrs['CPRNS_4'] = "ENABLE"
                    dsp_attrs['CPRBY_4'] = "ENABLE"
                else:
                    dsp_attrs['CLK_BSIGN12'] = clk_val
                    dsp_attrs['RST_BSIGN12'] = reset_val
                    if 'MULT_RESET_MODE' in params:
                        if params['MULT_RESET_MODE'] == 'SYNC':
                            dsp_attrs[f'RSTGENMUX_BSIGN12'] = 'SYNC'

        if parm == 'PIPE_REG':
            if val == '0':
                dsp_attrs[f'CPRNS_{3 * mode_01}'] = "ENABLE"
                dsp_attrs[f'CPRBY_{3 * mode_01}'] = "ENABLE"
                dsp_attrs[f'CPRNS_{1 + 3 * mode_01}'] = "ENABLE"
                dsp_attrs[f'CPRBY_{1 + 3 * mode_01}'] = "ENABLE"
                for i, h in _01LH:
                    dsp_attrs[f'PPREG{mode_01}_NS{h}_{2 * mode_01 + i}']  = "ENABLE"
                    dsp_attrs[f'PPREG{mode_01}_BYP{h}_{2 * mode_01 + i}']  = "ENABLE"
            else:
                for i in "AB":
                    dsp_attrs[f'CEMUX_{i}SIGN{1 - mode_01}2']  = ce_val
                    dsp_attrs[f'CLKMUX_{i}SIGN{1 - mode_01}2'] = clk_val
                    dsp_attrs[f'RSTMUX_{i}SIGN{1 - mode_01}2'] = reset_val
                for i in "LH":
                    dsp_attrs[f'CE{i}MUX_REGP{1 - mode_01}']  = ce_val
                    dsp_attrs[f'CLK{i}MUX_REGP{1 - mode_01}'] = clk_val
                    dsp_attrs[f'RST{i}MUX_REGP{1 - mode_01}'] = reset_val
                if 'MULT_RESET_MODE' in params:
                    if params['MULT_RESET_MODE'] == 'SYNC':
                        dsp_attrs[f'RSTGENMUX_ASIGN{1 - mode_01}2'] = 'SYNC'
                        dsp_attrs[f'RSTGENMUX_BSIGN{1 - mode_01}2'] = 'SYNC'
                        dsp_attrs[f'RSTGENLMUX_REGP{1 - mode_01}'] = 'SYNC'
                        dsp_attrs[f'RSTGENHMUX_REGP{1 - mode_01}'] = 'SYNC'
        if parm == 'OUT_REG':
            if val == '0':
                for i in range(2):
                    dsp_attrs[f'OREG{i}_NSL_{2 * i}'] = "ENABLE"
                    dsp_attrs[f'OREG{i}_BYPL_{2 * i}'] = "ENABLE"
                    dsp_attrs[f'OREG{i}_NSH_{2 * i + 1}'] = "ENABLE"
                    dsp_attrs[f'OREG{i}_BYPH_{2 * i + 1}'] = "ENABLE"
            else:
                for i in range(2):
                    for h in "LH":
                        dsp_attrs[f'CE{h}MUX_OREG{i}']  = ce_val
                        dsp_attrs[f'CLK{h}MUX_OREG{i}'] = clk_val
                        dsp_attrs[f'RST{h}MUX_OREG{i}'] = reset_val
                if 'MULT_RESET_MODE' in params:
                    if params['MULT_RESET_MODE'] == 'SYNC':
                        for h in "LH":
                            dsp_attrs[f'RSTGEN{h}MUX_OREG0'] = 'SYNC'
                            dsp_attrs[f'RSTGEN{h}MUX_OREG1'] = 'SYNC'
        if parm == 'ACCLOAD_REG0':
            if val == '0':
                dsp_attrs['CINNS_2'] = "ENABLE"
                dsp_attrs['CINBY_2'] = "ENABLE"
            else:
                dsp_attrs['CEMUX_ALUSEL1']  = ce_val
                dsp_attrs['CLKMUX_ALUSEL1'] = clk_val
                dsp_attrs['RSTMUX_ALUSEL1'] = reset_val
                if 'MULT_RESET_MODE' in params:
                    if params['MULT_RESET_MODE'] == 'SYNC':
                        dsp_attrs['RSTGENMUX_ALUSEL1'] = 'SYNC'
        if parm == 'ACCLOAD_REG1':
            if val == '0':
                dsp_attrs['CPRNS_2'] = "ENABLE"
                dsp_attrs['CPRBY_2'] = "ENABLE"
            else:
                dsp_attrs['CEMUX_ALUSEL2']  = ce_val
                dsp_attrs['CLKMUX_ALUSEL2'] = clk_val
                dsp_attrs['RSTMUX_ALUSEL2'] = reset_val
                if 'MULT_RESET_MODE' in params:
                    if params['MULT_RESET_MODE'] == 'SYNC':
                        dsp_attrs['RSTGENMUX_ALUSEL2'] = 'SYNC'

# MULTADDALU18X18
def set_multaddalu18x18_attrs(db, typ, params, num, attrs, dsp_attrs, mac):
    ce_val = 'UNKNOWN'
    if int(attrs['CE'], 2):
        ce_val = f"CEIN{int(attrs['CE'], 2)}"
    clk_val = 'UNKNOWN'
    if int(attrs['CLK'], 2):
        clk_val = f"CLKIN{int(attrs['CLK'], 2)}"
    reset_val = 'UNKNOWN'
    if int(attrs['RESET'], 2):
        reset_val = f"RSTIN{int(attrs['RESET'], 2)}"

    mode = int(params['MULTADDALU18X18_MODE'], 2)
    accload = attrs['NET_ACCLOAD']

    if mode == 0:
        dsp_attrs["RCISEL_3"] = "1"
        dsp_attrs["RCISEL_1"] = "1"

    dsp_attrs['OR2CIB_EN0L_0'] = "ENABLE"
    dsp_attrs['OR2CIB_EN0H_1'] = "ENABLE"
    dsp_attrs['OR2CIB_EN1L_2'] = "ENABLE"
    dsp_attrs['OR2CIB_EN1H_3'] = "ENABLE"

    if 'B_ADD_SUB' in params:
        if int(params['B_ADD_SUB'], 2) == 1:
            dsp_attrs['OPCD_7'] = "1"

    if "USE_CASCADE_IN" in attrs:
        dsp_attrs['CSGIN_EXT'] = "ENABLE"
        dsp_attrs['CSIGN_PRE'] = "ENABLE"
    if "USE_CASCADE_OUT" in attrs:
        dsp_attrs['OR2CASCADE_EN'] = "ENABLE"

    dsp_attrs['ALU_EN'] = "ENABLE"
    dsp_attrs['OPCD_0'] = "1"
    dsp_attrs['OPCD_2'] = "1"
    dsp_attrs['OPCD_9'] = "1"
    for i in {5, 6}:
        dsp_attrs[f'CINBY_{i}'] = "ENABLE"
        dsp_attrs[f'CINNS_{i}'] = "ENABLE"
        dsp_attrs[f'CPRBY_{i}'] = "ENABLE"
        dsp_attrs[f'CPRNS_{i}'] = "ENABLE"

    if mode == 0:
        dsp_attrs['OPCD_4'] = "1"
        dsp_attrs['OPCD_5'] = "1"
        if 'C_ADD_SUB' in params:
            if int(params['C_ADD_SUB'], 2) == 1:
                dsp_attrs['OPCD_8'] = "1"
    elif mode == 2:
        dsp_attrs['OPCD_5'] = "1"
    else:
        if accload == "VCC":
            dsp_attrs['OPCD_4'] = "1"
            dsp_attrs['OPCD_6'] = "1"
            dsp_attrs['OR2CASCADE_EN'] = "ENABLE"
        elif accload != "GND":
            dsp_attrs['OPCDDYN_4'] = "ENABLE"
            dsp_attrs['OPCDDYN_6'] = "ENABLE"
            dsp_attrs['OR2CASCADE_EN'] = "ENABLE"

    if attrs['NET_ASEL0'] == 'VCC':
        dsp_attrs['AIRMUX1_0'] = "ENABLE"
    elif attrs['NET_ASEL0'] and attrs['NET_ASEL0'] != 'GND':
        dsp_attrs['AIRMUX1_SEL_0'] = "ENABLE"

    if attrs['NET_ASEL1'] == 'VCC':
        dsp_attrs['AIRMUX1_1'] = "ENABLE"
    elif attrs['NET_ASEL1'] and attrs['NET_ASEL1'] != 'GND':
        dsp_attrs['AIRMUX1_SEL_1'] = "ENABLE"

    if attrs['NET_BSEL0'] == 'VCC':
        dsp_attrs['BIRMUX1_0'] = "ENABLE"
    elif attrs['NET_BSEL0'] and attrs['NET_BSEL0'] != 'GND':
        dsp_attrs['BIRMUX0_0'] = "ENABLE"
        dsp_attrs['BIRMUX0_1'] = "ENABLE"
        dsp_attrs['BIRMUX1_0'] = "ENABLE"
        dsp_attrs['BIRMUX1_1'] = "ENABLE"

    if attrs['NET_BSEL1'] == 'VCC':
        dsp_attrs['BIRMUX1_2'] = "ENABLE"
    elif attrs['NET_BSEL1'] and attrs['NET_BSEL1'] != 'GND':
        dsp_attrs['BIRMUX1_2'] = "ENABLE"
        dsp_attrs['BIRMUX1_3'] = "ENABLE"

    dsp_attrs['MATCH_SHFEN'] = "ENABLE"
    dsp_attrs['IRASHFEN_0'] = "1"
    dsp_attrs['IRASHFEN_1'] = "1"
    dsp_attrs['IRBSHFEN_0'] = "1"
    dsp_attrs['IRBSHFEN_1'] = "1"

    for parm, val in params.items():
        if parm in {'A0REG', 'A1REG'}:
            k = int(parm[1], 2)
            if val == '0':
                for i, h in _01LH:
                    dsp_attrs[f'IRBY_IREG{k}A{h}_{4 * k + i}']  = "ENABLE"
                    dsp_attrs[f'IRNS_IREG{k}A{h}_{4 * k + i}']  = "ENABLE"
            else:
                for h in "LH":
                    dsp_attrs[f'CE{h}MUX_REGMA{k}']  = ce_val
                    dsp_attrs[f'CLK{h}MUX_REGMA{k}'] = clk_val
                    dsp_attrs[f'RST{h}MUX_REGMA{k}'] = reset_val
                if 'MULT_RESET_MODE' in params:
                    if params['MULT_RESET_MODE'] == 'SYNC':
                        for h in "LH":
                            dsp_attrs[f'RSTGEN{h}MUX_REGMA{k}'] = 'SYNC'
        if parm in {'B0REG', 'B1REG'}:
            k = int(parm[1], 2)
            if val == '0':
                for i, h in _01LH:
                    dsp_attrs[f'IRBY_IREG{k}B{h}_{4 * k + 2 + i}']  = "ENABLE"
                    dsp_attrs[f'IRNS_IREG{k}B{h}_{4 * k + 2 + i}']  = "ENABLE"
            else:
                for h in "LH":
                    dsp_attrs[f'CE{h}MUX_REGMB{k}']  = ce_val
                    dsp_attrs[f'CLK{h}MUX_REGMB{k}'] = clk_val
                    dsp_attrs[f'RST{h}MUX_REGMB{k}'] = reset_val
                if 'MULT_RESET_MODE' in params:
                    if params['MULT_RESET_MODE'] == 'SYNC':
                        for h in "LH":
                            dsp_attrs[f'RSTGEN{h}MUX_REGMB{k}'] = 'SYNC'
        if parm == 'CREG' and mode == 0:
            if val == '0':
                for i, h in _01LH:
                    dsp_attrs[f'CIR_BYP{h}_{i}'] = "1"
            else:
                for h in "LH":
                    dsp_attrs[f'CE{h}MUX_CREG']  = ce_val
                    dsp_attrs[f'CLK{h}MUX_CREG'] = clk_val
                    dsp_attrs[f'RST{h}MUX_CREG'] = reset_val
                if 'MULT_RESET_MODE' in params:
                    if params['MULT_RESET_MODE'] == 'SYNC':
                        for h in "LH":
                            dsp_attrs[f'RSTGEN{h}MUX_REGC0'] = 'SYNC'
        if parm in {'ASIGN0_REG', 'ASIGN1_REG'}:
            k = int(parm[5], 2)
            if val == '0':
                dsp_attrs[f'CINNS_{3 * k}'] = "ENABLE"
                dsp_attrs[f'CINBY_{3 * k}'] = "ENABLE"
            else:
                dsp_attrs[f'CEMUX_ASIGN{k}1']  = ce_val
                dsp_attrs[f'CLKMUX_ASIGN{k}1'] = clk_val
                dsp_attrs[f'RSTMUX_ASIGN{k}1'] = reset_val
                if 'MULT_RESET_MODE' in params:
                    if params['MULT_RESET_MODE'] == 'SYNC':
                        dsp_attrs[f'RSTGENMUX_ASIGN{k}1'] = 'SYNC'
        if parm in {'BSIGN0_REG', 'BSIGN1_REG'}:
            k = int(parm[5], 2)
            if val == '0':
                dsp_attrs[f'CINNS_{1 + 3 * k}'] = "ENABLE"
                dsp_attrs[f'CINBY_{1 + 3 * k}'] = "ENABLE"
            else:
                dsp_attrs[f'CEMUX_BSIGN{k}1']  = ce_val
                dsp_attrs[f'CLKMUX_BSIGN{k}1'] = clk_val
                dsp_attrs[f'RSTMUX_BSIGN{k}1'] = reset_val
                if 'MULT_RESET_MODE' in params:
                    if params['MULT_RESET_MODE'] == 'SYNC':
                        dsp_attrs[f'RSTGENMUX_BSIGN{k}1'] = 'SYNC'
        if parm in {'PIPE0_REG', 'PIPE1_REG'}:
            k = int(parm[4], 2)
            if val == '0':
                dsp_attrs[f'CPRNS_{3 * k}'] = "ENABLE"
                dsp_attrs[f'CPRBY_{3 * k}'] = "ENABLE"
                dsp_attrs[f'CPRNS_{1 + 3 * k}'] = "ENABLE"
                dsp_attrs[f'CPRBY_{1 + 3 * k}'] = "ENABLE"
                for i, h in _01LH:
                    dsp_attrs[f'PPREG{k}_NS{h}_{2 * k + i}']  = "ENABLE"
                    dsp_attrs[f'PPREG{k}_BYP{h}_{2 * k + i}']  = "ENABLE"
            else:
                for i in "AB":
                    dsp_attrs[f'CEMUX_{i}SIGN{k}2']  = ce_val
                    dsp_attrs[f'CLKMUX_{i}SIGN{k}2'] = clk_val
                    dsp_attrs[f'RSTMUX_{i}SIGN{k}2'] = reset_val
                for i in "LH":
                    dsp_attrs[f'CE{i}MUX_REGP{k}']  = ce_val
                    dsp_attrs[f'CLK{i}MUX_REGP{k}'] = clk_val
                    dsp_attrs[f'RST{i}MUX_REGP{k}'] = reset_val
                if 'MULT_RESET_MODE' in params:
                    if params['MULT_RESET_MODE'] == 'SYNC':
                        dsp_attrs[f'RSTGENMUX_ASIGN{k}2'] = 'SYNC'
                        dsp_attrs[f'RSTGENMUX_BSIGN{k}2'] = 'SYNC'
                        dsp_attrs[f'RSTGENLMUX_REGP{k}'] = 'SYNC'
                        dsp_attrs[f'RSTGENHMUX_REGP{k}'] = 'SYNC'
        if parm == 'SOA_REG':
            if val == '0':
                dsp_attrs['IRBY_IRMATCHH_9'] = "ENABLE"
                dsp_attrs['IRNS_IRMATCHH_9'] = "ENABLE"
                dsp_attrs['IRBY_IRMATCHL_8'] = "ENABLE"
                dsp_attrs['IRNS_IRMATCHL_8'] = "ENABLE"
            else:
                dsp_attrs[f'CEHMUX_REGSD']  = ce_val
                dsp_attrs[f'CLKHMUX_REGSD'] = clk_val
                dsp_attrs[f'RSTHMUX_REGSD'] = reset_val
                dsp_attrs[f'CELMUX_REGSD']  = ce_val
                dsp_attrs[f'CLKLMUX_REGSD'] = clk_val
                dsp_attrs[f'RSTLMUX_REGSD'] = reset_val
                if 'MULT_RESET_MODE' in params:
                    if params['MULT_RESET_MODE'] == 'SYNC':
                        dsp_attrs[f'RSTGENHMUX_REGSD'] = 'SYNC'
                        dsp_attrs[f'RSTGENLMUX_REGSD'] = 'SYNC'
        if parm == 'OUT_REG':
            if val == '0':
                for k in range(2):
                    dsp_attrs[f'OREG{k}_NSL_{2 * k}'] = "ENABLE"
                    dsp_attrs[f'OREG{k}_BYPL_{2 * k}'] = "ENABLE"
                    dsp_attrs[f'OREG{k}_NSH_{2 * k + 1}'] = "ENABLE"
                    dsp_attrs[f'OREG{k}_BYPH_{2 * k + 1}'] = "ENABLE"
            else:
                for k in range(2):
                    for h in "LH":
                        dsp_attrs[f'CE{h}MUX_OREG{k}']  = ce_val
                        dsp_attrs[f'CLK{h}MUX_OREG{k}'] = clk_val
                        dsp_attrs[f'RST{h}MUX_OREG{k}'] = reset_val
                if 'MULT_RESET_MODE' in params:
                    if params['MULT_RESET_MODE'] == 'SYNC':
                        for h in "LH":
                            dsp_attrs[f'RSTGEN{h}MUX_OREG0'] = 'SYNC'
                            dsp_attrs[f'RSTGEN{h}MUX_OREG1'] = 'SYNC'
        if parm == 'ACCLOAD_REG0':
            if val == '0':
                dsp_attrs['CINNS_2'] = "ENABLE"
                dsp_attrs['CINBY_2'] = "ENABLE"
            else:
                dsp_attrs['CEMUX_ALUSEL1']  = ce_val
                dsp_attrs['CLKMUX_ALUSEL1'] = clk_val
                dsp_attrs['RSTMUX_ALUSEL1'] = reset_val
                if 'MULT_RESET_MODE' in params:
                    if params['MULT_RESET_MODE'] == 'SYNC':
                        dsp_attrs['RSTGENMUX_ALUSEL1'] = 'SYNC'
        if parm == 'ACCLOAD_REG1':
            if val == '0':
                dsp_attrs['CPRNS_2'] = "ENABLE"
                dsp_attrs['CPRBY_2'] = "ENABLE"
            else:
                dsp_attrs['CEMUX_ALUSEL2']  = ce_val
                dsp_attrs['CLKMUX_ALUSEL2'] = clk_val
                dsp_attrs['RSTMUX_ALUSEL2'] = reset_val
                if 'MULT_RESET_MODE' in params:
                    if params['MULT_RESET_MODE'] == 'SYNC':
                        dsp_attrs['RSTGENMUX_ALUSEL2'] = 'SYNC'


# MULTALU36X18
def set_multalu36x18_attrs(db, typ, params, num, attrs, dsp_attrs, mac):
    ce_val = 'UNKNOWN'
    if int(attrs['CE'], 2):
        ce_val = f"CEIN{int(attrs['CE'], 2)}"
    clk_val = 'UNKNOWN'
    if int(attrs['CLK'], 2):
        clk_val = f"CLKIN{int(attrs['CLK'], 2)}"
    reset_val = 'UNKNOWN'
    if int(attrs['RESET'], 2):
        reset_val = f"RSTIN{int(attrs['RESET'], 2)}"

    # the mode is not as important as in the case of MULTALU18X18 since the
    # registers do not change places yet and both multipliers are always used,
    # but let’s remember it just in case
    mode = int(params['MULTALU36X18_MODE'], 2)
    accload = attrs['NET_ACCLOAD']

    dsp_attrs["RCISEL_1"] = "1"
    dsp_attrs["RCISEL_3"] = "1"

    dsp_attrs['OR2CIB_EN0L_0'] = "ENABLE"
    dsp_attrs['OR2CIB_EN0H_1'] = "ENABLE"
    dsp_attrs['OR2CIB_EN1L_2'] = "ENABLE"
    dsp_attrs['OR2CIB_EN1H_3'] = "ENABLE"

    dsp_attrs['ALU_EN'] = "ENABLE"
    for i in {5, 6}:
        dsp_attrs[f'CINBY_{i}'] = "ENABLE"
        dsp_attrs[f'CINNS_{i}'] = "ENABLE"
        dsp_attrs[f'CPRBY_{i}'] = "ENABLE"
        dsp_attrs[f'CPRNS_{i}'] = "ENABLE"

    if "USE_CASCADE_IN" in attrs:
        dsp_attrs['CSGIN_EXT'] = "ENABLE"
        dsp_attrs['CSIGN_PRE'] = "ENABLE"
    if "USE_CASCADE_OUT" in attrs:
        dsp_attrs['OR2CASCADE_EN'] = "ENABLE"

    dsp_attrs['OPCD_0'] = "1"
    dsp_attrs['OPCD_9'] = "1"
    if mode == 0:
        dsp_attrs['OPCD_4'] = "1"
        dsp_attrs['OPCD_5'] = "1"
        if 'C_ADD_SUB' in params:
            if int(params['C_ADD_SUB'], 2) == 1:
                dsp_attrs['OPCD_8'] = "1"
    elif mode == 2:
        dsp_attrs['OPCD_5'] = "1"
    else:
        if accload == "VCC":
            dsp_attrs['OPCD_4'] = "1"
            dsp_attrs['OPCD_6'] = "1"
            dsp_attrs['OR2CASCADE_EN'] = "ENABLE"
        elif accload != "GND":
            dsp_attrs['OPCDDYN_4'] = "ENABLE"
            dsp_attrs['OPCDDYN_6'] = "ENABLE"
            dsp_attrs['OR2CASCADE_EN'] = "ENABLE"

    for parm, val in params.items():
        if parm == 'AREG':
            if val == '0':
                for k in range(2):
                    for i, h in _01LH:
                        dsp_attrs[f'IRBY_IREG{k}A{h}_{4 * k + i}']  = "ENABLE"
                        dsp_attrs[f'IRNS_IREG{k}A{h}_{4 * k + i}']  = "ENABLE"
            else:
                for k in range(2):
                    for h in "LH":
                        dsp_attrs[f'CE{h}MUX_REGMA{k}']  = ce_val
                        dsp_attrs[f'CLK{h}MUX_REGMA{k}'] = clk_val
                        dsp_attrs[f'RST{h}MUX_REGMA{k}'] = reset_val
                if 'MULT_RESET_MODE' in params:
                    if params['MULT_RESET_MODE'] == 'SYNC':
                        for k in range(2):
                            for h in "LH":
                                dsp_attrs[f'RSTGEN{h}MUX_REGMA{k}'] = 'SYNC'
        if parm == 'BREG':
            if val == '0':
                for k in range(2):
                    for i, h in _01LH:
                        dsp_attrs[f'IRBY_IREG{k}B{h}_{4 * k + 2 + i}']  = "ENABLE"
                        dsp_attrs[f'IRNS_IREG{k}B{h}_{4 * k + 2 + i}']  = "ENABLE"
            else:
                for k in range(2):
                    for h in "LH":
                        dsp_attrs[f'CE{h}MUX_REGMB{k}']  = ce_val
                        dsp_attrs[f'CLK{h}MUX_REGMB{k}'] = clk_val
                        dsp_attrs[f'RST{h}MUX_REGMB{k}'] = reset_val
                if 'MULT_RESET_MODE' in params:
                    if params['MULT_RESET_MODE'] == 'SYNC':
                        for k in range(2):
                            for h in "LH":
                                dsp_attrs[f'RSTGEN{h}MUX_REGMB{k}'] = 'SYNC'
        if parm == 'CREG':
            if val == '0':
                for i, h in _01LH:
                    dsp_attrs[f'CIR_BYP{h}_{i}'] = "1"
            else:
                for h in "LH":
                    dsp_attrs[f'CE{h}MUX_CREG']  = ce_val
                    dsp_attrs[f'CLK{h}MUX_CREG'] = clk_val
                    dsp_attrs[f'RST{h}MUX_CREG'] = reset_val
                if 'MULT_RESET_MODE' in params:
                    if params['MULT_RESET_MODE'] == 'SYNC':
                        for h in "LH":
                            dsp_attrs[f'RSTGEN{h}MUX_REGC0'] = 'SYNC'
        if parm == 'ASIGN_REG':
            if val == '0':
                for k in range(2):
                    dsp_attrs[f'CINNS_{3 * k}'] = "ENABLE"
                    dsp_attrs[f'CINBY_{3 * k}'] = "ENABLE"
            else:
                for k in range(2):
                    dsp_attrs[f'CEMUX_ASIGN{k}1']  = ce_val
                    dsp_attrs[f'CLKMUX_ASIGN{k}1'] = clk_val
                    dsp_attrs[f'RSTMUX_ASIGN{k}1'] = reset_val
                if 'MULT_RESET_MODE' in params:
                    if params['MULT_RESET_MODE'] == 'SYNC':
                        for k in range(2):
                            dsp_attrs[f'RSTGENMUX_ASIGN{k}1'] = 'SYNC'
        if parm == 'BSIGN_REG':
            if val == '0':
                for k in range(2):
                    dsp_attrs[f'CINNS_{1 + 3 * k}'] = "ENABLE"
                    dsp_attrs[f'CINBY_{1 + 3 * k}'] = "ENABLE"
            else:
                for k in range(2):
                    dsp_attrs[f'CEMUX_BSIGN{k}1']  = ce_val
                    dsp_attrs[f'CLKMUX_BSIGN{k}1'] = clk_val
                    dsp_attrs[f'RSTMUX_BSIGN{k}1'] = reset_val
                if 'MULT_RESET_MODE' in params:
                    if params['MULT_RESET_MODE'] == 'SYNC':
                        for k in range(2):
                            dsp_attrs[f'RSTGENMUX_BSIGN{k}1'] = 'SYNC'
        if parm == 'PIPE_REG':
            if val == '0':
                for k in range(2):
                    dsp_attrs[f'CPRNS_{3 * k}'] = "ENABLE"
                    dsp_attrs[f'CPRBY_{3 * k}'] = "ENABLE"
                    dsp_attrs[f'CPRNS_{1 + 3 * k}'] = "ENABLE"
                    dsp_attrs[f'CPRBY_{1 + 3 * k}'] = "ENABLE"
                    for i, h in _01LH:
                        dsp_attrs[f'PPREG{k}_NS{h}_{2 * k + i}']  = "ENABLE"
                        dsp_attrs[f'PPREG{k}_BYP{h}_{2 * k + i}']  = "ENABLE"
            else:
                for k in range(2):
                    for i in "AB":
                        dsp_attrs[f'CEMUX_{i}SIGN{k}2']  = ce_val
                        dsp_attrs[f'CLKMUX_{i}SIGN{k}2'] = clk_val
                        dsp_attrs[f'RSTMUX_{i}SIGN{k}2'] = reset_val
                    for i in "LH":
                        dsp_attrs[f'CE{i}MUX_REGP{k}']  = ce_val
                        dsp_attrs[f'CLK{i}MUX_REGP{k}'] = clk_val
                        dsp_attrs[f'RST{i}MUX_REGP{k}'] = reset_val
                if 'MULT_RESET_MODE' in params:
                    if params['MULT_RESET_MODE'] == 'SYNC':
                        for k in range(2):
                            dsp_attrs[f'RSTGENMUX_ASIGN{k}2'] = 'SYNC'
                            dsp_attrs[f'RSTGENMUX_BSIGN{k}2'] = 'SYNC'
                            dsp_attrs[f'RSTGENLMUX_REGP{k}'] = 'SYNC'
                            dsp_attrs[f'RSTGENHMUX_REGP{k}'] = 'SYNC'
        if parm == 'OUT_REG':
            # do out reg in unoptimal way because of MULT36X36
            if mac == 0 and typ == 'MULT36X36':
                dsp_attrs['OREG0_NSH_1'] = "ENABLE"
                dsp_attrs['OREG0_BYPH_1'] = "ENABLE"
                dsp_attrs['OREG1_NSL_2'] = "ENABLE"
                dsp_attrs['OREG1_BYPL_2'] = "ENABLE"
                dsp_attrs['OREG1_NSH_3'] = "ENABLE"
                dsp_attrs['OREG1_BYPH_3'] = "ENABLE"
                if val == '0':
                    dsp_attrs['OREG0_NSL_0'] = "ENABLE"
                    dsp_attrs['OREG0_BYPL_0'] = "ENABLE"
                else:
                    dsp_attrs['CELMUX_OREG0']  = ce_val
                    dsp_attrs['CLKLMUX_OREG0'] = clk_val
                    dsp_attrs['RSTLMUX_OREG0'] = reset_val
                    if 'MULT_RESET_MODE' in params:
                        if params['MULT_RESET_MODE'] == 'SYNC':
                            dsp_attrs['RSTGENLMUX_OREG0'] = 'SYNC'
            else:
                if val == '0':
                    for k in range(2):
                        dsp_attrs[f'OREG{k}_NSL_{2 * k}'] = "ENABLE"
                        dsp_attrs[f'OREG{k}_BYPL_{2 * k}'] = "ENABLE"
                        dsp_attrs[f'OREG{k}_NSH_{2 * k + 1}'] = "ENABLE"
                        dsp_attrs[f'OREG{k}_BYPH_{2 * k + 1}'] = "ENABLE"
                else:
                    for k in range(2):
                        for h in "LH":
                            dsp_attrs[f'CE{h}MUX_OREG{k}']  = ce_val
                            dsp_attrs[f'CLK{h}MUX_OREG{k}'] = clk_val
                            dsp_attrs[f'RST{h}MUX_OREG{k}'] = reset_val
                    if 'MULT_RESET_MODE' in params:
                        if params['MULT_RESET_MODE'] == 'SYNC':
                            for h in "LH":
                                dsp_attrs[f'RSTGEN{h}MUX_OREG0'] = 'SYNC'
                                dsp_attrs[f'RSTGEN{h}MUX_OREG1'] = 'SYNC'
        if parm == 'ACCLOAD_REG0':
            if val == '0':
                dsp_attrs['CINNS_2'] = "ENABLE"
                dsp_attrs['CINBY_2'] = "ENABLE"
            else:
                dsp_attrs['CEMUX_ALUSEL1']  = ce_val
                dsp_attrs['CLKMUX_ALUSEL1'] = clk_val
                dsp_attrs['RSTMUX_ALUSEL1'] = reset_val
                if 'MULT_RESET_MODE' in params:
                    if params['MULT_RESET_MODE'] == 'SYNC':
                        dsp_attrs['RSTGENMUX_ALUSEL1'] = 'SYNC'
        if parm == 'ACCLOAD_REG1':
            if val == '0':
                dsp_attrs['CPRNS_2'] = "ENABLE"
                dsp_attrs['CPRBY_2'] = "ENABLE"
            else:
                dsp_attrs['CEMUX_ALUSEL2']  = ce_val
                dsp_attrs['CLKMUX_ALUSEL2'] = clk_val
                dsp_attrs['RSTMUX_ALUSEL2'] = reset_val
                if 'MULT_RESET_MODE' in params:
                    if params['MULT_RESET_MODE'] == 'SYNC':
                        dsp_attrs['RSTGENMUX_ALUSEL2'] = 'SYNC'
# ALU54D
def set_alu54d_attrs(db, typ, params, num, attrs, dsp_attrs, mac):
    dsp_attrs['ALU_EN'] = "ENABLE"
    for i in range(2, 7):
        dsp_attrs[f'CPRNS_{i}'] = "ENABLE"
        dsp_attrs[f'CPRBY_{i}'] = "ENABLE"
        if i > 4:
            dsp_attrs[f'CINNS_{i}'] = "ENABLE"
            dsp_attrs[f'CINBY_{i}'] = "ENABLE"

    dsp_attrs["OPCD_3"] = "1"
    dsp_attrs["OPCD_9"] = "1"
    if params['B_ADD_SUB'] == '1':
        dsp_attrs['OPCD_7'] = "1"

    # cascade link
    if "USE_CASCADE_IN" in attrs:
        dsp_attrs['CSGIN_EXT'] = "ENABLE"
        dsp_attrs['CSIGN_PRE'] = "ENABLE"
    if "USE_CASCADE_OUT" in attrs:
        dsp_attrs['OR2CASCADE_EN'] = "ENABLE"

    ce_val = 'UNKNOWN'
    if int(attrs['CE'], 2):
        ce_val = f"CEIN{int(attrs['CE'], 2)}"
    clk_val = 'UNKNOWN'
    if int(attrs['CLK'], 2):
        clk_val = f"CLKIN{int(attrs['CLK'], 2)}"
    reset_val = 'UNKNOWN'
    if int(attrs['RESET'], 2):
        reset_val = f"RSTIN{int(attrs['RESET'], 2)}"

    for parm, val in params.items():
        if parm == 'ALUD_MODE':
            ival = int(val, 2)
            if ival == 2:
                dsp_attrs['OPCD_1'] = "1"
                dsp_attrs['OPCD_5'] = "1"
            else:
                if ival == 0:
                    dsp_attrs['OPCD_6'] = "1"
                    if params['C_ADD_SUB'] == "1":
                        dsp_attrs['OPCD_8'] = "1"
                else:
                    dsp_attrs['OPCD_5'] = "1"
                if attrs['NET_ACCLOAD'] == "GND":
                    dsp_attrs['OPCD_0'] = "1"
                    dsp_attrs['OPCD_1'] = "1"
                elif attrs['NET_ACCLOAD'] == "VCC":
                    dsp_attrs['OR2CASCADE_EN'] = "ENABLE"
                else:
                    dsp_attrs['OR2CASCADE_EN'] = "ENABLE"
                    dsp_attrs['OPCDDYN_0'] = "ENABLE"
                    dsp_attrs['OPCDDYN_1'] = "ENABLE"
                    dsp_attrs['OPCDDYN_INV_0'] = "ENABLE"
                    dsp_attrs['OPCDDYN_INV_1'] = "ENABLE"

        if parm == 'OUT_REG':
            ii = 0
            if val == '0':
                for i, h in [(i, h) for i in range(2) for h in "LH"]:
                    dsp_attrs[f'OREG{i}_NS{h}_{ii}']  = "ENABLE"
                    dsp_attrs[f'OREG{i}_BYP{h}_{ii}']  = "ENABLE"
                    dsp_attrs[f'OR2CIB_EN{i}{h}_{ii}']  = "ENABLE"
                    ii += 1
            else:
                for i, h in [(i, h) for i in range(2) for h in "LH"]:
                    dsp_attrs[f'CE{h}MUX_OREG{i}']  = ce_val
                    dsp_attrs[f'CLK{h}MUX_OREG{i}'] = clk_val
                    dsp_attrs[f'RST{h}MUX_OREG{i}'] = reset_val
                    dsp_attrs[f'OR2CIB_EN{i}{h}_{ii}']  = "ENABLE"
                    ii += 1

                if 'ALU_RESET_MODE' in params:
                    if params['ALU_RESET_MODE'] == 'SYNC':
                        for i, h in [(i, h) for h in "HL" for i in range(2)]:
                            dsp_attrs[f'RSTGEN{h}MUX_OREG{i}'] = 'SYNC'
        if parm == 'AREG':
            if val == '0':
                ii = 0
                dsp_attrs['CIR_BYPL_0']  = "1"
                for i, h in [(i, h) for i in "AB" for h in "LH"]:
                    dsp_attrs[f'IRBY_IREG0{i}{h}_{ii}']  = "ENABLE"
                    dsp_attrs[f'IRNS_IREG0{i}{h}_{ii}']  = "ENABLE"
                    ii += 1
            else:
                dsp_attrs['CELMUX_CREG'] = ce_val
                dsp_attrs['CLKLMUX_CREG'] = clk_val
                dsp_attrs['RSTLMUX_CREG'] = reset_val
                for i, h in [(i, h) for i in "AB" for h in "LH"]:
                    dsp_attrs[f'CE{h}MUX_REGM{i}0']  = ce_val
                    dsp_attrs[f'CLK{h}MUX_REGM{i}0'] = clk_val
                    dsp_attrs[f'RST{h}MUX_REGM{i}0'] = reset_val

                if 'ALU_RESET_MODE' in params:
                    if params['ALU_RESET_MODE'] == 'SYNC':
                        dsp_attrs['RSTGENLMUX_REGC0'] = 'SYNC'
                        for i, h in [(i, h) for i in "AB" for h in "LH"]:
                            dsp_attrs[f'RSTGEN{h}MUX_REGM{i}0'] = 'SYNC'

        if parm == 'BREG':
            if val == '0':
                ii = 4
                dsp_attrs['CIR_BYPH_1']  = "1"
                for i, h in [(i, h) for i in "AB" for h in "LH"]:
                    dsp_attrs[f'IRBY_IREG1{i}{h}_{ii}']  = "ENABLE"
                    dsp_attrs[f'IRNS_IREG1{i}{h}_{ii}']  = "ENABLE"
                    ii += 1
            else:
                dsp_attrs['CEHMUX_CREG'] = ce_val
                dsp_attrs['CLKHMUX_CREG'] = clk_val
                dsp_attrs['RSTHMUX_CREG'] = reset_val
                for i, h in [(i, h) for i in "AB" for h in "LH"]:
                    dsp_attrs[f'CE{h}MUX_REGM{i}1']  = ce_val
                    dsp_attrs[f'CLK{h}MUX_REGM{i}1'] = clk_val
                    dsp_attrs[f'RST{h}MUX_REGM{i}1'] = reset_val

                if 'ALU_RESET_MODE' in params:
                    if params['ALU_RESET_MODE'] == 'SYNC':
                        dsp_attrs['RSTGENLMUX_REGC0'] = 'SYNC'
                        for i, h in [(i, h) for i in "AB" for h in "LH"]:
                            dsp_attrs[f'RSTGEN{h}MUX_REGM{i}0'] = 'SYNC'

        if parm == 'ASIGN_REG':
            if val == '0':
                dsp_attrs['CINBY_3']  = "ENABLE"
                dsp_attrs['CINNS_3']  = "ENABLE"
            else:
                dsp_attrs['CEMUX_ASIGN11'] = ce_val
                dsp_attrs['CLKMUX_ASIGN11'] = clk_val
                dsp_attrs['RSTMUX_ASIGN11'] = reset_val

                if 'ALU_RESET_MODE' in params:
                    if params['ALU_RESET_MODE'] == 'SYNC':
                        dsp_attrs['RSTGENMUX_ASIGN11'] = 'SYNC'

        if parm == 'BSIGN_REG':
            if val == '0':
                dsp_attrs['CINBY_4']  = "ENABLE"
                dsp_attrs['CINNS_4']  = "ENABLE"
            else:
                dsp_attrs['CEMUX_BSIGN11'] = ce_val
                dsp_attrs['CLKMUX_BSIGN11'] = clk_val
                dsp_attrs['RSTMUX_BSIGN11'] = reset_val

                if 'ALU_RESET_MODE' in params:
                    if params['ALU_RESET_MODE'] == 'SYNC':
                        dsp_attrs['RSTGENMUX_BSIGN11'] = 'SYNC'

        if parm == 'ACCLOAD_REG':
            if val == '0':
                dsp_attrs['CINBY_2']  = "ENABLE"
                dsp_attrs['CINNS_2']  = "ENABLE"
            else:
                dsp_attrs['CEMUX_ALUSEL1'] = ce_val
                dsp_attrs['CLKMUX_ALUSEL1'] = clk_val
                dsp_attrs['RSTMUX_ALUSEL1'] = reset_val

                if 'ALU_RESET_MODE' in params:
                    if params['ALU_RESET_MODE'] == 'SYNC':
                        dsp_attrs['RSTGENMUX_ALUSEL1'] = 'SYNC'

    dsp_attrs['RCISEL_1'] = "1"
    dsp_attrs['RCISEL_3'] = "1"

# DSP PADD9
def set_padd9_attrs(db, typ, params, num, attrs, dsp_attrs, mac, idx, even_odd, pair_idx):
    dsp_attrs[f'CINBY_{pair_idx + 7}'] = "ENABLE"
    dsp_attrs[f'CINNS_{pair_idx + 7}'] = "ENABLE"
    if pair_idx:
        dsp_attrs['CIR_BYPH_1'] = "1"
        dsp_attrs['RCISEL_3'] = "1"
    else:
        dsp_attrs['CIR_BYPL_0'] = "1"
        dsp_attrs['RCISEL_1'] = "1"

    if pair_idx == 0 and 'LAST_IN_CHAIN' in attrs:
        dsp_attrs['PRAD_FBB1'] = "ENABLE"

    dsp_attrs[f'PRAD_MUXA0EN_{pair_idx}']   = "ENABLE"
    # sel nets
    if attrs['NET_ASEL'] == 'VCC':
        dsp_attrs[f'PRAD_MUXA1_{pair_idx * 2}'] = "ENABLE"
    elif attrs['NET_ASEL'] and attrs['NET_ASEL'] != 'GND':
        dsp_attrs[f'PRAD_MUXA1_{pair_idx * 2}'] = "ENABLE"
        dsp_attrs[f'PRAD_MUXA1_{pair_idx * 2 + 1}'] = "ENABLE"

    # ctrl nets
    ce_val = 'UNKNOWN'
    if int(attrs['CE'], 2):
        ce_val = f"CEIN{int(attrs['CE'], 2)}"
    clk_val = 'UNKNOWN'
    if int(attrs['CLK'], 2):
        clk_val = f"CLKIN{int(attrs['CLK'], 2)}"
    reset_val = 'UNKNOWN'
    if int(attrs['RESET'], 2):
        reset_val = f"RSTIN{int(attrs['RESET'], 2)}"

    if pair_idx:
        dsp_attrs['MATCH'] = "ENABLE"
        dsp_attrs['MATCH_SHFEN'] = "ENABLE"

    dsp_attrs[f'OR2CIB_EN{pair_idx}L_{pair_idx * 2}'] = "ENABLE"

    for parm, val in params.items():
        if parm == 'AREG':
            if val == '0':
                if even_odd:
                    dsp_attrs[f'IRNS_PRAD{pair_idx}AH_{pair_idx * 4 + 1}'] = "ENABLE"
                    dsp_attrs[f'IRBY_PRAD{pair_idx}AH_{pair_idx * 4 + 1}'] = "ENABLE"
                else:
                    dsp_attrs[f'IRNS_PRAD{pair_idx}AL_{pair_idx * 4}'] = "ENABLE"
                    dsp_attrs[f'IRBY_PRAD{pair_idx}AL_{pair_idx * 4}'] = "ENABLE"
            else:
                if even_odd:
                    dsp_attrs[f'CEHMUX_REGA{pair_idx}']  = ce_val
                    dsp_attrs[f'CLKHMUX_REGA{pair_idx}'] = clk_val
                    dsp_attrs[f'RSTHMUX_REGA{pair_idx}'] = reset_val
                    if 'PADD_RESET_MODE' in params:
                        if params['PADD_RESET_MODE'] == 'SYNC':
                            dsp_attrs[f'RSTGENHMUX_REGA{pair_idx}'] = 'SYNC'
                else:
                    dsp_attrs[f'CELMUX_REGMA{pair_idx}']  = ce_val
                    dsp_attrs[f'CLKLMUX_REGMA{pair_idx}'] = clk_val
                    dsp_attrs[f'RSTLMUX_REGMA{pair_idx}'] = reset_val
                    if 'PADD_RESET_MODE' in params:
                        if params['PADD_RESET_MODE'] == 'SYNC':
                            dsp_attrs[f'RSTGENLMUX_REGA{pair_idx}'] = 'SYNC'
        if parm == 'BREG':
            if val == '0':
                if even_odd:
                    dsp_attrs[f'IRNS_PRAD{pair_idx}BH_{pair_idx * 4 + 3}'] = "ENABLE"
                    dsp_attrs[f'IRBY_PRAD{pair_idx}BH_{pair_idx * 4 + 3}'] = "ENABLE"
                else:
                    dsp_attrs[f'IRNS_PRAD{pair_idx}BL_{pair_idx * 4 + 2}'] = "ENABLE"
                    dsp_attrs[f'IRBY_PRAD{pair_idx}BL_{pair_idx * 4 + 2}'] = "ENABLE"
            else:
                if even_odd:
                    dsp_attrs[f'CEHMUX_REGB{pair_idx}']  = ce_val
                    dsp_attrs[f'CLKHMUX_REGB{pair_idx}'] = clk_val
                    dsp_attrs[f'RSTHMUX_REGB{pair_idx}'] = reset_val
                    if 'PADD_RESET_MODE' in params:
                        if params['PADD_RESET_MODE'] == 'SYNC':
                            dsp_attrs[f'RSTGENHMUX_REGB{pair_idx}'] = 'SYNC'
                else:
                    dsp_attrs[f'CELMUX_REGMA{pair_idx}']  = ce_val
                    dsp_attrs[f'CLKLMUX_REGMA{pair_idx}'] = clk_val
                    dsp_attrs[f'RSTLMUX_REGMA{pair_idx}'] = reset_val
                    if 'PADD_RESET_MODE' in params:
                        if params['PADD_RESET_MODE'] == 'SYNC':
                            dsp_attrs[f'RSTGENLMUX_REGB{pair_idx}'] = 'SYNC'
        if parm == 'SOREG':
            if pair_idx:
                if val == '0':
                    if even_odd:
                        dsp_attrs['IRNS_IRMATCHH_9'] = "ENABLE"
                        dsp_attrs['IRBY_IRMATCHH_9'] = "ENABLE"
                    else:
                        dsp_attrs['IRNS_IRMATCHL_8'] = "ENABLE"
                        dsp_attrs['IRBY_IRMATCHL_8'] = "ENABLE"
                else:
                    if even_odd:
                        dsp_attrs['CEHMUX_REGSD']  = ce_val
                        dsp_attrs['CLKHMUX_REGSD'] = clk_val
                        dsp_attrs['RSTHMUX_REGSD'] = reset_val
                        if 'PADD_RESET_MODE' in params:
                            if params['PADD_RESET_MODE'] == 'SYNC':
                                dsp_attrs['RSTGENHMUX_REGSD'] = 'SYNC'
                    else:
                        dsp_attrs['CELMUX_REGSD']  = ce_val
                        dsp_attrs['CLKLMUX_REGSD'] = clk_val
                        dsp_attrs['RSTLMUX_REGSD'] = reset_val
                        if 'PADD_RESET_MODE' in params:
                            if params['PADD_RESET_MODE'] == 'SYNC':
                                dsp_attrs['RSTGENLMUX_REGSD'] = 'SYNC'

        if parm == 'BSEL_MODE':
            if val == '0':
                dsp_attrs[f'PRAD_MUXB_{pair_idx * 2}'] = "ENABLE"
            else:
                dsp_attrs[f'PRAD_MUXB_{pair_idx * 2 + 1}'] = "ENABLE"

    # mult: * C=1
    dsp_attrs[f'AIRMUX0_{pair_idx}'] = "ENABLE"
    dsp_attrs[f'BIRMUX0_{pair_idx * 2}'] = "ENABLE"
    if even_odd:
        dsp_attrs[f'IRBY_IREG{pair_idx}AH_{pair_idx * 4 + 1}'] = "ENABLE"
        dsp_attrs[f'IRNS_IREG{pair_idx}AH_{pair_idx * 4 + 1}'] = "ENABLE"
        dsp_attrs[f'IRBY_IREG{pair_idx}BH_{pair_idx * 4 + 3}'] = "ENABLE"
        dsp_attrs[f'IRNS_IREG{pair_idx}BH_{pair_idx * 4 + 3}'] = "ENABLE"
        dsp_attrs[f'CINNS_{pair_idx * 3}'] = "ENABLE"
        dsp_attrs[f'CINBY_{pair_idx * 3}'] = "ENABLE"
        dsp_attrs[f'CPRNS_{pair_idx * 3}'] = "ENABLE"
        dsp_attrs[f'CPRBY_{pair_idx * 3}'] = "ENABLE"
        dsp_attrs[f'CINNS_{pair_idx * 3 + 1}'] = "ENABLE"
        dsp_attrs[f'CINBY_{pair_idx * 3 + 1}'] = "ENABLE"
        dsp_attrs[f'CPRNS_{pair_idx * 3 + 1}'] = "ENABLE"
        dsp_attrs[f'CPRBY_{pair_idx * 3 + 1}'] = "ENABLE"
        dsp_attrs[f'PPREG{pair_idx}_NSH_{pair_idx * 2 + 1}'] = "ENABLE"
        dsp_attrs[f'PPREG{pair_idx}_BYPH_{pair_idx * 2 + 1}'] = "ENABLE"
        dsp_attrs[f'OREG{pair_idx}_NSH_{pair_idx * 2 + 1}'] = "ENABLE"
        dsp_attrs[f'OREG{pair_idx}_BYPH_{pair_idx * 2 + 1}'] = "ENABLE"
        dsp_attrs[f'OR2CIB_EN{pair_idx}H_{pair_idx * 2 + 1}'] = "ENABLE"
    else:
        dsp_attrs[f'IRBY_IREG{pair_idx}AL_{pair_idx * 4}'] = "ENABLE"
        dsp_attrs[f'IRNS_IREG{pair_idx}AL_{pair_idx * 4}'] = "ENABLE"
        dsp_attrs[f'IRBY_IREG{pair_idx}BL_{pair_idx * 4 + 2}'] = "ENABLE"
        dsp_attrs[f'IRNS_IREG{pair_idx}BL_{pair_idx * 4 + 2}'] = "ENABLE"
        dsp_attrs[f'CINNS_{pair_idx * 3}'] = "ENABLE"
        dsp_attrs[f'CINBY_{pair_idx * 3}'] = "ENABLE"
        dsp_attrs[f'CPRNS_{pair_idx * 3}'] = "ENABLE"
        dsp_attrs[f'CPRBY_{pair_idx * 3}'] = "ENABLE"
        dsp_attrs[f'CINNS_{pair_idx * 3 + 1}'] = "ENABLE"
        dsp_attrs[f'CINBY_{pair_idx * 3 + 1}'] = "ENABLE"
        dsp_attrs[f'CPRNS_{pair_idx * 3 + 1}'] = "ENABLE"
        dsp_attrs[f'CPRBY_{pair_idx * 3 + 1}'] = "ENABLE"
        dsp_attrs[f'PPREG{pair_idx}_NSL_{pair_idx * 2}'] = "ENABLE"
        dsp_attrs[f'PPREG{pair_idx}_BYPL_{pair_idx * 2}'] = "ENABLE"
        dsp_attrs[f'OREG{pair_idx}_NSL_{pair_idx * 2}'] = "ENABLE"
        dsp_attrs[f'OREG{pair_idx}_BYPL_{pair_idx * 2}'] = "ENABLE"
        dsp_attrs[f'OR2CIB_EN{pair_idx}L_{pair_idx * 2}'] = "ENABLE"

# DSP mult9x9
def set_mult9x9_attrs(db, typ, params, num, attrs, dsp_attrs, mac, idx, even_odd, pair_idx):
    ce_val = 'UNKNOWN'
    if int(attrs['CE'], 2):
        ce_val = f"CEIN{int(attrs['CE'], 2)}"
    clk_val = 'UNKNOWN'
    if int(attrs['CLK'], 2):
        clk_val = f"CLKIN{int(attrs['CLK'], 2)}"
    reset_val = 'UNKNOWN'
    if int(attrs['RESET'], 2):
        reset_val = f"RSTIN{int(attrs['RESET'], 2)}"

    dsp_attrs[f'IRASHFEN_{pair_idx}'] = "1"
    dsp_attrs[f'IRBSHFEN_{pair_idx}'] = "1"
    if pair_idx:
        dsp_attrs['MATCH_SHFEN'] = "ENABLE"
    if even_odd:
        dsp_attrs[f'OR2CIB_EN{pair_idx}H_{idx}'] = "ENABLE"
    else:
        dsp_attrs[f'OR2CIB_EN{pair_idx}L_{idx}'] = "ENABLE"
    # sel nets
    if attrs['NET_ASEL'] == 'VCC':
        dsp_attrs[f'AIRMUX1_{pair_idx}'] = "ENABLE"
    elif attrs['NET_ASEL'] and attrs['NET_ASEL'] != 'GND':
        dsp_attrs[f'AIRMUX1_SEL_{pair_idx}'] = "ENABLE"
    if attrs['NET_BSEL'] == 'VCC':
        dsp_attrs[f'BIRMUX1_{pair_idx * 2}'] = "ENABLE"
    elif attrs['NET_BSEL'] and attrs['NET_BSEL'] != 'GND':
        dsp_attrs[f'BIRMUX0_{pair_idx * 2}'] = "ENABLE"
        dsp_attrs[f'BIRMUX0_{pair_idx * 2 + 1}'] = "ENABLE"
        dsp_attrs[f'BIRMUX1_{pair_idx * 2}'] = "ENABLE"
        dsp_attrs[f'BIRMUX1_{pair_idx * 2 + 1}'] = "ENABLE"

    for parm, val in params.items():
        if parm == 'AREG':
            if val == '0':
                if even_odd:
                    dsp_attrs[f'IRBY_IREG{pair_idx}AH_{pair_idx * 4 + 1}'] = "ENABLE"
                    dsp_attrs[f'IRNS_IREG{pair_idx}AH_{pair_idx * 4 + 1}'] = "ENABLE"
                else:
                    dsp_attrs[f'IRBY_IREG{pair_idx}AL_{pair_idx * 4}'] = "ENABLE"
                    dsp_attrs[f'IRNS_IREG{pair_idx}AL_{pair_idx * 4}'] = "ENABLE"
            else:
                if even_odd:
                    dsp_attrs[f'CEHMUX_REGMA{pair_idx}']  = ce_val
                    dsp_attrs[f'CLKHMUX_REGMA{pair_idx}'] = clk_val
                    dsp_attrs[f'RSTHMUX_REGMA{pair_idx}'] = reset_val
                    if 'MULT_RESET_MODE' in params:
                        if params['MULT_RESET_MODE'] == 'SYNC':
                            dsp_attrs[f'RSTGENHMUX_REGMA{pair_idx}'] = 'SYNC'
                else:
                    dsp_attrs[f'CELMUX_REGMA{pair_idx}']  = ce_val
                    dsp_attrs[f'CLKLMUX_REGMA{pair_idx}'] = clk_val
                    dsp_attrs[f'RSTLMUX_REGMA{pair_idx}'] = reset_val
                    if 'MULT_RESET_MODE' in params:
                        if params['MULT_RESET_MODE'] == 'SYNC':
                            dsp_attrs[f'RSTGENLMUX_REGMA{pair_idx}'] = 'SYNC'
        if parm == 'BREG':
            if val == '0':
                if even_odd:
                    dsp_attrs[f'IRBY_IREG{pair_idx}BH_{pair_idx * 4 + 3}'] = "ENABLE"
                    dsp_attrs[f'IRNS_IREG{pair_idx}BH_{pair_idx * 4 + 3}'] = "ENABLE"
                else:
                    dsp_attrs[f'IRBY_IREG{pair_idx}BL_{pair_idx * 4 + 2}'] = "ENABLE"
                    dsp_attrs[f'IRNS_IREG{pair_idx}BL_{pair_idx * 4 + 2}'] = "ENABLE"
            else:
                if even_odd:
                    dsp_attrs[f'CEHMUX_REGMB{pair_idx}']  = ce_val
                    dsp_attrs[f'CLKHMUX_REGMB{pair_idx}'] = clk_val
                    dsp_attrs[f'RSTHMUX_REGMB{pair_idx}'] = reset_val
                    if 'MULT_RESET_MODE' in params:
                        if params['MULT_RESET_MODE'] == 'SYNC':
                            dsp_attrs[f'RSTGENHMUX_REGMB{pair_idx}'] = 'SYNC'
                else:
                    dsp_attrs[f'CELMUX_REGMB{pair_idx}']  = ce_val
                    dsp_attrs[f'CLKLMUX_REGMB{pair_idx}'] = clk_val
                    dsp_attrs[f'RSTLMUX_REGMB{pair_idx}'] = reset_val
                    if 'MULT_RESET_MODE' in params:
                        if params['MULT_RESET_MODE'] == 'SYNC':
                            dsp_attrs[f'RSTGENLMUX_REGMB{pair_idx}'] = 'SYNC'
        if parm == 'ASIGN_REG':
            if val == '0':
                dsp_attrs[f'CINNS_{pair_idx * 3}'] = "ENABLE"
                dsp_attrs[f'CINBY_{pair_idx * 3}'] = "ENABLE"
            else:
                dsp_attrs[f'CEMUX_ASIGN{pair_idx}1']  = ce_val
                dsp_attrs[f'CLKMUX_ASIGN{pair_idx}1'] = clk_val
                dsp_attrs[f'RSTMUX_ASIGN{pair_idx}1'] = reset_val
                if 'MULT_RESET_MODE' in params:
                    if params['MULT_RESET_MODE'] == 'SYNC':
                        dsp_attrs[f'RSTGENMUX_ASIGN{pair_idx}1'] = 'SYNC'
        if parm == 'BSIGN_REG':
            if val == '0':
                dsp_attrs[f'CINNS_{pair_idx * 3 + 1}'] = "ENABLE"
                dsp_attrs[f'CINBY_{pair_idx * 3 + 1}'] = "ENABLE"
            else:
                dsp_attrs[f'CEMUX_BSIGN{pair_idx}1']  = ce_val
                dsp_attrs[f'CLKMUX_BSIGN{pair_idx}1'] = clk_val
                dsp_attrs[f'RSTMUX_BSIGN{pair_idx}1'] = reset_val
                if 'MULT_RESET_MODE' in params:
                    if params['MULT_RESET_MODE'] == 'SYNC':
                        dsp_attrs[f'RSTGENMUX_BSIGN{pair_idx}1'] = 'SYNC'
        if parm == 'PIPE_REG':
            if val == '0':
                dsp_attrs[f'CPRNS_{pair_idx * 3}'] = "ENABLE"
                dsp_attrs[f'CPRBY_{pair_idx * 3}'] = "ENABLE"
                dsp_attrs[f'CPRNS_{pair_idx * 3 + 1}'] = "ENABLE"
                dsp_attrs[f'CPRBY_{pair_idx * 3 + 1}'] = "ENABLE"
                if even_odd:
                    dsp_attrs[f'PPREG{pair_idx}_NSH_{idx}'] = "ENABLE"
                    dsp_attrs[f'PPREG{pair_idx}_BYPH_{idx}'] = "ENABLE"
                else:
                    dsp_attrs[f'PPREG{pair_idx}_NSL_{idx}'] = "ENABLE"
                    dsp_attrs[f'PPREG{pair_idx}_BYPL_{idx}'] = "ENABLE"
            else:
                dsp_attrs[f'CEMUX_ASIGN{pair_idx}2']  = ce_val
                dsp_attrs[f'CLKMUX_ASIGN{pair_idx}2'] = clk_val
                dsp_attrs[f'RSTMUX_ASIGN{pair_idx}2'] = reset_val
                dsp_attrs[f'CEMUX_BSIGN{pair_idx}2']  = ce_val
                dsp_attrs[f'CLKMUX_BSIGN{pair_idx}2'] = clk_val
                dsp_attrs[f'RSTMUX_BSIGN{pair_idx}2'] = reset_val
                if even_odd:
                    dsp_attrs[f'CEHMUX_REGP{pair_idx}']  = ce_val
                    dsp_attrs[f'CLKHMUX_REGP{pair_idx}'] = clk_val
                    dsp_attrs[f'RSTHMUX_REGP{pair_idx}'] = reset_val
                else:
                    dsp_attrs[f'CELMUX_REGP{pair_idx}']  = ce_val
                    dsp_attrs[f'CLKLMUX_REGP{pair_idx}'] = clk_val
                    dsp_attrs[f'RSTLMUX_REGP{pair_idx}'] = reset_val
                if 'MULT_RESET_MODE' in params:
                    if params['MULT_RESET_MODE'] == 'SYNC':
                        dsp_attrs[f'RSTGENMUX_ASIGN{pair_idx}2'] = 'SYNC'
                        dsp_attrs[f'RSTGENMUX_BSIGN{pair_idx}2'] = 'SYNC'
                        if even_odd:
                            dsp_attrs[f'RSTGENHMUX_REGP{pair_idx}'] = 'SYNC'
                        else:
                            dsp_attrs[f'RSTGENLMUX_REGP{pair_idx}'] = 'SYNC'
        if parm == 'OUT_REG':
            if val == '0':
                if even_odd:
                    dsp_attrs[f'OREG{pair_idx}_BYPH_{idx}'] = "ENABLE"
                    dsp_attrs[f'OREG{pair_idx}_NSH_{idx}'] = "ENABLE"
                else:
                    dsp_attrs[f'OREG{pair_idx}_BYPL_{idx}'] = "ENABLE"
                    dsp_attrs[f'OREG{pair_idx}_NSL_{idx}'] = "ENABLE"
            else:
                if even_odd:
                    dsp_attrs[f'CEHMUX_OREG{pair_idx}']  = ce_val
                    dsp_attrs[f'CLKHMUX_OREG{pair_idx}'] = clk_val
                    dsp_attrs[f'RSTHMUX_OREG{pair_idx}'] = reset_val
                else:
                    dsp_attrs[f'CELMUX_OREG{pair_idx}']  = ce_val
                    dsp_attrs[f'CLKLMUX_OREG{pair_idx}'] = clk_val
                    dsp_attrs[f'RSTLMUX_OREG{pair_idx}'] = reset_val
                if 'MULT_RESET_MODE' in params:
                    if params['MULT_RESET_MODE'] == 'SYNC':
                        if even_odd:
                            dsp_attrs[f'RSTGENHMUX_OREG{pair_idx}'] = 'SYNC'
                        else:
                            dsp_attrs[f'RSTGENLMUX_OREG{pair_idx}'] = 'SYNC'

        if parm == 'SOA_REG' and pair_idx:
            if val == '0':
                if pair_idx:
                    if even_odd:
                        dsp_attrs['IRBY_IRMATCHH_9'] = "ENABLE"
                        dsp_attrs['IRNS_IRMATCHH_9'] = "ENABLE"
                    else:
                        dsp_attrs['IRBY_IRMATCHL_8'] = "ENABLE"
                        dsp_attrs['IRNS_IRMATCHL_8'] = "ENABLE"
            else:
                if even_odd:
                    dsp_attrs[f'CEHMUX_REGSD']  = ce_val
                    dsp_attrs[f'CLKHMUX_REGSD'] = clk_val
                    dsp_attrs[f'RSTHMUX_REGSD'] = reset_val
                else:
                    dsp_attrs[f'CELMUX_REGSD']  = ce_val
                    dsp_attrs[f'CLKLMUX_REGSD'] = clk_val
                    dsp_attrs[f'RSTLMUX_REGSD'] = reset_val
                if 'MULT_RESET_MODE' in params:
                    if params['MULT_RESET_MODE'] == 'SYNC':
                        if even_odd:
                            dsp_attrs[f'RSTGENHMUX_REGSD'] = 'SYNC'
                        else:
                            dsp_attrs[f'RSTGENLMUX_REGSD'] = 'SYNC'

def set_dsp_attrs(db, typ, params, num, attrs):
    dsp_attrs = {}
    mac = int(num[0])
    idx = int(num[1])
    even_odd = idx & 1
    pair_idx = idx // 2
    #print(f"{typ}, mac:{mac}, idx:{idx}, even_odd:{even_odd}, pair_idx:{pair_idx}")

    if typ in {"PADD9", "MULT9X9"}:
        dsp_attrs['M9MODE_EN'] = "ENABLE"

    if typ == "PADD9":
        set_padd9_attrs(db, typ, params, num, attrs, dsp_attrs, mac, idx, even_odd, pair_idx)
    elif typ == "PADD18":
        idx *= 2
        even_odd = idx & 1
        pair_idx = idx // 2
        set_padd9_attrs(db, typ, params, num, attrs, dsp_attrs, mac, idx, even_odd, pair_idx)
        idx += 1
        even_odd = idx & 1
        pair_idx = idx // 2
        set_padd9_attrs(db, typ, params, num, attrs, dsp_attrs, mac, idx, even_odd, pair_idx)
    elif typ == "MULT9X9":
        set_mult9x9_attrs(db, typ, params, num, attrs, dsp_attrs, mac, idx, even_odd, pair_idx)
    elif typ == "MULT18X18":
        idx *= 2
        even_odd = idx & 1
        pair_idx = idx // 2
        set_mult9x9_attrs(db, typ, params, num, attrs, dsp_attrs, mac, idx, even_odd, pair_idx)
        idx += 1
        even_odd = idx & 1
        pair_idx = idx // 2
        set_mult9x9_attrs(db, typ, params, num, attrs, dsp_attrs, mac, idx, even_odd, pair_idx)
    elif typ == "ALU54D":
        set_alu54d_attrs(db, typ, params, num, attrs, dsp_attrs, mac)
    elif typ == "MULTALU18X18":
        set_multalu18x18_attrs(db, typ, params, num, attrs, dsp_attrs, mac)
    elif typ == "MULTALU36X18":
        set_multalu36x18_attrs(db, typ, params, num, attrs, dsp_attrs, mac)
    elif typ == "MULTADDALU18X18":
        set_multaddalu18x18_attrs(db, typ, params, num, attrs, dsp_attrs, mac)

    fin_attrs = set()
    for attr, val in dsp_attrs.items():
        if isinstance(val, str):
            val = attrids.dsp_attrvals[val]
        add_attr_val(db, 'DSP', fin_attrs, attrids.dsp_attrids[attr], val)
    return fin_attrs

# special case - returns attrs for two macros []
def set_dsp_mult36x36_attrs(db, typ, params, attrs):
    attrs['NET_ASEL'] = 'GND'
    attrs['NET_BSEL'] = 'GND'

    # macro 0
    dsp_attrs = {}
    params['MULTALU36X18_MODE'] = "1"  # ACC/0 + A*B
    attrs['NET_ACCLOAD'] = "GND"
    params['OUT_REG'] = params.get('OUT0_REG', "0")
    params['ACCLOAD_REG0'] = "0"
    params['ACCLOAD_REG1'] = "0"
    set_multalu36x18_attrs(db, typ, params, "00", attrs, dsp_attrs, 0)
    dsp_attrs['OR2CASCADE_EN'] = "ENABLE"
    dsp_attrs['IRNS_IRMATCHH_9'] = "ENABLE"
    dsp_attrs['IRNS_IRMATCHL_8'] = "ENABLE"
    dsp_attrs['IRBY_IRMATCHH_9'] = "ENABLE"
    dsp_attrs['IRBY_IRMATCHL_8'] = "ENABLE"
    dsp_attrs['MATCH_SHFEN'] = "ENABLE"
    dsp_attrs.pop('IRASHFEN_0', None)
    dsp_attrs.pop('RCISEL_1', None)
    dsp_attrs.pop('RCISEL_3', None)

    ret_attrs = []
    fin_attrs = set()
    for attr, val in dsp_attrs.items():
        if isinstance(val, str):
            val = attrids.dsp_attrvals[val]
        add_attr_val(db, 'DSP', fin_attrs, attrids.dsp_attrids[attr], val)
    ret_attrs.append(fin_attrs)

    # macro 1
    dsp_attrs = {}
    params['MULTALU36X18_MODE'] = "10" # A*B + CASI
    params['OUT_REG'] = params.get('OUT1_REG', "0")
    set_multalu36x18_attrs(db, typ, params, "00", attrs, dsp_attrs, 1)

    dsp_attrs['CSGIN_EXT'] = "ENABLE"
    dsp_attrs['CSIGN_PRE'] = "ENABLE"
    dsp_attrs['IRNS_IRMATCHH_9'] = "ENABLE"
    dsp_attrs['IRNS_IRMATCHL_8'] = "ENABLE"
    dsp_attrs['IRBY_IRMATCHH_9'] = "ENABLE"
    dsp_attrs['IRBY_IRMATCHL_8'] = "ENABLE"
    dsp_attrs['MATCH_SHFEN'] = "ENABLE"
    dsp_attrs.pop('IRASHFEN_0', None)
    dsp_attrs.pop('RCISEL_1', None)
    dsp_attrs.pop('RCISEL_3', None)
    dsp_attrs.pop('OPCD_5', None)
    dsp_attrs['OPCD_4'] = "1"

    fin_attrs = set()
    for attr, val in dsp_attrs.items():
        if isinstance(val, str):
            val = attrids.dsp_attrvals[val]
        add_attr_val(db, 'DSP', fin_attrs, attrids.dsp_attrids[attr], val)
    ret_attrs.append(fin_attrs)
    return ret_attrs

def set_osc_attrs(db, typ, params):
    osc_attrs = dict()
    for param, val in params.items():
        if param == 'FREQ_DIV':
            fdiv = int(val, 2)
            if fdiv % 2 == 1:
                raise Exception(f"Divisor of {typ} must be even")
            osc_attrs['MCLKCIB'] = fdiv
            osc_attrs['MCLKCIB_EN'] = "ENABLE"
            osc_attrs['NORMAL'] = "ENABLE"
            if typ not in {'OSC', 'OSCW'}:
                osc_attrs['USERPOWER_SAVE'] = 'ENABLE'
            continue
        if param == 'REGULATOR_EN':
            reg = int(val, 2)
            if reg == 1:
                osc_attrs['OSCREG'] = "ENABLE"
            continue

    fin_attrs = set()
    for attr, val in osc_attrs.items():
        if isinstance(val, str):
            val = attrids.osc_attrvals[val]
        add_attr_val(db, 'OSC', fin_attrs, attrids.osc_attrids[attr], val)
    return fin_attrs

_iologic_default_attrs = {
        'DUMMY': {},
        'IOLOGIC': {},
        'IOLOGIC_DUMMY': {},
        'ODDR': { 'TXCLK_POL': '0'},
        'ODDRC': { 'TXCLK_POL': '0'},
        'OSER4': { 'GSREN': 'false', 'LSREN': 'true', 'TXCLK_POL': '0', 'HWL': 'false'},
        'OSER8': { 'GSREN': 'false', 'LSREN': 'true', 'TXCLK_POL': '0', 'HWL': 'false'},
        'OSER10': { 'GSREN': 'false', 'LSREN': 'true'},
        'OSER16': { 'GSREN': 'false', 'LSREN': 'true', 'CLKOMUX': 'ENABLE'},
        'OVIDEO': { 'GSREN': 'false', 'LSREN': 'true'},
        'IDES4': { 'GSREN': 'false', 'LSREN': 'true'},
        'IDES8': { 'GSREN': 'false', 'LSREN': 'true'},
        'IDES10': { 'GSREN': 'false', 'LSREN': 'true'},
        'IVIDEO': { 'GSREN': 'false', 'LSREN': 'true'},
        'IDDR' :  {'CLKIMUX': 'ENABLE', 'LSRIMUX_0': '0', 'LSROMUX_0': '0'},
        'IDDRC' : {'CLKIMUX': 'ENABLE', 'LSRIMUX_0': '1', 'LSROMUX_0': '0'},
        'IDES16': { 'GSREN': 'false', 'LSREN': 'true', 'CLKIMUX': 'ENABLE'},
        }
def iologic_mod_attrs(attrs):
    if 'TXCLK_POL' in attrs:
        if int(attrs['TXCLK_POL']) == 0:
            attrs['TSHX'] = 'SIG'
        else:
            attrs['TSHX'] = 'INV'
        del attrs['TXCLK_POL']
    if 'HWL' in attrs:
        if attrs['HWL'] == 'true':
            attrs['UPDATE'] = 'SAME'
        del attrs['HWL']
    if 'GSREN' in attrs:
        if attrs['GSREN'] == 'true':
            attrs['GSR'] = 'ENGSR'
        del attrs['GSREN']
    # XXX ignore for now
    attrs.pop('LSREN', None)
    attrs.pop('Q0_INIT', None)
    attrs.pop('Q1_INIT', None)

def set_iologic_attrs(db, attrs, param):
    in_attrs = _iologic_default_attrs[param['IOLOGIC_TYPE']].copy()
    in_attrs.update(attrs)
    iologic_mod_attrs(in_attrs)
    fin_attrs = set()
    if 'OUTMODE' in attrs:
        if attrs['OUTMODE'] != 'ODDRX1':
            in_attrs['CLKODDRMUX_WRCLK'] = 'ECLK0'
        if attrs['OUTMODE'] != 'ODDRX1' or param['IOLOGIC_TYPE'] == 'ODDRC':
            in_attrs['LSROMUX_0'] = '1'
        else:
            in_attrs['LSROMUX_0'] = '0'
        in_attrs['CLKODDRMUX_ECLK'] = 'UNKNOWN'
        if param['IOLOGIC_FCLK'] in {'SPINE12', 'SPINE13'}:
            in_attrs['CLKODDRMUX_ECLK'] = 'ECLK1'
        elif param['IOLOGIC_FCLK'] in {'SPINE10', 'SPINE11'}:
            in_attrs['CLKODDRMUX_ECLK'] = 'ECLK0'
        if attrs['OUTMODE'] == 'ODDRX8' or attrs['OUTMODE'] == 'DDRENABLE16':
            in_attrs['LSROMUX_0'] = '0'
        if attrs['OUTMODE'] == 'DDRENABLE16':
            in_attrs['OUTMODE'] = 'DDRENABLE'
            in_attrs['ISI'] = 'ENABLE'
        if attrs['OUTMODE'] == 'DDRENABLE':
            in_attrs['ISI'] = 'ENABLE'
        in_attrs['LSRIMUX_0'] = '0'
        in_attrs['CLKOMUX'] = 'ENABLE'
        #in_attrs['LSRMUX_LSR'] = 'INV'
    if 'INMODE' in attrs:
        if param['IOLOGIC_TYPE'] not in {'IDDR', 'IDDRC'}:
            #in_attrs['CLKODDRMUX_WRCLK'] = 'ECLK0'
            in_attrs['CLKOMUX_1'] = '1'
            in_attrs['CLKODDRMUX_ECLK'] = 'UNKNOWN'
            if param['IOLOGIC_FCLK'] in {'SPINE12', 'SPINE13'}:
                in_attrs['CLKIDDRMUX_ECLK'] = 'ECLK1'
            elif param['IOLOGIC_FCLK'] in {'SPINE10', 'SPINE11'}:
                in_attrs['CLKIDDRMUX_ECLK'] = 'ECLK0'
            in_attrs['LSRIMUX_0'] = '1'
            if attrs['INMODE'] == 'IDDRX8' or attrs['INMODE'] == 'DDRENABLE16':
                in_attrs['LSROMUX_0'] = '0'
            if attrs['INMODE'] == 'DDRENABLE16':
                in_attrs['INMODE'] = 'DDRENABLE'
                in_attrs['ISI'] = 'ENABLE'
            if attrs['INMODE'] == 'DDRENABLE':
                in_attrs['ISI'] = 'ENABLE'
            in_attrs['LSROMUX_0'] = '0'
            in_attrs['CLKIMUX'] = 'ENABLE'

    for k, val in in_attrs.items():
        if k not in attrids.iologic_attrids:
            print(f'XXX IOLOGIC: add {k} key handle')
        else:
            add_attr_val(db, 'IOLOGIC', fin_attrs, attrids.iologic_attrids[k], attrids.iologic_attrvals[val])
    return fin_attrs

_iostd_alias = {
        frozenset({"BLVDS25E"}): "BLVDS_E",
        frozenset({"LVTTL33"}): "LVCMOS33",
        frozenset({"LVCMOS12D", "LVCMOS15D", "LVCMOS18D", "LVCMOS25D", "LVCMOS33D", }): "LVCMOS_D",
        frozenset({"HSTL15", "HSTL18_I", "HSTL18_II"}): "HSTL",
        frozenset({"SSTL15", "SSTL18_I", "SSTL18_II", "SSTL25_I", "SSTL25_II", "SSTL33_I", "SSTL33_II"}): "SSTL",
        frozenset({"MLVDS25E"}): "MLVDS_E",
        frozenset({"SSTL15D", "SSTL18D_I", "SSTL18D_II", "SSTL25D_I", "SSTL25D_II", "SSTL33D_I", "SSTL33D_II"}): "SSTL_D",
        frozenset({"HSTL15D", "HSTL18D_I", "HSTL18D_II"}): "HSTL_D",
        frozenset({"RSDS"}): "RSDS25",
        frozenset({"RSDS25E"}): "RSDS_E",
        }
def get_iostd_alias(iostd):
    for k, v in _iostd_alias.items():
        if iostd in k:
            iostd = v
            break
    return iostd

# For each bank, remember the Bels used, mark whether Outs were among them and the standard.
class BankDesc:
    def __init__(self, iostd, inputs_only, bels_tiles, true_lvds_drive):
        self.iostd = iostd
        self.inputs_only = inputs_only
        self.bels_tiles = bels_tiles
        self.true_lvds_drive = true_lvds_drive

_banks = {}

# IO encode in two passes: the first collect the IO attributes and place them
# according to the banks, the second after processing actually forms the fuses.
class IOBelDesc:
    def __init__(self, row, col, idx, attrs, flags, connections):
        self.pos = (row, col, idx)
        self.attrs = attrs  # standard attributes
        self.flags = flags  # aux special flags
        self.connections = connections
_io_bels = {}
_default_iostd = {
        'IBUF': 'LVCMOS18', 'OBUF': 'LVCMOS18', 'TBUF': 'LVCMOS18', 'IOBUF': 'LVCMOS18',
        'TLVDS_IBUF': 'LVDS25', 'TLVDS_OBUF': 'LVDS25', 'TLVDS_TBUF': 'LVDS25',
        'TLVDS_IOBUF': 'LVDS25',
        'ELVDS_IBUF': 'LVCMOS33D', 'ELVDS_OBUF': 'LVCMOS33D', 'ELVDS_TBUF': 'LVCMOS33D',
        'ELVDS_IOBUF': 'LVCMOS33D',
        }
_vcc_ios = {'LVCMOS12': '1.2', 'LVCMOS15': '1.5', 'LVCMOS18': '1.8', 'LVCMOS25': '2.5',
        'LVCMOS33': '3.3', 'LVDS25': '2.5', 'LVCMOS33D': '3.3', 'LVCMOS_D': '3.3'}
_init_io_attrs = {
        'IBUF': {'PADDI': 'PADDI', 'HYSTERESIS': 'NONE', 'PULLMODE': 'UP', 'SLEWRATE': 'SLOW',
                 'DRIVE': '0', 'CLAMP': 'OFF', 'OPENDRAIN': 'OFF', 'DIFFRESISTOR': 'OFF',
                 'VREF': 'OFF', 'LVDS_OUT': 'OFF'},
        'OBUF': {'ODMUX_1': '1', 'PULLMODE': 'UP', 'SLEWRATE': 'FAST',
                 'DRIVE': '8', 'HYSTERESIS': 'NONE', 'CLAMP': 'OFF', 'DIFFRESISTOR': 'OFF',
                 'SINGLERESISTOR': 'OFF', 'VCCIO': '1.8', 'LVDS_OUT': 'OFF', 'DDR_DYNTERM': 'NA', 'TO': 'INV', 'OPENDRAIN': 'OFF'},
        'TBUF': {'ODMUX_1': 'UNKNOWN', 'PULLMODE': 'UP', 'SLEWRATE': 'FAST',
                 'DRIVE': '8', 'HYSTERESIS': 'NONE', 'CLAMP': 'OFF', 'DIFFRESISTOR': 'OFF',
                 'SINGLERESISTOR': 'OFF', 'VCCIO': '1.8', 'LVDS_OUT': 'OFF', 'DDR_DYNTERM': 'NA',
                 'TO': 'INV', 'PERSISTENT': 'OFF', 'ODMUX': 'TRIMUX', 'OPENDRAIN': 'OFF'},
        'IOBUF': {'ODMUX_1': 'UNKNOWN', 'PULLMODE': 'UP', 'SLEWRATE': 'FAST',
                 'DRIVE': '8', 'HYSTERESIS': 'NONE', 'CLAMP': 'OFF', 'DIFFRESISTOR': 'OFF',
                 'SINGLERESISTOR': 'OFF', 'VCCIO': '1.8', 'LVDS_OUT': 'OFF', 'DDR_DYNTERM': 'NA',
                 'TO': 'INV', 'PERSISTENT': 'OFF', 'ODMUX': 'TRIMUX', 'PADDI': 'PADDI', 'OPENDRAIN': 'OFF'},
        }
_refine_attrs = {'SLEW_RATE': 'SLEWRATE', 'PULL_MODE': 'PULLMODE', 'OPEN_DRAIN': 'OPENDRAIN'}
def refine_io_attrs(attr):
    return _refine_attrs.get(attr, attr)

def place_lut(db, tiledata, tile, parms, num):
    lutmap = tiledata.bels[f'LUT{num}'].flags
    init = str(parms['INIT'])
    if len(init) > 16:
        init = init[-16:]
    else:
        init = init*(16//len(init))
    for bitnum, lutbit in enumerate(init[::-1]):
        if lutbit == '0':
            fuses = lutmap[bitnum]
            for brow, bcol in fuses:
                tile[brow][bcol] = 1

def place_alu(db, tiledata, tile, parms, num):
    lutmap = tiledata.bels[f'LUT{num}'].flags
    alu_bel = tiledata.bels[f"ALU{num}"]
    mode = str(parms['ALU_MODE'])
    for r_c in lutmap.values():
        for r, c in r_c:
            tile[r][c] = 0
    if mode in alu_bel.modes:
        bits = alu_bel.modes[mode]
    else:
        bits = alu_bel.modes[str(int(mode, 2))]
    for r, c in bits:
        tile[r][c] = 1

def place_dff(db, tiledata, tile, parms, num, mode):
        dff_attrs = set()
        add_attr_val(db, 'SLICE', dff_attrs, attrids.cls_attrids['REGMODE'], attrids.cls_attrvals['FF'])
        # REG0_REGSET and REG1_REGSET select set/reset or preset/clear options for each DFF individually
        if mode in {'DFFR', 'DFFC', 'DFFNR', 'DFFNC', 'DFF', 'DFFN'}:
            add_attr_val(db, 'SLICE', dff_attrs, attrids.cls_attrids[f'REG{int(num) % 2}_REGSET'], attrids.cls_attrvals['RESET'])
        else:
            add_attr_val(db, 'SLICE', dff_attrs, attrids.cls_attrids[f'REG{int(num) % 2}_REGSET'], attrids.cls_attrvals['SET'])
        # are set/reset/clear/preset port needed?
        if mode not in {'DFF', 'DFFN'}:
            add_attr_val(db, 'SLICE', dff_attrs, attrids.cls_attrids['LSRONMUX'], attrids.cls_attrvals['LSRMUX'])
        # invert clock?
        if mode in {'DFFN', 'DFFNR', 'DFFNC', 'DFFNP', 'DFFNS'}:
            add_attr_val(db, 'SLICE', dff_attrs, attrids.cls_attrids['CLKMUX_CLK'], attrids.cls_attrvals['INV'])
        else:
            add_attr_val(db, 'SLICE', dff_attrs, attrids.cls_attrids['CLKMUX_CLK'], attrids.cls_attrvals['SIG'])

        # async option?
        if mode in {'DFFNC', 'DFFNP', 'DFFC', 'DFFP'}:
            add_attr_val(db, 'SLICE', dff_attrs, attrids.cls_attrids['SRMODE'], attrids.cls_attrvals['ASYNC'])

        dffbits = get_shortval_fuses(db, tiledata.ttyp, dff_attrs, f'CLS{int(num) // 2}')
        #print(f'({row - 1}, {col - 1}) mode:{mode}, num{num}, attrs:{dff_attrs}, bits:{dffbits}')
        for brow, bcol in dffbits:
            tile[brow][bcol] = 1

def place_slice(db, tiledata, tile, parms, num):
    lutmap = tiledata.bels[f'LUT{num}'].flags

    if 'ALU_MODE' in parms:
        place_alu(db, tiledata, tile, parms, num)
    else:
        place_lut(db, tiledata, tile, parms, num)

    if int(num) < 6 and int(parms['FF_USED'], 2):
        mode = str(parms['FF_TYPE']).strip('E')
        place_dff(db, tiledata, tile, parms, num, mode)

_sides = "AB"
def place(db, tilemap, bels, cst, args):
    for typ, row, col, num, parms, attrs, cellname, cell in bels:
        tiledata = db.grid[row-1][col-1]
        tile = tilemap[(row-1, col-1)]

        if typ in {'IBUF', 'OBUF', 'TBUF', 'IOBUF'}:
            if typ == 'IBUF':
                parms['OUTPUT_USED'] = "0"
                parms['INPUT_USED'] =  "1"
                parms['ENABLE_USED'] = "0"
            elif typ == 'TBUF':
                parms['OUTPUT_USED'] = "1"
                parms['INPUT_USED'] =  "0"
                parms['ENABLE_USED'] = "1"
            elif typ == 'IOBUF':
                parms['OUTPUT_USED'] = "1"
                parms['INPUT_USED'] =  "1"
                parms['ENABLE_USED'] = "1"
            else:
                parms['OUTPUT_USED'] = "1"
                parms['INPUT_USED'] =  "0"
                parms['ENABLE_USED'] = "0"
            typ = 'IOB'

        if is_himbaechel and typ in {'IOLOGIC', 'IOLOGICI', 'IOLOGICO', 'IOLOGIC_DUMMY', 'ODDR', 'ODDRC', 'OSER4',
                                     'OSER8', 'OSER10', 'OVIDEO', 'IDDR', 'IDDRC', 'IDES4', 'IDES8', 'IDES10', 'IVIDEO'}:
            if num[-1] in {'I', 'O'}:
                num = num[:-1]
            if typ == 'IOLOGIC_DUMMY':
                attrs['IOLOGIC_FCLK'] = pnr['modules']['top']['cells'][attrs['MAIN_CELL']]['attributes']['IOLOGIC_FCLK']
            attrs['IOLOGIC_TYPE'] = typ
            if typ not in {'IDDR', 'IDDRC', 'ODDR', 'ODDRC'}:
                # We clearly distinguish between the HCLK wires and clock
                # spines at the nextpnr level by name, but in the fuse tables
                # they have the same number, this is possible because the clock
                # spines never go along the edges of the chip where the HCLK
                # wires are.
                recode_spines = {'UNKNOWN': 'UNKNOWN', 'HCLK_OUT0': 'SPINE10',
                                 'HCLK_OUT1': 'SPINE11', 'HCLK_OUT2': 'SPINE12',
                                 'HCLK_OUT3': 'SPINE13'}
                if attrs['IOLOGIC_FCLK'] in recode_spines:
                    attrs['IOLOGIC_FCLK'] = recode_spines[attrs['IOLOGIC_FCLK']]
            else:
                attrs['IOLOGIC_FCLK'] = 'UNKNOWN'
            typ = 'IOLOGIC'

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
        elif typ.startswith("BUFG"):
            continue

        elif typ in {'OSC', 'OSCZ', 'OSCF', 'OSCH', 'OSCW', 'OSCO'}:
            # XXX turn on (GW1NZ-1)
            if device == 'GW1NZ-1':
                en_tiledata = db.grid[db.rows - 1][db.cols - 1]
                en_tile = tilemap[(db.rows - 1, db.cols - 1)]
                en_tile[23][63] = 0
            # clear powersave fuses
            clear_attrs = set()
            add_attr_val(db, 'OSC', clear_attrs, attrids.osc_attrids['POWER_SAVE'], attrids.osc_attrvals['ENABLE'])
            bits = get_shortval_fuses(db, tiledata.ttyp, clear_attrs, 'OSC')
            for r, c in bits:
                tile[r][c] = 0

            osc_attrs = set_osc_attrs(db, typ, parms)
            bits = get_shortval_fuses(db, tiledata.ttyp, osc_attrs, 'OSC')
            for r, c in bits:
                tile[r][c] = 1
        elif typ == "SLICE":
            place_slice(db, tiledata, tile, parms, num)
        elif typ.startswith("DFF"):
            mode = typ.strip('E')
            place_dff(db, tiledata, tile, parms, num, mode)
        elif typ.startswith('LUT'):
            place_lut(db, tiledata, tile, parms, num)

        elif typ[:3] == "IOB":
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
            bel_name = f"IO{edge}{idx}{num}"
            cst.ports[cellname] = bel_name
            iob = tiledata.bels[f'IOB{num}']
            if 'DIFF' in parms:
                # skip negative pin for lvds
                if parms['DIFF'] == 'N':
                    continue
                # valid pin?
                if not iob.is_diff:
                    raise ValueError(f"Cannot place {cellname} at {bel_name} - not a diff pin")
                if not iob.is_diff_p:
                    raise ValueError(f"Cannot place {cellname} at {bel_name} - not a P pin")
                mode = parms['DIFF_TYPE']
                if iob.is_true_lvds and mode[0] != 'T':
                    raise ValueError(f"Cannot place {cellname} at {bel_name} - it is a true lvds pin")
                if not iob.is_true_lvds and mode[0] == 'T':
                    raise ValueError(f"Cannot place {cellname} at {bel_name} - it is an emulated lvds pin")
            else:
                if int(parms["ENABLE_USED"], 2):
                    if int(parms["INPUT_USED"], 2):
                        mode = "IOBUF"
                    else:
                        mode = "TBUF"
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

            flags = {'mode': mode}
            flags.update({port: net for port, net in parms.items() if port.startswith('NET_')})
            if int(parms.get("IOLOGIC_IOB", "0")):
                flags['USED_BY_IOLOGIC'] = True

            io_desc = _io_bels.setdefault(bank, {})[bel_name] = IOBelDesc(row - 1, col - 1, num, {}, flags, cell['connections'])

            # find io standard
            iostd = _default_iostd[mode]
            io_desc.attrs['IO_TYPE'] = iostd
            for flag in attrs.keys():
                flag_name_val = flag.split("=")
                if len(flag_name_val) < 2:
                    continue
                if flag[0] != chipdb.mode_attr_sep:
                    continue
                if flag_name_val[0] == chipdb.mode_attr_sep + "IO_TYPE":
                    iostd = _iostd_alias.get(flag_name_val[1], flag_name_val[1])
                else:
                    io_desc.attrs[flag_name_val[0][1:]] = flag_name_val[1]
            io_desc.attrs['IO_TYPE'] = iostd
            if pinless_io:
                return
        elif typ.startswith("RAM16SDP") or typ == "RAMW":
            ram_attrs = set()
            add_attr_val(db, 'SLICE', ram_attrs, attrids.cls_attrids['MODE'], attrids.cls_attrvals['SSRAM'])
            rambits = get_shortval_fuses(db, tiledata.ttyp, ram_attrs, 'CLS3')
            # In fact, the WRE signal is considered active when it is low, so
            # we include an inverter on the LSR2 line here to comply with the
            # documentation
            add_attr_val(db, 'SLICE', ram_attrs, attrids.cls_attrids['LSR_MUX_1'], attrids.cls_attrvals['0'])
            add_attr_val(db, 'SLICE', ram_attrs, attrids.cls_attrids['LSR_MUX_LSR'], attrids.cls_attrvals['INV'])
            rambits.update(get_shortval_fuses(db, tiledata.ttyp, ram_attrs, 'CLS2'))
            #print(f'({row - 1}, {col - 1}) attrs:{ram_attrs}, bits:{rambits}')
            for brow, bcol in rambits:
                tile[brow][bcol] = 1
        elif typ ==  'IOLOGIC':
            #print(row, col, cellname)
            iologic_attrs = set_iologic_attrs(db, parms, attrs)
            bits = set()
            table_type = f'IOLOGIC{num}'
            bits = get_shortval_fuses(db, tiledata.ttyp, iologic_attrs, table_type)
            for r, c in bits:
                tile[r][c] = 1
        elif typ in _bsram_cell_types or typ == 'BSRAM_AUX':
            store_bsram_init_val(db, row - 1, col -1, typ, parms, attrs)
            if typ == 'BSRAM_AUX':
                typ = cell['type']
            bsram_attrs = set_bsram_attrs(db, typ, parms)
            bsrambits = get_shortval_fuses(db, tiledata.ttyp, bsram_attrs, f'BSRAM_{typ}')
            #print(f'({row - 1}, {col - 1}) attrs:{bsram_attrs}, bits:{bsrambits}')
            for brow, bcol in bsrambits:
                tile[brow][bcol] = 1
        elif typ in {'MULTADDALU18X18', 'MULTALU36X18', 'MULTALU18X18', 'MULT36X36', 'MULT18X18', 'MULT9X9', 'PADD18', 'PADD9', 'ALU54D'} or typ == 'DSP_AUX':
            if typ == 'DSP_AUX':
                typ = cell['type']
            if typ in {'MULTADDALU18X18', 'MULTALU36X18', 'MULTALU18X18', 'ALU54D'}:
                num = num[-1] + num[-1]
            if typ != 'MULT36X36':
                dsp_attrs = set_dsp_attrs(db, typ, parms, num, attrs)
                dspbits = set()
                if f'DSP{num[-2]}' in db.shortval[tiledata.ttyp]:
                    dspbits = get_shortval_fuses(db, tiledata.ttyp, dsp_attrs, f'DSP{num[-2]}')
            else:
                dsp_attrs = set_dsp_mult36x36_attrs(db, typ, parms, attrs)
                dspbits = set()
                for mac in range(2):
                    if f'DSP{mac}' in db.shortval[tiledata.ttyp]:
                        dspbits.update(get_shortval_fuses(db, tiledata.ttyp, dsp_attrs[mac], f'DSP{mac}'))

            #1406.0iprint(f'({row - 1}, {col - 1}) attrs:{dsp_attrs}, bits:{sorted(dspbits)}')
            for brow, bcol in dspbits:
                tile[brow][bcol] = 1
        elif typ.startswith('RPLL'):
            pll_attrs = set_pll_attrs(db, 'RPLL', 0,  parms)
            bits = set()
            if 'PLL' in db.shortval[tiledata.ttyp]:
                bits = get_shortval_fuses(db, tiledata.ttyp, pll_attrs, 'PLL')
            #print(typ, tiledata.ttyp, bits)
            for r, c in bits:
                tile[r][c] = 1
        elif typ.startswith('ALU'):
            place_alu(db, tiledata, tile, parms, num)
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

    # second IO pass
    for bank, ios in _io_bels.items():
        # check IO standard
        vccio = None
        iostd = None
        for iob in ios.values():
            # diff io can't be placed at simplified io
            if iob.pos[0] in db.simplio_rows:
                if iob.flags['mode'].startswith('ELVDS') or iob.flags['mode'].startswith('TLVDS'):
                    raise Exception(f"Differential IO cant be placed at special row {iob.pos[0]}")

            if iob.flags['mode'] in {'IBUF', 'IOBUF', 'TLVDS_IBUF', 'TLVDS_IOBUF', 'ELVDS_IBUF', 'ELVDS_IOBUF'}:
                iob.attrs['IO_TYPE'] = get_iostd_alias(iob.attrs['IO_TYPE'])
                if iob.attrs.get('SINGLERESISTOR', 'OFF') != 'OFF':
                    iob.attrs['DDR_DYNTERM'] = 'ON'
            if iob.flags['mode'] in {'OBUF', 'IOBUF', 'TLVDS_IOBUF', 'ELVDS_IOBUF'}:
                if not vccio:
                    iostd = iob.attrs['IO_TYPE']
                    vccio = _vcc_ios[iostd]
                elif vccio != _vcc_ios[iob.attrs['IO_TYPE']] and not iostd.startswith('LVDS') and not iob.attrs['IO_TYPE'].startswith('LVDS'):
                    snd_type = iob.attrs['IO_TYPE']
                    fst = [name for name, iob in ios.items() if iob.attrs['IO_TYPE'] == iostd][0]
                    snd = [name for name, iob in ios.items() if iob.attrs['IO_TYPE'] == snd_type][0]
                    raise Exception(f"Different IO standard for bank {bank}: {fst} sets {iostd}, {snd} sets {iob.attrs['IO_TYPE']}.")

        if not vccio:
            iostd = 'LVCMOS12'

        in_bank_attrs = {}
        in_bank_attrs['VCCIO'] = _vcc_ios[iostd]

        # set io bits
        for name, iob in ios.items():
            row, col, idx = iob.pos
            tiledata = db.grid[row][col]

            mode_for_attrs = iob.flags['mode']
            lvds_attrs = {}
            if mode_for_attrs.startswith('TLVDS_') or mode_for_attrs.startswith('ELVDS_'):
                mode_for_attrs = mode_for_attrs[6:]
                lvds_attrs = {'HYSTERESIS': 'NA', 'PULLMODE': 'NONE', 'OPENDRAIN': 'OFF'}

            in_iob_attrs = _init_io_attrs[mode_for_attrs].copy()
            in_iob_attrs.update(lvds_attrs)

            # constant OEN connections lead to the use of special fuses
            if iob.flags['mode'] not in {'IBUF', 'TLVDS_IBUF', 'ELVDS_IBUF'}:
                if iob_is_connected(iob.flags, 'OEN'):
                    if iob_is_gnd_net(iob.flags, 'OEN'):
                        in_iob_attrs['TRIMUX_PADDT'] = 'SIG'
                    elif iob_is_vcc_net(iob.flags, 'OEN'):
                        in_iob_attrs['ODMUX_1'] = '0'
                    else:
                        in_iob_attrs['TRIMUX_PADDT'] = 'SIG'
                        in_iob_attrs['TO'] = 'SIG'
                else:
                    in_iob_attrs['ODMUX_1'] = '1'

            #
            for k, val in iob.attrs.items():
                k = refine_io_attrs(k)
                in_iob_attrs[k] = val
            in_iob_attrs['VCCIO'] = in_bank_attrs['VCCIO']
            #print(in_iob_attrs)

            # lvds
            if iob.flags['mode'] in {'TLVDS_OBUF', 'TLVDS_TBUF', 'TLVDS_IOBUF'}:
                in_iob_attrs.update({'LVDS_OUT': 'ON', 'ODMUX_1': 'UNKNOWN', 'ODMUX': 'TRIMUX',
                    'SLEWRATE': 'FAST', 'DRIVE': '0', 'PERSISTENT': 'OFF'})
            elif iob.flags['mode'] in {'ELVDS_OBUF', 'ELVDS_TBUF', 'ELVDS_IOBUF'}:
                in_iob_attrs.update({'ODMUX_1': 'UNKNOWN', 'ODMUX': 'TRIMUX',
                    'PERSISTENT': 'OFF'})
                in_iob_attrs['IO_TYPE'] = get_iostd_alias(in_iob_attrs['IO_TYPE'])
            if iob.flags['mode'] in {'TLVDS_IBUF', 'ELVDS_IBUF'}:
                in_iob_attrs['ODMUX_1'] = 'UNKNOWN'
                in_iob_attrs.pop('VCCIO', None)

            # XXX may be here do GW9 pins also
            if device == 'GW1N-1':
                if row == 5 and mode_for_attrs == 'OBUF':
                    in_iob_attrs['TO'] = 'UNKNOWN'
            if device not in {'GW1N-4', 'GW1NS-4'}:
                if mode[1:].startswith('LVDS') and in_iob_attrs['DRIVE'] != '0':
                    in_iob_attrs['DRIVE'] = 'UNKNOWN'
            in_iob_b_attrs = {}
            if iob.flags['mode'] in {'TLVDS_OBUF', 'TLVDS_TBUF', 'TLVDS_IOBUF'}:
                in_iob_b_attrs = in_iob_attrs.copy()
            elif iob.flags['mode'] in {'TLVDS_IBUF', 'ELVDS_IBUF'}:
                in_iob_b_attrs = in_iob_attrs.copy()
                if iob.flags['mode'] in {'ELVDS_IBUF'}:
                    in_iob_attrs['PULLMODE'] = 'UP'
                    in_iob_b_attrs['PULLMODE'] = 'NONE'
                in_iob_b_attrs['IO_TYPE'] = in_iob_attrs.get('IO_TYPE', 'UNKNOWN')
                in_iob_b_attrs['DIFFRESISTOR'] = in_iob_attrs.get('DIFFRESISTOR', 'OFF')
            elif iob.flags['mode'] in {'ELVDS_OBUF', 'ELVDS_TBUF', 'ELVDS_IOBUF'}:
                if iob.flags['mode'] in {'ELVDS_IOBUF'}:
                    in_iob_attrs['PULLMODE'] = 'UP'
                    in_iob_b_attrs['PULLMODE'] = 'UP'
                in_iob_b_attrs = in_iob_attrs.copy()

            for iob_idx, atr in [(idx, in_iob_attrs), ('B', in_iob_b_attrs)]:
                #print(name, iob.pos, atr)
                iob_attrs = set()
                for k, val in atr.items():
                    if k not in attrids.iob_attrids:
                        print(f'XXX IO: add {k} key handle')
                    elif k == 'OPENDRAIN' and val == 'OFF' and 'LVDS' not in iob.flags['mode'] and 'IBUF' not in iob.flags['mode']:
                        continue
                    else:
                        add_attr_val(db, 'IOB', iob_attrs, attrids.iob_attrids[k], attrids.iob_attrvals[val])
                        if k in {'VCCIO'}:
                            continue
                        if k == 'LVDS_OUT' and val not in {'ENABLE', 'ON'}:
                            continue
                        in_bank_attrs[k] = val
                bits = get_longval_fuses(db, tiledata.ttyp, iob_attrs, f'IOB{iob_idx}')
                tile = tilemap[(row, col)]
                for row_, col_ in bits:
                    tile[row_][col_] = 1

        # bank bits
        brow, bcol = db.bank_tiles[bank]
        tiledata = db.grid[brow][bcol]

        bank_attrs = set()
        for k, val in in_bank_attrs.items():
            #print(k, val)
            if k not in attrids.iob_attrids:
                print(f'XXX BANK: add {k} key handle')
            else:
                add_attr_val(db, 'IOB', bank_attrs, attrids.iob_attrids[k], attrids.iob_attrvals[val])
        bits = get_bank_fuses(db, tiledata.ttyp, bank_attrs, 'BANK', int(bank))
        btile = tilemap[(brow, bcol)]
        for row, col in bits:
            btile[row][col] = 1

    #for k, v in _io_bels.items():
    #    for io, bl in v.items():
    #        print(k, io, vars(bl))

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
            if dest in tiledata.alonenode_6:
                tile = tilemap[(fuse_row, col - 1)]
                _, bits = tiledata.alonenode_6[dest]
                for row, col in bits:
                    tile[row][col] = 1


def route(db, tilemap, pips):
    for row, col, src, dest in pips:
        tiledata = db.grid[row-1][col-1]
        tile = tilemap[(row-1, col-1)]

        try:
            if dest in tiledata.clock_pips:
                bits = tiledata.clock_pips[dest][src]
            elif is_himbaechel and (row - 1, col - 1) in db.hclk_pips and dest in db.hclk_pips[row - 1, col - 1]:
                bits = db.hclk_pips[row - 1, col - 1][dest][src]
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
    bs = bitmatrix.fliplr(bs)
    bs = bitmatrix.packbits(bs)
    # configuration data checksum is computed on all
    # data in 16bit format
    res = int(sum(bs[0::2]) * pow(2,8) + sum(bs[1::2]))
    checksum = res & 0xffff

    if compress:
        # update line 0x10 with compress enable bit
        # rest (keys) is done in bslib.write_bitstream
        hdr10 = int.from_bytes(db.cmd_hdr[4], 'big') | (1 << 13)
        db.cmd_hdr[4] = bytearray.fromhex(f"{hdr10:016x}")

    # set the checksum
    db.cmd_ftr[1] = bytearray.fromhex(f"{0x0A << 56 | checksum:016x}")

def gsr(db, tilemap, args):
    gsr_attrs = set()
    for k, val in {'GSRMODE': 'ACTIVE_LOW'}.items():
        if k not in attrids.gsr_attrids:
            print(f'XXX GSR: add {k} key handle')
        else:
            add_attr_val(db, 'GSR', gsr_attrs, attrids.gsr_attrids[k], attrids.gsr_attrvals[val])

    cfg_attrs = set()
    for k, val in {'GSR': 'USED'}.items():
        if k not in attrids.cfg_attrids:
            print(f'XXX CFG GSR: add {k} key handle')
        else:
            add_attr_val(db, 'CFG', cfg_attrs, attrids.cfg_attrids[k], attrids.cfg_attrvals[val])

    # The configuration fuses are described in the ['shortval'][60] table, global set/reset is
    # described in the ['shortval'][20] table. Look for cells with type with these tables
    gsr_type = {50, 83}
    cfg_type = {50, 51}
    if device in {'GW2A-18', 'GW2A-18C'}:
        gsr_type = {1, 83}
        cfg_type = {1, 51}
    for row, rd in enumerate(db.grid):
        for col, rc in enumerate(rd):
            bits = set()
            if rc.ttyp in gsr_type:
                bits = get_shortval_fuses(db, rc.ttyp, gsr_attrs, 'GSR')
            if rc.ttyp in cfg_type:
                bits.update(get_shortval_fuses(db, rc.ttyp, cfg_attrs, 'CFG'))
            if bits:
                btile = tilemap[(row, col)]
                for brow, bcol in bits:
                    btile[brow][bcol] = 1

def dualmode_pins(db, tilemap, args):
    pin_flags = {'JTAG_AS_GPIO': 'UNKNOWN', 'SSPI_AS_GPIO': 'UNKNOWN', 'MSPI_AS_GPIO': 'UNKNOWN',
            'DONE_AS_GPIO': 'UNKNOWN', 'RECONFIG_AS_GPIO': 'UNKNOWN', 'READY_AS_GPIO': 'UNKNOWN'}
    if args.jtag_as_gpio:
        pin_flags['JTAG_AS_GPIO'] = 'YES'
    if args.sspi_as_gpio:
        pin_flags['SSPI_AS_GPIO'] = 'YES'
    if args.mspi_as_gpio:
        pin_flags['MSPI_AS_GPIO'] = 'YES'
    if args.ready_as_gpio:
        pin_flags['READY_AS_GPIO'] = 'YES'
    if args.done_as_gpio:
        pin_flags['DONE_AS_GPIO'] = 'YES'
    if args.reconfign_as_gpio:
        pin_flags['RECONFIG_AS_GPIO'] = 'YES'

    set_attrs = set()
    clr_attrs = set()
    for k, val in pin_flags.items():
        if k not in attrids.cfg_attrids:
            print(f'XXX CFG: add {k} key handle')
        else:
            add_attr_val(db, 'CFG', set_attrs, attrids.cfg_attrids[k], attrids.cfg_attrvals[val])
            add_attr_val(db, 'CFG', clr_attrs, attrids.cfg_attrids[k], attrids.cfg_attrvals['YES'])

    # The configuration fuses are described in the ['shortval'][60] table, here
    # we are looking for cells with types that have such a table.
    cfg_type = {50, 51}
    if device in {'GW2A-18', 'GW2A-18C'}:
        cfg_type = {1, 51}
    for row, rd in enumerate(db.grid):
        for col, rc in enumerate(rd):
            bits = set()
            clr_bits = set()
            if rc.ttyp in cfg_type:
                bits.update(get_shortval_fuses(db, rc.ttyp, set_attrs, 'CFG'))
                clr_bits.update(get_shortval_fuses(db, rc.ttyp, clr_attrs, 'CFG'))
            if clr_bits:
                btile = tilemap[(row, col)]
                for brow, bcol in clr_bits:
                    btile[brow][bcol] = 0
                for brow, bcol in bits:
                    btile[brow][bcol] = 1

def main():
    global device
    global pnr

    pil_available = True
    try:
        from PIL import Image
    except ImportError:
        pil_available = False
    parser = argparse.ArgumentParser(description='Pack Gowin bitstream')
    parser.add_argument('netlist')
    parser.add_argument('-d', '--device', required=True)
    parser.add_argument('-o', '--output', default='pack.fs')
    parser.add_argument('-c', '--compress', action='store_true')
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

    with open(args.netlist) as f:
        pnr = json.load(f)

    # check for new P&R
    if pnr['modules']['top']['settings'].get('packer.arch', '') == 'himbaechel/gowin':
        global is_himbaechel
        is_himbaechel = True

    # For tool integration it is allowed to pass a full part number
    m = re.match("GW1N(S|Z)?[A-Z]*-(LV|UV|UX)([0-9])C?([A-Z]{2}[0-9]+P?)(C[0-9]/I[0-9])", device)
    if m:
        mods = m.group(1) or ""
        luts = m.group(3)
        device = f"GW1N{mods}-{luts}"
    with importlib.resources.path('apycula', f'{device}.pickle') as path:
        with closing(gzip.open(path, 'rb')) as f:
            db = pickle.load(f)

    const_nets = {'GND': '$PACKER_GND_NET', 'VCC': '$PACKER_GND_NET'}
    if is_himbaechel:
        const_nets = {'GND': '$PACKER_GND', 'VCC': '$PACKER_GND'}

    _gnd_net = pnr['modules']['top']['netnames'].get(const_nets['GND'], {'bits': []})['bits']
    _vcc_net = pnr['modules']['top']['netnames'].get(const_nets['VCC'], {'bits': []})['bits']

    tilemap = chipdb.tile_bitmap(db, db.template, empty=True)
    cst = codegen.Constraints()
    pips = get_pips(pnr)
    route(db, tilemap, pips)
    bels = get_bels(pnr)
    # routing can add pass-through LUTs
    place(db, tilemap, itertools.chain(bels, _pip_bels) , cst, args)
    gsr(db, tilemap, args)
    dualmode_pins(db, tilemap, args)
    # XXX Z-1 some kind of power saving for pll, disable
    # When comparing images with a working (IDE) and non-working PLL (apicula),
    # no differences were found in the fuses of the PLL cell itself, but a
    # change in one bit in the root cell was replaced.
    # If the PLL configurations match, then the assumption has been made that this
    # bit simply disables it somehow.

    if device in {'GW1NZ-1'}:
        tile = tilemap[(db.rows - 1, db.cols - 1)]
        for row, col in {(23, 63)}:
            tile[row][col] = 0

    res = chipdb.fuse_bitmap(db, tilemap)
    header_footer(db, res, args.compress)
    if pil_available and args.png:
        bslib.display(args.png, res)

    if has_bsram_init:
        bslib.write_bitstream_with_bsram_init(args.output, res, db.cmd_hdr, db.cmd_ftr, args.compress, bsram_init_map)
    else:
        bslib.write_bitstream(args.output, res, db.cmd_hdr, db.cmd_ftr, args.compress)
    if args.cst:
        with open(args.cst, "w") as f:
                cst.write(f)

if __name__ == '__main__':
    main()
