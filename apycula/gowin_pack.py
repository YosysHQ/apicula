import sys
import os
import re
import pickle
import bisect
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
from apycula.chipdb import add_attr_val, get_shortval_fuses, get_longval_fuses, get_bank_fuses, get_bank_io_fuses, get_long_fuses
from apycula import attrids
from apycula import bslib
from apycula import bitmatrix
from apycula import wirenames as wnames

device = ""
pnr = None
bsram_init_map = None
gw5a_bsrams = []
adc_iolocs = {} # pos: {}

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

def iob_is_connected_to_HCLK_GCLK(connections):
    if 'O' not in connections:
        return False
    for net_name in pnr['modules']['top']['netnames']:
        net = pnr['modules']['top']['netnames'][net_name]
        for out_bits in connections['O']:
            if out_bits in net['bits']:
                if 'ROUTING' in net['attributes'] and 'HCLK_GCLK' in net['attributes']['ROUTING']:
                    return True
    return False

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
    return f"\\{retname} "

def attrs_upper(attrs):
    for k, v in attrs.items():
        if isinstance(v, str):
            attrs[k] = v.upper()

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

def extra_clkdiv_bels(cell, row, col, num, cellname):
    if device in {'GW1NS-4'}:
        if int(col) == 18:
            bel_type = f'{cell["type"]}_AUX'
            yield (bel_type, int(row), int(col) + 3, num,
                cell['parameters'], cell['attributes'], sanitize_name(cellname) + 'AUX', cell)
        if int(col) == 17:
            bel_type = f'{cell["type"]}_AUX'
            yield (bel_type, int(row), int(col) + 1, num,
                cell['parameters'], cell['attributes'], sanitize_name(cellname) + 'AUX', cell)

def extra_mipi_bels(cell, row, col, num, cellname):
    yield ('MIPI_IBUF_AUX', int(row), int(col) + 1, num,
        cell['parameters'], cell['attributes'], sanitize_name(cellname) + 'AUX', cell)

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
# one single nonzero bit at address 0 in the initialization. You generate an
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
def store_bsram_init_val(db, row, col, typ, parms, attrs, map_offset = 0):
    global bsram_init_map

    if typ == 'BSRAM_AUX' or 'INIT_RAM_00' not in parms:
        return

    attrs_upper(attrs)
    subtype = attrs['BSRAM_SUBTYPE']
    if not bsram_init_map:
        if device in {'GW5A-25A'}:
            # 72 * bsram rows * chip bit width
            bsram_init_map = bitmatrix.zeros(72 * len(db.simplio_rows), db.width)
        else:
            # 256 * bsram rows * chip bit width
            bsram_init_map = bitmatrix.zeros(256 * len(db.simplio_rows), db.width)
    if device in {'GW5A-25A'}:
        # 1 BSRAM cell have width 72
        loc_map = bitmatrix.zeros(256, 72)
    else:
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
        row_name = f'INIT_RAM_{init_row:02X}'
        # skip missing init rows
        if row_name not in parms:
            addr += 0x100
            continue
        init_data = parms[row_name]
        #print(init_data)
        for ptr_bit_inc in get_bits(init_data):
            addr = ptr_bit_inc[2](addr)
            if ptr_bit_inc[0] == '0':
                continue
            logic_line = ptr_bit_inc[1] * 4 + (addr >> 12)
            bit = db.rev_logicinfo('BSRAM_INIT')[logic_line][0] - 1
            quad = {0x30: 0xc0, 0x20: 0x40, 0x10: 0x80, 0x00: 0x00}[addr & 0x30]
            map_row = quad + ((addr >> 6) & 0x3f)
            #print(f'map_row:{map_row}, addr: {addr}, bit {ptr_bit_inc[1]}, bit:{bit}')
            loc_map[map_row][bit] = 1

    # now put one cell init data into global space
    height = 256
    if device in {'GW5A-25A'}:
        height = 72
        loc_map = bitmatrix.transpose(loc_map)
    y = 0
    for brow in db.simplio_rows:
        if row == brow:
            break
        y += height

    if device in {'GW5A-25A'}:
        x = 256 * map_offset
    else:
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

_clkdiv_cell_types = {'CLKDIV', 'CLKDIV2'}
_bsram_cell_types = {'DP', 'SDP', 'SP', 'ROM'}
_dsp_cell_types = {'ALU54D', 'MULT36X36', 'MULTALU36X18', 'MULTADDALU18X18', 'MULTALU18X18', 'MULT18X18', 'MULT9X9', 'PADD18', 'PADD9'}
def get_bels(data):
    later = []
    belre = re.compile(r"X(\d+)Y(\d+)/(?:GSR|LUT|DFF|IOB|MUX|ALU|ODDR|OSC[ZFHWOA]?|BUF[GS]|RAM16SDP4|RAM16SDP2|RAM16SDP1|PLL|IOLOGIC|CLKDIV2|CLKDIV|BSRAM|ALU|MULTALU18X18|MULTALU36X18|MULTADDALU18X18|MULT36X36|MULT18X18|MULT9X9|PADD18|PADD9|BANDGAP|DQCE|DCS|USERFLASH|EMCU|DHCEN|MIPI_OBUF|MIPI_IBUF|DLLDLY|PINCFG|PLLA|ADC)(\w*)")

    for cellname, cell in data['modules']['top']['cells'].items():
        if cell['type'].startswith('DUMMY_') or cell['type'] in {'OSER16', 'IDES16'} or 'NEXTPNR_BEL' not in cell['attributes']:
            continue
        bel = cell['attributes']['NEXTPNR_BEL']
        if bel in {"VCC", "GND"}: continue
        if bel[-4:] in {'/GND', '/VCC'}:
            continue

        bels = belre.match(bel)
        if not bels:
            raise Exception(f"Unknown bel:{bel}")
        col, row, num = bels.groups()
        col = str(int(col) + 1)
        row = str(int(row) + 1)

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
        if cell_type in _clkdiv_cell_types:
            yield from extra_clkdiv_bels(cell, row, col, num, cellname)
        if cell_type in _bsram_cell_types:
            yield from extra_bsram_bels(cell, row, col, num, cellname)
        if cell_type in _dsp_cell_types:
            yield from extra_dsp_bels(cell, row, col, num, cellname)
        if cell_type == 'MIPI_IBUF':
            yield from extra_mipi_bels(cell, row, col, num, cellname)
        yield (cell_type, int(row), int(col), num,
                cell['parameters'], cell['attributes'], sanitize_name(cellname), cell)

    # diff iobs
    for cellname, cell, row, col, num in later:
        yield (cell['type'], int(row), int(col), num,
                cell['parameters'], cell['attributes'], sanitize_name(cellname), cell)

_pip_bels = []
def get_pips(data):
    pipre = re.compile(r"X(\d+)Y(\d+)/([\w_]+)/([\w_]+)")
    for net in data['modules']['top']['netnames'].values():
        routing = net['attributes']['ROUTING']
        pips = routing.split(';')[1::3]
        for pip in pips:
            res = pipre.fullmatch(pip) # ignore alias
            if res:
                row, col, src, dest = res.groups()
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
            elif pip and "DUMMY" not in pip:
                print("Invalid pip:", pip)

# Because of the default connection, the segment may end up being enabled at
# both ends. Nextpnr detects and lists the wires that need to be isolated, here
# we parse this information and disconnect using the "alonenode" table.
def isolate_segments(pnr, db, tilemap):
    wire_re = re.compile(r"X(\d+)Y(\d+)/([\w]+)")
    for net in pnr['modules']['top']['netnames'].values():
        if 'SEG_WIRES_TO_ISOLATE' not in net['attributes']:
            continue
        val = net['attributes']['SEG_WIRES_TO_ISOLATE']
        wires = val.split(';')
        for wire_ex in wires:
            if not wire_ex:
                continue
            res = wire_re.fullmatch(wire_ex)
            if res:
                s_col, s_row, wire = res.groups()
                row = int(s_row)
                col = int(s_col)
                tiledata = db.grid[row][col]
                tile = tilemap[(row, col)]
                if wire not in tiledata.alonenode_6:
                    raise Exception(f"Wire {wire} is not in alonenode fuse table")
                if len(tiledata.alonenode_6[wire]) != 1:
                    raise Exception(f"Incorrect alonenode fuse table for {wire}")
                bits = tiledata.alonenode_6[wire][0][1]
                for row, col in bits:
                    tile[row][col] = 1
            else:
                raise Exception(f"Invalid isolated wire:{wire_ex}")

def infovaluemap(infovalue, start=2):
    return {tuple(iv[:start]):iv[start:] for iv in infovalue}

