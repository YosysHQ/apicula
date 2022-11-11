import sys
import os
import re
import random
import numpy as np
from itertools import chain, count
import pickle
import argparse
import importlib.resources
from apycula import codegen
from apycula import chipdb
from apycula.attrids import pll_attrids, pll_attrvals
from apycula.bslib import read_bitstream
from apycula.wirenames import wirenames

# bank iostandards
# XXX default io standard may be board-dependent!
_banks = {'0': "LVCMOS18", '1': "LVCMOS18", '2': "LVCMOS18", '3': "LVCMOS18"}

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
def get_attr_name(attrname_table, code):
    for name, cod in attrname_table.items():
        if cod == code:
            return name
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
def pll_attrs_refine(in_attrs):
    res = set()
    for attr, val in in_attrs.items():
        if attr not in _pll_attrs.keys():
            continue
        attr = _pll_attrs[attr]
        new_val = f'"{val}"'
        if attr in ['CLKOUTP_DLY_STEP', 'CLKOUT_DLY_STEP']:
            new_val = val / 50
        elif attr in ['PSDA_SEL', 'DUTYDA_SEL']:
            new_val = f'"{val:04b}"'
        elif attr in ['IDIV_SEL', 'FBDIV_SEL']:
            new_val = val - 1
        elif attr == 'DYN_SDIV_SEL':
            new_val = val - 2
        elif attr == 'ODIV_SEL':
            new_val = val
        res.add(f'{attr}={new_val}')
    return res

# parse attributes and values use 'logicinfo' table
# returns {attr: value}
# attribute names are decoded with the attribute table, but the values are returned in raw form
def parse_attrvals(tile, logicinfo_table, fuse_table, attrname_table):
    def is_neg_key(key):
        for k in key:
            if k < 0:
                return True
        return False

    def is_pos_key(key):
        return not is_neg_key(key)

    res = {}
    set_mask = set()
    zero_mask = set()
    # collect masks
    for av, bits in fuse_table.items():
        if is_neg_key(av):
            zero_mask.update(bits)
        else:
            set_mask.update(bits)
    set_bits =  {(row, col) for row, col in set_mask if tile[row][col] == 1}
    zero_bits = {(row, col) for row, col in set_mask if tile[row][col] == 0}
    # find candidates from fuse table
    attrvals = set()
    for raw_bits, test_fn in [(zero_bits, is_neg_key), (set_bits, is_pos_key)]:
        cnd = { av: bits for av, bits in fuse_table.items() if test_fn(av) and bits.issubset(raw_bits)}
        for av, bits in cnd.items():
            keep = True
            for bt in cnd.values():
                if bits !=  bt and bits.issubset(bt):
                    keep = False
                    break
            if keep:
                attrvals.add(av)

    for key in attrvals:
        for av in [a for a in key if a != 0]:
            attr, val = logicinfo_table[av]
            res[get_attr_name(attrname_table, attr)] = val
    return res

# { (row, col, type) : idx}
# type 'A'| 'B'
_pll_cells = {}

# returns the A cell of the PLL
def get_pll_A(db, row, col, typ):
    if typ == 'B':
        col -= 1
    return row, col, 'A'

# noiostd --- this is the case when the function is called
# with iostd by default, e.g. from the clock fuzzer
# With normal gowin_unpack io standard is determined first and it is known.
# (bels, pips, clock_pips)
def parse_tile_(db, row, col, tile, default=True, noalias=False, noiostd = True):
    # TLVDS takes two BUF bels, so skip the B bels.
    skip_bels = set()
    #print((row, col))
    tiledata = db.grid[row][col]
    clock_pips = {}
    bels = {}
    for name, bel in tiledata.bels.items():
        if name.startswith("RPLL"):
            idx = _pll_cells.setdefault(get_pll_A(db, row, col, name[4]), len(_pll_cells))
            attrvals = pll_attrs_refine(parse_attrvals(tile, db.logicinfo['PLL'], db.shortval[tiledata.ttyp]['PLL'], pll_attrids))
            modes = bels.setdefault(f'{name}{idx}', set())
            for attrval in attrvals:
                modes.add(attrval)
            print(idx, modes)
            continue
        if name.startswith("IOB"):
            #print(name)
            if noiostd:
                iostd = ''
            else:
                try: # we can ask for invalid pin here because the IOBs share some stuff
                    iostd = _banks[chipdb.loc2bank(db, row, col)]
                except KeyError:
                    iostd = ''
            # Here we don't use a mask common to all modes (it didn't work),
            # instead we try the longest bit sequence first.
            for mode, mode_rec in sorted(bel.iob_flags[iostd].items(),
                key = _io_mode_sort_func, reverse = True):
                #print(mode, mode_rec.decode_bits)
                mode_bits = {(row, col)
                             for row, col in mode_rec.decode_bits
                             if tile[row][col] == 1}
                #print("read", mode_bits)
                if mode_rec.decode_bits == mode_bits:
                    zeros = zero_bits(mode, bel.iob_flags[iostd])
                    #print("zeros", zeros)
                    used_bits = {tile[row][col] for row, col in zeros}
                    if not any(used_bits):
                        bels.setdefault(name, set()).add(mode)
                        #print(f"found: {mode}")
                        # mode found
                        break

            for flag, flag_parm in bel.iob_flags[iostd][mode].flags.items():
                flag_bits = {(row, col)
                              for row, col in flag_parm.mask
                              if tile[row][col] == 1}
                for opt, bits in flag_parm.options.items():
                    if bits == flag_bits:
                        bels.setdefault(name, set()).add(f"{flag}={opt}")
            # skip B bel
            if mode.startswith('TLVDS'):
                skip_bels.update({name[:-1] + 'B'})
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
                    if name[0:4] == "BANK":
                        # set iostd for bank
                        flag_bits = {(row, col)
                                      for row, col in bel.bank_mask
                                      if tile[row][col] == 1}
                        for iostd, bits in bel.bank_flags.items():
                            if bits == flag_bits:
                                if iostd.startswith('LVDS25'):
                                    iostd = iostd[7:]
                                _banks[name[4:]] = iostd
                                break
                        # mode found
                        break
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
            # only report connection aliased to by a spine
            if bits == used_bits and (noalias or (row, col, src) in db.aliases):
                clock_pips[dest] = src

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
    "IOBUF": {"wires": ["I", "O", "OE"], "inouts": ["IO"]},
    "TLVDS_OBUF": {"wires": ["I"], "outputs": ["O", "OB"]},
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


def have_iologic(bels):
    return 'ODDRA' in bels.keys() or 'ODDRB' in bels.keys()

def move_iologic(bels):
    res = []
    if 'ODDRA' in bels.keys():
        res.append(('ODDRA', bels['ODDRA']))
    if 'ODDRB' in bels.keys():
        res.append(('ODDRB', bels['ODDRB']))
    res += [(bel, flags) for bel, flags in bels.items() if not bel.startswith('ODDR')]
    return res

_sides = "AB"
def tile2verilog(dbrow, dbcol, bels, pips, clock_pips, mod, cst, db):
    # db is 0-based, floorplanner is 1-based
    row = dbrow+1
    col = dbcol+1
    aliases = db.grid[dbrow][dbcol].aliases
    for dest, src in chain(pips.items(), aliases.items(), clock_pips.items()):
        srcg = chipdb.wire2global(row, col, db, src)
        destg = chipdb.wire2global(row, col, db, dest)
        mod.wires.update({srcg, destg})
        mod.assigns.append((destg, srcg))

    belre = re.compile(r"(IOB|LUT|DFF|BANK|CFG|ALU|RAM16|ODDR|OSC[ZFH]?|BUFS|RPLL[AB])(\w*)")
    if have_iologic(bels):
        bels_items = move_iologic(bels)
    else:
        bels_items = bels.items()

    iologic_detected = None
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
        elif typ.startswith("RPLL"):
            name = f"PLL_{idx}"
            pll = mod.primitives.setdefault(name, codegen.Primitive("rPLL", name))
            for paramval in flags:
                param, _, val = paramval.partition('=')
                pll.params[param] = val
            portmap = db.grid[dbrow][dbcol].bels[bel[:-1]].portmap
            for port, wname in portmap.items():
                pll.portmap[port] = f"R{row}C{col}_{wname}"
            mod.wires.update(pll.portmap.values())
        elif typ == "ALU":
            #print(flags)
            kind, = flags # ALU only have one flag
            idx = int(idx)
            name = f"R{row}C{col}_ALU_{idx}"
            if kind == 'hadder':
                kind = '0'
            if kind in "012346789": # main ALU
                alu = codegen.Primitive("ALU", name)
                alu.params["ALU_MODE"] = kind
                alu.portmap['SUM'] = f"R{row}C{col}_F{idx}"
                alu.portmap['CIN'] = f"R{row}C{col}_CIN{idx}"
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
            ram16.portmap['DI'] = [f"R{row}C{col}_{x}5" for x in "ABCD"]
            ram16.portmap['CLK'] = f"R{row}C{col}_CLK2"
            ram16.portmap['WRE'] = f"R{row}C{col}_LSR2"
            ram16.portmap['WAD'] = [f"R{row}C{col}_{x}4" for x in "ABCD"]
            ram16.portmap['RAD'] = [f"R{row}C{col}_{x}0" for x in "ABCD"]
            ram16.portmap['DO'] = [f"R{row}C{col}_F{x}" for x in range(4)]
            mod.wires.update(chain.from_iterable([x if isinstance(x, list) else [x] for x in ram16.portmap.values()]))
            mod.primitives[name] = ram16
        elif typ in {"OSC", "OSCZ", "OSCF", "OSCH"}:
            name = f"R{row}C{col}_{typ}"
            osc = codegen.Primitive(typ, name)
            divisor, = flags
            osc.params["FREQ_DIV"] = f"{divisor*2}"
            portmap = db.grid[dbrow][dbcol].bels[bel].portmap
            for port, wname in portmap.items():
                osc.portmap[port] = f"R{row}C{col}_{wname}"
            mod.wires.update(osc.portmap.values())
            mod.primitives[name] = osc
        elif typ == "DFF":
            #print(flags)
            kind, = flags # DFF only have one flag
            if kind == "RAM": continue
            idx = int(idx)
            port = dffmap[kind]
            name = f"R{row}C{col}_{typ}E_{idx}"
            dff = codegen.Primitive(kind+"E", name)
            dff.portmap['CLK'] = f"R{row}C{col}_CLK{idx//2}"
            dff.portmap['D'] = f"R{row}C{col}_F{idx}"
            dff.portmap['Q'] = f"R{row}C{col}_Q{idx}"
            dff.portmap['CE'] = f"R{row}C{col}_CE{idx//2}"
            if port:
                dff.portmap[port] = f"R{row}C{col}_LSR{idx//2}"
            mod.wires.update(dff.portmap.values())
            mod.primitives[name] = dff
            cst.cells[name] = (row, col, int(idx) // 2, _sides[int(idx) % 2])
        elif typ == "ODDR":
            iologic_detected = idx
            portmap = db.grid[dbrow][dbcol].bels[bel].portmap
            name = f"R{row}C{col}_ODDR{idx}"
            oddr = codegen.Primitive("ODDR", name)
            for port in {'TX', 'D0', 'D1', 'CLK'}:
                wname = portmap[port]
                oddr.portmap[port] = f"R{row}C{col}_{wname}"
            oddr.portmap['Q0'] = f"R{row}C{col}_{portmap['D0']}_IOL"
            #oddr.portmap['Q1'] = f"R{row}C{col}_{portmap['Q1']}_IOL"
            mod.wires.update(oddr.portmap.values())
            # XXX implement ODDR with TBUF
            oddr.portmap['Q1'] = ""
            mod.primitives[name] = oddr
        elif typ == "IOB":
            try:
                kind, = flags.intersection(iobmap.keys())
            except ValueError:
                continue
            flags.remove(kind)
            portmap = db.grid[dbrow][dbcol].bels[bel].portmap
            name = f"R{row}C{col}_{kind}_{idx}"
            wires = set(iobmap[kind]['wires'])
            ports = set(chain.from_iterable(iobmap[kind].values())) - wires

            iob = codegen.Primitive(kind, name)

            if iologic_detected == idx:
                wires_suffix = '_IOL'
            else:
                wires_suffix = ''
            for port in wires:
                wname = portmap[port]
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
            bank = chipdb.loc2bank(db, dbrow, dbcol)
            cst.ports[name] = f"{pos}{idx}"
            if kind[0:5] == 'TLVDS':
                cst.ports[name] = f"{pos}{idx},{pos}{chr(ord(idx) + 1)}"
            iostd = _banks.get(bank)
            if iostd:
                cst.attrs.setdefault(name, {}).update({"IO_TYPE" : iostd})
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

def main():
    parser = argparse.ArgumentParser(description='Unpack Gowin bitstream')
    parser.add_argument('bitstream')
    parser.add_argument('-d', '--device', required=True)
    parser.add_argument('-o', '--output', default='unpack.v')
    parser.add_argument('-s', '--cst', default=None)
    parser.add_argument('--noalu', action = 'store_true')

    args = parser.parse_args()

    device = args.device
    # For tool integration it is allowed to pass a full part number
    m = re.match("GW1N([A-Z]*)-(LV|UV|UX)([0-9])C?([A-Z]{2}[0-9]+)(C[0-9]/I[0-9])", device)
    m = re.match("GW1N(S?)[A-Z]*-(LV|UV|UX)([0-9])C?([A-Z]{2}[0-9]+P?)(C[0-9]/I[0-9])", device)
    if m:
        mods = m.group(1)
        luts = m.group(3)
        device = f"GW1N{mods}-{luts}"

    with importlib.resources.open_binary("apycula", f"{device}.pickle") as f:
        db = pickle.load(f)

    bitmap = read_bitstream(args.bitstream)[0]
    bm = chipdb.tile_bitmap(db, bitmap)
    mod = codegen.Module()
    cst = codegen.Constraints()

    for (drow, dcol, dname), (srow, scol, sname) in db.aliases.items():
        src = f"R{srow+1}C{scol+1}_{sname}"
        dest = f"R{drow+1}C{dcol+1}_{dname}"
        mod.wires.update({src, dest})
        mod.assigns.append((dest, src))

    # banks first: need to know iostandards
    for pos in db.corners.keys():
        row, col = pos
        try:
            t = bm[(row, col)]
        except KeyError:
            continue
        bels, pips, clock_pips = parse_tile_(db, row, col, t)
        tile2verilog(row, col, bels, pips, clock_pips, mod, cst, db)

    for idx, t in bm.items():
        row, col = idx
        # skip banks & dual pisn
        if (row, col) in db.corners:
            continue
        #for bitrow in t:
        #    print(*bitrow, sep='')
        #if idx == (5, 0):
        #    from fuse_h4x import *
        #    fse = readFse(open("/home/pepijn/bin/gowin/IDE/share/device/GW1N-1/GW1N-1.fse", 'rb'))
        #    breakpoint()
        bels, pips, clock_pips = parse_tile_(db, row, col, t, noiostd = False)
        #print(bels)
        #print(pips)
        #print(clock_pips)
        if args.noalu:
            removeALUs(bels)
        else:
            removeLUTs(bels)
        ram16_remove_bels(bels)
        tile2verilog(row, col, bels, pips, clock_pips, mod, cst, db)

    with open(args.output, 'w') as f:
        mod.write(f)

    if args.cst:
        with open(args.cst, 'w') as f:
            cst.write(f)

if __name__ == "__main__":
    main()
