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
from apycula.chipdb import add_attr_val, get_shortval_fuses, get_longval_fuses, get_bank_fuses
from apycula import attrids
from apycula import bslib
from apycula.wirenames import wirenames, wirenumbers

device = ""

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
    return f'NET_{wire}' in flags.keys()

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
    if device in {'GW1N-9C', 'GW1N-9'}:
        if int(col) > 28:
            offx = -1
        for off in [1, 2, 3]:
            yield ('RPLLB', int(row), int(col) + offx * off, num,
                cell['parameters'], cell['attributes'], sanitize_name(cellname) + f'B{off}', cell)
    elif device in {'GW1N-1', 'GW1NZ-1', 'GW1N-4'}:
        for off in [1]:
            yield ('RPLLB', int(row), int(col) + offx * off, num,
                cell['parameters'], cell['attributes'], sanitize_name(cellname) + f'B{off}', cell)

def get_bels(data):
    later = []
    belre = re.compile(r"R(\d+)C(\d+)_(?:GSR|SLICE|IOB|MUX2_LUT5|MUX2_LUT6|MUX2_LUT7|MUX2_LUT8|ODDR|OSC[ZFHWO]?|BUFS|RAMW|rPLL|PLLVR|IOLOGIC)(\w*)")
    for cellname, cell in data['modules']['top']['cells'].items():
        if cell['type'].startswith('DUMMY_') or cell['type'] in {'OSER16', 'IDES16'}:
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
                cell['parameters'], cell['attributes'], sanitize_name(cellname), cell)

    # diff iobs
    for cellname, cell, row, col, num in later:
        yield (cell['type'], int(row), int(col), num,
                cell['parameters'], cell['attributes'], sanitize_name(cellname), cell)

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
            val = attrids.pll_attrvals[val]
        add_attr_val(db, 'PLL', fin_attrs, attrids.pll_attrids[attr], val)
    #print(fin_attrs)
    return fin_attrs

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
    if 'TXCLK_POL' in attrs.keys():
        if int(attrs['TXCLK_POL']) == 0:
            attrs['TSHX'] = 'SIG'
        else:
            attrs['TSHX'] = 'INV'
        del attrs['TXCLK_POL']
    if 'HWL' in attrs.keys():
        if attrs['HWL'] == 'true':
            attrs['UPDATE'] = 'SAME'
        del attrs['HWL']
    if 'GSREN' in attrs.keys():
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
    if 'OUTMODE' in attrs.keys():
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
    if 'INMODE' in attrs.keys():
        if param['IOLOGIC_TYPE'] not in {'IDDR', 'IDDRC'}:
            in_attrs['CLKODDRMUX_WRCLK'] = 'ECLK0'
            in_attrs['CLKODDRMUX_ECLK'] = 'UNKNOWN'
            if param['IOLOGIC_FCLK'] in {'SPINE12', 'SPINE13'}:
                in_attrs['CLKIDDRMUX_ECLK'] = 'ECLK1'
            elif param['IOLOGIC_FCLK'] in {'SPINE10', 'SPINE11'}:
                in_attrs['CLKODDRMUX_ECLK'] = 'ECLK0'
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
        if k not in attrids.iologic_attrids.keys():
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
                 'DRIVE': '0', 'OPENDRAIN': 'OFF', 'CLAMP': 'OFF', 'DIFFRESISTOR': 'OFF',
                 'VREF': 'OFF', 'LVDS_OUT': 'OFF'},
        'OBUF': {'ODMUX_1': '1', 'OPENDRAIN': 'OFF', 'PULLMODE': 'UP', 'SLEWRATE': 'FAST',
                 'DRIVE': '8', 'HYSTERESIS': 'NONE', 'CLAMP': 'OFF', 'DIFFRESISTOR': 'OFF',
                 'SINGLERESISTOR': 'OFF', 'VCCIO': '1.8', 'LVDS_OUT': 'OFF', 'DDR_DYNTERM': 'NA', 'TO': 'INV'},
        'TBUF': {'ODMUX_1': 'UNKNOWN', 'OPENDRAIN': 'OFF', 'PULLMODE': 'UP', 'SLEWRATE': 'FAST',
                 'DRIVE': '8', 'HYSTERESIS': 'NONE', 'CLAMP': 'OFF', 'DIFFRESISTOR': 'OFF',
                 'SINGLERESISTOR': 'OFF', 'VCCIO': '1.8', 'LVDS_OUT': 'OFF', 'DDR_DYNTERM': 'NA',
                 'TO': 'INV', 'PERSISTENT': 'OFF', 'ODMUX': 'TRIMUX'},
        'IOBUF': {'ODMUX_1': 'UNKNOWN', 'OPENDRAIN': 'OFF', 'PULLMODE': 'UP', 'SLEWRATE': 'FAST',
                 'DRIVE': '8', 'HYSTERESIS': 'NONE', 'CLAMP': 'OFF', 'DIFFRESISTOR': 'OFF',
                 'SINGLERESISTOR': 'OFF', 'VCCIO': '1.8', 'LVDS_OUT': 'OFF', 'DDR_DYNTERM': 'NA',
                 'TO': 'INV', 'PERSISTENT': 'OFF', 'ODMUX': 'TRIMUX', 'PADDI': 'PADDI'},
        }
_refine_attrs = {'SLEW_RATE': 'SLEWRATE', 'PULL_MODE': 'PULLMODE'}
def refine_io_attrs(attr):
    return _refine_attrs.get(attr, attr)

_sides = "AB"
def place(db, tilemap, bels, cst, args):
    for typ, row, col, num, parms, attrs, cellname, cell in bels:
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
                    #if int(mode, 2) == 2:
                    #print('ALU mode:', int(mode, 2), ' bits:', bits)
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

            if int(num) < 6 and int(parms['FF_USED'], 2):
                mode = str(parms['FF_TYPE']).strip('E')
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

            # XXX skip power
            if not cellname.startswith('\$PACKER'):
                cst.cells[cellname] = (row, col, int(num) // 2, _sides[int(num) % 2])
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
            if 'DIFF' in parms.keys():
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
            io_desc.attrs['IO_TYPE'] = iostd
            if pinless_io:
                return
        elif typ == "RAMW":
            bel = tiledata.bels['RAM16']
            bits = bel.modes['0']
            #print(typ, bits)
            for r, c in bits:
                tile[r][c] = 1
        elif typ ==  'IOLOGIC':
            iologic_attrs = set_iologic_attrs(db, parms, attrs)
            bits = set()
            table_type = f'IOLOGIC{num}'
            bits = get_shortval_fuses(db, tiledata.ttyp, iologic_attrs, table_type)
            for r, c in bits:
                tile[r][c] = 1
        elif typ.startswith('RPLL'):
            pll_attrs = set_pll_attrs(db, 'RPLL', 0,  parms)
            bits = set()
            if 'PLL' in db.shortval[tiledata.ttyp].keys():
                bits = get_shortval_fuses(db, tiledata.ttyp, pll_attrs, 'PLL')
            #print(typ, tiledata.ttyp, bits)
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

    # second IO pass
    for bank, ios in _io_bels.items():
        # check IO standard
        # IBUFs do not affect bank io
        iostds = {iob.attrs['IO_TYPE'] for iob in ios.values() if iob.flags['mode'] != 'IBUF'}
        iostds = set()
        for iob in ios.values():
            if iob.flags['mode'] in {'IBUF', 'IOBUF', 'TLVDS_IBUF', 'TLVDS_IOBUF', 'ELVDS_IBUF', 'ELVDS_IOBUF'}:
                iob.attrs['IO_TYPE'] = get_iostd_alias(iob.attrs['IO_TYPE'])
                if iob.attrs.get('SINGLERESISTOR', 'OFF') != 'OFF':
                    iob.attrs['DDR_DYNTERM'] = 'ON'
                if iob.flags['mode'] in {'IOBUF', 'TLVDS_IOBUF', 'ELVDS_IOBUF'}:
                    iostds.add(iob.attrs['IO_TYPE'])
            else: # TBUF and OBUF
                iostds.add(iob.attrs['IO_TYPE'])

        if len(iostds) >= 2:
            conflict_std = list(iostds)
            fst = [name for name, iob in ios.items() if iob.attrs['IO_TYPE'] == conflict_std[0]][0]
            snd = [name for name, iob in ios.items() if iob.attrs['IO_TYPE'] == conflict_std[1]][0]
            raise Exception(f"Different IO standard for bank {bank}: {fst} sets {conflict_std[0]}, {snd} sets {conflict_std[1]}.")
        if len(iostds) == 0:
            iostds.add('LVCMOS12')
        iostd = list(iostds)[0]

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
                iob_attrs = set()
                for k, val in atr.items():
                    if k not in attrids.iob_attrids.keys():
                        print(f'XXX IO: add {k} key handle')
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
            if k not in attrids.iob_attrids.keys():
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

    _vcc_net = pnr['modules']['top']['netnames']['$PACKER_VCC_NET']['bits']
    _gnd_net = pnr['modules']['top']['netnames']['$PACKER_GND_NET']['bits']

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