# Permitted frequencies for chips
# { device : (max_in, max_out, min_out, max_vco, min_vco) }
_permitted_freqs = {
        "GW1N-1":  (400, 450, 3.125,  900,  400),
        "GW1NZ-1": (400, 400, 3.125,  800,  400),
        "GW1N-4":  (400, 500, 3.125,  1000, 400),
        "GW1NS-4": (400, 600, 4.6875, 1200, 400),
        "GW1N-9":  (400, 500, 3.125,  1000, 400),
        "GW1N-9C": (400, 600, 3.125,  1200, 400),
        "GW1NS-2": (400, 500, 3.125,  1200, 400),
        "GW2A-18": (500, 625, 3.90625, 1250, 500),
        "GW2A-18C": (500, 625, 3.90625, 1250, 500),
        "GW5A-25A": (800, 1600, 6.25, 1600, 800),
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
_freq_R = [[(2.6, 65100.0), (3.87, 43800.0), (7.53, 22250.0), (14.35, 11800.0), (28.51, 5940.0), (57.01, 2970.0), (114.41, 1480), (206.34, 820.0)],
           [(2.4, 69410.0), (3.53, 47150.0), (6.82, 24430.0), (12.93, 12880.0), (25.7, 6480.0), (51.4, 3240.0), (102.81, 1620), (187.13, 890.0)],
           [(3.24, 72300), (4.79, 48900), (9.22, 25400), (17.09, 13700), (34.08, 6870), (68.05, 3440), (136.1, 1720), (270.95, 864)]]
def calc_pll_pump(fref, fvco):
    fclkin_idx = int((fref - 1) // 30)
    if (fclkin_idx == 13 and fref <= 395) or (fclkin_idx == 14 and fref <= 430) or (fclkin_idx == 15 and fref <= 465) or fclkin_idx == 16:
        fclkin_idx = fclkin_idx - 1

    if device in {'GW2A-18', 'GW2A-18C'}:
        freq_Ri = _freq_R[1]
    elif device in {'GW5A-25A'}:
        freq_Ri = _freq_R[2]
    else:
        freq_Ri = _freq_R[0]
    r_vals = [(fr[1], len(freq_Ri) - 1 - idx) for idx, fr in enumerate(freq_Ri) if fr[0] < fref]
    r_vals.reverse()

    # Find the resistor that provides the minimum current through the capacitor
    if device in {'GW2A-18', 'GW2A-18C'}:
        K0 = (-28.938 + math.sqrt(837.407844 - (385.07 - fvco) * 0.9892)) / 0.4846
        K1 = 0.1942 * K0 * K0 - 13.173 * K0 + 518.86
        C1 = 6.69244e-11
    elif device in {'GW5A-25A'}:
        K1 = 120
        if fvco >= 1400.0:
            K1 = 240
        C1 = 4.725e-11
    else:
        K0 = (497.5 - math.sqrt(247506.25 - (2675.4 - fvco) * 78.46)) / 39.23
        K1 = 4.8714 * K0 * K0 + 6.5257 * K0 + 142.67
        C1 = 6.69244e-11
    Kvco = 1000000.0 * K1
    Ndiv = fvco / fref

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
            'DYN_IDIV_SEL'  : 'FALSE',
            'FBDIV_SEL'     : '00000000000000000000000000000000',
            'DYN_FBDIV_SEL' : 'FALSE',
            'ODIV_SEL'      : '00000000000000000000000000001000',
            'DYN_ODIV_SEL'  : 'FALSE',
            'PSDA_SEL'      : '0000 ', # XXX extra space for compatibility, but it will work with or without it in the future
            'DUTYDA_SEL'    : '1000 ', # ^^^
            'DYN_DA_EN'     : 'FALSE',
            'CLKOUT_FT_DIR' : '1',
            'CLKOUT_DLY_STEP': '00000000000000000000000000000000',
            'CLKOUTP_FT_DIR': '1',
            'CLKOUTP_DLY_STEP': '00000000000000000000000000000000',
            'DYN_SDIV_SEL'  : '00000000000000000000000000000010',
            'CLKFB_SEL'     : 'INTERNAL',
            'CLKOUTD_SRC'   : 'CLKOUT',
            'CLKOUTD3_SRC'  : 'CLKOUT',
            'CLKOUT_BYPASS' : 'FALSE',
            'CLKOUTP_BYPASS': 'FALSE',
            'CLKOUTD_BYPASS': 'FALSE',
            'DEVICE'        : 'GW1N-1'
        }

_default_plla_inattrs = {
            'FCLKIN'              : '100.00',
            'A_IDIV_SEL'          : '1',
            'A_FBDIV_SEL'         : '1',
            'A_ODIV0_SEL'         : '8',
            'A_ODIV1_SEL'         : '8',
            'A_ODIV2_SEL'         : '8',
            'A_ODIV3_SEL'         : '8',
            'A_ODIV4_SEL'         : '8',
            'A_ODIV5_SEL'         : '8',
            'A_ODIV6_SEL'         : '8',
            'A_MDIV_SEL'          : '8',
            'A_MDIV_FRAC_SEL'     : '0',
            'A_ODIV0_FRAC_SEL'    : '0',
            'A_CLKOUT0_EN'        : 'TRUE',
            'A_CLKOUT1_EN'        : 'TRUE',
            'A_CLKOUT2_EN'        : 'TRUE',
            'A_CLKOUT3_EN'        : 'TRUE',
            'A_CLKOUT4_EN'        : 'TRUE',
            'A_CLKOUT5_EN'        : 'TRUE',
            'A_CLKOUT6_EN'        : 'TRUE',
            'A_CLKFB_SEL'         : 'INTERNAL',
            'A_CLKOUT0_DT_DIR'    : 1,
            'A_CLKOUT1_DT_DIR'    : 1,
            'A_CLKOUT2_DT_DIR'    : 1,
            'A_CLKOUT3_DT_DIR'    : 1,
            'A_CLKOUT0_DT_STEP'   : 0,
            'A_CLKOUT1_DT_STEP'   : 0,
            'A_CLKOUT2_DT_STEP'   : 0,
            'A_CLKOUT3_DT_STEP'   : 0,
            'A_CLK0_IN_SEL'       : 0,
            'A_CLK0_OUT_SEL'      : 0,
            'A_CLK1_IN_SEL'       : 0,
            'A_CLK1_OUT_SEL'      : 0,
            'A_CLK2_IN_SEL'       : 0,
            'A_CLK2_OUT_SEL'      : 0,
            'A_CLK3_IN_SEL'       : 0,
            'A_CLK3_OUT_SEL'      : 0,
            'A_CLK4_IN_SEL'       : 0,
            'A_CLK4_OUT_SEL'      : 0,
            'A_CLK5_IN_SEL'       : 0,
            'A_CLK5_OUT_SEL'      : 0,
            'A_CLK6_IN_SEL'       : 0,
            'A_CLK6_OUT_SEL'      : 0,
            'A_DYN_DPA_EN'        : 'FALSE',
            'A_CLKOUT0_PE_COARSE' : 0,
            'A_CLKOUT0_PE_FINE'   : 0,
            'A_CLKOUT1_PE_COARSE' : 0,
            'A_CLKOUT1_PE_FINE'   : 0,
            'A_CLKOUT2_PE_COARSE' : 0,
            'A_CLKOUT2_PE_FINE'   : 0,
            'A_CLKOUT3_PE_COARSE' : 0,
            'A_CLKOUT3_PE_FINE'   : 0,
            'A_CLKOUT4_PE_COARSE' : 0,
            'A_CLKOUT4_PE_FINE'   : 0,
            'A_CLKOUT5_PE_COARSE' : 0,
            'A_CLKOUT5_PE_FINE'   : 0,
            'A_CLKOUT6_PE_COARSE' : 0,
            'A_CLKOUT6_PE_FINE'   : 0,
            'A_DYN_PE0_SEL'       : 'FALSE',
            'A_DYN_PE1_SEL'       : 'FALSE',
            'A_DYN_PE2_SEL'       : 'FALSE',
            'A_DYN_PE3_SEL'       : 'FALSE',
            'A_DYN_PE4_SEL'       : 'FALSE',
            'A_DYN_PE5_SEL'       : 'FALSE',
            'A_DYN_PE6_SEL'       : 'FALSE',
            'A_DE0_EN'            : 'FALSE',
            'A_DE1_EN'            : 'FALSE',
            'A_DE2_EN'            : 'FALSE',
            'A_DE3_EN'            : 'FALSE',
            'A_DE4_EN'            : 'FALSE',
            'A_DE5_EN'            : 'FALSE',
            'A_DE6_EN'            : 'FALSE',
            'A_RESET_I_EN'        : 'FALSE',
            'A_RESET_O_EN'        : 'FALSE',
            'A_DYN_ICP_SEL'       : 'FALSE',
            'A_ICP_SEL'           : 0,
            'A_DYN_LPF_SEL'       : 'FALSE',
            'A_LPF_RES'           : 0,
            'A_LPF_CAP'           : 0,
            'A_SSC_EN'            : 0,
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

_default_plla_internal_attrs = {
            'A_RESET_EN'    : 'TRUE',
            'PWDEN'         : 'ENABLE',
            'PDN'           : 'ENABLE',
            'PLOCK'         : 'ENABLE',
            'FLOCK'         : 'ENABLE',
            'FLTOP'         : 'ENABLE',
            'A_GMC_SEL'     : 15,
            'A_CLKIN_SEL'   : 'CLKIN0',
            'FLDCOUNT'      : 32,
            'A_VR_EN'       : 'DISABLE',
            'A_DYN_DPA_EN'  : 'FALSE',
            'A_RESET_I_EN'  : 'FALSE',
            'A_RESET_O_EN'  : 'FALSE',
            'A_DYN_ICP_SEL' : 'FALSE',
            'A_DYN_LPF_SEL' : 'FALSE',
            'A_SSC_EN'      : 'FALSE',
            'A_CLKFBOUT_PE_COARSE' : 0,
            'A_CLKFBOUT_PE_FINE' : 0,
}

_default_adc_attrs = {
            'CLK_SEL'              : "0",
            'DIV_CTL'              : "0",
            'PHASE_SEL'            : "0",
            'UNK0'                 : "101",
            'ADC_EN_SEL'           : "0",
            'IBIAS_CTL'            : "1000",
            'UNK1'                 : "1",
            'UNK2'                 : "10000",
            'CHOP_EN'              : "1",
            'GAIN'                 : "100",
            'CAP_CTL'              : "0",
            'BUF_EN'               : "0",
            'CSR_VSEN_CTRL'        : "0",
            'CSR_ADC_MODE'         : "1",
            'CSR_SAMPLE_CNT_SEL'   : "0",
            'CSR_RATE_CHANGE_CTRL' : "0",
            'CSR_FSCAL'            : bin(730),
            'CSR_OFFSET'           : bin(1180),
}

def plla_attr_rename(attrs):
    new_attrs = {}
    for attr, val in attrs.items():
        if attr != 'FCLKIN':
            new_attrs['A_' + attr] = val
        else:
            new_attrs[attr] = val
    return new_attrs

def add_pll_default_attrs(attrs, default_attrs = _default_pll_inattrs):
    pll_inattrs = attrs.copy()
    for k, v in default_attrs.items():
        if k in pll_inattrs:
            continue
        pll_inattrs[k] = v
    return pll_inattrs

def add_adc_default_attrs(attrs, default_attrs = _default_adc_attrs):
    adc_inattrs = attrs.copy()
    for k, v in default_attrs.items():
        if k in adc_inattrs:
            continue
        adc_inattrs[k] = v
    return adc_inattrs

def set_adc_attrs(db, idx, attrs):
    attrs_upper(attrs)
    adc_inattrs = add_adc_default_attrs(attrs)

    # parse attrs
    adc_attrs = {}
    for attr, vl in adc_inattrs.items():
        val = int(vl, 2)
        if not attr.startswith('BUF_BK'):
            adc_attrs[attr] = val
        if attr == 'CLK_SEL':
            if val == 1:
                adc_attrs[attr] = 'CLK_CLK'
            continue
        if attr == 'DIV_CTL':
            if val:
                adc_attrs[attr] = 2**val
            continue
        if attr == 'PHASE_SEL':
            if val:
                adc_attrs[attr] = 'PHASE_180'
            continue
        if attr == 'ADC_EN_SEL':
            if val == 1:
                adc_attrs[attr] = 'ADC'
            continue
        if attr == 'UNK0':
            if val == 0:
                adc_attrs[attr] = 'DISABLE'
            else:
                adc_attrs[attr] = val
            continue
        if attr == 'UNK1':
            if val == 1:
                adc_attrs[attr] = 'OFF'
            continue
        if attr == 'UNK2':
            if val == 0:
                adc_attrs[attr] = 'DISABLE'
            continue
        if attr == 'IBIAS_CTL':
            if val == 0:
                adc_attrs[attr] = 'DISABLE'
            else:
                adc_attrs[attr] = val
            continue
        if attr == 'CHOP_EN':
            if val == 1:
                adc_attrs[attr] = 'ON'
            else:
                adc_attrs[attr] = 'UNKNOWN'
            continue
        if attr == 'GAIN':
            if val == 0:
                adc_attrs[attr] = 'DISABLE'
            else:
                adc_attrs[attr] = val
            continue
        if attr == 'CAP_CTL':
            adc_attrs[attr] = val
            continue
        if attr == 'BUF_EN':
            for i in range(12):
                if val & (2**i):
                    adc_attrs[f'BUF_{i}_EN'] = 'ON'
            del(adc_attrs[attr])
            continue
        if attr == 'CSR_ADC_MODE':
            if val == 1:
                adc_attrs[attr] = '1'
            else:
                adc_attrs[attr] = 'UNKNOWN'
            continue
        if attr == 'CSR_VSEN_CTRL':
            if val == 4:
                adc_attrs[attr] = 'UNK1'
            elif val == 7:
                adc_attrs[attr] = 'UNK0'
            continue
        if attr == 'CSR_SAMPLE_CNT_SEL':
            if val > 4:
               adc_attrs[attr] = 2048
            else:
               adc_attrs[attr] = (2**val) * 64
            continue
        if attr == 'CSR_RATE_CHANGE_CTRL':
            if val > 4:
                adc_attrs[attr] = 80
            else:
                adc_attrs[attr] = (2**val) * 4
            continue
        if attr == 'CSR_FSCAL':
            if val in range(452, 841):
                adc_attrs['CSR_FSCAL1'] = val
            adc_attrs['CSR_FSCAL0'] = val
            del(adc_attrs[attr])
            continue
        if attr == 'CSR_OFFSET':
            if val == 0:
                adc_attrs[attr] = 'DISABLE'
            else:
                if val & 1 << 11:
                    val -= 1 << 12;
                adc_attrs[attr] = val
            continue

    fin_attrs = set()
    #print(adc_attrs)
    for attr, val in adc_attrs.items():
        if isinstance(val, str):
            val = attrids.adc_attrvals[val]
        add_attr_val(db, 'ADC', fin_attrs, attrids.adc_attrids[attr], val)
    return fin_attrs

# typ - PLL type (RPLL, etc)
def set_pll_attrs(db, typ, idx, attrs):
    attrs_upper(attrs)
    if typ not in {'RPLL', 'PLLVR', 'PLLA'}:
        raise Exception(f"PLL type {typ} is not supported for now")
    if typ in {'RPLL', 'PLLVR'}:
        pll_inattrs = add_pll_default_attrs(attrs)
        pll_attrs = _default_pll_internal_attrs.copy()
    else:
        new_attrs = plla_attr_rename(attrs)
        pll_inattrs = add_pll_default_attrs(new_attrs, _default_plla_inattrs)
        pll_attrs = _default_plla_internal_attrs.copy()

    if typ == 'PLLVR':
        pll_attrs[['PLLVCC0', 'PLLVCC1'][idx]] = 'ENABLE'

    # parse attrs
    for attr, val in pll_inattrs.items():
        if attr in pll_attrs:
            pll_attrs[attr] = val
        if attr.startswith('A_CLKOUT') and attr[-3:] == '_EN':
            pll_attrs[attr] = val
            continue
        if attr.startswith('A_DYN_PE') and attr[-3:] == 'SEL':
            pll_attrs[attr] = val
            continue
        if attr.startswith('A_DE') and attr[-3:] == '_EN':
            pll_attrs[attr] = val
            continue
        if attr == 'A_CLKFB_SEL':
            if val == 'INTERNAL':
                pll_attrs[attr] = 'CLKFB2'
            continue
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
        if attr == 'A_IDIV_SEL':
            idiv = int(val, 2)
            pll_attrs['A_IDIV_SEL'] = idiv
            continue
        if attr == 'FBDIV_SEL':
            fbdiv = 1 + int(val, 2)
            pll_attrs['FDIV'] = fbdiv
            continue
        if attr == 'A_FBDIV_SEL':
            fbdiv = int(val, 2)
            pll_attrs['A_FBDIV_SEL'] = fbdiv
            continue
        if attr == 'DYN_SDIV_SEL':
            pll_attrs['SDIV'] = int(val, 2)
            continue
        if attr == 'ODIV_SEL':
            odiv = int(val, 2)
            pll_attrs['ODIV'] = odiv
            continue
        if attr == 'A_ODIV0_FRAC_SEL':
            odiv_frac = int(val, 2)
            pll_attrs['A_ODIV0_FRAC_SEL'] = odiv_frac
            continue
        if attr == 'A_ODIV0_SEL':
            odiv = int(val, 2)
            pll_attrs['A_ODIV0_SEL'] = odiv
            continue
        if attr == 'A_ODIV1_SEL':
            odiv = int(val, 2)
            pll_attrs['A_ODIV1_SEL'] = odiv
            continue
        if attr == 'A_ODIV2_SEL':
            odiv = int(val, 2)
            pll_attrs['A_ODIV2_SEL'] = odiv
            continue
        if attr == 'A_ODIV3_SEL':
            odiv = int(val, 2)
            pll_attrs['A_ODIV3_SEL'] = odiv
            continue
        if attr == 'A_ODIV4_SEL':
            odiv = int(val, 2)
            pll_attrs['A_ODIV4_SEL'] = odiv
            continue
        if attr == 'A_ODIV5_SEL':
            odiv = int(val, 2)
            pll_attrs['A_ODIV5_SEL'] = odiv
            continue
        if attr == 'A_ODIV6_SEL':
            odiv = int(val, 2)
            pll_attrs['A_ODIV6_SEL'] = odiv
            continue
        if attr == 'A_MDIV_SEL':
            mdiv = int(val, 2)
            pll_attrs['A_MDIV_SEL'] = mdiv
            continue
        if attr == 'A_MDIV_FRAC_SEL':
            mdiv_frac_sel = int(val, 2)
            pll_attrs['A_MDIV_FRAC_SEL'] = mdiv_frac_sel
            continue
        if attr == 'A_CLKOUT0_DT_DIR':
            dt_dir = int(val, 2)
            pll_attrs['A_CLKOUT0_DT_DIR'] = dt_dir
            continue
        if attr == 'A_CLKOUT1_DT_DIR':
            dt_dir = int(val, 2)
            pll_attrs['A_CLKOUT1_DT_DIR'] = dt_dir
            continue
        if attr == 'A_CLKOUT2_DT_DIR':
            dt_dir = int(val, 2)
            pll_attrs['A_CLKOUT2_DT_DIR'] = dt_dir
            continue
        if attr == 'A_CLKOUT3_DT_DIR':
            dt_dir = int(val, 2)
            pll_attrs['A_CLKOUT3_DT_DIR'] = dt_dir
            continue
        if attr == 'A_CLKOUT0_DT_STEP':
            dt_step = int(val, 2)
            pll_attrs['A_CLKOUT0_DT_STEP'] = dt_step
            continue
        if attr == 'A_CLKOUT1_DT_STEP':
            dt_step = int(val, 2)
            pll_attrs['A_CLKOUT1_DT_STEP'] = dt_step
            continue
        if attr == 'A_CLKOUT2_DT_STEP':
            dt_step = int(val, 2)
            pll_attrs['A_CLKOUT2_DT_STEP'] = dt_step
            continue
        if attr == 'A_CLKOUT3_DT_STEP':
            dt_step = int(val, 2)
            pll_attrs['A_CLKOUT3_DT_STEP'] = dt_step
            continue
        if attr == 'A_CLKIN0_SEL':
            a_clkin_sel= int(val, 2)
            pll_attrs['A_CLKIN0_SEL'] = a_clkin_sel
            continue
        if attr == 'A_CLKOUT0_SEL':
            a_clkout_sel= int(val, 2)
            pll_attrs['A_CLKOUT0_SEL'] = a_clkout_sel
            continue
        if attr == 'A_CLKIN1_SEL':
            a_clkin_sel= int(val, 2)
            pll_attrs['A_CLKIN1_SEL'] = a_clkin_sel
            continue
        if attr == 'A_CLKOUT1_SEL':
            a_clkout_sel= int(val, 2)
            pll_attrs['A_CLKOUT1_SEL'] = a_clkout_sel
            continue
        if attr == 'A_CLKIN2_SEL':
            a_clkin_sel= int(val, 2)
            pll_attrs['A_CLKIN2_SEL'] = a_clkin_sel
            continue
        if attr == 'A_CLKOUT2_SEL':
            a_clkout_sel= int(val, 2)
            pll_attrs['A_CLKOUT2_SEL'] = a_clkout_sel
            continue
        if attr == 'A_CLKIN3_SEL':
            a_clkin_sel= int(val, 2)
            pll_attrs['A_CLKIN3_SEL'] = a_clkin_sel
            continue
        if attr == 'A_CLKOUT3_SEL':
            a_clkout_sel= int(val, 2)
            pll_attrs['A_CLKOUT3_SEL'] = a_clkout_sel
            continue
        if attr == 'A_CLKIN4_SEL':
            a_clkin_sel= int(val, 2)
            pll_attrs['A_CLKIN4_SEL'] = a_clkin_sel
            continue
        if attr == 'A_CLKOUT4_SEL':
            a_clkout_sel= int(val, 2)
            pll_attrs['A_CLKOUT4_SEL'] = a_clkout_sel
            continue
        if attr == 'A_CLKIN5_SEL':
            a_clkin_sel= int(val, 2)
            pll_attrs['A_CLKIN5_SEL'] = a_clkin_sel
            continue
        if attr == 'A_CLKOUT5_SEL':
            a_clkout_sel= int(val, 2)
            pll_attrs['A_CLKOUT5_SEL'] = a_clkout_sel
            continue
        if attr == 'A_CLKIN6_SEL':
            a_clkin_sel= int(val, 2)
            pll_attrs['A_CLKIN6_SEL'] = a_clkin_sel
            continue
        if attr == 'A_CLKOUT6_SEL':
            a_clkout_sel= int(val, 2)
            pll_attrs['A_CLKOUT6_SEL'] = a_clkout_sel
            continue
        if attr == 'A_CLKOUT0_PE_COARSE':
            pe_coarse = int(val, 2)
            pll_attrs['A_CLKOUT0_PE_COARSE'] = pe_coarse
            continue
        if attr == 'A_CLKOUT0_PE_FINE':
            pe_fine = int(val, 2)
            pll_attrs['A_CLKOUT0_PE_FINE'] = pe_fine
            continue
        if attr == 'A_CLKOUT1_PE_COARSE':
            pe_coarse = int(val, 2)
            pll_attrs['A_CLKOUT1_PE_COARSE'] = pe_coarse
            continue
        if attr == 'A_CLKOUT1_PE_FINE':
            pe_fine = int(val, 2)
            pll_attrs['A_CLKOUT1_PE_FINE'] = pe_fine
            continue
        if attr == 'A_CLKOUT2_PE_COARSE':
            pe_coarse = int(val, 2)
            pll_attrs['A_CLKOUT2_PE_COARSE'] = pe_coarse
            continue
        if attr == 'A_CLKOUT2_PE_FINE':
            pe_fine = int(val, 2)
            pll_attrs['A_CLKOUT2_PE_FINE'] = pe_fine
            continue
        if attr == 'A_CLKOUT3_PE_COARSE':
            pe_coarse = int(val, 2)
            pll_attrs['A_CLKOUT3_PE_COARSE'] = pe_coarse
            continue
        if attr == 'A_CLKOUT3_PE_FINE':
            pe_fine = int(val, 2)
            pll_attrs['A_CLKOUT3_PE_FINE'] = pe_fine
            continue
        if attr == 'A_CLKOUT4_PE_COARSE':
            pe_coarse = int(val, 2)
            pll_attrs['A_CLKOUT4_PE_COARSE'] = pe_coarse
            continue
        if attr == 'A_CLKOUT4_PE_FINE':
            pe_fine = int(val, 2)
            pll_attrs['A_CLKOUT4_PE_FINE'] = pe_fine
            continue
        if attr == 'A_CLKOUT5_PE_COARSE':
            pe_coarse = int(val, 2)
            pll_attrs['A_CLKOUT5_PE_COARSE'] = pe_coarse
            continue
        if attr == 'A_CLKOUT5_PE_FINE':
            pe_fine = int(val, 2)
            pll_attrs['A_CLKOUT5_PE_FINE'] = pe_fine
            continue
        if attr == 'A_CLKOUT6_PE_COARSE':
            pe_coarse = int(val, 2)
            pll_attrs['A_CLKOUT6_PE_COARSE'] = pe_coarse
            continue
        if attr == 'A_CLKOUT6_PE_FINE':
            pe_fine = int(val, 2)
            pll_attrs['A_CLKOUT6_PE_FINE'] = pe_fine
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
    if device in {'GW5A-25A'}:
        # only static
        Fpfd = fclkin / idiv
        Fclkfb = Fpfd * fbdiv
        # XXX internal feedback for now
        Fvco = Fclkfb * mdiv
        fclkin_idx, icp, r_idx = calc_pll_pump(Fpfd, Fvco)
        pll_attrs['KVCO'] = fclkin_idx // 16
        if Fvco >= 1400.0:
            fclkin_idx += 1
        pll_attrs['A_ICP_SEL'] = int(icp)
        pll_attrs['A_LPF_RES_SEL'] = f"R{r_idx}"
    else:
        if pll_inattrs['DYN_IDIV_SEL'] == 'FALSE' and pll_inattrs['DYN_FBDIV_SEL'] == 'FALSE' and pll_inattrs['DYN_ODIV_SEL'] == 'FALSE':
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
        pll_attrs['ICPSEL'] = int(icp)
        pll_attrs['LPR'] = f"R{r_idx}"
    pll_attrs['FLDCOUNT'] = fclkin_idx

    fin_attrs = set()
    for i in range(16):
        add_attr_val(db, 'PLL', fin_attrs, i, 0)
    for attr, val in pll_attrs.items():
        if isinstance(val, str):
            val = attrids.pll_attrvals[val]
        add_attr_val(db, 'PLL', fin_attrs, attrids.pll_attrids[attr], val)
    return fin_attrs

_dcs_spine2quadrant_idx = {
        'SPINE6'  : ('1', 'DCS6'),
        'SPINE7'  : ('1', 'DCS7'),
        'SPINE14' : ('2', 'DCS6'),
        'SPINE15' : ('2', 'DCS7'),
        'SPINE22' : ('3', 'DCS6'),
        'SPINE23' : ('3', 'DCS7'),
        'SPINE30' : ('4', 'DCS6'),
        'SPINE31' : ('4', 'DCS7'),
        }
def set_dcs_attrs(db, spine, attrs):
    q, _ = _dcs_spine2quadrant_idx[spine]

    attrs_upper(attrs)
    dcs_attrs = {}
    dcs_attrs[q] = attrs['DCS_MODE']

    fin_attrs = set()
    for attr, val in dcs_attrs.items():
        if isinstance(val, str):
            val = attrids.dcs_attrvals[val]
        add_attr_val(db, 'DCS', fin_attrs, attrids.dcs_attrids[attr], val)
    return fin_attrs

_bsram_bit_widths = { 1: '1', 2: '2', 4: '4', 8: '9', 9: '9', 16: '16', 18: '16', 32: 'X36', 36: 'X36'}
def set_bsram_attrs(db, typ, params):
    bsram_attrs = {}
    bsram_attrs['MODE'] = 'ENABLE'
    bsram_attrs['GSR'] = 'DISABLE'

    attrs_upper(params)
    # We bring it into line with what is observed in the Gowin images - in the
    # ROM, port A has a signal CE = VCC and inversion is turned on on this pin.
    # We will provide VCC in nextpnr, and enable the inversion here.
    if typ == 'ROM':
        bsram_attrs['CEMUX_CEA'] = 'INV'

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
    #print(bsram_attrs)
    for attr, val in bsram_attrs.items():
        if isinstance(val, str):
            val = attrids.bsram_attrvals[val]
        add_attr_val(db, 'BSRAM', fin_attrs, attrids.bsram_attrids[attr], val)
    return fin_attrs

# MULTALU18X18
_ABLH = [('A', 'L'), ('A', 'H'), ('B', 'L'), ('B', 'H')]
_01LH = [(0, 'L'), (1, 'H')]
def set_multalu18x18_attrs(db, typ, params, num, attrs, dsp_attrs, mac):
    attrs_upper(attrs)
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
    attrs_upper(attrs)
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
    attrs_upper(attrs)
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
    attrs_upper(attrs)
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
    attrs_upper(attrs)
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
    attrs_upper(attrs)
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
    attrs_upper(attrs)
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
    attrs_upper(params)
    osc_attrs = dict()
    for param, val in params.items():
        if param == 'FREQ_DIV':
            fdiv = int(val, 2)
            if fdiv % 2 == 1:
                if fdiv == 3 and device in {'GW5A-25A'}:
                    fdiv = 0
                else:
                    raise Exception(f"Divisor of {typ} must be even")
            osc_attrs['MCLKCIB'] = fdiv
            osc_attrs['MCLKCIB_EN'] = "ENABLE"
            continue
        if param == 'REGULATOR_EN':
            reg = int(val, 2)
            if reg == 1:
                osc_attrs['OSCREG'] = "ENABLE"
            continue
    if typ not in {'OSCA'}:
        osc_attrs['NORMAL'] = "ENABLE"
    if typ not in {'OSC', 'OSCW'}:
        osc_attrs['USERPOWER_SAVE'] = 'ENABLE'

    fin_attrs = set()
    for attr, val in osc_attrs.items():
        if isinstance(val, str):
            val = attrids.osc_attrvals[val]
        add_attr_val(db, 'OSC', fin_attrs, attrids.osc_attrids[attr], val)
    return fin_attrs

def set_dlldly_attrs(db, typ, params, cell):
    attrs_upper(params)
    dlldly_attrs = dict()
    dlldly_attrs['DLL_INSEL'] = params.get('DLL_INSEL', "1")
    dlldly_attrs['DLY_SIGN'] = params.get('DLY_SIGN', "0")
    dlldly_attrs['DLY_ADJ'] = params.get('DLY_ADJ', "00000000000000000000000000000000")

    if dlldly_attrs['DLL_INSEL'] != '1':
        raise Exception(f"DLL_INSEL parameter values other than 1 are not supported")
    dlldly_attrs.pop('DLL_INSEL')
    dlldly_attrs['ENABLED'] = 'ENABLE'
    dlldly_attrs['MODE'] = 'NORMAL'

    if dlldly_attrs['DLY_SIGN'] == '1':
        dlldly_attrs['SIGN'] = 'NEG'
    dlldly_attrs.pop('DLY_SIGN')

    for i, ch in enumerate(dlldly_attrs['DLY_ADJ'][-1::-1]):
        if ch == '1':
            dlldly_attrs[f'ADJ{i}'] = '1'
    dlldly_attrs.pop('DLY_ADJ')

    fin_attrs = set()
    for attr, val in dlldly_attrs.items():
        if isinstance(val, str):
            val = attrids.dlldly_attrvals[val]
        add_attr_val(db, 'DLLDLY', fin_attrs, attrids.dlldly_attrids[attr], val)
    return fin_attrs

_wire2attr_val = {
        'HCLK_IN0': ('HSB0MUX0_HSTOP', 'HCLKCIBSTOP0'),
        'HCLK_IN1': ('HSB1MUX0_HSTOP', 'HCLKCIBSTOP2'),
        'HCLK_IN2': ('HSB0MUX1_HSTOP', 'HCLKCIBSTOP1'),
        'HCLK_IN3': ('HSB1MUX1_HSTOP', 'HCLKCIBSTOP3'),
        'HCLK_BANK_OUT0': ('BRGMUX0_BRGSTOP', 'BRGCIBSTOP0'),
        'HCLK_BANK_OUT1': ('BRGMUX1_BRGSTOP', 'BRGCIBSTOP1'),
        }
def find_and_set_dhcen_hclk_fuses(db, tilemap, wire, side):
    fin_attrs = set()
    attr, attr_val = _wire2attr_val[wire]
    val = attrids.hclk_attrvals[attr_val]
    add_attr_val(db, 'HCLK', fin_attrs, attrids.hclk_attrids[attr], val)

    def set_fuse():
        ttyp = db.grid[row][col].ttyp
        if 'HCLK' in db.shortval[ttyp]:
            bits = get_shortval_fuses(db, ttyp, fin_attrs, "HCLK")
            tile = tilemap[row, col]
            for r, c in bits:
                tile[r][c] = 1

    if side in "TB":
        if side == 'T':
            row = 0
        else:
            row = db.rows - 1
        for col in range(db.cols):
            set_fuse()
    else:
        if side == 'L':
            col = 0
        else:
            col = db.cols - 1
        for row in range(db.rows):
            set_fuse()

def bin_str_to_dec(str_val):
    bin_pattern = r'^[0,1]+'
    bin_str = re.findall(bin_pattern, str_val)
    if bin_str:
        dec_num = int(bin_str[0], 2)
        return str(dec_num)
    return None



_hclk_default_params ={"GSREN": "FALSE", "DIV_MODE":"2"}
def set_hclk_attrs(db, params, num, typ, cell_name):
    attrs_upper(params)
    name_pattern = r'^_HCLK([0,1])_SECT([0,1])$'
    params = dict(_hclk_default_params | params)
    attrs = {}
    pattern_match = re.findall(name_pattern, num)
    if (not pattern_match):
        raise Exception (f"Unknown HCLK Bel/HCLK Section: {typ}{num}")
    hclk_idx, section_idx = pattern_match[0]

    valid_div_modes = ["2", "3.5", "4", "5"]
    if device in ["GW1N-1S","GW1N-2","GW1NR-2","GW1NS-4","GW1NS-4C","GW1NSR-4",\
                       "GW1NSR-4C","GW1NSER-4C","GW1N-9","GW1NR-9", "GW1N-9C","GW1NR-9C","GW1N-1P5"]:
        valid_div_modes.append("8")

    if (params["DIV_MODE"]) not in valid_div_modes:
        bin_match = bin_str_to_dec(params["DIV_MODE"])
        if bin_match is None or bin_match not in valid_div_modes:
            raise Exception(f"Invalid DIV_MODE {bin_match or params['DIV_MODE']} for CLKDIV {cell_name} on device {device}")
        params["DIV_MODE"] = str(bin_match[0])

    if typ.startswith("CLKDIV2"):
        attrs[f"BK{section_idx}MUX{hclk_idx}_OUTSEL"] = "DIV2"
    elif typ.startswith("CLKDIV"):
        attrs[f"HCLKDIV{hclk_idx}_DIV"] = params["DIV_MODE"]
        if (section_idx == '1'):
            attrs[f"HCLKDCS{hclk_idx}_SEL"] = f"HCLKBK{section_idx}{hclk_idx}"

    fin_attrs = set()
    for attr, val in attrs.items():
        if isinstance(val, str):
            val = attrids.hclk_attrvals[val]
        add_attr_val(db, 'HCLK', fin_attrs, attrids.hclk_attrids[attr], val)
    return fin_attrs

_iologic_default_attrs = {
        'DUMMY': {},
        'IOLOGIC': {},
        'IOLOGIC_DUMMY': {},
        'IOLOGICI_EMPTY': {'GSREN': 'FALSE', 'LSREN': 'true'},
        'IOLOGICO_EMPTY': {'GSREN': 'FALSE', 'LSREN': 'true'},
        'ODDR': { 'TXCLK_POL': '0'},
        'ODDRC': { 'TXCLK_POL': '0'},
        'OSER4': { 'GSREN': 'FALSE', 'LSREN': 'true', 'TXCLK_POL': '0', 'HWL': 'false'},
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
    attrs_upper(attrs)
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

def make_iodelay_attrs(in_attrs, param):
    if 'IODELAY' not in param:
        return
    if param['IODELAY'] == 'IN':
        in_attrs['INDEL'] = 'ENABLE'
    else:
        in_attrs['OUTDEL'] = 'ENABLE'
    in_attrs['CLKOMUX'] = 'ENABLE'
    in_attrs['IMARG'] = 'ENABLE'
    in_attrs['INDEL_0'] = 'ENABLE'
    in_attrs['INDEL_1'] = 'ENABLE'
    if 'C_STATIC_DLY' not in in_attrs:
        return
    for i in range(1, 8):
        if in_attrs['C_STATIC_DLY'][-i] == '1':
            in_attrs[f'DELAY_DEL{i - 1}'] = '1'
    in_attrs.pop('C_STATIC_DLY', None);

def set_iologic_attrs(db, attrs, param):
    attrs_upper(attrs)
    in_attrs = _iologic_default_attrs[param['IOLOGIC_TYPE']].copy()
    in_attrs.update(attrs)
    iologic_mod_attrs(in_attrs)
    fin_attrs = set()
    if 'OUTMODE' in attrs:
        if param['IOLOGIC_TYPE'] == 'IOLOGICO_EMPTY':
            in_attrs.pop('OUTMODE', None);
        else:
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
            # in_attrs['LSRMUX_LSR'] = 'INV'

    if 'INMODE' in attrs:
        if param['IOLOGIC_TYPE'] == 'IOLOGICI_EMPTY':
            in_attrs.pop('INMODE', None);
        elif param['IOLOGIC_TYPE'] not in {'IDDR', 'IDDRC'}:
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
    make_iodelay_attrs(in_attrs, param);
    #print(in_attrs)

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
        'LVCMOS33': '3.3', 'LVDS25': '2.5', 'LVCMOS33D': '3.3', 'LVCMOS_D': '3.3', 'MIPI': '1.2',
        'SSTL15': '1.5', 'SSTL18_I': '1.8', 'SSTL18_II': '1.8', 'SSTL25_I': '2.5', 'SSTL25_II': '2.5', 'SSTL33_I': '3.3', 'SSTL33_II': '3.3',
        'SSTL15D': '1.5', 'SSTL18D_I': '1.8', 'SSTL18D_II': '1.8', 'SSTL25D_I': '2.5', 'SSTL25D_II': '2.5', 'SSTL33D_I': '3.3', 'SSTL33D_II': '3.3'}
_init_io_attrs = {
        'IBUF': {'PADDI': 'PADDI', 'HYSTERESIS': 'NONE', 'PULLMODE': 'UP', 'SLEWRATE': 'SLOW',
                 'DRIVE': '0', 'CLAMP': 'OFF', 'OPENDRAIN': 'OFF', 'DIFFRESISTOR': 'OFF',
                 'VREF': 'OFF', 'LVDS_OUT': 'OFF'},
        'OBUF': {'ODMUX_1': '1', 'PULLMODE': 'UP', 'SLEWRATE': 'FAST',
                 'DRIVE': '8', 'HYSTERESIS': 'NONE', 'CLAMP': 'OFF',
                 'SINGLERESISTOR': 'OFF', 'BANK_VCCIO': '1.8', 'LVDS_OUT': 'OFF', 'DDR_DYNTERM': 'NA', 'TO': 'INV', 'OPENDRAIN': 'OFF'},
        'TBUF': {'ODMUX_1': 'UNKNOWN', 'PULLMODE': 'UP', 'SLEWRATE': 'FAST',
                 'DRIVE': '8', 'HYSTERESIS': 'NONE', 'CLAMP': 'OFF',
                 'SINGLERESISTOR': 'OFF', 'BANK_VCCIO': '1.8', 'LVDS_OUT': 'OFF', 'DDR_DYNTERM': 'NA',
                 'TO': 'INV', 'PERSISTENT': 'OFF', 'ODMUX': 'TRIMUX', 'OPENDRAIN': 'OFF'},
        'IOBUF': {'ODMUX_1': 'UNKNOWN', 'PULLMODE': 'UP', 'SLEWRATE': 'FAST',
                 'DRIVE': '8', 'HYSTERESIS': 'NONE', 'CLAMP': 'OFF', 'DIFFRESISTOR': 'OFF',
                 'SINGLERESISTOR': 'OFF', 'BANK_VCCIO': '1.8', 'LVDS_OUT': 'OFF', 'DDR_DYNTERM': 'NA',
                 'TO': 'INV', 'PERSISTENT': 'OFF', 'ODMUX': 'TRIMUX', 'PADDI': 'PADDI', 'OPENDRAIN': 'OFF'},
        }
_refine_attrs = {'SLEW_RATE': 'SLEWRATE', 'PULL_MODE': 'PULLMODE', 'OPEN_DRAIN': 'OPENDRAIN'}
def refine_io_attrs(attr):
    return _refine_attrs.get(attr, attr)

def place_lut(db, tiledata, tile, parms, num, row, col, slice_attrvals):
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
    slice_attrvals.setdefault((row, col, int(num) // 2), {})

def place_alu(db, tiledata, tile, parms, num, row, col, slice_attrvals):
    lutmap = tiledata.bels[f'LUT{num}'].flags
    alu_bel = tiledata.bels[f"ALU{num}"]
    for r_c in lutmap.values():
        for r, c in r_c:
            tile[r][c] = 0
    # XXX Fix for bug in nextpnr 0.9, will be unnecessary with the next release.
    if "ALU_MODE" in parms and parms['ALU_MODE'] == "0 ":
        parms['RAW_ALU_LUT'] = "0011000011001100"
    # ALU_RAW_LUT - bits for ALU LUT init value, which are formed in nextpnr as
    # a result of optimization.
    if 'RAW_ALU_LUT' in parms:
        alu_init = parms['RAW_ALU_LUT']
        if len(alu_init) > 16:
            alu_init = alu_init[-16:]
        else:
            alu_init = alu_init*(16 // len(alu_init))
        bits = set()
        for bitnum, bit in enumerate(alu_init[::-1]):
            if bit == '0':
                bits.update(lutmap[bitnum])
    else:
        mode = str(parms['ALU_MODE'])
        if mode in alu_bel.modes:
            bits = alu_bel.modes[mode]
        else:
            bits = alu_bel.modes[str(int(mode, 2))]
    for r, c in bits:
        tile[r][c] = 1
    #print(row, col, num, bits)

    # enable ALU
    alu_mode_attrs = slice_attrvals.setdefault((row, col, int(num) // 2), {})
    alu_mode_attrs.update({'MODE': 'ALU'})
    alu_mode_attrs.update({f'MODE_5A_{int(num) % 2}': 'ALU'})

    if 'CIN_NETTYPE' in parms:
        if parms['CIN_NETTYPE'] == 'VCC':
            alu_mode_attrs.update({'ALU_CIN_MUX': 'ALU_5A_CIN_VCC'})
        elif parms['CIN_NETTYPE'] == 'GND':
            alu_mode_attrs.update({'ALU_CIN_MUX': 'ALU_5A_CIN_GND'})
        else:
            alu_mode_attrs.update({'ALU_CIN_MUX': 'ALU_5A_CIN_COUT'})
    elif 'ALU_CIN_MUX' not in alu_mode_attrs:
        alu_mode_attrs.update({'ALU_CIN_MUX': 'ALU_5A_CIN_COUT'})

def place_dff(db, tiledata, tile, parms, num, mode, row, col, slice_attrvals):
        dff_attrs = slice_attrvals.setdefault((row, col, int(num) // 2), {})
        dff_attrs.update({'REGMODE': 'FF'})
        # XXX always net for now
        dff_attrs.update({'CEMUX_1': 'UNKNOWN', 'CEMUX_CE': 'SIG'})
        # REG0_REGSET and REG1_REGSET select set/reset or preset/clear options for each DFF individually
        if mode in {'DFFR', 'DFFC', 'DFFNR', 'DFFNC', 'DFF', 'DFFN'}:
            dff_attrs.update({f'REG{int(num) % 2}_REGSET': 'RESET'})
        else:
            dff_attrs.update({f'REG{int(num) % 2}_REGSET': 'SET'})
        # are set/reset/clear/preset port needed?
        if mode not in {'DFF', 'DFFN'}:
            dff_attrs.update({'LSRONMUX': 'LSRMUX'})
        # invert clock?
        if mode in {'DFFN', 'DFFNR', 'DFFNC', 'DFFNP', 'DFFNS'}:
            dff_attrs.update({'CLKMUX_CLK': 'INV'})
        else:
            dff_attrs.update({'CLKMUX_CLK': 'SIG'})
        # async option?
        if mode in {'DFFNC', 'DFFNP', 'DFFC', 'DFFP'}:
            dff_attrs.update({'SRMODE': 'ASYNC'})

_mipi_aux_attrs = {
        'A': {('IO_TYPE', 'LVDS25'), ('LPRX_A2', 'ENABLE'), ('ODMUX', 'TRIMUX'), ('OPENDRAIN', 'OFF'),
              ('DIFFRESISTOR', 'OFF'), ('BANK_VCCIO', '2.5')},
        'B': {('IO_TYPE', 'LVDS25'), ('BANK_VCCIO', '2.5')},
}

_hclk_io_pairs = {(36, 11): (36, 30), (36, 25): (36, 32), (36, 53): (36, 28), (36, 74): (36, 90), }

_sides = "AB"

def set_dcs_fuses(db, tilemap, dcs_idx, dcs_attrs, spine_idx):
    dcs_name = f'DCS{dcs_idx + 6}'
    for row, rd in enumerate(db.grid):
        for col, rc in enumerate(rd):
            if rc.ttyp in db.longfuses and dcs_name in db.longfuses[rc.ttyp]:
                tile = tilemap[(row, col)]
                bits = get_long_fuses(db, rc.ttyp, dcs_attrs, spine_idx)
                for brow, bcol in bits:
                    tile[brow][bcol] = 1

def check_adc_io(db, io_loc):
    global adc_iolocs

    iore = re.compile(r"(\d+)/X(\d+)Y(\d+)")
    res = iore.fullmatch(io_loc)
    if not res:
        raise Exception(f"Bad IOLOC {ioloc} in the ADC src list.")
    adc_bus, io_col, io_row = res.groups()
    row = int(io_row)
    col = int(io_col)
    pin_bus = db.extra_func[row, col]['adcio']['bus']
    if pin_bus != f'BUS{adc_bus}':
        raise Exception(f"IO({row}, {col}) has ADC bus {pin_bus[-1]}, but used in bus {adc_bus}.")

    for pos, desc in adc_iolocs.items():
        if desc['bus'] == adc_bus and adc_bus in "01":
            raise Exception(f"IO at ({row}, {col}) and at ({pos[0]}, {pos[1]}) have same bus {adc_bus}. Only one IO in the one bus allowed.")

    adc = adc_iolocs.setdefault((row, col), {})
    adc['bus'] = adc_bus

def place(db, tilemap, bels, cst, args, slice_attrvals, extra_slots):
    global adc_ios
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

        if typ in {'IOLOGIC', 'IOLOGICI', 'IOLOGICO', 'IOLOGIC_DUMMY', 'ODDR', 'ODDRC', 'OSER4',
                   'OSER8', 'OSER10', 'OVIDEO', 'IDDR', 'IDDRC', 'IDES4', 'IDES8', 'IDES10', 'IVIDEO',
                   'IOLOGICI_EMPTY', 'IOLOGICO_EMPTY'}:
            if num[-1] in {'I', 'O'}:
                num = num[:-1]
            if typ == 'IOLOGIC_DUMMY':
                attrs['IOLOGIC_FCLK'] = pnr['modules']['top']['cells'][attrs['MAIN_CELL']]['attributes']['IOLOGIC_FCLK']
            attrs['IOLOGIC_TYPE'] = typ
            if typ not in {'IDDR', 'IDDRC', 'ODDR', 'ODDRC', 'IOLOGICI_EMPTY', 'IOLOGICO_EMPTY'}:
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
        elif typ == "BANDGAP":
            pass
        elif typ == "PINCFG":
            if args.i2c_as_gpio != ('I2C' in parms):
                raise Exception(f" i2c_as_gpio has conflicting settings in nexpnr and gowin_pack.")
            if args.sspi_as_gpio != ('SSPI' in parms):
                raise Exception(f" sspi_as_gpio has conflicting settings in nexpnr and gowin_pack.")
        elif typ.startswith("FLASH"):
            pass
        elif typ.startswith("EMCU"):
            pass
        elif typ.startswith('MUX2_'):
            pass
        elif typ.startswith("MIPI_OBUF"):
            pass
        elif typ.startswith("MIPI_IBUF_AUX"):
            for iob_idx in ['A', 'B']:
                iob_attrs = set()
                for k, val in _mipi_aux_attrs[iob_idx]:
                    add_attr_val(db, 'IOB', iob_attrs, attrids.iob_attrids[k], attrids.iob_attrvals[val])
                bits = get_longval_fuses(db, tiledata.ttyp, iob_attrs, f'IOB{iob_idx}')
                for row_, col_ in bits:
                    tile[row_][col_] = 1
            pass
        elif typ.startswith("MIPI_IBUF"):
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

        elif typ in {'OSC', 'OSCZ', 'OSCF', 'OSCH', 'OSCW', 'OSCO', 'OSCA'}:
            # XXX turn on (GW1NZ-1)
            if device == 'GW1NZ-1':
                en_tiledata = db.grid[db.rows - 1][db.cols - 1]
                en_tile = tilemap[(db.rows - 1, db.cols - 1)]
                en_tile[23][63] = 0
                en_tile[22][63] = 1
            # clear powersave fuses
            clear_attrs = set()
            add_attr_val(db, 'OSC', clear_attrs, attrids.osc_attrids['POWER_SAVE'], attrids.osc_attrvals['ENABLE'])
            bits = get_shortval_fuses(db, tiledata.ttyp, clear_attrs, 'OSC')
            for r, c in bits:
                tile[r][c] = 0

            osc_attrs = set_osc_attrs(db, typ, parms)
            if device in {'GW5A-25A'}:
                # set the fuses in all cells
                for row_col, func_desc in db.extra_func.items():
                    if 'osc' in func_desc or 'osc_fuses_only' in func_desc:
                        osc_row, osc_col = row_col
                        osc_tile = tilemap[osc_row, osc_col]
                        bits = get_shortval_fuses(db, db.grid[osc_row][osc_col].ttyp, osc_attrs, 'OSC')
                        #print(osc_row, osc_col, osc_attrs)
                        for r, c in bits:
                            osc_tile[r][c] = 1
            else:
                bits = get_shortval_fuses(db, tiledata.ttyp, osc_attrs, 'OSC')
                for r, c in bits:
                    tile[r][c] = 1

        elif typ.startswith("DFF"):
            mode = typ.strip('E')
            place_dff(db, tiledata, tile, parms, num, mode, row, col, slice_attrvals)
        elif typ.startswith('LUT'):
            place_lut(db, tiledata, tile, parms, num, row, col, slice_attrvals)

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
            if 'MIPI_IBUF' in parms and num == 'B':
                continue
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
                if parms['DIFF_TYPE'] == 'TLVDS_IBUF_ADC':
                    # ADC diff io
                    check_adc_io(db, f'2/X{col - 1}Y{row - 1}')
                    continue
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

            io_desc = IOBelDesc(row - 1, col - 1, num, {}, flags, cell['connections'])
            _io_bels.setdefault(bank, {})[bel_name] = io_desc

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
            if 'DIFF' in parms and 'MIPI_OBUF' in parms:
                io_desc.attrs['MIPI'] = 'ENABLE'
            if 'I3C_IOBUF' in parms:
                io_desc.attrs['I3C_IOBUF'] = 'ENABLE'
            if device in {'GW5A-25A'}:
                # mark clock ibuf
                if iob_is_connected_to_HCLK_GCLK(io_desc.connections):
                    # The GW5A-25A has an interesting phenomenon on the bottom
                    # side of the chip: if certain pins are used as a clock
                    # source (this also applies to the standard soldered E2)
                    # and the routing passes through HCLK, fuses are set not
                    # only in this IBUF, but also in another one. The purpose
                    # of this mechanism is unclear; we have only found a few
                    # such pins and are repeating this process.
                    if (row - 1, col - 1) in _hclk_io_pairs:
                        pair_row, pair_col = _hclk_io_pairs[row - 1, col - 1]
                        io_desc_pair = IOBelDesc(pair_row, pair_col, 'A', {}, flags.copy(), {})
                        _io_bels.setdefault(bank, {})[f'{bel_name}$pair'] = io_desc_pair
                        io_desc_pair.flags['HCLK_PAIR'] = True
                        io_desc_pair.attrs['IO_TYPE'] = iostd
                    io_desc.flags['HCLK'] = True
            if pinless_io:
                return
        elif typ.startswith("RAM16SDP") or typ == "RAMW":
            for idx in range(4):
                ram_attrs = slice_attrvals.setdefault((row, col, idx), {})
                ram_attrs.update({'MODE': 'SSRAM'})
            # In fact, the WRE signal is considered active when it is low, so
            # we include an inverter on the LSR2 line here to comply with the
            # documentation
            ram_attrs = slice_attrvals.setdefault((row, col, 2), {})
            ram_attrs.update({'LSRONMUX': 'LSRMUX'})
            ram_attrs.update({'LSR_MUX_LSR': 'INV'})
            ram_attrs.update({'CLKMUX_1': 'UNKNOWN'})
            ram_attrs.update({'CLKMUX_CLK': 'SIG'})
        elif typ ==  'IOLOGIC':
            #print(row, col, cellname)
            iologic_attrs = set_iologic_attrs(db, parms, attrs)
            bits = set()
            table_type = f'IOLOGIC{num}'
            bits = get_shortval_fuses(db, tiledata.ttyp, iologic_attrs, table_type)
            for r, c in bits:
                tile[r][c] = 1
        elif typ in _bsram_cell_types or typ == 'BSRAM_AUX':
            if typ == 'BSRAM_AUX':
                typ = cell['type']
            elif device in {'GW5A-25A'}:
                bisect.insort(gw5a_bsrams, (col - 1, row - 1, typ, parms, attrs))
            else:
                store_bsram_init_val(db, row - 1, col -1, typ, parms, attrs)
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

            #print(f'({row - 1}, {col - 1}) attrs:{dsp_attrs}, bits:{sorted(dspbits)}')
            for brow, bcol in dspbits:
                tile[brow][bcol] = 1
        elif typ.startswith('ADC'):
            # extract adc ios
            for attr, val in attrs.items():
                if attr.startswith('ADC_IO_'):
                    check_adc_io(db, val)

            # main grid cell
            adc_attrs = set_adc_attrs(db, 0, parms)
            bits = set()
            if 'ADC' in db.shortval[tiledata.ttyp]:
                bits = get_shortval_fuses(db, tiledata.ttyp, adc_attrs, 'ADC')
            #print(typ, tiledata.ttyp, bits)
            for r, c in bits:
                tile[r][c] = 1
            # slot
            bits = get_shortval_fuses(db, 1026, adc_attrs, 'ADC')
            slot_bitmap = extra_slots.setdefault(db.extra_func[row - 1, col - 1]['adc']['slot_idx'], bitmatrix.zeros(8, 6))
            #print(bits)
            for r, c in bits:
                slot_bitmap[r][c] = 1
            #for rd in slot_bitmap:
            #    print(rd)
        elif typ.startswith('RPLL'):
            pll_attrs = set_pll_attrs(db, 'RPLL', 0,  parms)
            bits = set()
            if 'PLL' in db.shortval[tiledata.ttyp]:
                bits = get_shortval_fuses(db, tiledata.ttyp, pll_attrs, 'PLL')
            #print(typ, tiledata.ttyp, bits)
            for r, c in bits:
                tile[r][c] = 1
        elif typ.startswith('PLLA'):
            pll_attrs = set_pll_attrs(db, 'PLLA', 0,  parms)
            bits = get_shortval_fuses(db, 1024, pll_attrs, 'PLL')
            slot_bitmap = extra_slots.setdefault(db.extra_func[row - 1, col - 1]['pll']['slot_idx'], bitmatrix.zeros(8, 35))
            for r, c in bits:
                slot_bitmap[r][c] = 1
            #for rd in slot_bitmap:
            #    print(rd)
        elif typ.startswith('ALU'):
            place_alu(db, tiledata, tile, parms, num, row, col, slice_attrvals)
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
        elif typ == 'DLLDLY':
            dlldly_attrs = set_dlldly_attrs(db, typ, parms, cell)
            for dlldly_row, dlldly_col in db.extra_func[row - 1, col -1]['dlldly_fusebels']:
                dlldly_tiledata = db.grid[dlldly_row][dlldly_col]
                dlldly_tile = tilemap[(dlldly_row, dlldly_col)]
                bits = get_long_fuses(db, dlldly_tiledata.ttyp, dlldly_attrs, f'DLLDEL{num}')
                for r, c in bits:
                    dlldly_tile[r][c] = 1
        elif typ == 'DHCEN':
            if 'DHCEN_USED' not in attrs:
                continue
            # DHCEN as such is just a control wire and does not have a fuse
            # itself, but HCLK has fuses that allow this control. Here we look
            # for the corresponding HCLK and set its fuses.
            _, wire, _, side = db.extra_func[row - 1, col -1]['dhcen'][int(num)]['pip']
            hclk_attrs = find_and_set_dhcen_hclk_fuses(db, tilemap, wire, side)
        elif typ.startswith("CLKDIV"):
            hclk_attrs = set_hclk_attrs(db, parms, num, typ, cellname)
            bits = get_shortval_fuses(db, tiledata.ttyp, hclk_attrs, "HCLK")
            for r, c in bits:
                tile[r][c] = 1
        elif typ == 'DQCE':
            # Himbaechel only
            pipre = re.compile(r"X(\d+)Y(\d+)/([\w_]+)/([\w_]+)")
            if 'DQCE_PIP' not in attrs:
                continue
            pip = attrs['DQCE_PIP']
            res = pipre.fullmatch(pip)
            if not res:
                raise Exception(f"Bad DQCE pip {pip} at {cellname}")
            pip_col, pip_row, dest, src = res.groups()
            pip_row = int(pip_row)
            pip_col = int(pip_col)

            pip_tiledata = db.grid[pip_row][pip_col]
            pip_tile = tilemap[(pip_row, pip_col)]
            bits = pip_tiledata.clock_pips[dest][src]
            for r, c in bits:
                pip_tile[r][c] = 1
        elif typ == 'DCS':
            if 'DCS_MODE' not in attrs:
                continue
            spine = db.extra_func[row - 1, col - 1]['dcs'][int(num)]['clkout']
            dcs_attrs = set_dcs_attrs(db, spine, attrs)
            _, idx = _dcs_spine2quadrant_idx[spine]
            if device in {'GW5A-25A'}:
                set_dcs_fuses(db, tilemap, int(num), dcs_attrs, idx)
            else:
                bits = get_long_fuses(db, tiledata.ttyp, dcs_attrs, idx)
                for r, c in bits:
                    tile[r][c] = 1
        else:
            print("unknown type", typ)

    # second IO pass
    for bank, ios in _io_bels.items():
        in_bank_attrs = {}
        # check IO standard
        vccio = None
        iostd = None
        for iob_name, iob in ios.items():
            # ADC IOs can't be used as gpio
            if (iob.pos[0], iob.pos[1]) in adc_iolocs:
                raise Exception(f"{iob_name} is ADC IO. Can't use it as GPIO.")

            # diff io can't be placed at simplified io
            if iob.pos[0] in db.simplio_rows:
                if iob.flags['mode'].startswith('ELVDS') or iob.flags['mode'].startswith('TLVDS'):
                    raise Exception(f"Differential IO cant be placed at special row {iob.pos[0]}")

            if iob.flags['mode'] in {'IBUF', 'IOBUF', 'TLVDS_IBUF', 'TLVDS_IOBUF', 'ELVDS_IBUF', 'ELVDS_IOBUF'}:
                iob.attrs['IO_TYPE'] = get_iostd_alias(iob.attrs['IO_TYPE'])
                if iob.attrs.get('SINGLERESISTOR', 'OFF') != 'OFF':
                    iob.attrs['DDR_DYNTERM'] = 'ON'
            if iob.flags['mode'] in {'OBUF', 'IOBUF', 'TLVDS_OBUF', 'TLVDS_IOBUF', 'TLVDS_TBUF', 'TLVDS_TBUF', 'ELVDS_OBUF', 'ELVDS_IOBUF'}:
                if iob.flags['mode'] in {'ELVDS_OBUF', 'ELVDS_IOBUF'}:
                    in_bank_attrs['BANK_VCCIO'] = '1.2'

                if 'BANK_VCCIO' in iob.attrs:
                    if iob.attrs['BANK_VCCIO'] != _vcc_ios[iob.attrs['IO_TYPE']]:
                        raise Exception(f"Conflict bank VCC at {iob_name}.")
                if not vccio:
                    if not iob.attrs['IO_TYPE'].startswith('LVDS'):
                        iostd = iob.attrs['IO_TYPE']
                        vccio = _vcc_ios[iostd]
                elif vccio != _vcc_ios[iob.attrs['IO_TYPE']] and not iob.attrs['IO_TYPE'].startswith('LVDS'):
                    snd_type = iob.attrs['IO_TYPE']
                    fst = [name for name, iob in ios.items() if iob.attrs['IO_TYPE'] == iostd][0]
                    snd = iob_name
                    raise Exception(f"Different IO standard for bank {bank}: {fst} sets {iostd}, {snd} sets {iob.attrs['IO_TYPE']}.")

        if not vccio:
            iostd = 'LVCMOS12'

        if 'BANK_VCCIO' not in in_bank_attrs:
            in_bank_attrs['BANK_VCCIO'] = _vcc_ios[iostd]

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
            in_iob_attrs['BANK_VCCIO'] = in_bank_attrs['BANK_VCCIO']
            #print(name, in_iob_attrs)

            # lvds
            if iob.flags['mode'] in {'TLVDS_OBUF', 'TLVDS_TBUF', 'TLVDS_IOBUF'}:
                in_iob_attrs.update({'LVDS_OUT': 'ON', 'ODMUX_1': 'UNKNOWN', 'ODMUX': 'TRIMUX',
                                     'SLEWRATE': 'FAST', 'PERSISTENT': 'OFF', 'DRIVE': '0', 'DIFFRESISTOR': 'OFF'})
            elif iob.flags['mode'] in {'ELVDS_OBUF', 'ELVDS_TBUF', 'ELVDS_IOBUF'}:
                in_iob_attrs.update({'ODMUX_1': 'UNKNOWN', 'ODMUX': 'TRIMUX',
                    'PERSISTENT': 'OFF', 'DIFFRESISTOR': 'OFF'})
                in_iob_attrs['IO_TYPE'] = get_iostd_alias(in_iob_attrs['IO_TYPE'])
            if iob.flags['mode'] in {'TLVDS_IBUF', 'ELVDS_IBUF'}:
                in_iob_attrs['ODMUX_1'] = 'UNKNOWN'
                in_iob_attrs.pop('BANK_VCCIO', None)
            if 'IO_TYPE' in in_iob_attrs and in_iob_attrs['IO_TYPE'] == 'MIPI':
                in_iob_attrs['LPRX_A1'] = 'ENABLE'
                in_iob_attrs.pop('SLEWRATE', None)
                in_iob_attrs.pop('BANK_VCCIO', None)
                in_iob_attrs['PULLMODE'] = 'NONE'
                in_iob_attrs['LVDS_ON'] = 'ENABLE'
                in_iob_attrs['IOBUF_MIPI_LP'] = 'ENABLE'
            if 'I3C_IOBUF' in in_iob_attrs:
                in_iob_attrs.pop('I3C_IOBUF', None)
                in_iob_attrs['PULLMODE'] = 'NONE'
                in_iob_attrs['OPENDRAIN'] = 'OFF'
                in_iob_attrs['OD'] = 'ENABLE'
                in_iob_attrs['DIFFRESISTOR'] = 'NA'
                in_iob_attrs['SINGLERESISTOR'] = 'NA'
                in_iob_attrs['DRIVE'] = '16'

            # XXX may be here do GW9 pins also
            if device == 'GW1N-1':
                if row == 5 and mode_for_attrs == 'OBUF':
                    in_iob_attrs['TO'] = 'UNKNOWN'
            if device not in {'GW1N-4', 'GW1NS-4'}:
                if mode[1:].startswith('LVDS') and in_iob_attrs['DRIVE'] != '0':
                    in_iob_attrs['DRIVE'] = 'UNKNOWN'
            in_iob_b_attrs = {}
            if 'IO_TYPE' in in_iob_attrs and in_iob_attrs['IO_TYPE'] == 'MIPI':
                in_iob_attrs['IO_TYPE'] = 'LVDS25'
                in_iob_b_attrs['IO_TYPE'] = 'LVDS25'
                in_iob_b_attrs['PULLMODE'] = 'NONE'
                in_iob_b_attrs['OPENDRAIN'] = 'OFF'
                in_iob_b_attrs['IOBUF_MIPI_LP'] = 'ENABLE'
                in_iob_b_attrs['PERSISTENT'] = 'OFF'
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
                    if k not in attrids.iob_attrids:
                        print(f'XXX IO: add {k} key handle')
                    else:
                        add_attr_val(db, 'IOB', iob_attrs, attrids.iob_attrids[k], attrids.iob_attrvals[val])
                        if k == 'LVDS_OUT' and val not in {'ENABLE', 'ON'}:
                            if device not in {'GW5A-25A'}:
                                continue
                        if k == 'IO_TYPE' and k in in_bank_attrs and in_bank_attrs[k].startswith('LVDS'):
                            continue
                        in_bank_attrs[k] = val
                fuse_row, fuse_col = (row, col)
                if device not in {'GW5A-25A'}:
                    bits = get_longval_fuses(db, tiledata.ttyp, iob_attrs, f'IOB{iob_idx}')
                else:
                    #print(row, col, f'mode:{mode_for_attrs}, idx:{iob_idx}')
                    if mode_for_attrs in {'OBUF', 'IOBUF'}:
                        iob_attrs.update({147}) # IOB_UNKNOWN51=TRIMUX
                    elif mode_for_attrs == 'IBUF':
                        if 'HCLK' in iob.flags:
                            iob_attrs.update({190}) # IOB_UNKNOWN67=263
                        elif 'HCLK_PAIR' in iob.flags:
                            iob_attrs.update({192}) # IOB_UNKNOWN67=266
                    # fuses may be in another cell
                    fuse_ttyp = tiledata.ttyp
                    off = tiledata.bels[f'IOB{iob_idx}'].fuse_cell_offset
                    if off:
                        fuse_row += off[0]
                        fuse_col += off[1]
                        fuse_ttyp = db.grid[fuse_row][fuse_col].ttyp
                    bits = get_longval_fuses(db, fuse_ttyp, iob_attrs, f'IOB{iob_idx}')

                tile = tilemap[(fuse_row, fuse_col)]
                for row_, col_ in bits:
                    tile[row_][col_] = 1
                if idx == 'B':
                    break
                if not lvds_attrs:
                    break

        # bank bits
        brow, bcol = db.bank_tiles[bank]
        tiledata = db.grid[brow][bcol]

        bank_attrs = set()
        for k, val in in_bank_attrs.items():
            if k not in attrids.iob_attrids:
                print(f'XXX BANK: add {k} key handle')
            else:
                if k in {'BANK_VCCIO', 'IO_TYPE', 'LVDS_OUT', 'DRIVE', 'OPENDRAIN'}:
                    add_attr_val(db, 'IOB', bank_attrs, attrids.iob_attrids[k], attrids.iob_attrvals[val])

        bits = get_bank_fuses(db, tiledata.ttyp, bank_attrs, 'BANK', int(bank))
        bits.update(get_bank_io_fuses(db, tiledata.ttyp, bank_attrs))

        btile = tilemap[(brow, bcol)]
        for row, col in bits:
            btile[row][col] = 1

    #for k, v in _io_bels.items():
    #    for io, bl in v.items():
    #        print(k, io, vars(bl))


# hclk interbank requires to set some non-route fuses
def do_hclk_banks(db, row, col, src, dest):
    res = set()
    if dest in {'HCLK_BANK_OUT0', 'HCLK_BANK_OUT1'}:
        fin_attrs = set()
        add_attr_val(db, 'HCLK', fin_attrs, attrids.hclk_attrids[f'BRGMUX{dest[-1]}_BRGOUT'], attrids.hclk_attrvals['ENABLE'])

        ttyp = db.grid[row][col].ttyp
        if 'HCLK' in db.shortval[ttyp]:
            res = get_shortval_fuses(db, ttyp, fin_attrs, "HCLK")
    return res

def route(db, tilemap, pips):
    # The mux for clock wires can be "spread" across several cells. Here we determine whether pip is such a candidate.
    def is_clock_pip(src, dest):
        if src not in wnames.clknumbers:
            return False
        if dest not in wnames.clknumbers:
            return False
        if device in {'GW5A-25A'}:
            return wnames.clknumbers[src] < wnames.clknumbers['UNK212'] \
                    or wnames.clknumbers[src] in range(wnames.clknumbers['MPLL4CLKOUT0'], wnames.clknumbers['UNK569'] + 1)
        # XXX for future
        return wnames.clknumbers[src] < wnames.clknumbers['P10A']

    used_spines = set() # We don't know exactly where and how many fuses there
                        # are to allow the use of a particular spine, so we check each cell for
                        # potential fuses.

    def set_clock_fuses(row, col, src, dest):
        # SPINE->{GT00, GT10} must be set in the cell only
        if dest in {'GT00', 'GT10'}:
            bits = db.grid[row - 1][col - 1].clock_pips[dest][src]
            tile = tilemap[(row - 1, col - 1)]
            for brow, bcol in bits:
                tile[brow][bcol] = 1
            return

        spine_enable_table = None
        if dest.startswith('SPINE') and dest not in used_spines:
            used_spines.update({dest})
            spine_enable_table = f'5A_PCLK_ENABLE_{wnames.clknumbers[dest]:02}'

        for row, rd in enumerate(db.grid):
            for col, rc in enumerate(rd):
                bits = set()
                if dest in rc.clock_pips:
                    if src in rc.clock_pips[dest]:
                        bits = rc.clock_pips[dest][src]
                if spine_enable_table in db.shortval[rc.ttyp] and (1, 0) in db.shortval[rc.ttyp][spine_enable_table]:
                    bits.update(db.shortval[rc.ttyp][spine_enable_table][(1, 0)]) # XXX find the meaning
                if bits:
                    tile = tilemap[(row, col)]
                    for brow, bcol in bits:
                        tile[brow][bcol] = 1

    for row, col, src, dest in pips:
        if device in {'GW5A-25A'} and is_clock_pip(src, dest):
            set_clock_fuses(row, col, src, dest)
            continue

        tiledata = db.grid[row-1][col-1]
        tile = tilemap[(row-1, col-1)]

        try:
            # XXX consider use set_clock_fuses
            if device not in {'GW5A-25A'} and dest in tiledata.clock_pips:
                bits = tiledata.clock_pips[dest][src]
            elif (row - 1, col - 1) in db.hclk_pips and dest in db.hclk_pips[row - 1, col - 1] and src in db.hclk_pips[row - 1, col - 1][dest]:
                bits = db.hclk_pips[row - 1, col - 1][dest][src]
                bits.update(do_hclk_banks(db, row - 1, col - 1, src, dest))
            else:
                bits = tiledata.pips[dest][src]
                # check if we have 'not conencted to' situation
                if dest in tiledata.alonenode:
                    for srcs_fuses in tiledata.alonenode[dest]:
                        srcs, fuses = srcs_fuses
                        if src not in srcs:
                            bits |= fuses
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
    # set the checksum
    db.cmd_ftr[1] = bytearray.fromhex(f"{0x0A << 56 | checksum:016x}")
    if device in {'GW5A-25A'}:
        db.cmd_ftr.insert(1, bytearray(b'\x68\x00\x00\x00\x00\x00\x00\x00'))

def gsr(db, tilemap, args):
    gsr_attrs = set()
    for k, val in {'GSRMODE': 'ACTIVE_LOW'}.items():
        if k not in attrids.gsr_attrids:
            print(f'XXX GSR: add {k} key handle')
        else:
            add_attr_val(db, 'GSR', gsr_attrs, attrids.gsr_attrids[k], attrids.gsr_attrvals[val])

    cfg_attrs = set()
    cfg_function = 'F0'
    if device in {'GW5A-25A'}:
        cfg_function = 'F1'
    for k, val in {'GSR': 'USED', 'GOE': cfg_function}.items():
        if k not in attrids.cfg_attrids:
            print(f'XXX CFG GSR: add {k} key handle')
        else:
            add_attr_val(db, 'CFG', cfg_attrs, attrids.cfg_attrids[k], attrids.cfg_attrvals[val])
    add_attr_val(db, 'CFG', cfg_attrs, attrids.cfg_attrids['GSR'], attrids.cfg_attrvals[cfg_function])
    add_attr_val(db, 'CFG', cfg_attrs, attrids.cfg_attrids['DONE'], attrids.cfg_attrvals[cfg_function])
    add_attr_val(db, 'CFG', cfg_attrs, attrids.cfg_attrids['GWD'], attrids.cfg_attrvals[cfg_function])

    # The configuration fuses are described in the ['shortval'][60] table, global set/reset is
    # described in the ['shortval'][20] table. Look for cells with type with these tables
    gsr_type = {50, 83}
    cfg_type = {50, 51}
    if device in {'GW2A-18', 'GW2A-18C'}:
        gsr_type = {1, 83}
        cfg_type = {1, 51}
    elif device in {'GW5A-25A'}:
        gsr_type = {49, 83}
        cfg_type = {49, 51}
    elif device in {'GW5AST-138C'}:
        gsr_type = {220}
        cfg_type = {220}

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
            'DONE_AS_GPIO': 'UNKNOWN', 'RECONFIG_AS_GPIO': 'UNKNOWN', 'READY_AS_GPIO': 'UNKNOWN',
                 'CPU_AS_GPIO': 'UNKNOWN', 'I2C_AS_GPIO': 'UNKNOWN'}
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
    if args.cpu_as_gpio:
        pin_flags['CPU_AS_GPIO'] = 'YES'
    if args.i2c_as_gpio:
        pin_flags['I2C_AS_GPIO'] = 'YES'

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
    elif device in {'GW5A-25A'}:
        cfg_type = {49, 51}
    elif device in {'GW5AST-138C'}:
        cfg_type = {220}

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

def set_const_fuses(db, row, col, tile):
    tiledata = db.grid[row][col]
    if tiledata.ttyp in db.const:
        for bits in db.const[tiledata.ttyp]:
            brow, bcol = bits
            tile[brow][bcol] = 1

def set_adc_iobuf_fuses(db, tilemap):
    for ioloc in adc_iolocs.keys():
        row, col = ioloc
        bus = adc_iolocs[ioloc]['bus']
        tiledata = db.grid[row][col]
        # A
        attrs = {}
        if bus not in '01':
            attrs['IOB_GW5_ADC_DYN_IN'] = 'ENABLE'
            attrs['IOB_UNKNOWN70'] = 'UNKNOWN'
            attrs['IOB_UNKNOWN71'] = 'UNKNOWN'
        attrs['IO_TYPE'] = 'GW5_ADC_IN'
        attrs['IOB_GW5_ADC_IN'] = 'ENABLE'
        attrs['PULLMODE'] = 'NONE'
        attrs['HYSTERESIS'] = 'NONE'
        attrs['CLAMP'] = 'OFF'
        attrs['OPENDRAIN'] = 'OFF'
        attrs['DDR_DYNTERM'] = 'NA'
        attrs['IO_BANK'] = 'NA'
        attrs['PADDI'] = 'PADDI'
        attrs['IOB_GW5_PULL_50'] = 'NONE'
        attrs['IOB_GW5_VCCX_64'] = '3.3'

        io_attrs = set()
        for k, val in attrs.items():
            add_attr_val(db, 'IOB', io_attrs, attrids.iob_attrids[k], attrids.iob_attrvals[val])

        bits = get_longval_fuses(db, tiledata.ttyp, io_attrs, 'IOBA')
        tile = tilemap[(row, col)]
        for row_, col_ in bits:
            tile[row_][col_] = 1

        # B
        if tiledata.bels['IOBB'].fuse_cell_offset:
            row += tiledata.bels['IOBB'].fuse_cell_offset[0]
            col += tiledata.bels['IOBB'].fuse_cell_offset[1]
            tiledata = db.grid[row][col]

        attrs = {}
        if bus in '01':
            attrs['IOB_UNKNOWN60'] = 'ON'
            attrs['IOB_UNKNOWN61'] = 'ON'
        else:
            attrs['IOB_GW5_ADC_DYN_IN'] = 'ENABLE'
            attrs['IOB_UNKNOWN70'] = 'UNKNOWN'
            attrs['IOB_UNKNOWN71'] = 'UNKNOWN'
        attrs['IO_TYPE'] = 'GW5_ADC_IN'
        attrs['IOB_GW5_ADC_IN'] = 'ENABLE'
        attrs['PULLMODE'] = 'NONE'
        attrs['HYSTERESIS'] = 'NONE'
        attrs['CLAMP'] = 'OFF'
        attrs['OPENDRAIN'] = 'OFF'
        attrs['DDR_DYNTERM'] = 'NA'
        attrs['IO_BANK'] = 'NA'
        attrs['PADDI'] = 'PADDI'
        attrs['IOB_GW5_PULL_50'] = 'NONE'
        attrs['IOB_GW5_VCCX_64'] = '3.3'

        io_attrs = set()
        for k, val in attrs.items():
            add_attr_val(db, 'IOB', io_attrs, attrids.iob_attrids[k], attrids.iob_attrvals[val])

        bits = get_longval_fuses(db, tiledata.ttyp, io_attrs, 'IOBB')
        tile = tilemap[(row, col)]
        for row_, col_ in bits:
            tile[row_][col_] = 1

# set fuse for entire slice
def set_slice_fuses(db, tilemap, slice_attrvals):
    for pos, attrvals in slice_attrvals.items():
        row, col, num = pos
        if 'MODE' in attrvals and attrvals['MODE'] == 'SSRAM':
            attrvals.update({'REG0_REGSET': 'UNKNOWN'})
            attrvals.update({'REG1_REGSET': 'UNKNOWN'})
        elif 'REGMODE' not in attrvals:
            attrvals.update({'LSRONMUX': '0'})
            attrvals.update({'CLKMUX_1': '1'})
        if 'REG0_REGSET' not in attrvals:
            attrvals.update({'REG0_REGSET': 'RESET'})
        if 'REG1_REGSET' not in attrvals:
            attrvals.update({'REG1_REGSET': 'RESET'})
        if num == 0 and 'ALU_CIN_MUX' not in attrvals:
            attrvals.update({'ALU_CIN_MUX': 'ALU_5A_CIN_COUT'})

        av = set()
        for attr, val in attrvals.items():
            add_attr_val(db, 'SLICE', av, attrids.cls_attrids[attr], attrids.cls_attrvals[val])

        if f'CLS{num}' in db.shortval[db.grid[row - 1][col - 1].ttyp]:
            #print(f"slice ({row - 1}, {col - 1}), {num}, {attrvals}, {av}")
            bits = get_shortval_fuses(db, db.grid[row - 1][col - 1].ttyp, av, f'CLS{num}')
            tile = tilemap[(row - 1, col - 1)]
            for brow, bcol in bits:
                tile[brow][bcol] = 1

def main():
    global device
    global pnr
    global bsram_init_map

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
    parser.add_argument('--jtag_as_gpio', action = 'store_true')
    parser.add_argument('--sspi_as_gpio', action = 'store_true')
    parser.add_argument('--mspi_as_gpio', action = 'store_true')
    parser.add_argument('--ready_as_gpio', action = 'store_true')
    parser.add_argument('--done_as_gpio', action = 'store_true')
    parser.add_argument('--reconfign_as_gpio', action = 'store_true')
    parser.add_argument('--cpu_as_gpio', action = 'store_true')
    parser.add_argument('--i2c_as_gpio', action = 'store_true')
    if pil_available:
        parser.add_argument('--png')

    args = parser.parse_args()
    device = args.device

    with open(args.netlist) as f:
        pnr = json.load(f)

    # check for new P&R
    if pnr['modules']['top']['settings'].get('packer.arch', '') != 'himbaechel/gowin':
        raise Exception("Only files made with nextpnr-himbaechel are supported.")

    # For tool integration it is allowed to pass a full part number
    m = re.match("(GW..)(S|Z)?[A-Z]*-(LV|UV|UX)([0-9]{1,2})C?([A-Z]{2}[0-9]+P?)(C[0-9]/I[0-9])", device)
    if m:
        series = m.group(1)
        mods = m.group(2) or ""
        num = m.group(4)
        device = f"{series}{mods}-{num}"

    with importlib.resources.path('apycula', f'{device}.pickle') as path:
        with closing(gzip.open(path, 'rb')) as f:
            db = pickle.load(f)

    wnames.select_wires(device)
    if not args.sspi_as_gpio and device in {'GW5A-25A'}:
        # must be always on
        print('Warning. For GW5A-25A SSPI must be set as GPIO.')
        args.sspi_as_gpio = True

    const_nets = {'GND': '$PACKER_GND', 'VCC': '$PACKER_GND'}

    _gnd_net = pnr['modules']['top']['netnames'].get(const_nets['GND'], {'bits': []})['bits']
    _vcc_net = pnr['modules']['top']['netnames'].get(const_nets['VCC'], {'bits': []})['bits']

    tilemap = chipdb.tile_bitmap(db, bitmatrix.zeros(db.height, db.width), empty=True)
    extra_slots = {}

    cst = codegen.Constraints()
    pips = get_pips(pnr)
    route(db, tilemap, pips)
    isolate_segments(pnr, db, tilemap)
    bels = get_bels(pnr)
    gsr(db, tilemap, args)
    # LUT/RAM/ALU/DFF use shortval[][CLS0/1/2/3]
    # Their fuses corresponding to attributes can be set independently, but the
    # problem arises with default attributes, i.e., those whose fuses are set
    # if the corresponding attributes are "NOT SPECIFIED". Naturally, in this
    # case, the default fuses for DFF will be set when, for example, fuses for
    # ALU are being processed, simply because ALU does not have attributes
    # specified for DFF.
    # Therefore, we will set fuses for attributes for the entire slice after we
    # figure out which DFF/LUT/ALU/RAM fall into it.
    # {(row, col, idx): {attr:val, attr:val}}
    slice_attrvals = {}
    # routing can add pass-through LUTs
    place(db, tilemap, itertools.chain(bels, _pip_bels) , cst, args, slice_attrvals, extra_slots)
    set_slice_fuses(db, tilemap, slice_attrvals)
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

    set_adc_iobuf_fuses(db, tilemap)

    for row in range(db.rows):
        for col in range(db.cols):
            set_const_fuses(db, row, col, tilemap[(row, col)])
    main_map = chipdb.fuse_bitmap(db, tilemap)

    if pil_available and args.png:
        bslib.display(args.png, main_map)

    if device in {'GW5A-25A'}:
        main_map = bitmatrix.transpose(main_map)

    header_footer(db, main_map, args.compress)

    if device in {'GW5A-25A'} and gw5a_bsrams:
        # In the series preceding GW5A, the data for initialising BSRAM was
        # specified as one huge array describing all BSRAM primitives at once.
        # As a result, this array was unloaded immediately after the main grid
        # without any identifying marks.
        # In the GW5A series, the approach is different: only data for those
        # primitives that are actually used is unloaded.
        # This requires the use of commands describing BSRAM positions in the
        # output file. When testing file generation using Gowin IDE and setting
        # BSRAM positions as specified in the documentation for the GW5A series
        # (SUG1018-1.7E_Arora Ⅴ Design Physical Constraints User Guide. pdf),
        # it was found that the number of blocks in the output file describing
        # BSRAM is not proportional to the number of primitives used — that is,
        # one command lock describes several primitives located next to each
        # other, and another block begins only if there is a gap in the BSRAM
        # location.
        # Thus, for the GW5A series, we first need to collect data on the
        # location of BSRAM primitives, and only then proceed directly to
        # encoding the initialisation data.
        #import ipdb; ipdb.set_trace()
        last_col = -1
        map_offset = -1
        for bsram in gw5a_bsrams:
            col, row, typ, parms, attrs = bsram
            if col != last_col:
                last_col = col
                map_offset += 1
            store_bsram_init_val(db, row, col, typ, parms, attrs, map_offset)

        bsram_init_map = bitmatrix.transpose(bsram_init_map)
        bslib.write_bitstream(args.output, main_map, db.cmd_hdr, db.cmd_ftr, args.compress, extra_slots, bsram_init_map, gw5a_bsrams)
    elif bsram_init_map:
        bslib.write_bitstream_with_bsram_init(args.output, main_map, db.cmd_hdr, db.cmd_ftr, args.compress, extra_slots, bsram_init_map)
    else:
        bslib.write_bitstream(args.output, main_map, db.cmd_hdr, db.cmd_ftr, args.compress, extra_slots)

    if args.cst:
        with open(args.cst, "w") as f:
                cst.write(f)

if __name__ == '__main__':
    main()

# vim: set et sw=4 ts=4:
