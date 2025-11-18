import sys
import os
import re
import random
from itertools import chain, count
import pickle
import gzip
import argparse
import importlib.resources
from contextlib import closing
from apycula import codegen
from apycula import chipdb
from apycula import attrids
from apycula.bslib import read_bitstream, display

_device = ""
_pinout = ""
_packages = {
        'GW1N-1' : 'LQFP144', 'GW1NZ-1' : 'QFN48', 'GW1N-4' : 'PBGA256', 'GW1N-9C' : 'UBGA332',
        'GW1N-9' : 'PBGA256', 'GW1NS-4' : 'QFN48P', 'GW1NS-2' : 'LQFP144', 'GW2A-18': 'PBGA256',
        'GW2A-18C' : 'PBGA256S', 'GW5A-25A' : 'MBGA121N'
}

def print_sorted_dict(start, d):
    print(start, end='{')
    for i in sorted(d):
        print(f'{i}:{d[i]}, ', end='')
    print('}')

# bank iostandards
# XXX default io standard may be board-dependent!
_banks = {'0': "LVCMOS18", '1': "LVCMOS18", '2': "LVCMOS18", '3': "LVCMOS18"}

# bank fuse tables. They are created here from the standard 'longval' because for
# banks the key of these tables starts with the bank number and unpack is not
# called so often that one can make 'right' tables on the fly.
_bank_fuse_tables = {}

# for a given mode returns a mask of zero bits
def zero_bits(mode, all_modes):
    res = set()
    for m, m_rec in all_modes.items():
        if m == mode:
            continue
        res.update(m_rec.decode_bits)
        for flag in m_rec.flags.values():
            res.update(flag.mask)
    m_mask = set()
    for flag in all_modes[mode].flags.values():
        m_mask.update(flag.mask)
    return res.difference(all_modes[mode].decode_bits).difference(m_mask)

# If the length of the bit pattern is equal, start the comparison with IOBUF
def _io_mode_sort_func(mode):
    l = len(mode[1].decode_bits) * 10
    if mode[0] == 'IOBUF':
        l += 2
    elif mode[0] == 'OBUF':
        l += 1
    return l

#
def get_attr_name(attrname_table, code, tableName):
    for name, cod in attrname_table.items():
        if cod == code:
            return name
    print(f'Unknown attr name for table: {tableName} code:{code}')
    return ''

# fix names and types of the PLL attributes
# { internal_name: external_name }
_pll_attrs = {
        'IDIV' :            'IDIV_SEL',
        'IDIVSEL' :         'DYN_IDIV_SEL',
        'FDIV' :            'FBDIV_SEL',
        'FDIVSEL' :         'DYN_FBDIV_SEL',
        'ODIV' :            'ODIV_SEL',
        'ODIVSEL' :         'DYN_ODIV_SEL',
        'PHASE' :           'PSDA_SEL',
        'DUTY' :            'DUTYDA_SEL',
        'DPSEL' :           'DYN_DA_EN',

        'OPDLY' :           'CLKOUT_DLY_STEP',

        'OSDLY' :           'CLKOUTP_DLY_STEP',
        'SDIV' :            'DYN_SDIV_SEL',

        'CLKOUTDIVSEL' :    'CLKOUTD_SRC',
        'CLKOUTDIV3SEL' :   'CLKOUTD3_SRC',
        'BYPCK' :           'CLKOUT_BYPASS',
        'BYPCKPS' :         'CLKOUTP_BYPASS',
        'BYPCKDIV' :        'CLKOUTD_BYPASS',
        }

_pll_vals = {
        'DYN' :             'true',
        'CLKOUTPS' :        'CLKOUTP',
        'BYPASS' :          'true',
        }
def pll_attrs_refine(in_attrs):
    res = set()
    for attr, val in in_attrs.items():
        #print(attr, val)
        if attr not in _pll_attrs.keys():
            if attr in ['INSEL', 'FBSEL', 'PWDEN', 'RSTEN', 'CLKOUTDIV3', 'CLKOUTPS']:
                res.add(f'{attr}="{[ name for name, vl in attrids.pll_attrvals.items() if vl == val ][0]}"')
            continue
        attr = _pll_attrs[attr]
        if attr in ['CLKOUTP_DLY_STEP', 'CLKOUT_DLY_STEP']:
            new_val = val / 50
        elif attr in ['PSDA_SEL', 'DUTYDA_SEL']:
            new_val = f'"{val:04b}"'
        elif attr in ['IDIV_SEL', 'FBDIV_SEL']:
            new_val = val - 1
        elif attr in ['DYN_SDIV_SEL', 'ODIV_SEL']:
            new_val = val
        else:
            attrvals = [ name for name, vl in attrids.pll_attrvals.items() if vl == val ]
            if not attrvals:
                raise Exception(f"PLL no {attr} = {val}")
            if attrvals[0] in _pll_vals.keys():
                new_val = _pll_vals[attrvals[0]]
            new_val = f'"{new_val}"'
        res.add(f'{attr}={new_val}')
    return res

_osc_attrs = {
        'MCLKCIB': 'FREQ_DIV',
        'OSCREG': 'REGULATOR_EN'
}

def osc_attrs_refine(in_attrs):
    res = set()
    for attr, val in in_attrs.items():
        if attr not in _osc_attrs.keys():
            continue
        attr = _osc_attrs[attr]
        if attr == 'FREQ_DIV':
            new_val = val
        else:
            attrvals = [ name for name, vl in osc_attrvals.items() if vl == val ]
            if attrvals[0] in osc_attrvals.keys():
                new_val = attrvals[0]
            new_val = f'"{new_val}"'
        res.add(f'{attr}={new_val}')
    if 'MCLKCIB' not in in_attrs.keys() and 'MCLKCIB_EN' in in_attrs.keys():
        res.add('FREQ_DIV=128')
    return res

# {(REGSET, LSRONMUX, CLKMUX_CLK, SRMODE) : dff_type}
_dff_types = {
   ('RESET', '',       'SIG', '') :      'DFF',
   ('RESET', '',       'INV', '') :      'DFFN',
   ('RESET', 'LSRMUX', 'SIG', 'ASYNC') : 'DFFC',
   ('RESET', 'LSRMUX', 'INV', 'ASYNC') : 'DFFNC',
   ('RESET', 'LSRMUX', 'SIG', '') :      'DFFR',
   ('RESET', 'LSRMUX', 'INV', '') :      'DFFNR',
   ('SET',   'LSRMUX', 'SIG', 'ASYNC') : 'DFFP',
   ('SET',   'LSRMUX', 'INV', 'ASYNC') : 'DFFNP',
   ('SET',   'LSRMUX', 'SIG', '') :      'DFFS',
   ('SET',   'LSRMUX', 'INV', '') :      'DFFNS',
}

def get_dff_type(dff_idx, in_attrs):
    def get_attrval_name(val):
        for nam, vl in attrids.cls_attrvals.items():
            if vl == val:
                return nam
        return None

    attrs = {}
    if 'LSRONMUX' in in_attrs.keys():
        attrs['LSRONMUX'] = get_attrval_name(in_attrs['LSRONMUX'])
    else:
        attrs['LSRONMUX'] = ''
    if 'CLKMUX_CLK' in in_attrs.keys():
        attrs['CLKMUX_CLK'] = get_attrval_name(in_attrs['CLKMUX_CLK'])
    else:
        attrs['CLKMUX_CLK'] = 'SIG'
    if 'SRMODE' in in_attrs.keys():
        attrs['SRMODE'] = get_attrval_name(in_attrs['SRMODE'])
    else:
        attrs['SRMODE'] = ''
    if f'REG{dff_idx % 2}_REGSET' in in_attrs.keys():
        attrs['REGSET'] = get_attrval_name(in_attrs[f'REG{dff_idx % 2}_REGSET'])
    else:
        attrs['REGSET'] = 'SET'
    return _dff_types.get((attrs['REGSET'], attrs['LSRONMUX'], attrs['CLKMUX_CLK'], attrs['SRMODE']))

# parse attributes and values use 'logicinfo' table
# returns {attr: value}
# attribute names are decoded with the attribute table, but the values are returned in raw form
def parse_attrvals(tile, logicinfo_table, fuse_table, attrname_table, tableName):
    def is_neg_key(key):
        for k in key:
            if k < 0:
                return True
        return False

    def is_pos_key(key):
        return not is_neg_key(key)

    def get_positive(av):
        return {a for a in av if a > 0}

    def get_negative(av):
        return {abs(a) for a in av if a < 0}

    res = {}
    set_mask = set()
    zero_mask = set()
    # collect masks
    for av, bits in fuse_table.items():
        if is_neg_key(av):
            zero_mask.update(bits)
        else:
            set_mask.update(bits)
    set_bits = {(row, col) for row, col in set_mask if tile[row][col] == 1}
    neg_bits = {(row, col) for row, col in zero_mask if tile[row][col] == 1}

    # find candidates from fuse table
    # the set bits are more unique
    attrvals = set()
    cnd = {av: bits for av, bits in fuse_table.items() if is_pos_key(av) and bits.issubset(set_bits)}
    for av, bits in cnd.items():
        keep = True
        for bt in cnd.values():
            if bits != bt and bits.issubset(bt):
                keep = False
                break
        if keep:
            clean_av = get_positive(av)
            attrvals.update(clean_av) # set attributes
            for idx in clean_av:
                attr, val = logicinfo_table[idx]
                res[get_attr_name(attrname_table, attr, tableName)] = val

    # records with a negative keys and used fuses
    neg_attrvals = set()
    ignore_attrs = set()
    cnd = {av: bits for av, bits in fuse_table.items() if is_neg_key(av) and bits.issubset(neg_bits)}
    for av, bits in cnd.items():
        keep = True
        for bt in cnd.values():
            if bits != bt and bits.issubset(bt):
                keep = False
                break
            for idx in av:
                attr, _ = logicinfo_table[abs(idx)]
                if attr in res.keys():
                    keep = False
                    break
        if keep:
            neg_attrvals.update(get_positive(av))
            ignore_attrs.update(get_negative(av))

    for idx in neg_attrvals:
        attr, val = logicinfo_table[idx]
        res[get_attr_name(attrname_table, attr, tableName)] = val

    # records with a negative keys and unused fuses
    cnd = {av for av, bits in fuse_table.items() if is_neg_key(av) and not bits.issubset(neg_bits)}
    for av in cnd:
        keep = True
        for idx in get_negative(av):
            if idx in ignore_attrs or not get_positive(av).issubset(attrvals):
                keep = False
                break
        if keep:
            for idx in get_negative(av):
                attr, val = logicinfo_table[idx]
                res[get_attr_name(attrname_table, attr, tableName)] = val
    return res

# { (row, col, type) : idx}
# type 'A'| 'B'
_pll_cells = {}

# returns the A cell of the PLL
def get_pll_A(db, row, col, typ):
    if typ == 'B':
        if _device in {"GW1N-9C", "GW1N-9"}:
            if col > 28:
                col = db.cols - 1
            else:
                col = 0
        else:
            col -= 1
    return row, col, 'A'

_iologic_mode = {
        'MODDRX2':  'OSER4',  'ODDRX2': 'OSER4',
        'MODDRX21': 'OSER4',  'ODDRX2': 'OSER4',
        'MODDRX4':  'OSER8',  'ODDRX4': 'OSER8',
        'MODDRX5':  'OSER10', 'ODDRX5': 'OSER10',
        'VIDEORX':  'OVIDEO', 'ODDRX8': 'OSER16',
        'MIDDRX2':  'IDES4',  'IDDRX2': 'IDES4',
        'MIDDRX4':  'IDES8',  'IDDRX4': 'IDES8',
        'MIDDRX5':  'IDES10', 'IDDRX5': 'IDES10',
        'IDDRX8':   'IDES16',
        }

# BSRAM has 3 cells: BSRAM, BSRAM0 and BSRAM1
# { (row, col) : idx }
_bsram_cells = {}
def get_bsram_main_cell(db, row, col, typ):
    if typ[-4:] == '_AUX':
        col -= 1
        if 'BSRAM_AUX' in db.grid[row][col].bels:
            col -= 1
    return row, col

# The DSP has 9 cells: the main one and a group of auxiliary ones.
def get_dsp_main_cell(db, row, col, typ):
    if typ[-6:-2] == '_AUX':
        col = 1 + (col - 1) // 9
    return row, col

# noiostd --- this is the case when the function is called
# with iostd by default, e.g. from the clock fuzzer
# With normal gowin_unpack io standard is determined first and it is known.
# (bels, pips, clock_pips)
def parse_tile_(db, row, col, tile, bm=None, default=True, noiostd = True):
    if not _bank_fuse_tables:
        # create bank fuse table
        for ttyp in db.longval.keys():
            if 'BANK' in db.longval[ttyp].keys():
                for key, val in db.longval[ttyp]['BANK'].items():
                    _bank_fuse_tables.setdefault(ttyp, {}).setdefault(f'BANK{key[0]}', {})[key[1:]] = val

    # TLVDS takes two BUF bels, so skip the B bels.
    skip_bels = set()
    #print((row, col))
    tiledata = db.grid[row][col]
    #if 'HCLK' in db.shortval[tiledata.ttyp].keys():
    #    attrvals =parse_attrvals(tile, db.logicinfo['HCLK'], db.shortval[tiledata.ttyp]['HCLK'], attrids.hclk_attrids)
    #    if attrvals:
    #        print(row, col, attrvals)

    #if tiledata.ttyp in db.longfuses:
    #    if 'DLLDEL0' in db.longfuses[tiledata.ttyp].keys():
    #        attrvals =parse_attrvals(tile, db.logicinfo['DLLDLY'], db.longfuses[tiledata.ttyp]['DLLDEL0'], attrids.dlldly_attrids)
    #        if attrvals:
    #            print(row, col, attrvals)
    #    if 'DLLDEL1' in db.longfuses[tiledata.ttyp].keys():
    #        attrvals =parse_attrvals(tile, db.logicinfo['DLLDLY'], db.longfuses[tiledata.ttyp]['DLLDEL1'], attrids.dlldly_attrids)
    #        if attrvals:
    #            print(row, col, attrvals)

    clock_pips = {}
    bels = {}
    for name, bel in tiledata.bels.items():
        if name.startswith("ADC"):
            attrvals = parse_attrvals(tile, db.rev_logicinfo('ADC'), db.shortval[tiledata.ttyp]['ADC'], attrids.adc_attrids, "ADC")
            print(row, col, name, tiledata.ttyp, attrvals)
        if name.startswith("RPLL"):
            idx = _pll_cells.setdefault(get_pll_A(db, row, col, name[4]), len(_pll_cells))
            modes = { f'DEVICE="{_device}"' }
            if 'PLL' in db.shortval[tiledata.ttyp].keys():
                attrvals = pll_attrs_refine(parse_attrvals(tile, db.rev_logicinfo('PLL'), db.shortval[tiledata.ttyp]['PLL'], attrids.pll_attrids, "PLL"))
                for attrval in attrvals:
                    modes.add(attrval)
            if modes:
                bels[f'{name}{idx}'] = modes
            continue
        if name == "PLLVR":
            idx = _pll_cells.setdefault(get_pll_A(db, row, col, 'A'), len(_pll_cells))
            attrvals = pll_attrs_refine(parse_attrvals(tile, db.rev_logicinfo('PLL'), db.shortval[tiledata.ttyp]['PLL'], attrids.pll_attrids, "PLL"))
            modes = { f'DEVICE="{_device}"' }
            for attrval in attrvals:
                modes.add(attrval)
            if modes:
                bels[f'{name}{idx}'] = modes
            continue
        if name.startswith("OSC"):
            attrvals = osc_attrs_refine(parse_attrvals(tile, db.rev_logicinfo('OSC'), db.shortval[tiledata.ttyp]['OSC'], attrids.osc_attrids, "OSC"))
            modes = set()
            for attrval in attrvals:
                modes.add(attrval)
            if modes:
                bels[name] = modes
            continue
        if name.startswith("BSRAM"):
            # disabled BSRAM cells have no fuse tables
            if 'BSRAM_SP' not in db.shortval[tiledata.ttyp]:
                continue
            idx = _bsram_cells.setdefault(get_bsram_main_cell(db, row, col, name), len(_bsram_cells))
            #print(row, col, name, idx, tiledata.ttyp)
            attrvals = parse_attrvals(tile, db.rev_logicinfo('BSRAM'), db.shortval[tiledata.ttyp]['BSRAM_SP'], attrids.bsram_attrids, "BSRAM")
            if not attrvals:
                continue
            #print(row, col, name, idx, tiledata.ttyp, attrvals)
            bels[f'{name}{idx}'] = {}
            continue
        if name.startswith("ALU54D"):
            continue
        if name.startswith("DSP") or name.startswith("DSP_AUX"):
            modes = set()
            idx = name[-1]
            #print(row, col, name, idx, tiledata.ttyp)
            if name.startswith("DSP_AUX"):
                row, col = get_dsp_main_cell(db, row, col, name)

            if f'DSP{idx}' in db.shortval[tiledata.ttyp]:
                attrvals = parse_attrvals(tile, db.rev_logicinfo('DSP'), db.shortval[tiledata.ttyp][f'DSP{idx}'], attrids.dsp_attrids, "DSP")
                #print_sorted_dict(f'{row}, {col}, {name}, {idx}, {tiledata.ttyp} - ', attrvals)
                for attrval in attrvals:
                    modes.add(attrval)
            if modes and not name.startswith("DSP_AUX"):
                bels[f'{name}{idx}'] = modes
            continue
        if name.startswith("IOLOGIC"):
            idx = name[-1]
            attrvals = parse_attrvals(tile, db.rev_logicinfo('IOLOGIC'), db.shortval[tiledata.ttyp][f'IOLOGIC{idx}'], attrids.iologic_attrids, "IOLOGIC")
            if not attrvals:
                continue
            # additional IOLOGIC components
            # XXX delays and FFs in IO
            # main component
            if 'OUTMODE' in attrvals.keys():
                # XXX skip oddr
                if attrvals['OUTMODE'] in {attrids.iologic_attrvals['MODDRX1'], attrids.iologic_attrvals['ODDRX1']}:
                    if 'LSROMUX_0' in attrvals.keys():
                        bels.setdefault(name, set()).add(f"MODE=ODDRC")
                    else:
                        bels.setdefault(name, set()).add(f"MODE=ODDR")
                    continue
                # skip aux cells
                if attrvals['OUTMODE'] == attrids.iologic_attrvals['DDRENABLE']:
                    continue
                if attrids.iologic_num2val[attrvals['OUTMODE']] in _iologic_mode.keys():
                    bels.setdefault(name, set()).add(f"MODE={_iologic_mode[attrids.iologic_num2val[attrvals['OUTMODE']]]}")
            elif 'INMODE' in attrvals.keys():
                if attrvals['INMODE'] in {attrids.iologic_attrvals['MIDDRX1'], attrids.iologic_attrvals['IDDRX1']}:
                    if 'LSRIMUX_0' in attrvals.keys():
                        bels.setdefault(name, set()).add(f"MODE=IDDRC")
                    else:
                        bels.setdefault(name, set()).add(f"MODE=IDDR")
                    continue
                # skip aux cells
                if attrvals['INMODE'] == attrids.iologic_attrvals['DDRENABLE']:
                    continue
                if attrids.iologic_num2val[attrvals['INMODE']] in _iologic_mode.keys():
                    in_mode = _iologic_mode[attrids.iologic_num2val[attrvals['INMODE']]]
                    if in_mode == 'OVIDEO':
                        in_mode = 'IVIDEO'
                    bels.setdefault(name, set()).add(f"MODE={in_mode}")
            else:
                continue
            if 'CLKODDRMUX_ECLK' in attrvals.keys():
                bels.setdefault(name, set()).add(f"CLKODDRMUX_ECLK={attrids.iologic_num2val[attrvals['CLKODDRMUX_ECLK']]}")
        if name.startswith("DFF"):
            idx = int(name[3])
            attrvals = parse_attrvals(tile, db.rev_logicinfo('SLICE'), db.shortval[tiledata.ttyp][f'CLS{idx // 2}'], attrids.cls_attrids, "CLS")
            #print('parse', row, col, attrvals)
            # skip ALU and unsupported modes
            if attrvals.get('MODE') == attrids.cls_attrvals['SSRAM']:
                continue
            dff_type = get_dff_type(idx, attrvals)
            if dff_type:
                bels[f'{name}'] = {dff_type}
            if f'REG{idx % 2}_SD' in attrvals:
                bels[f'{name}'].update({'SD'})
            continue
        if name.startswith("IOB"):
            idx = name[-1]
            io_row, io_col = row, col
            io_tile = tile
            io_ttyp = tiledata.ttyp

            if idx == 'B' and _device == 'GW5A-25A' and tiledata.bels[name].fuse_cell_offset:
                io_row += tiledata.bels[name].fuse_cell_offset[0]
                io_col += tiledata.bels[name].fuse_cell_offset[1]
                io_tiledata = db.grid[io_row][io_col]
                io_tile = bm[io_row, io_col]
                io_ttyp = io_tiledata.ttyp
            # XXX
            if idx == 'B' and 'IOBB' not in db.longval[io_ttyp]:
                continue
            attrvals = parse_attrvals(io_tile, db.rev_logicinfo('IOB'), db.longval[io_ttyp][f'IOB{idx}'], attrids.iob_attrids, "IOB")
            #print(name, io_row, io_col, attrvals)
            try: # we can ask for invalid pin here because the IOBs share some stuff
                bank = chipdb.loc2bank(db, io_row, io_col)
            except KeyError:
                bank = None
            if attrvals:
                mode = 'IBUF'
                if attrvals.get('PERSISTENT', None) == attrids.iob_attrvals['OFF']:
                    mode = 'IOBUF'
                elif 'ODMUX' in attrvals or 'ODMUX_1' in attrvals:
                    mode = 'OBUF'
                # Z-1 row 6
                if _device in {'GW1NZ-1', 'GW1N-1'} and row == 5:
                    mode = 'IOBUF'
                if 'LVDS_OUT' in attrvals:
                    if mode == 'IOBUF':
                        mode = 'TBUF'
                    if 'MIPI' in attrvals:
                        mode = 'MIPI_OBUF'
                    else:
                        mode = f'TLVDS_{mode}'
                    # skip B bel
                    skip_bels.update({name[:-1] + 'B'})
                elif 'OD' in attrvals:
                    mode = 'I3C_IOBUF'
                elif idx == 'B' and 'DRIVE' not in attrvals and 'IO_TYPE' in attrvals:
                    mode = f'ELVDS_{mode}'
                    # skip B bel
                    skip_bels.update({name})
                elif 'LPRX_A1' in attrvals:
                    mode = f'MIPI_IBUF'
                    # skip B bel
                    skip_bels.update({name[:-1] + 'B'})
                elif 'IOBUF_MIPI_LP' in attrvals:
                    mode = f'ELVDS_{mode}'
                    # skip B bel
                    skip_bels.update({name[:-1] + 'B'})

                bels.setdefault(name, set()).add(mode)
        if name.startswith("BANK"):
            attrvals = parse_attrvals(tile, db.rev_logicinfo('IOB'), _bank_fuse_tables[tiledata.ttyp][name], attrids.iob_attrids, "IOB")
            #print(name, row, col, attrvals)

            for a, v in attrvals.items():
                bels.setdefault(name, set()).add(f'{a}={attrids.iob_num2val.get(v, str(v))}')
        if name.startswith("ALU"):
            idx = int(name[3])
            attrvals = parse_attrvals(tile, db.rev_logicinfo('SLICE'), db.shortval[tiledata.ttyp][f'CLS{idx // 2}'], attrids.cls_attrids, "CLS")
            # skip ALU and unsupported modes
            if attrvals.get('MODE') != attrids.cls_attrvals['ALU']:
                continue
            bels[name] = {"C2L"}
            mode_bits = {(row, col)
                         for row, col in bel.mode_bits
                         if tile[row][col] == 1}
            for mode, bits in bel.modes.items():
                if bits == mode_bits and (default or bits):
                    bels[name] = {mode}
        else:
            mode_bits = {(row, col)
                         for row, col in bel.mode_bits
                         if tile[row][col] == 1}
            #print(name, sorted(bel.mode_bits))
            #print("read mode:", sorted(mode_bits))
            for mode, bits in bel.modes.items():
                #print(mode, sorted(bits))
                if bits == mode_bits and (default or bits):
                    bels.setdefault(name, set()).add(mode)
        # simple flags
        for flag, bits in bel.flags.items():
            used_bits = {tile[row][col] for row, col in bits}
            if all(used_bits):
                if name == "RAM16" and not name in bels:
                    continue
                bels.setdefault(name, set()).add(flag)
        # revert BUFS flags
        if name.startswith('BUFS'):
            flags = bels.get(name, set()) ^ {'R', 'L'}
            if flags:
                num = name[4:]
                half = 'T'
                if row != 0:
                    half = 'B'
                for qd in flags:
                    clock_pips[f'LWSPINE{half}{qd}{num}'] = f'LW{half}{num}'
        #print("flags:", sorted(bels.get(name, set())))

    pips = {}
    for dest, srcs in tiledata.pips.items():
        pip_bits = set().union(*srcs.values())
        used_bits = {(row, col)
                     for row, col in pip_bits
                     if tile[row][col] == 1}
        for src, bits in srcs.items():
            # optionally ignore the defautl set() state
            if bits == used_bits and (default or bits):
                pips[dest] = src

    for dest, srcs in tiledata.clock_pips.items():
        pip_bits = set().union(*srcs.values())
        used_bits = {(row, col)
                     for row, col in pip_bits
                     if tile[row][col] == 1}
        for src, bits in srcs.items():
            if bits == used_bits:
                clock_pips[dest] = src

    # elvds IO uses the B bel bits
    for name in skip_bels:
        bel_a_name = f'{name[:-1]}A'
        if bel_a_name not in bels:
            continue

        bel_a = bels[bel_a_name]
        if not bel_a.intersection({'ELVDS_IBUF', 'ELVDS_OBUF', 'ELVDS_IOBUF', 'ELVDS_TBUF',
                                   'TLVDS_IBUF', 'TLVDS_OBUF', 'TLVDS_IOBUF', 'TLVDS_TBUF', 'MIPI_IBUF', 'MIPI_OBUF'}):
            mode = bels[name].intersection({'ELVDS_IBUF', 'ELVDS_OBUF', 'ELVDS_IOBUF', 'ELVDS_TBUF'})
            if mode:
                old_mode = bel_a.intersection({'IBUF', 'OBUF', 'IOBUF', 'TBUF'})
                bel_a -= old_mode
                bel_a.update(mode)

    return {name: bel for name, bel in bels.items() if name not in skip_bels}, pips, clock_pips

dffmap = {
    "DFF": None,
    "DFFN": None,
    "DFFS": "SET",
    "DFFR": "RESET",
    "DFFP": "PRESET",
    "DFFC": "CLEAR",
    "DFFNS": "SET",
    "DFFNR": "RESET",
    "DFFNP": "PRESET",
    "DFFNC": "CLEAR",
}
iobmap = {
    "IBUF": {"wires": ["O"], "inputs": ["I"]},
    "OBUF": {"wires": ["I"], "outputs": ["O"]},
    "TBUF": {"wires": ["I", "OE"], "outputs": ["O"]},
    "IOBUF": {"wires": ["I", "O", "OE"], "inouts": ["IO"]},
    "TLVDS_OBUF": {"wires": ["I"], "outputs": ["O", "OB"]},
    "TLVDS_TBUF": {"wires": ["I", "OE"], "outputs": ["O", "OB"]},
    "TLVDS_IBUF": {"wires": ["O"], "inputs": ["I", "IB"]},
    "ELVDS_OBUF": {"wires": ["I"], "outputs": ["O", "OB"]},
    "ELVDS_TBUF": {"wires": ["I", "OE"], "outputs": ["O", "OB"]},
    "ELVDS_IBUF": {"wires": ["O"], "inputs": ["I", "IB"]},
    "ELVDS_IOBUF": {"wires": ["I", "O", "OE"], "inouts": ["IO", "IOB"]},
    "MIPI_IBUF": {"wires": ["I", "IB", "OEN", "OENB", "HSREN", "OH", "OL", "OB"], "inouts": ["IO", "IOB"]},
    "MIPI_OBUF": {"wires": ["I", "IB", "IL", "MODESEL"], "inouts": ["O", "OB"]},
    "I3C_IOBUF": {"wires": ["I", "O", "MODESEL"], "inouts": ["IO"]},
}

# OE -> OEN
def portname(n):
    if n == "OE":
        return "OEN"
    return n

def make_muxes(row, col, idx, db, mod):
    name = f"R{row}C{col}_MUX2_LUT50"
    if name in mod.primitives.keys():
        return

    # one MUX8
    if col < db.cols :
        name = f"R{row}C{col}_MUX2_LUT80"
        mux2 = codegen.Primitive("MUX2", name)
        mux2.portmap['I0'] = f"R{row}C{col + 1}_OF3"
        mux2.portmap['I1'] = f"R{row}C{col}_OF3"
        mux2.portmap['O']  = f"R{row}C{col}_OF7"
        mux2.portmap['S0'] = f"R{row}C{col}_SEL7"
        mod.wires.update(mux2.portmap.values())
        mod.primitives[name] = mux2

    # one MUX7
    name = f"R{row}C{col}_MUX2_LUT70"
    mux2 = codegen.Primitive("MUX2", name)
    mux2.portmap['I0'] = f"R{row}C{col}_OF5"
    mux2.portmap['I1'] = f"R{row}C{col}_OF1"
    mux2.portmap['O']  = f"R{row}C{col}_OF3"
    mux2.portmap['S0'] = f"R{row}C{col}_SEL3"
    mod.wires.update(mux2.portmap.values())
    mod.primitives[name] = mux2

    # two MUX6
    for i in range(2):
        name = f"R{row}C{col}_MUX2_LUT6{i}"
        mux2 = codegen.Primitive("MUX2", name)
        mux2.portmap['I0'] = f"R{row}C{col}_OF{i * 4 + 2}"
        mux2.portmap['I1'] = f"R{row}C{col}_OF{i * 4}"
        mux2.portmap['O']  = f"R{row}C{col}_OF{i * 4 + 1}"
        mux2.portmap['S0'] = f"R{row}C{col}_SEL{i * 4 + 1}"
        mod.wires.update(mux2.portmap.values())
        mod.primitives[name] = mux2

    # four MUX5
    for i in range(4):
        name = f"R{row}C{col}_MUX2_LUT5{i}"
        mux2 = codegen.Primitive("MUX2", name)
        mux2.portmap['I0'] = f"R{row}C{col}_F{i * 2}"
        mux2.portmap['I1'] = f"R{row}C{col}_F{i * 2  + 1}"
        mux2.portmap['O']  = f"R{row}C{col}_OF{i * 2}"
        mux2.portmap['S0'] = f"R{row}C{col}_SEL{i * 2}"
        mod.wires.update(mux2.portmap.values())
        mod.primitives[name] = mux2

_alu_re = re.compile(r"ALU(\w*)")
def removeLUTs(bels):
    bels_to_remove = []
    for bel in bels:
        match = _alu_re.match(bel)
        if match:
            bels_to_remove.append(f"LUT{match.group(1)}")
    for bel in bels_to_remove:
        bels.pop(bel, None)

def removeALUs(bels):
    bels_to_remove = []
    for bel in bels:
        match = _alu_re.match(bel)
        if match:
            bels_to_remove.append(match.group(0))
    for bel in bels_to_remove:
        bels.pop(bel, None)

def ram16_remove_bels(bels):
    bels_to_remove = []
    for bel in bels:
        if bel == "RAM16":
            bels_to_remove.extend(f"LUT{x}" for x in range(6))
            bels_to_remove.extend(f"DFF{x}" for x in range(4, 6))
    for bel in bels_to_remove:
        bels.pop(bel, None)

_iologic_bels = ['IOLOGICA', 'IOLOGICB', 'ODDRA', 'ODDRB']
def move_iologic(bels):
    res = []
    for iol_bel in _iologic_bels:
        if iol_bel in bels.keys():
            res.append((iol_bel, bels[iol_bel]))
    res += [(bel, flags) for bel, flags in bels.items() if bel not in _iologic_bels]
    return res

def disable_unused_pll_ports(pll):
    if 'DYN_DA_EN' not in pll.params:
        for n in range(0, 4):
            if f'PSDA{n}' in pll.portmap:
                del pll.portmap[f'PSDA{n}']
                del pll.portmap[f'DUTYDA{n}']
                del pll.portmap[f'FDLY{n}']
    if 'DYN_IDIV_SEL' not in pll.params:
        for n in range(0, 6):
            if f'IDSEL{n}' in pll.portmap:
                del pll.portmap[f'IDSEL{n}']
    if 'DYN_FBDIV_SEL' not in pll.params:
        for n in range(0, 6):
            if f'FBDSEL{n}' in pll.portmap:
                del pll.portmap[f'FBDSEL{n}']
    if 'DYN_ODIV_SEL' not in pll.params:
        for n in range(0, 6):
            if f'ODSEL{n}' in pll.portmap:
                del pll.portmap[f'ODSEL{n}']
    if 'PWDEN' in pll.params:
        if pll.params['PWDEN'] == 'DISABLE':
            if 'RESET_P' in pll.portmap:
                del pll.portmap['RESET_P']
        del pll.params['PWDEN']
    if 'RSTEN' in pll.params:
        if pll.params['RSTEN'] == 'DISABLE':
            if 'RESET' in pll.portmap:
                del pll.portmap['RESET']
        del pll.params['RSTEN']
    if 'CLKOUTDIV3' in pll.params:
        if pll.params['CLKOUTDIV3'] == 'DISABLE':
            if 'CLKOUTD3' in pll.portmap:
                del pll.portmap['CLKOUTD3']
        del pll.params['CLKOUTDIV3']
    if 'CLKOUTDIV' in pll.params:
        if pll.params['CLKOUTDIV'] == 'DISABLE':
            if 'CLKOUTD' in pll.portmap:
                del pll.portmap['CLKOUTD']
        del pll.params['CLKOUTDIV']
    if 'CLKOUTPS' in pll.params:
        if pll.params['CLKOUTPS'] == 'DISABLE':
            if 'CLKOUTP' in pll.portmap:
                del pll.portmap['CLKOUTP']
        del pll.params['CLKOUTPS']

_tbrlre = re.compile(r"IO([TBRL])(\d+)(\w)")
def tbrl2rc(db, loc):
    side, num, bel_idx = _tbrlre.match(loc).groups()
    if side == 'T':
        row = 0
        col = int(num) - 1
    elif side == 'B':
        row = db.rows - 1
        col = int(num) - 1
    elif side == 'L':
        row = int(num) - 1
        col = 0
    elif side == 'R':
        row = int(num) - 1
        col = db.cols - 1
    return (row, col, bel_idx)

def find_pll_in_pin(db, pll):
    locs = [loc for (loc, cfgs) in _pinout.values() if 'RPLL_T_IN' in cfgs or 'LRPLL_T_IN' in cfgs]
    if not locs:
        raise Exception(f"No [RL]PLL_T_IN pin in the current package")
    row, col, bel_idx = tbrl2rc(db, locs[0])
    wire = db.grid[row][col].bels[f'IOB{bel_idx}'].portmap['O']
    pll.portmap['CLKIN'] = f'R{row + 1}C{col + 1}_{wire}'

def modify_pll_inputs(db, pll):
    if 'INSEL' in pll.params.keys():
        insel = pll.params['INSEL']
        if insel != 'CLKIN1':
            # pin
            if insel == 'CLKIN0':
                find_pll_in_pin(db, pll)
            else:
                if 'CLKIN' in pll.portmap:
                    del pll.portmap['CLKIN']
        del pll.params['INSEL']
    if 'FBSEL' in pll.params.keys():
        fbsel = pll.params['FBSEL']
        if fbsel == 'CLKFB3':
            # internal
            pll.params['CLKFB_SEL'] = '"internal"'
            if 'CLKFB' in pll.portmap:
                del pll.portmap['CLKFB']
        elif fbsel == 'CLKFB0':
            # external CLK2
            pll.params['CLKFB_SEL'] = '"external"'
        elif fbsel == 'CLKFB2':
            # external pin
            pll.params['CLKFB_SEL'] = '"external"'
            # XXX find pin
        del pll.params['FBSEL']

_iologic_ports = {
        'ODDR' :  {'D0': 'D0', 'D1': 'D1', 'Q0': 'Q0', 'Q1': 'Q1', 'CLK': 'CLK'},
        'ODDRC' : {'D0': 'D0', 'D1': 'D1', 'Q0': 'Q0', 'Q1': 'Q1', 'CLK': 'CLK', 'CLEAR': 'CLEAR'},
        'OSER4': {'D0': 'D0', 'D1': 'D1', 'D2': 'D2', 'D3': 'D3',
                  'Q0': 'Q0', 'Q1': 'Q1', 'RESET': 'RESET', 'TX0': 'TX0',
                  'TX1': 'TX1', 'PCLK': 'PCLK', 'FCLK': 'FCLK'},
        'OSER8': {'D0': 'D0', 'D1': 'D1', 'D2': 'D2', 'D3': 'D3',
                  'D4': 'D4', 'D5': 'D5', 'D6': 'D6', 'D7': 'D7',
                  'Q0': 'Q0', 'Q1': 'Q1', 'RESET': 'RESET', 'TX0': 'TX90',
                  'TX1': 'TX1', 'TX2': 'TX2', 'TX3': 'TX3',
                  'PCLK': 'PCLK', 'FCLK': 'FCLK'},
        'OVIDEO':{'D0': 'D0', 'D1': 'D1', 'D2': 'D2', 'D3': 'D3',
                  'D4': 'D4', 'D5': 'D5', 'D6': 'D6', 'Q': 'Q',
                  'RESET': 'RESET', 'PCLK': 'PCLK', 'FCLK': 'FCLK'},
        'OSER10': {'D0': 'D0', 'D1': 'D1', 'D2': 'D2', 'D3': 'D3',
                   'D4': 'D4', 'D5': 'D5', 'D6': 'D6', 'D7': 'D7', 'D8': 'D8', 'D9': 'D9',
                   'Q': 'Q', 'RESET': 'RESET', 'PCLK': 'PCLK', 'FCLK': 'FCLK'},
        'OSER16': {'D0': 'A0', 'D1': 'A1', 'D2': 'A2', 'D3': 'A3',
                   'D4': 'C1', 'D5': 'C0', 'D6': 'D1', 'D7': 'D0', 'D8': 'C3', 'D9': 'C2',
                   'D10': 'B4', 'D11': 'B5', 'D12': 'A0', 'D13': 'A1', 'D14': 'A2',
                   'D15': 'A3',},
        'IDDR' :  {'D': 'D', 'Q8': 'Q0', 'Q9': 'Q1', 'CLK': 'CLK'},
        'IDDRC' : {'D': 'D', 'Q8': 'Q0', 'Q9': 'Q1', 'CLK': 'CLK', 'CLEAR': 'CLEAR'},
        'IDES4':  {'D': 'D', 'Q6': 'Q0', 'Q7': 'Q1', 'Q8': 'Q2', 'Q9': 'Q3',
                   'RESET': 'RESET', 'CALIB': 'CALIB', 'PCLK': 'PCLK', 'FCLK': 'FCLK'},
        'IDES8': {'D': 'D', 'Q2': 'Q0', 'Q3': 'Q1', 'Q4': 'Q2', 'Q5': 'Q3', 'Q6': 'Q4',
                  'Q7': 'Q5', 'Q8': 'Q6', 'Q9': 'Q7',
                  'RESET': 'RESET', 'CALIB': 'CALIB', 'PCLK': 'PCLK', 'FCLK': 'FCLK'},
        'IVIDEO': {'D': 'D', 'Q3': 'Q0', 'Q4': 'Q1', 'Q5': 'Q2', 'Q6': 'Q3', 'Q7': 'Q4',
                   'Q8': 'Q5', 'Q9': 'Q6',
                   'RESET': 'RESET', 'CALIB': 'CALIB', 'PCLK': 'PCLK', 'FCLK': 'FCLK'},
        'IDES10': {'D': 'D', 'Q0': 'Q0', 'Q1': 'Q1', 'Q2': 'Q2', 'Q3': 'Q3', 'Q4': 'Q4',
                   'Q5': 'Q5', 'Q6': 'Q6', 'Q7': 'Q7', 'Q8': 'Q8', 'Q9': 'Q9',
                   'RESET': 'RESET', 'CALIB': 'CALIB', 'PCLK': 'PCLK', 'FCLK': 'FCLK'},
        'IDES16': {'Q0': 'F2', 'Q1': 'F3', 'Q2': 'F4', 'Q3': 'F5', 'Q4': 'Q0', 'Q5': 'Q1',
                   'Q6': 'Q2', 'Q7': 'Q3', 'Q8': 'Q4', 'Q9': 'Q5', 'Q10': 'F0',
                   'Q11': 'F1', 'Q12': 'F2', 'Q13': 'F3', 'Q14': 'F4', 'Q15': 'F5' },
}
def iologic_ports_by_type(typ, portmap):
    if typ not in {'IDES16', 'OSER16'}:
        return { (_iologic_ports[typ][port], wire) for port, wire in portmap.items() if port in _iologic_ports[typ].keys() }
    elif typ in {'OSER16', 'IDES16'}:
        ports = { (port, wire) for port, wire in _iologic_ports[typ].items()}
        ports.add(('RESET', portmap['RESET']))
        ports.add(('PCLK', portmap['PCLK']))
        ports.add(('FCLK', portmap['FCLK']))
        if typ == 'IDES16':
            ports.add(('CALIB', portmap['CALIB']))
            ports.add(('D', portmap['D']))
        else:
            ports.add(('Q', portmap['Q']))
        return ports

_sides = "AB"
def tile2verilog(dbrow, dbcol, bels, pips, clock_pips, mod, cst, db):
    # db is 0-based, floorplanner is 1-based
    row = dbrow+1
    col = dbcol+1

    for dest, src in chain(pips.items(), clock_pips.items()):
        srcg = chipdb.wire2global(row, col, db, src)
        destg = chipdb.wire2global(row, col, db, dest)
        mod.wires.update({srcg, destg})
        mod.assigns.append((destg, srcg))

    belre = re.compile(r"(IOB|LUT|DFF|BANK|CFG|ALU|RAM16|ODDR|OSC[ZFHWO]?|BUFS|RPLL[AB]|PLLVR|IOLOGIC|BSRAM|DSP)(\w*)")
    bels_items = move_iologic(bels)

    iologic_detected = set()
    disable_oddr = False
    for bel, flags in bels_items:
        typ, idx = belre.match(bel).groups()

        if typ == "LUT":
            val = 0xffff - sum(1<<f for f in flags)
            if val == 0:
                mod.assigns.append((f"R{row}C{col}_F{idx}", "VSS"))
            else:
                name = f"R{row}C{col}_LUT4_{idx}"
                lut = codegen.Primitive("LUT4", name)
                lut.params["INIT"] = f"16'h{val:04x}"
                lut.portmap['F'] = f"R{row}C{col}_F{idx}"
                lut.portmap['I0'] = f"R{row}C{col}_A{idx}"
                lut.portmap['I1'] = f"R{row}C{col}_B{idx}"
                lut.portmap['I2'] = f"R{row}C{col}_C{idx}"
                lut.portmap['I3'] = f"R{row}C{col}_D{idx}"
                mod.wires.update(lut.portmap.values())
                mod.primitives[name] = lut
                cst.cells[name] = (row, col, int(idx) // 2, _sides[int(idx) % 2])
            make_muxes(row, col, idx, db, mod)
        elif typ.startswith("IOLOGIC"):
            iologic_detected.add(idx)
            iol_mode = 'IVIDEO' #XXX
            disable_oddr = True
            eclk = 'HCLK0'
            iol_params = {}
            for paramval in flags:
                param, _, val = paramval.partition('=')
                if param == 'MODE':
                    iol_mode = val
                    if val == 'OSER4':
                        disable_oddr = False
                    continue
                if param == 'CLKODDRMUX_ECLK':
                    eclk == val
                    continue
                if param == 'CLKIDDRMUX_ECLK':
                    eclk == val
                    continue
                iol_params[param] = val
            name = f"R{row}C{col}_{iol_mode}_{idx}"
            iol = mod.primitives.setdefault(name, codegen.Primitive(iol_mode, name))
            iol.params.update(iol_params)
            iol_oser = iol_mode in {'ODDR', 'ODDRC', 'OSER4', 'OVIDEO', 'OSER8', 'OSER10', 'OSER16'}

            portmap = db.grid[dbrow][dbcol].bels[bel].portmap
            for port, wname in iologic_ports_by_type(iol_mode, portmap):
                if iol_oser:
                    if port in {'Q', 'Q0', 'Q1'}:
                        if port == 'Q1':
                            iol.portmap[port] = f"R{row}C{col}_{portmap['TX0']}_IOL"
                        else:
                            iol.portmap[port] = f"R{row}C{col}_{portmap['D0']}_IOL"
                    elif port == 'FCLK':
                        wname = eclk
                        if eclk == 'HCLK0' and _device in {'GW1N-1'}:
                            wname = 'CLK2'
                        iol.portmap[port] = f"R{row}C{col}_{wname}"
                    else:
                        if iol_mode != 'OSER16' or port not in {'D12', 'D13', 'D14', 'D15'}:
                            iol.portmap[port] = f"R{row}C{col}_{wname}"
                        else:
                            if row == 1 or row == db.rows:
                                iol.portmap[port] = f"R{row}C{col + 1}_{wname}"
                            else:
                                iol.portmap[port] = f"R{row + 1}C{col}_{wname}"
                else: # IDES
                    if port in {'D'}:
                        iol.portmap[port] = f"R{row}C{col}_{portmap['D']}_IOL"
                    else:
                        if iol_mode != 'IDES16':
                            iol.portmap[port] = f"R{row}C{col}_{wname}"
                        else:
                            if port not in {'Q0', 'Q1', 'Q2', 'Q3'}:
                                iol.portmap[port] = f"R{row}C{col}_{wname}"
                            else:
                                if row == 1 or row == db.rows:
                                    iol.portmap[port] = f"R{row}C{col + 1}_{wname}"
                                else:
                                    iol.portmap[port] = f"R{row + 1}C{col}_{wname}"
                if port == 'FCLK':
                    wname = eclk
                    if eclk == 'HCLK0' and _device in {'GW1N-1'}:
                        wname = 'CLK2'
                    iol.portmap[port] = f"R{row}C{col}_{wname}"

        elif typ.startswith("RPLL"):
            name = f"PLL_{idx}"
            pll = mod.primitives.setdefault(name, codegen.Primitive("rPLL", name))
            for paramval in flags:
                param, _, val = paramval.partition('=')
                pll.params[param] = val
            portmap = db.grid[dbrow][dbcol].bels[bel[:5]].portmap
            for port, wname in portmap.items():
                pll.portmap[port] = f"R{row}C{col}_{wname}"
        elif typ.startswith("PLLVR"):
            name = f"PLL_{idx}"
            pll = mod.primitives.setdefault(name, codegen.Primitive("PLLVR", name))
            for paramval in flags:
                param, _, val = paramval.partition('=')
                pll.params[param] = val
            portmap = db.grid[dbrow][dbcol].bels[bel[:-1]].portmap
            for port, wname in portmap.items():
                pll.portmap[port] = f"R{row}C{col}_{wname}"
        elif typ.startswith("BSRAM"):
            #print(dbrow, dbcol, typ, bel, idx)
            if idx.startswith("_AUX"):
                continue
            bel_name = "BSRAM"
            name = f"BSRAM_{idx}"
            pll = mod.primitives.setdefault(name, codegen.Primitive("BSRAM", name))
            for paramval in flags:
                param, _, val = paramval.partition('=')
                pll.params[param] = val
            portmap = db.grid[dbrow][dbcol].bels[bel_name].portmap
            for port, wname in portmap.items():
                pll.portmap[port] = f"R{row}C{col}_{wname}"
        elif typ == "ALU":
            #print(flags)
            kind, = flags # ALU only have one flag
            idx = int(idx)
            name = f"R{row}C{col}_ALU_{idx}"
            if kind == 'hadder':
                kind = '0'
            if kind in "012346789" or kind == "C2L" : # main ALU
                alu = codegen.Primitive("ALU", name)
                alu.params["ALU_MODE"] = kind
                if kind != "C2L":
                    alu.portmap['SUM'] = f"R{row}C{col}_F{idx}"
                alu.portmap['CIN'] = f"R{row}C{col}_CIN{idx}"
                alu.portmap['I2'] = f"R{row}C{col}_C{idx}"
                if idx != 5:
                    alu.portmap['COUT'] = f"R{row}C{col}_CIN{idx+1}"
                else:
                    alu.portmap['COUT'] = f"R{row}C{col + 1}_CIN{0}"
                if kind in "2346789":
                    alu.portmap['I0'] = f"R{row}C{col}_A{idx}"
                    alu.portmap['I1'] = f"R{row}C{col}_B{idx}"
                    if kind in "28":
                        alu.portmap['I3'] = f"R{row}C{col}_D{idx}"
                elif kind == "0":
                    alu.portmap['I0'] = f"R{row}C{col}_B{idx}"
                    alu.portmap['I1'] = f"R{row}C{col}_D{idx}"
                    alu.portmap['I3'] = f"R{row}C{col}_A{idx}"
                elif kind == "C2L":
                    alu.portmap['I0'] = f"R{row}C{col}_B{idx}"
                    alu.portmap['I1'] = f"R{row}C{col}_D{idx}"
                    alu.portmap['COUT'] = f"R{row}C{col}_F{idx}"
                    alu.params["ALU_MODE"] = "9" # XXX
                else:
                    alu.portmap['I0'] = f"R{row}C{col}_A{idx}"
                    alu.portmap['I1'] = f"R{row}C{col}_D{idx}"
                mod.wires.update(alu.portmap.values())
                mod.primitives[name] = alu
        elif typ == "RAM16":
            val0 = sum(1<<x for x in range(0,16) if not x in flags)
            val1 = sum(1<<(x-16) for x in range(16,32) if not x in flags)
            val2 = sum(1<<(x-32) for x in range(32,48) if not x in flags)
            val3 = sum(1<<(x-48) for x in range(48,64) if not x in flags)
            name = f"R{row}C{col}_RAM16"
            ram16 = codegen.Primitive("RAM16SDP4", name)
            ram16.params["INIT_0"] = f"16'b{val0:016b}"
            ram16.params["INIT_1"] = f"16'b{val1:016b}"
            ram16.params["INIT_2"] = f"16'b{val2:016b}"
            ram16.params["INIT_3"] = f"16'b{val3:016b}"
            ram16.portmap['DI'] = [f"R{row}C{col}_{x}5" for x in "DCBA"]
            ram16.portmap['CLK'] = f"R{row}C{col}_CLK2"
            ram16.portmap['WRE'] = f"R{row}C{col}_LSR2"
            ram16.portmap['WAD'] = [f"R{row}C{col}_{x}4" for x in "DCBA"]
            ram16.portmap['RAD'] = [f"R{row}C{col}_{x}0" for x in "DCBA"]
            ram16.portmap['DO'] = [f"R{row}C{col}_F{x}" for x in range(4, -1, -1)]
            mod.wires.update(chain.from_iterable([x if isinstance(x, list) else [x] for x in ram16.portmap.values()]))
            mod.primitives[name] = ram16
        elif typ in {"OSC", "OSCZ", "OSCF", "OSCH", "OSCW", "OSCO"}:
            name = f"R{row}C{col}_{typ}"
            osc = codegen.Primitive(typ, name)
            for paramval in flags:
                param, _, val = paramval.partition('=')
                osc.params[param] = val
            portmap = db.grid[dbrow][dbcol].bels[bel].portmap
            for port, wname in portmap.items():
                osc.portmap[port] = f"R{row}C{col}_{wname}"
            mod.wires.update(osc.portmap.values())
            mod.primitives[name] = osc
        elif typ == "DFF":
            #print(flags)
            sd = False
            if 'SD' in flags:
                sd = True
                flags.remove('SD')
            kind, = flags # DFF only have one flag
            if kind == "RAM": continue
            idx = int(idx)
            port = dffmap[kind]
            name = f"R{row}C{col}_{typ}E_{idx}"
            dff = codegen.Primitive(kind+"E", name)
            dff.portmap['CLK'] = f"R{row}C{col}_CLK{idx//2}"
            if sd:
                dff.portmap['D'] = f"R{row}C{col}_SEL{idx}"
            else:
                dff.portmap['D'] = f"R{row}C{col}_F{idx}"
            dff.portmap['Q'] = f"R{row}C{col}_Q{idx}"
            dff.portmap['CE'] = f"R{row}C{col}_CE{idx//2}"
            if port:
                dff.portmap[port] = f"R{row}C{col}_LSR{idx//2}"
            mod.wires.update(dff.portmap.values())
            mod.primitives[name] = dff
            cst.cells[name] = (row, col, int(idx) // 2, _sides[int(idx) % 2])
        elif typ == "IOB":
            try:
                kind, = flags.intersection(iobmap.keys())
            except ValueError:
                continue
            flags.remove(kind)
            if kind == 'MIPI_IBUF':
                portmap = {}
                portmap['I'] = db.grid[dbrow][dbcol].bels["IOBA"].portmap['I']
                portmap['IB'] = db.grid[dbrow][dbcol].bels["IOBB"].portmap['I']
                portmap['OEN'] = db.grid[dbrow][dbcol].bels["IOBA"].portmap['OE']
                portmap['OENB'] = db.grid[dbrow][dbcol].bels["IOBB"].portmap['OE']
                portmap['OH'] = db.grid[dbrow][dbcol].bels["IOBA"].portmap['O']
                portmap['OB'] = db.grid[dbrow][dbcol].bels["IOBB"].portmap['O']
                portmap['HSREN'] = db.grid[dbrow][dbcol].bels["IOLOGICB"].portmap['SETN']
                portmap['OL'] = db.grid[dbrow][dbcol + 1].bels["IOBA"].portmap['O']
            elif kind == 'MIPI_OBUF':
                portmap = {}
                portmap['I'] = db.grid[dbrow][dbcol].bels["IOBA"].portmap['I']
                portmap['IB'] = db.grid[dbrow][dbcol].bels["IOBB"].portmap['I']
                portmap['IL'] = db.grid[dbrow][dbcol].bels["IOBA"].portmap['I']
                portmap['MODESEL'] = db.grid[dbrow][dbcol].bels["IOBA"].portmap['OE']
            elif kind == 'I3C_IOBUF':
                portmap = db.grid[dbrow][dbcol].bels[bel].portmap.copy()
                portmap['MODESEL'] = portmap['OE']
                portmap.pop('OE', None)
            else:
                portmap = db.grid[dbrow][dbcol].bels[bel].portmap
            name = f"R{row}C{col}_{kind}_{idx}"
            wires = set(iobmap[kind]['wires'])
            ports = set(chain.from_iterable(iobmap[kind].values())) - wires

            iob = codegen.Primitive(kind, name)

            if idx in iologic_detected:
                wires_suffix = '_IOL'
            else:
                wires_suffix = ''
            for port in wires:
                wname = portmap[port]
                if kind == 'MIPI_IBUF':
                    if port == 'OH':
                        wires_suffix_mipi = wires_suffix
                    else:
                        wires_suffix_mipi = ''
                    iob.portmap[portname(port)] = f"R{row}C{col}_{wname}{wires_suffix_mipi}"
                elif kind == 'MIPI_OBUF':
                    if port == 'I':
                        wires_suffix_mipi = wires_suffix
                    else:
                        wires_suffix_mipi = ''
                    iob.portmap[portname(port)] = f"R{row}C{col}_{wname}{wires_suffix_mipi}"
                else:
                    iob.portmap[portname(port)] = f"R{row}C{col}_{wname}{wires_suffix}"

            for port in ports:
                iob.portmap[port] = f"R{row}C{col}_{port}{idx}"

            wnames = [f"R{row}C{col}_{portmap[w]}" for w in iobmap[kind]['wires']]
            mod.wires.update(wnames)
            for direction in ['inputs', 'outputs', 'inouts']:
                wnames = [f"R{row}C{col}_{w}{idx}" for w in iobmap[kind].get(direction, [])]
                getattr(mod, direction).update(wnames)
            mod.primitives[name] = iob
            # constraints
            pos = chipdb.loc2pin_name(db, dbrow, dbcol)
            # XXX tangnano4k uses IOT30 not found in the package
            #bank = chipdb.loc2bank(db, dbrow, dbcol)
            cst.ports[name] = f"{pos}{idx}"
            if kind[0:5] == 'TLVDS':
                cst.ports[name] = f"{pos}{idx},{pos}{chr(ord(idx) + 1)}"
            #iostd = _banks.get(bank)
            #if iostd:
            #    cst.attrs.setdefault(name, {}).update({"IO_TYPE" : iostd})
            for flg in flags:
                name_val = flg.split('=')
                cst.attrs.setdefault(name, {}).update({name_val[0] : name_val[1]})

    # gnd = codegen.Primitive("GND", "mygnd")
    # gnd.portmap["G"] = "VSS"
    # mod.primitives["mygnd"] = gnd
    # vcc = codegen.Primitive("VCC", "myvcc")
    # vcc.portmap["V"] = "VCC"
    # mod.primitives["myvcc"] = vcc
    mod.assigns.append(("VCC", "1'b1"))
    mod.assigns.append(("VSS", "1'b0"))

def default_device_config():
    return {
        "JTAG regular_io":          "false",
        "SSPI regular_io":          "false",
        "MSPI regular_io":          "false",
        "READY regular_io":         "false",
        "DONE regular_io":          "false",
        "RECONFIG_N regular_io":    "false",
        "MODE regular_io":          "false",
        "CRC_check": "true",
        "compress": "false",
        "encryption": "false",
        "security_bit_enable": "true",
        "bsram_init_fuse_print": "true",
        "download_speed": "250/100",
        "spi_flash_address": "0x00FFF000",
        "format": "txt",
        "background_programming": "false",
        "secure_mode": "false"}

def fix_pll_ports(pll):
    for portname, up_limit in [('PSDA', 4), ('DUTYDA', 4), ('FDLY', 4), ('FBDSEL', 6), ('IDSEL', 6), ('ODSEL', 6)]:
        for n in range(0, up_limit):
            if f'{portname}{n}' in pll.portmap.keys():
                port = pll.portmap.setdefault(portname, [])
                port.append(pll.portmap[f'{portname}{n}'])
                pll.portmap.pop(f'{portname}{n}')

def fix_plls(db, mod):
    for pll_name, pll in [pr for pr in mod.primitives.items() if pr[1].typ in {'rPLL', 'PLLVR'}]:
        if 'INSEL' not in pll.params.keys():
            del mod.primitives[pll_name]
            continue
        disable_unused_pll_ports(pll)
        modify_pll_inputs(db, pll)
        mod.wires.update(pll.portmap.values())
        fix_pll_ports(pll)

def main():
    pil_available = True
    try:
        from PIL import Image
    except ImportError:
        pil_available = False

    parser = argparse.ArgumentParser(description='Unpack Gowin bitstream')
    parser.add_argument('bitstream')
    parser.add_argument('-d', '--device', required=True)
    parser.add_argument('-o', '--output', default='unpack.v')
    parser.add_argument('-s', '--cst', default=None)
    parser.add_argument('--noalu', action = 'store_true')
    if pil_available:
        parser.add_argument('--png')

    args = parser.parse_args()

    global _device
    _device = args.device
    # For tool integration it is allowed to pass a full part number
    m = re.match("GW1N(S?)[A-Z]*-(LV|UV|UX)([0-9])C?([A-Z]{2}[0-9]+P?)(C[0-9]/I[0-9])", _device)
    if m:
        mods = m.group(1)
        luts = m.group(3)
        _device = f"GW1N{mods}-{luts}"

    with importlib.resources.path('apycula', f'{args.device}.pickle') as path:
        with closing(gzip.open(path, 'rb')) as f:
            db = pickle.load(f)

    global _pinout
    _pinout = db.pinout[_device][_packages[_device]]

    bitmap, _, _, extra_slots = read_bitstream(args.bitstream)
    bm = chipdb.tile_bitmap(db, bitmap)
    mod = codegen.Module()
    cst = codegen.Constraints()

    if pil_available and args.png:
        display(args.png, bitmap)

    # make wire aliases from Himbaechel nodes
    def by_name_len(el):
        return len(el[2])

    for node_desc in db.nodes.values():
        root_wire = None
        for row, col, wire in sorted(node_desc[1], key = by_name_len):
            wire_name = f'R{row + 1}C{col + 1}_{wire}'
            if not root_wire:
                root_wire = wire_name
                continue
            mod.wire_aliases[wire_name] = root_wire
    for row in range(db.rows):
        for col in range(db.cols):
            for i in [1, 2]:
                mod.wire_aliases[chipdb.wire2global(row + 0, col + 1, db, f'N1{i}1')] = f'R{row + 1}C{col + 1}_SN{i}0'
                mod.wire_aliases[chipdb.wire2global(row + 2, col + 1, db, f'S1{i}1')] = f'R{row + 1}C{col + 1}_SN{i}0'
                mod.wire_aliases[chipdb.wire2global(row + 1, col + 0, db, f'W1{i}1')] = f'R{row + 1}C{col + 1}_EW{i}0'
                mod.wire_aliases[chipdb.wire2global(row + 1, col + 2, db, f'E1{i}1')] = f'R{row + 1}C{col + 1}_EW{i}0'

    # Slots have no wires only func fuses
    if extra_slots:
        for slot_idx, slot_bitmap in extra_slots.items():
            if slot_idx in {2, 3, 4, 5, 6, 8}:
                av = parse_attrvals(slot_bitmap, db.rev_logicinfo('PLL'), db.shortval[1024]['PLL'], attrids.pll_attrids, "PLL")
                print('Slot:', slot_idx, av)
            elif slot_idx in {1}:
                av = parse_attrvals(slot_bitmap, db.rev_logicinfo('ADC'), db.shortval[1026]['ADC'], attrids.adc_attrids, "ADC")
                print('Slot:', slot_idx, av)
            else:
                print('Unknown Slot:', slot_idx)

    # XXX this PLLs have empty main cell
    if _device in {'GW1N-9C', 'GW1N-9'}:
        bm_pll = chipdb.tile_bitmap(db, bitmap, empty = True)
        bm[(9, 0)] = bm_pll[(9, 0)]
        bm[(9, 46)] = bm_pll[(9, 46)]
    if _device in {'GW2A-18', 'GW2A-18C'}:
        bm_pll = chipdb.tile_bitmap(db, bitmap, empty = True)
        bm[(9, 0)] = bm_pll[(9, 0)]
        bm[(9, 55)] = bm_pll[(9, 55)]
        bm[(45, 0)] = bm_pll[(45, 0)]
        bm[(45, 55)] = bm_pll[(45, 55)]

    # banks first: need to know iostandards
    for pos in db.corners.keys():
        row, col = pos
        try:
            t = bm[(row, col)]
        except KeyError:
            continue
        bels, pips, clock_pips = parse_tile_(db, row, col, t, bm)
        #print("bels:", bels)
        tile2verilog(row, col, bels, pips, clock_pips, mod, cst, db)

    for idx, t in bm.items():
        row, col = idx
        # skip banks & dual pisn
        if (row, col) in db.corners:
            continue
        bels, pips, clock_pips = parse_tile_(db, row, col, t, bm, noiostd = False)
        #print("bels:", idx, bels)
        #print(pips)
        #print(clock_pips)
        if args.noalu:
            removeALUs(bels)
        else:
            removeLUTs(bels)
        ram16_remove_bels(bels)
        tile2verilog(row, col, bels, pips, clock_pips, mod, cst, db)

    fix_plls(db, mod)

    with open(args.output, 'w') as f:
        mod.write(f)

    if args.cst:
        with open(args.cst, 'w') as f:
            cst.write(f)

if __name__ == "__main__":
    main()
