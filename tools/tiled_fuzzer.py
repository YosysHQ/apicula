#!/usr/bin/env python3
"""Compare Apicula with the vendor on randomly configured primitives.

    pip install -e .[fuzz]
    GOWINHOME=... python3 tools/tiled_fuzzer.py -d GW1N-9C [-n 20] [--prims LUT4 DFFRE]
    GOWINHOME=... python3 tools/tiled_fuzzer.py -d GW1N-9C --replay out/batch0/mismatch_inst3.json

Hypothesis (tools/primitive_strategies.py) draws single primitive instances
("cases") with parameters from the IDE's primitive.xml. As the old tiled fuzzer
did, many cases are placed on separate sites in one design, so one vendor run
checks many of them. Each design goes through:

- the vendor: gw_sh `run pnr` on the netlist, placement fixed with INS_LOC;
- Apicula: Yosys (no synthesis), nextpnr with the same placement given as BEL
  attributes, then gowin_pack.

Each case is then checked twice:

- Both bitstreams are unpacked with gowin_unpack (tools/unpacked_netlist.py),
  and the cell on the case's site is compared: type and parameters (LUT INIT
  included) and which inputs are tied to a constant. Nets are not traced.
  Vendor and Apicula must agree, and Apicula must agree with the generated
  case.
- The bitstreams are compared tile by tile on the bits that are not routing
  fuses, which catches fuses the unpacker does not decode. Differences also
  present in a design with no cases (the I/O harness) are subtracted.

Statuses: ok; mismatch (vendor and Apicula differ); decode (they agree with
each other but not with the generated case: an unpacker bug, or a mistake both
make); invalid (the vendor rejected the case: a rule the generator should
learn); unsupported (the Apicula flow failed on it: a failure to fix, like a
mismatch). The exit status is 1 if any case failed. A design that fails in either flow is split in half and rerun
until the failing case is alone. Failing cases are written out on
their own for `--replay`.

Tools: YOSYS and NEXTPNR environment variables, else yosys/nextpnr-himbaechel,
else their yowasp- versions. `-j` runs several designs at the same time; the
vendor and Apicula flows of a design also run at the same time when neither
needs the other's placement.
"""
import argparse
import collections
import concurrent.futures
import copy
import functools
import json
import os
import random
import re
import subprocess
import sys

TOOLS = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(TOOLS)
sys.path[:0] = [REPO, TOOLS]  # this checkout's apycula, not an installed one
import primitive_strategies as ps  # noqa: E402
import unpacked_netlist  # noqa: E402
from gowin_primitives import tool, read_cell_library  # noqa: E402
from apycula import attrids, bslib, chipdb, codegen, gowin_unpack  # noqa: E402
from apycula.chipdb_builder import DEVICE_PARAMS  # noqa: E402

# device: (vendor device, part number, package), as the chipdbs are built. The
# vendor runs on GW5A-25A used the production part rather than the ES one.
PART_OVERRIDES = {'GW5A-25A': 'GW5A-LV25MG121NC1/I0'}
DEVICES = {dev: (p['device'], PART_OVERRIDES.get(dev, p['partnumber']), p['package'])
           for dev, p in DEVICE_PARAMS.items()}

# Module port lists, by port direction
PORT_LISTS = {'input': 'inputs', 'output': 'outputs', 'inout': 'inouts'}

WIDELUTS_PER_DESIGN = 8
DIVIDER_LOAD = {'CLKDIV2', 'DHCEN', 'DHCENC', 'DHCE', 'DCC'}
CLOCK_INPUTS = {'HCLKIN', 'CLKIN', 'CLKIN0', 'CLK0', 'I'}
CONTROL_PORTS = {'CE', 'SET', 'RESET', 'PRESET', 'CLEAR', 'GE', 'OSCEN'}

# Ports the vendor and Yosys' cell library name differently. The Apicula side
# renames them before Yosys; the mismatch itself is recorded in
# doc/agent/primitive-params.md (a vendor-style netlist with latches does not
# go through Yosys).
YOSYS_PORTS = {re.compile(r'DLN?[CP]?E?$'): {'G': 'CLK', 'GE': 'CE'}}


def lone_pads(ports, prim):
    """Pad ports of an I/O primitive without a site kind: its inouts, else the
    inputs of an input buffer or the outputs of an output buffer."""
    pads = [p for p, (d, _) in ports.items() if d == 'inout']
    if pads or 'BUF' not in prim:
        return pads
    if 'IBUF' in prim:
        return [p for p, (d, w) in ports.items() if d == 'input' and w == 1 and re.fullmatch(r'IB?\d?', p)]
    return [p for p, (d, w) in ports.items() if d == 'output' and w == 1 and re.fullmatch(r'OB?\d?', p)]

# Vendor log codes that make a case invalid rather than a mismatch.
INVALID_CODES = {'PA1002': 'invalid parameter value', 'CT1094': 'not placed at its constraint'}


# ---------------------------------------------------------------- sites

class Sites:
    """Free sites of each kind. A slice (CLS) holds two LUT cases or one DFF case,
    because the two flip-flops of a slice share clock, CE and set/reset modes.
    Sites are (row, col, cls, 'A'|'B') for slices and (row, col, 'BSRAM', n) for
    the n-th BSRAM of a row, which is how the vendor numbers them in INS_LOC."""

    def __init__(self, db, rng, pins, pinout):
        self.cls = [(r, c, cls) for r in range(db.rows) for c in range(db.cols)
                    for cls in range(4)
                    if {f'LUT{2 * cls}', f'LUT{2 * cls + 1}', f'DFF{2 * cls}'} <= db[r, c].bels.keys()]
        rng.shuffle(self.cls)
        # an ALU case goes in ALU1 (CLS0, B): with CIN tied to GND, nextpnr puts a
        # carry-in head in ALU0 of the same chain
        self.alu = [(r, c, 0, 'B') for r in range(db.rows) for c in range(db.cols)
                    if {'ALU0', 'ALU1'} <= db[r, c].bels.keys()]
        rng.shuffle(self.alu)
        # DSP blocks: the main tile with a 'DSP' bel, numbered per row as the
        # vendor's DSP_R<row>[n]; its DSP_AUX tiles are to the right
        self.dsp = []
        for r in range(db.rows):
            cols = [c for c in range(db.cols) if 'DSP' in db[r, c].bels]
            self.dsp += [(r, c, 'DSP', n) for n, c in enumerate(cols)]
        rng.shuffle(self.dsp)
        # SSRAM takes a whole logic tile
        self.ssram = [(r, c, 'RAM16', '-') for r in range(db.rows) for c in range(db.cols)
                      if 'RAM16' in db[r, c].bels]
        rng.shuffle(self.ssram)
        self.bsram = []
        for r in range(db.rows):
            cols = [c for c in range(db.cols) if 'BSRAM' in db[r, c].bels]
            self.bsram += [(r, c, 'BSRAM', n) for n, c in enumerate(cols)]
        rng.shuffle(self.bsram)
        # rPLLs: the vendor names them PLL_L and PLL_R by side, and PLL_L[n] when a
        # side has several (n counted top to bottom). Skip PLLs the chipdb marks
        # disabled, which nextpnr does not offer (GW2A-18C rows 10).
        self.pll = []
        for side, cols in (('L', range(db.cols // 2)), ('R', range(db.cols // 2, db.cols))):
            plls = [(r, c) for r in range(db.rows) for c in cols if 'RPLLA' in db[r, c].bels]
            for n, (r, c) in enumerate(plls):
                if not db.extra_func.get((r, c), {}).get('disabled', {}).get('PLL'):
                    self.pll.append((r, c, 'PLL', side if len(plls) == 1 else f'{side}[{n}]'))
        self.singletons = {'osc'}
        # GW5A PLLs (extra_func 'pll'), configured through a bitstream slot. The
        # vendor names them by side and row order (checked on GW5A-25A: PLL_L[0]
        # is slot 5, PLL_L[1] slot 6, PLL_R[0] slot 3, PLL_R[1] slot 2, PLL_T
        # slot 4, PLL_B slot 8).
        by_side = collections.defaultdict(list)
        for (r, c), f in sorted(db.extra_func.items()):
            if 'pll' in f:
                side = 'L' if c == 0 else 'R' if c == db.cols - 1 else 'T' if r == 0 else 'B'
                by_side[side].append((r, c))
        self.plla = [(r, c, 'PLLA', side if len(locs) == 1 else f'{side}[{n}]')
                     for side, locs in by_side.items() for n, (r, c) in enumerate(locs)]
        # I/O: plain package pins (no special function) not used by the harness,
        # as (row, col, 'IOBA'|'IOBB', pin number)
        harness = {pins['clk'], pins['out'], *pins['in']}
        self.iob = []
        for pin, (name, funcs) in pinout.items():
            if not funcs and pin not in harness:
                r, c, ab = gowin_unpack.tbrl2rc(db, name)
                self.iob.append((r, c, f'IOB{ab}', pin))
        rng.shuffle(self.iob)
        # IDES16/OSER16 need an "X16 location" (vendor PR2046): pin A of a tile
        # whose io16 role is MAIN; the AUX tile beside it is used as well
        self.iob16 = [s for s in self.iob if s[2] == 'IOBA'
                      and db.extra_func.get(s[:2], {}).get('io16', {}).get('role') == 'MAIN']
        if not any('io16' in f for f in db.extra_func.values()):
            self.iob16 = self.iob  # no X16 data in the chipdb (GW5A): let the vendor say
        # differential pairs: A is the positive pin; TLVDS needs true-LVDS pins
        self.tlvds, self.elvds = [], []
        names = {name: pin for pin, (name, funcs) in pinout.items() if not funcs and pin not in harness}
        for name, pin in names.items():
            if name.endswith('A') and name[:-1] + 'B' in names:
                r, c, _ = gowin_unpack.tbrl2rc(db, name)
                bel = db[r, c].bels.get('IOBA')
                if bel and bel.is_diff:
                    site = (r, c, 'IOBA', [pin, names[name[:-1] + 'B']])
                    (self.tlvds if bel.is_true_lvds else self.elvds).append(site)
        rng.shuffle(self.tlvds)
        # emulated LVDS can use any differential pair
        self.elvds += self.tlvds
        rng.shuffle(self.elvds)


def io_bank(db, r, c, ab):
    """Bank of the I/O at row, col, 'A'|'B'."""
    return db.pin_bank.get(chipdb.rc2tbrl_0(db, r, c, ab))


HARNESS_IO_TYPE = {'3.3': 'LVCMOS33', '2.5': 'LVCMOS25', '1.8': 'LVCMOS18', '1.5': 'LVCMOS15', '1.2': 'LVCMOS12'}
IO_PAD = {'IBUF': 'I', 'OBUF': 'O', 'TBUF': 'O', 'IOBUF': 'IO'}
DIFF_PAD = {'IBUF': ['I', 'IB'], 'OBUF': ['O', 'OB'], 'TBUF': ['O', 'OB'], 'IOBUF': ['IO', 'IOB']}
IO_SITES = ('iob', 'diob')
PIN_SITES = {'iob', 'diob', 'iol'}  # placed by IO_LOC on a pin
IOL_INPUT = {'D', 'DI'}  # I/O logic port fed by the input buffer
IOL_OUTPUT = {'Q', 'Q0', 'DO'}  # port that feeds the output buffer


def io_pads(case, site):
    """[(port, pin)] of an I/O case: one pad, or the positive and negative pads
    of a differential buffer."""
    if case.site == 'diob':
        return list(zip(DIFF_PAD[case.prim.rpartition('_')[2]], site[3]))
    return [(IO_PAD[case.prim], site[3])]


def io_class(batch):
    """Bank voltage shared by the I/O cases of a batch, or None."""
    return next((ps.io_vccio(c) for c, _ in batch if c.site in PIN_SITES), None)


def allocate(cases, sites):
    """Split cases into batches and give each a site. Returns [[(case, site), ...]]."""
    queues = collections.defaultdict(list)
    for case in cases:
        queues[case.site].append(case)
    batches = []
    # clock primitives drive the harness output, so one per design; nextpnr and
    # the vendor place them
    batches += [[(case, None)] for case in queues.pop('clock', []) + queues.pop('lone', [])]
    # wide LUT trees: placed by both tools, in designs of their own, with no
    # LUT INIT used twice in a design
    batch, inits = [], set()
    for case in queues.pop('widelut', []):
        mine = {v for _, v in case.params}
        if len(batch) >= WIDELUTS_PER_DESIGN or mine & inits:
            batches.append(batch)
            batch, inits = [], set()
        batch.append((case, None))
        inits |= mine
    if batch:
        batches.append(batch)
    for kind in ('alu', 'ssram'):  # these use slices too, so in designs of their own
        group, free = queues.pop(kind, []), getattr(sites, kind)
        for i in range(0, len(group), len(free) or 1):
            batches.append(list(zip(group[i:i + len(free)], free)))
    # I/O cases: one bank voltage per design, since a bank has one VCCIO
    by_vccio = collections.defaultdict(list)
    for case in queues.pop('iob', []) + queues.pop('diob', []) + queues.pop('iol', []):
        pool = (case.prim.split('_')[0].lower() if case.site == 'diob'
                else 'iob16' if case.prim in ('IDES16', 'OSER16') else 'iob')
        by_vccio[(ps.io_vccio(case), pool)].append(case)
    for (_, pool), group in by_vccio.items():
        free = getattr(sites, pool)
        if not free:
            print(f'no {pool} sites for {sorted({c.prim for c in group})}; {len(group)} cases not run')
            continue
        for i in range(0, len(group), len(free)):
            batches.append(list(zip(group[i:i + len(free)], free)))
    while any(queues.values()):
        batch, free = [], iter(sites.cls)
        luts = queues['lut']
        dffs = queues['dff']
        for r, c, cls in free:
            if dffs and (not luts or len(dffs) * 2 >= len(luts)):
                batch.append((dffs.pop(), (r, c, cls, 'A')))
            elif luts:
                batch.append((luts.pop(), (r, c, cls, 'A')))
                if luts:
                    batch.append((luts.pop(), (r, c, cls, 'B')))
            else:
                break
        for kind, free in (('bsram', sites.bsram), ('pll', sites.pll), ('plla', sites.plla), ('dsp', sites.dsp)):
            for site in free:
                if queues[kind]:
                    batch.append((queues[kind].pop(), site))
        for kind in sites.singletons:
            if queues[kind]:
                batch.append((queues[kind].pop(), None))
        batches.append(batch)
    return batches


# ---------------------------------------------------------------- netlist

def pick_pins(db, vendor_device, device, package):
    pins = db.pinout.get(vendor_device, db.pinout[device])[package]
    plain = sorted((p for p, (_, funcs) in pins.items() if not funcs), key=lambda p: int(p) if p.isdigit() else p)
    clocks = [p for p, (_, funcs) in pins.items() if any(f.startswith('GCLK') for f in funcs)]
    return {'clk': clocks[0], 'out': plain[0], 'in': plain[1:6]}


def netlist(batch, spec, pins, harness_io_type=None):
    """One design: an I/O harness and the cases. I/O cases get a top-level pad
    with IO_LOC and their attributes as IO_PORT; the harness pins then use
    `harness_io_type`, so that banks agree on VCCIO."""
    mod, cst = codegen.Module(), codegen.Constraints()

    def inst(typ, name, conns, params=()):
        p = codegen.Primitive(typ, name)
        for port, (direction, width) in spec[typ]['ports'].items():
            if port in conns:
                p.portmap[port] = conns[port]
            elif direction == 'input':  # the vendor rejects unconnected or constant ports
                p.portmap[port] = ['gnd'] * width if width > 1 else 'gnd'
            else:
                # the vendor reads netlists per bit: a `wire [7:0]` on a port is
                # rejected with PA2060, a concatenation of 1-bit wires is not
                wires = [f'{name}_{port}' + (f'_{b}' if width > 1 else '') for b in range(width)]
                mod.wires.update(wires)
                p.portmap[port] = wires[0] if width == 1 else wires[::-1]
        p.params = dict(params)
        mod.primitives[name] = p
        return p

    mod.wires.add('gnd')
    inst('GND', 'harness_gnd', {'G': 'gnd'})
    data = []
    for i, pin in enumerate(['clk'] + [f'in{n}' for n in range(len(pins['in']))]):
        mod.inputs.add(f'{pin}_pad')
        mod.wires.add(pin)
        inst('IBUF', f'harness_ib_{pin}', {'I': f'{pin}_pad', 'O': pin})
        cst.ports[f'{pin}_pad'] = pins['clk'] if pin == 'clk' else pins['in'][i - 1]
        if harness_io_type:
            cst.attrs[f'{pin}_pad'] = {'IO_TYPE': harness_io_type}
        if pin != 'clk':
            data.append(pin)

    # As in the old tiled fuzzer, data inputs get their own undriven dummy wires
    # and outputs are left unconnected. Nothing is routed to a LUT, so neither
    # tool reorders its inputs, and no constant reaches a case. The vendor keeps
    # cells whose outputs are unused. Slice control inputs (clock, CE, set/reset)
    # come from input pins: left undriven they become constants, which hides the
    # flip-flop type. They use dedicated slice ports, so they cannot be reordered.
    names, wiring = {}, {}
    for i, (case, site) in enumerate(batch):
        name = f'inst{i}_{case.prim}'
        names[name] = (case, site)
        conns, sources = {}, data[i % len(data):] + data[:i % len(data)]
        if case.site == 'widelut':
            # MUX2_LUTn over two MUX2_LUT(n-1) ... over LUT4 leaves. Leaf inputs
            # are dummy wires; each mux level selects from its own data pin.
            inits = widelut_inits(case)

            def tree(level, leaves, path):
                if level == 4:
                    out = f'{name}_f{path}'
                    ins = {p: f'{name}_l{path}_{p}' for p in ('I0', 'I1', 'I2', 'I3')}
                    mod.wires.update([out, *ins.values()])
                    inst('LUT4', f'{name}_l{path}', {'F': out, **ins}, [('INIT', leaves[0])])
                    return out
                half = len(leaves) // 2
                i0 = tree(level - 1, leaves[:half], path + '0')
                i1 = tree(level - 1, leaves[half:], path + '1')
                out = f'{name}_o{path}'
                mod.wires.add(out)
                inst(f'MUX2_LUT{level}', f'{name}_m{path}' if path else name,
                     {'I0': i0, 'I1': i1, 'S0': sources[(level - 5) % len(sources)], 'O': out})
                return out

            tree(int(case.prim[-1]), inits, '')
            wiring[name] = {}
            continue
        if case.site in IO_SITES:
            for k, (pad, pin) in enumerate(io_pads(case, site)):
                conns[pad] = f'{name}_pad' + ('_n' if k else '')
                direction = spec[case.prim]['ports'][pad][0]
                getattr(mod, PORT_LISTS[direction]).add(conns[pad])
                cst.ports[conns[pad]] = pin
                cst.attrs[conns[pad]] = dict(case.params)
        if case.site == 'lone':
            # pads become top-level ports; the vendor picks their pins and
            # nextpnr gets the same ones (run_batch)
            for pad in lone_pads(spec[case.prim]['ports'], case.prim):
                conns[pad] = f'{name}_{pad}'
                getattr(mod, PORT_LISTS[spec[case.prim]['ports'][pad][0]]).add(conns[pad])
        if case.site == 'iol':
            # I/O logic must connect to an I/O buffer (vendor PR0018): an IBUF
            # feeding its data input, or an OBUF fed by its output
            ports = spec[case.prim]['ports']
            data_in = next((p for p in ports if p in IOL_INPUT), None)
            pad = f'{name}_pad'
            if data_in:
                conns[data_in] = f'{name}_in'
                mod.wires.add(conns[data_in])
                mod.inputs.add(pad)
                inst('IBUF', f'{name}_buf', {'I': pad, 'O': conns[data_in]})
            else:
                out = next(p for p in ports if p in IOL_OUTPUT)
                conns[out] = f'{name}_out'
                mod.wires.add(conns[out])
                mod.outputs.add(pad)
                inst('OBUF', f'{name}_buf', {'I': conns[out], 'O': pad})
            cst.ports[pad] = site[3]
            cst.attrs[pad] = {'IO_TYPE': ps.IOL_IO_TYPE}
        for port, (d, w) in spec[case.prim]['ports'].items():
            if d != 'input' or w != 1 or port in conns:
                continue
            if case.site == 'iol' and port in ('CLK', 'PCLK', 'FCLK'):
                conns[port] = 'clk'
                continue
            if case.site == 'lone' and 'CLK' in port:
                conns[port] = 'clk'
                continue
            if case.site == 'clock':
                # the first clock input from the clock pin, the rest from data pins
                # DCS: every clock input from the clock pin (nextpnr crashes
                # routing GW5A DCS inputs from plain pins)
                if port in CLOCK_INPUTS and 'clk' not in conns.values() \
                        or case.prim == 'DCS' and port.startswith('CLK') and port != 'CLKSEL':
                    conns[port] = 'clk'
                elif sources:
                    conns[port] = sources.pop(0)
                continue
            if case.site in IO_SITES and sources:
                conns[port] = sources.pop(0)  # buffer data and enable inputs
            elif port == 'CLKIN' and sources:
                # a plain pin: nextpnr moves a PLL fed from a dedicated PLL input
                # pin (the harness clock on GW2A-18C) before applying its BEL
                conns[port] = sources.pop(0)
            elif port in ('CLK', 'G'):
                conns[port] = 'clk'
            elif case.site == 'alu' and port == 'CIN':
                conns[port] = 'gnd'
            elif port in CONTROL_PORTS and sources:
                conns[port] = sources.pop(0)
            else:
                conns[port] = f'{name}_{port}'
                mod.wires.add(conns[port])
        ports = spec[case.prim]['ports']
        if 'DLLSTEP' in ports:
            # DLLSTEP must come from a DLL (PR2015; DDRDLL on GW5A, PR0015)
            dll = 'DLL' if 'DLL' in spec else 'DDRDLL'
            inst(dll, f'{name}_dll', {'CLKIN': 'clk'})
            conns['DLLSTEP'] = [f'{name}_dll_STEP_{b}' for b in range(ports['DLLSTEP'][1])][::-1]
        if 'DQSIN' in ports:
            # DQSIN must come from an input buffer (PR0014)
            pad = f'{name}_dqs_pad'
            mod.inputs.add(pad)
            mod.wires.add(f'{name}_dqs')
            inst('IBUF', f'{name}_dqs_buf', {'I': pad, 'O': f'{name}_dqs'})
            conns['DQSIN'] = f'{name}_dqs'
        inst(case.prim, name, conns, () if case.site in IO_SITES else case.params)
        wiring[name] = conns
        if case.site in PIN_SITES:
            pass  # placed by IO_LOC
        elif site and site[2] == 'BSRAM':
            cst.cells[name] = f'BSRAM_R{site[0] + 1}[{site[3]}]'
        elif site and site[2] in ('PLL', 'PLLA'):
            cst.cells[name] = f'PLL_{site[3]}'
        elif site and site[2] == 'DSP':
            cst.cells[name] = f'DSP_R{site[0] + 1}[{site[3]}][A]'
        elif site and site[2] == 'RAM16':
            cst.cells[name] = f'R{site[0] + 1}C{site[1] + 1}'
        elif site:
            cst.cells[name] = (site[0] + 1, site[1] + 1, site[2], site[3])

    mod.outputs.add('out_pad')
    # a clock primitive drives the output; otherwise it would have no load
    clock_out = next((f'{name}_{port}' for name, (case, _) in names.items() if case.site == 'clock'
                      for port, (d, _) in spec[case.prim]['ports'].items() if d == 'output'), None)
    for name, (case, _) in names.items():
        if case.prim in DIVIDER_LOAD:
            # these may only drive HCLK loads (vendor PR2060 on an OBUF), and
            # no output may dangle (PA2099): a CLKDIV with default settings on
            # each clock output passes it on
            outs = [p for p, (d, _) in spec[case.prim]['ports'].items() if d == 'output' and 'CLK' in p]
            for k, port in enumerate(outs):
                inst('CLKDIV', f'harness_div{k}', {'HCLKIN': f'{name}_{port}', 'RESETN': data[0]})
            clock_out = 'harness_div0_CLKOUT'
    inst('OBUF', 'harness_ob', {'I': clock_out or data[0], 'O': 'out_pad'})
    cst.ports['out_pad'] = pins['out']
    if harness_io_type:
        cst.attrs['out_pad'] = {'IO_TYPE': harness_io_type}
    return mod, cst, names, wiring


def bel_name(case, site):
    """nextpnr bel of a site, for the kinds placed with a BEL attribute (not
    PIN_SITES or FOLLOW_NEXTPNR)."""
    r, c, cls, ab = site
    if cls == 'BEL':
        return f'X{c}Y{r}/{ab}'
    if cls == 'BSRAM':
        return f'X{c}Y{r}/BSRAM'
    if cls in ('PLL', 'PLLA'):
        return f'X{c}Y{r}/PLL'
    return f'X{c}Y{r}/{"DFF" if case.site == "dff" else "LUT"}{2 * cls + "AB".index(ab)}'


# ---------------------------------------------------------------- flows

def run_vendor(workdir, mod, cst, vendor_device, part):
    pnr = codegen.Pnr()
    pnr.device, pnr.partnumber, pnr.netlist, pnr.cst = vendor_device, part, mod, cst
    os.makedirs(workdir, exist_ok=True)
    with open(os.path.join(workdir, 'gw_sh.log'), 'w') as log:
        return pnr.run_pnr(workdir=workdir, stdout=log)


def run_apicula(workdir, mod, cst, names, device, part):
    os.makedirs(workdir, exist_ok=True)
    mod = copy.deepcopy(mod)
    for prim in mod.primitives.values():
        for pattern, rename in YOSYS_PORTS.items():
            if pattern.match(prim.typ):
                prim.portmap = {rename.get(k, k): v for k, v in prim.portmap.items()}
    with open(os.path.join(workdir, 'top.v'), 'w') as f:
        mod.write(f)
    with open(os.path.join(workdir, 'top.cst'), 'w') as f:
        cst.write(f)
    log = open(os.path.join(workdir, 'tools.log'), 'w')
    # yowasp tools only see the working directory, so use relative paths
    subprocess.run([tool('YOSYS', 'yosys', 'yowasp-yosys'), '-q', '-p',
                    f'{read_cell_library(ps.family(device))}read_verilog top.v; hierarchy -top top; '
                    # as synth_gowin does: differential buffers' pads get IBUF/OBUF cells,
                    # which nextpnr merges; pads that already have a buffer are skipped
                    # (enables not inverted: an inverter would need synthesis to map)
                    'iopadmap -bits -inpad IBUF O:I -outpad OBUF I:O -toutpad TBUF OEN:I:O '
                    '-tinoutpad IOBUF OEN:O:I:IO top; '
                    'blackbox =A:whitebox; write_json syn.json'],
                   cwd=workdir, check=True, stdout=log, stderr=subprocess.STDOUT)
    path = os.path.join(workdir, 'syn.json')
    with open(path) as f:
        syn = json.load(f)
    for name, cell in syn['modules']['top']['cells'].items():
        if cell['type'] == 'DCS' and 'DCS_MODE' in cell['parameters']:
            # nextpnr reads DCS_MODE from attributes only (globals.cc), so a
            # defparam is ignored and the DCS packed as RISING. Recorded in
            # doc/agent/tiled-fuzzer.md; passed as an attribute to test gowin_pack.
            cell['attributes']['DCS_MODE'] = cell['parameters']['DCS_MODE']
        if name in names and names[name][1] and names[name][0].site not in PIN_SITES | FOLLOW_NEXTPNR:
            cell['attributes']['BEL'] = bel_name(*names[name])  # nextpnr ignores INS_LOC
    with open(path, 'w') as f:
        json.dump(syn, f)
    subprocess.run([tool('NEXTPNR', 'nextpnr-himbaechel', 'yowasp-nextpnr-himbaechel-gowin'),
                    '--json', 'syn.json', '--write', 'pnr.json', '--device', part,
                    '--vopt', f'family={device}', '--vopt', 'cst=top.cst'],
                   cwd=workdir, check=True, stdout=log, stderr=subprocess.STDOUT)
    subprocess.run([sys.executable, '-m', 'apycula.gowin_pack', '-d', device, '-o', 'top.fs', 'pnr.json'],
                   cwd=workdir, check=True, stdout=log, stderr=subprocess.STDOUT,
                   env={**os.environ, 'PYTHONPATH': REPO})
    with open(os.path.join(workdir, 'pnr.json')) as f:
        placed = {n: c['attributes'].get('NEXTPNR_BEL') for n, c in json.load(f)['modules']['top']['cells'].items()}
    bm, _, _, slots = bslib.read_bitstream(os.path.join(workdir, 'top.fs'))
    return bm, slots, placed


# ---------------------------------------------------------------- compare

_masks = {}


def route_mask(db, r, c):
    ttyp = db.grid[r][c]
    if ttyp not in _masks:
        bits = set(chipdb.get_route_bits(db, r, c))
        # alonenode_6 holds the fuses that isolate long-wire segments
        for table in (db[r, c].alonenode, db[r, c].alonenode_6):
            for srcs in table.values():
                for _, fuses in srcs:
                    bits |= fuses
        bits |= dsp_line_select_bits(db, ttyp)
        _masks[ttyp] = bits
    # HCLK routing is per location, not per tile type
    hclk = db.hclk_pips.get((r, c))
    if hclk:
        return _masks[ttyp] | {bit for srcs in hclk.values() for fuses in srcs.values() for bit in fuses}
    return _masks[ttyp]


def dsp_line_select_bits(db, ttyp):
    """Fuses of DSP rows that only pick which of a block's clock, CE or reset
    lines (CLKINn, CEINn, RSTINn) a register uses. That follows from routing:
    the tools pick different lines for the same nets."""
    li = db.rev_logicinfo('DSP') if 'DSP' in db.logicinfo else {}
    names = {v: k for k, v in attrids.dsp_attrvals.items()}
    out = set()
    for table, rows in db.shortval.get(ttyp, {}).items():
        if not table.startswith('DSP'):
            continue
        for key, bits in rows.items():
            vals = [names.get(li[k][1], '') for k in key if k > 0 and k in li]
            if vals and all(re.fullmatch(r'(CLK|CE|RST)IN\d', v) for v in vals):
                out |= bits
    return out


def diff_bits(db, vt, at):
    """{(row, col): {(bit, vendor value)}} for non-routing bits that differ."""
    out = {}
    for (r, c), vtile in vt.items():
        atile, mask = at[(r, c)], route_mask(db, r, c)
        bits = {((y, x), v) for y, row in enumerate(vtile) for x, v in enumerate(row)
                if v != atile[y][x] and (y, x) not in mask}
        if bits:
            out[(r, c)] = bits
    return out


_owners = {}


def bit_owner(db, r, c, bit):
    """The bel a non-routing bit configures: LUTn for INIT fuses, CLSn for the
    slice table that holds the flip-flop modes, else None (tile level)."""
    ttyp = db.grid[r][c]
    if ttyp not in _owners:
        own = {}
        for name, rows in db.shortval.get(ttyp, {}).items():
            if name.startswith('CLS'):
                for bits in rows.values():
                    own.update(dict.fromkeys(bits, name))
        for bel, b in db[r, c].bels.items():
            if bel.startswith('LUT'):
                for bits in b.flags.values():
                    own.update(dict.fromkeys(bits, bel))
        for name, rows in db.shortval.get(ttyp, {}).items():
            if name in ('IOLOGICA', 'IOLOGICB'):
                for bits in rows.values():
                    own.update(dict.fromkeys(bits, name))
        # I/O: bits in only one of the IOBA and IOBB tables belong to that bel
        io = {name: set().union(*rows.values()) for name, rows in db.longval.get(ttyp, {}).items()
              if name in ('IOBA', 'IOBB') and rows}
        if len(io) == 2:
            own.update(dict.fromkeys(io['IOBA'] - io['IOBB'], 'IOBA'))
            own.update(dict.fromkeys(io['IOBB'] - io['IOBA'], 'IOBB'))
        _owners[ttyp] = own
    return _owners[ttyp].get(bit)


def case_bel(case, site):
    r, c, cls, ab = site
    if case.site == 'iol':
        return f'IOLOGIC{cls[-1]}'
    if cls == 'BEL':
        return ab
    if cls in ('BSRAM', 'PLL', 'PLLA', 'RAM16', 'DSP') or str(cls).startswith('IOB'):
        return cls
    return f'LUT{2 * cls + "AB".index(ab)}' if case.site == 'lut' else f'CLS{cls}'


def fuse_tables(db, r, c, bit):
    ttyp = db.grid[r][c]
    owners = [f'{name}{key}' for name, rows in db.shortval.get(ttyp, {}).items()
              for key, bits in rows.items() if bit in bits]
    owners += [f'{bel}.{flag}' for bel, b in db[r, c].bels.items()
               for flag, bits in b.flags.items() if bit in bits]
    return owners[:4]


# ---------------------------------------------------------------- unpacked netlists
#
# Each case sits on a known bel, so only the configuration of that bel is
# compared. Nets are dummies and are not traced; the only nets that matter are
# constants, which the unpacker ties to VCC or VSS in the same tile.

def literal_value(text):
    text = str(text).strip().strip('"')
    if re.fullmatch(r'-?\d+\.0*', text):  # gowin_unpack writes some integers as floats
        text = text.split('.')[0]
    m = re.fullmatch(r"(\d+)'([bhd])([0-9a-fA-F_]+)", text)
    if m:
        return int(m.group(3).replace('_', ''), {'b': 2, 'h': 16, 'd': 10}[m.group(2)])
    return int(text) if re.fullmatch(r'-?\d+', text) else text.upper()


def lut_init(case):
    """16-bit INIT of a generated LUTn: unused inputs do not matter."""
    n = int(case.prim[3:])
    init = literal_value(dict(case.params)['INIT'])
    return sum(((init >> (i & ((1 << n) - 1))) & 1) << i for i in range(16))


_SR = {'S': 'SET', 'R': 'RESET', 'P': 'PRESET', 'C': 'CLEAR'}


def canonical(cell, params, inputs):
    """Flip-flops in one form: no E means CE=VCC, and a set/reset input tied to
    VSS means no set/reset. The unpacker emits e.g. DFFPE with CE=VCC for DFFP.
    `inputs` maps each input port to 'VCC', 'VSS' or 'sig'."""
    m = re.fullmatch(r'(DFF|DL)(N?)([SRPC]?)(E?)', cell or '')
    if not m:
        return {'cell': cell, 'params': params, 'inputs': inputs}
    kind, neg, sr, ce = m.groups()
    if sr and inputs.get(_SR[sr]) == 'VSS':
        sr = ''
    enable = inputs.get('CE', inputs.get('GE', 'sig')) if ce else 'VCC'
    return {'cell': kind, 'params': params, 'edge': 'neg' if neg else 'pos', 'sr': sr or None, 'ce': enable}


def literals(items, skip=()):
    """{name: value} of (name, literal) pairs, without the names in `skip`."""
    return {k: literal_value(v) for k, v in items if k not in skip}


def widelut_inits(case):
    """Leaf INITs of a wide LUT case by leaf index (INIT0, INIT1, ... INIT15;
    Case.from_json sorts them by name)."""
    return [v for _, v in sorted(case.params, key=lambda kv: int(kv[0][4:]))]


def widelut_tree(nl, luts, case):
    """'ok' if every leaf of a MUX2_LUTn tree reaches one root through the mux
    inputs its index selects (bit i of the leaf index at the i-th mux level, I1
    for 1), following the MUX2 cells gowin_unpack writes for the hardwired
    wide-LUT muxes by wire name (resolving nets would join them to routing).
    Else 'missing' if a leaf INIT is not in the bitstream, or
    the (root, index) pairs each leaf can reach."""
    levels = int(case.prim[-1]) - 4
    into = collections.defaultdict(list)  # net -> [(mux O net, 0 for I0 or 1 for I1)]
    for cell in nl.cells.values():
        if cell['type'] == 'MUX2':
            for k, port in enumerate(('I0', 'I1')):
                into[cell['ports'][port]].append((cell['ports']['O'], k))

    def reach(net, level):
        """(root, index) pairs `level` muxes up from `net`; an OF3 output feeds
        two MUX2_LUT8s, its own and its west neighbour's."""
        if level == 0:
            return {(net, 0)}
        return {(root, (idx << 1) | bit) for out, bit in into.get(net, ())
                for root, idx in reach(out, level - 1)}

    reached = []
    for init in widelut_inits(case):
        leaf = luts.get(literal_value(init))
        if not leaf:
            return 'missing'
        # the root's select is the top bit of the index, the lowest mux's the bottom
        reached.append(reach(nl.cells[leaf[0]]['ports']['F'], levels))
    roots = {root for root, _ in reached[0]}
    if any(all((root, j) in r for j, r in enumerate(reached)) for root in roots):
        return 'ok'
    return [sorted(idx for _, idx in r) for r in reached]


class Decoded:
    """Cells of an unpacked bitstream, looked up by the site a case was placed on."""

    def __init__(self, nl, spec):
        self.nl, self.spec = nl, spec
        self.luts = collections.defaultdict(list)  # INIT -> [LUT4 cell names]
        for name, cell in nl.cells.items():
            if cell['type'] == 'LUT4' and 'INIT' in cell['params']:
                self.luts[literal_value(cell['params']['INIT'])].append(name)

    def find(self, case, site):
        if site is None:
            return next((n for n, c in self.nl.cells.items() if c['type'].startswith(case.site.upper())), None)
        r, c, cls, ab = site
        if case.site == 'iol' or case.site in IO_SITES:
            # gowin_unpack names I/O logic and buffers R<r>C<c>_<MODE or TYPE>_<A|B>
            prefix, suffix = f'R{r + 1}C{c + 1}_', f'_{cls[-1]}'
            match = ((lambda t: ps.SITES.get(t) == 'iol') if case.site == 'iol'
                     else (lambda t: t.endswith('BUF')))
            return next((n for n, cell in self.nl.cells.items() if n.startswith(prefix) and n.endswith(suffix)
                         and match(cell['type'])), None)
        if case.site in ('bsram', 'pll'):
            # gowin_unpack names these by a counter; find the one on this tile
            prefix, typ = f'R{r + 1}C{c + 1}_', {'bsram': 'BSRAM', 'pll': 'rPLL'}[case.site]
            return next((n for n, cell in self.nl.cells.items() if cell['type'] == typ
                         and any(str(w).startswith(prefix) for w in cell['ports'].values())), None)
        if case.site in ('ssram', 'alu', 'lut'):
            name = f'R{r + 1}C{c + 1}_' + ('RAM16' if case.site == 'ssram' else
                                           f'{"ALU" if case.site == "alu" else "LUT4"}_{2 * cls + "AB".index(ab)}')
            return name if name in self.nl.cells else None
        prefix, suffix = f'R{r + 1}C{c + 1}_', f'_{2 * cls}'
        return next((n for n, cell in self.nl.cells.items() if n.startswith(prefix) and n.endswith(suffix)
                     and cell['type'].startswith(('DFF', 'DL'))), None)  # flip-flops and latches

    def describe(self, case, site):
        if case.site in FUSE_ONLY:
            return describe_generated(case, None, None)
        if case.site == 'widelut':
            return {'cell': 'WIDELUT', 'tree': widelut_tree(self.nl, self.luts, case)}
        if case.site == 'ssram' and isinstance(site[2], int):
            # nextpnr implements ROM16 as a LUT; its INIT is the ROM contents
            cell = self.nl.cells.get(f'R{site[0] + 1}C{site[1] + 1}_LUT4_{2 * site[2] + "AB".index(site[3])}')
            return {'cell': 'SSRAM' if cell else None,
                    'params': {'INIT_0': literal_value(cell['params']['INIT'])} if cell else {}}
        name = self.find(case, site)
        cell = self.nl.cells[name] if name else None
        if case.site == 'iol':
            return {'cell': cell and cell['type'], 'params': literals(cell['params'].items()) if cell else {}}
        if case.site in IO_SITES:
            # attributes are compared on fuses; gowin_unpack writes them to a .cst
            return {'cell': cell and cell['type']}
        if case.site == 'ssram':
            # gowin_unpack writes every SSRAM as RAM16SDP4; compare INIT
            return {'cell': 'SSRAM' if cell else None, 'params': literals(cell['params'].items()) if cell else {}}
        if case.site == 'alu':
            if cell is None:
                return {'cell': None}
            return {'cell': 'ALU', 'params': {'ALU_MODE': literal_value(cell['params'].get('ALU_MODE'))}}
        if case.site == 'bsram':
            # gowin_unpack does not decode BSRAM parameters; the fuse comparison covers them
            return {'cell': 'BSRAM' if name else None}
        if case.site == 'pll':
            if name is None:
                return {'cell': None, 'params': {}}
            # DEVICE is not a fuse; it is unpacked as the family name
            return {'cell': 'rPLL', 'params': literals(cell['params'].items(), skip={'DEVICE'})}
        if case.site == 'lut':
            if name:
                return {'cell': 'LUT', 'init': literal_value(self.nl.cells[name]['params']['INIT'])}
            # constant LUTs are written as an assign of the F wire to VCC or VSS
            r, c, cls, ab = site
            const = self.nl.find(f'R{r + 1}C{c + 1}_F{2 * cls + "AB".index(ab)}')
            return {'cell': 'LUT', 'init': {'VCC': 0xffff, 'VSS': 0}.get(const)}
        if name is None:
            return {'cell': None}
        ports = self.spec.get(cell['type'], {'ports': {}})['ports']
        inputs = {}
        for port, wire in cell['ports'].items():
            if ports.get(port, ('input',))[0] == 'input':
                root = self.nl.find(wire)
                inputs[port] = root if root in ('VCC', 'VSS') else 'sig'
        return canonical(cell['type'], literals(cell['params'].items()), inputs)


# Kinds compared on fuses only (or, for plla, on its bitstream slot in
# run_batch): gowin_unpack does not decode them, so both sides describe them
# as the generated case does.
FUSE_ONLY = {'dsp', 'plla', 'clock', 'lone'}


def describe_generated(case, conns, spec):
    if case.site in FUSE_ONLY:
        return {'cell': case.prim}
    if case.site == 'ssram':
        return {'cell': 'SSRAM', 'params': literals(case.params)}
    if case.site == 'alu':
        return {'cell': 'ALU', 'params': {'ALU_MODE': literal_value(dict(case.params)['ALU_MODE'])}}
    if case.site == 'widelut':
        return {'cell': 'WIDELUT', 'tree': 'ok'}
    if case.site == 'iol':
        return {'cell': case.prim, 'params': literals(case.params)}
    if case.site in IO_SITES:
        return {'cell': case.prim}
    if case.site == 'bsram':
        return {'cell': 'BSRAM'}
    if case.site == 'pll':
        return {'cell': 'rPLL', 'params': literals(case.params, skip={'DEVICE'})}
    if case.site == 'lut':
        return {'cell': 'LUT', 'init': lut_init(case)}
    inputs = {p: 'VSS' if conns.get(p, 'gnd') == 'gnd' else 'sig'
              for p, (d, _) in spec[case.prim]['ports'].items() if d == 'input'}
    return canonical(case.prim, literals(case.params), inputs)


def same(a, b):
    """Compare descriptions. Parameters are compared where both sides have them,
    because the unpacker does not emit every parameter."""
    if a.keys() != b.keys():
        return False
    if any(a[k] != b[k] for k in a.keys() - {'params'}):
        return False
    x, y = a.get('params') or {}, b.get('params') or {}
    return all(x[k] == y[k] for k in x.keys() & y.keys())


# Placed by nextpnr, and the vendor constrained to where nextpnr put them: ALU
# clusters ignore BEL; SSRAM with a BEL makes nextpnr crash (RAM16SDP2/4) or
# leave its blocker cells unplaced (RAM16SDP1); ROM16 becomes a LUT.
# DSP clusters get DUMMY_CELLs that stay unplaced with a BEL.
FOLLOW_NEXTPNR = {'alu', 'ssram', 'dsp'}


def vendor_failed(workdir):
    log = os.path.join(workdir, 'vendor/impl/pnr/top.log')
    why = []
    if os.path.exists(log):
        with open(log, errors='replace') as f:
            why = [line.strip() for line in f if line.startswith('ERROR')]
    return {'error': 'vendor produced no bitstream', 'why': why}, None


_apicula_error = re.compile(r'\w*(Error|Exception): ')


def apicula_errors(log):
    """Error lines of an Apicula flow log (Yosys, nextpnr, gowin_pack)."""
    with open(log, errors='replace') as f:
        return [line.strip() for line in f if 'ERROR' in line or _apicula_error.match(line)]


def run_batch(args, db, spec, pins, batch, workdir, baseline, harness_io_type=None):
    vendor_device, part, _ = DEVICES[args.device]
    mod, cst, names, wiring = netlist(batch, spec, pins, harness_io_type)
    vendor = functools.partial(run_vendor, os.path.join(workdir, 'vendor'), mod, cst, vendor_device, part)

    def apicula():
        try:
            return run_apicula(os.path.join(workdir, 'apicula'), mod, cst, names, args.device, part)
        except subprocess.CalledProcessError:
            return None

    # Cases nextpnr places itself (FOLLOW_NEXTPNR) run through Apicula first,
    # and the vendor then gets the location nextpnr chose. Lone and clock cases
    # run through the vendor first, and nextpnr gets its pins and clock divider
    # bels. Otherwise the two flows are independent and run at the same time.
    follow = any(case.site in FOLLOW_NEXTPNR for case, _ in names.values())
    vendor_first = any(case.site in ('lone', 'clock') for case, _ in names.values())
    if follow or vendor_first:
        vres = None if follow else vendor()
        if vres is None and not follow:
            return vendor_failed(workdir)
        if vendor_first:
            cst.ports.update(vendor_pins(os.path.join(workdir, 'vendor')))
            vt = chipdb.tile_bitmap(db, vres.bitmap, empty=True)
            for name, (case, site) in list(names.items()):
                site = vendor_clock_site(db, vt, case) if case.site == 'clock' else None
                # GW5A-25A: the vendor uses HCLKDIV1 on X0Y1, where nextpnr has
                # no CLKDIV_1 bel; compared without positions instead
                if site and not re.fullmatch(r'CLKDIV_\d', site[3]):
                    names[name] = (case, site)
        ares = apicula()
    else:
        with concurrent.futures.ThreadPoolExecutor(2) as pool:
            vfut, afut = pool.submit(vendor), pool.submit(apicula)
            vres, ares = vfut.result(), afut.result()
    # a design the vendor rejects is invalid, whatever Apicula does with it
    if not follow and vres is None:
        return vendor_failed(workdir)
    if ares is None:
        return {'error': 'the Apicula flow failed', 'why': apicula_errors(os.path.join(workdir, 'apicula/tools.log'))}, None
    abm, aslots, placed = ares
    if follow:
        for name, (case, site) in list(names.items()):
            if case.site in FOLLOW_NEXTPNR:
                m = re.fullmatch(r'X(\d+)Y(\d+)/(\w+)', placed.get(name) or '')
                if m and case.site == 'dsp':
                    # DSP_R<row>[n][A|B]: n-th DSP block of the row, macro from the bel name
                    c, r, bel = int(m.group(1)), int(m.group(2)), m.group(3)
                    cols = [cc for cc in range(db.cols) if 'DSP' in db[r, cc].bels]
                    if c not in cols:
                        continue
                    macro = bel[len(case.prim):][:1]
                    names[name] = (case, (r, c, 'DSP', cols.index(c)))
                    cst.cells[name] = f'DSP_R{r + 1}[{cols.index(c)}]' + (f'[{"AB"[int(macro)]}]' if macro else '')
                    continue
                m = re.fullmatch(r'X(\d+)Y(\d+)/(ALU|LUT|RAM16SDP4)(\d?)', placed.get(name) or '')
                if not m:
                    continue
                c, r = int(m.group(1)), int(m.group(2))
                if m.group(3) == 'RAM16SDP4':
                    site = (r, c, 'RAM16', '-')
                    cst.cells[name] = f'R{r + 1}C{c + 1}'
                else:
                    n = int(m.group(4))
                    site = (r, c, n // 2, 'AB'[n % 2])
                    cst.cells[name] = (r + 1, c + 1, n // 2, 'AB'[n % 2])
                names[name] = (case, site)
        vres = vendor()
        if vres is None:
            return vendor_failed(workdir)
    vt = chipdb.tile_bitmap(db, vres.bitmap, empty=True)
    at = chipdb.tile_bitmap(db, abm, empty=True)
    diffs = diff_bits(db, vt, at)
    decoded = {}
    if batch:
        fs = {'vendor': os.path.join(workdir, 'vendor/impl/pnr/top.fs'), 'apicula': os.path.join(workdir, 'apicula/top.fs')}
        with concurrent.futures.ThreadPoolExecutor(2) as pool:
            nls = {side: pool.submit(unpacked_netlist.unpack, args.device, path,
                                     os.path.join(workdir, f'{side}_unpack.v'), REPO) for side, path in fs.items()}
            decoded = {side: Decoded(nl.result(), spec) for side, nl in nls.items()}
    if any(case.site == 'widelut' for case, _ in names.values()):
        diffs = {}  # placed freely by both tools; compared on leaf positions
    if baseline is not None:
        diffs = {k: v - baseline.get(k, set()) for k, v in diffs.items()}
        diffs = {k: v for k, v in diffs.items() if v}

    results = {}
    by_bel = {}  # (row, col, bel) -> case name
    by_tile = collections.defaultdict(list)
    by_bank = collections.defaultdict(list)  # I/O cases per bank
    for name, (case, site) in names.items():
        res = {'case': case.to_json(), 'site': site, 'status': 'ok'}
        problems = [msg for (n, code), msgs in vres.errs.items() if n == name
                    for msg in msgs if code in INVALID_CODES or msg.startswith('ERROR')]
        # I/O is placed by IO_LOC; nextpnr merges differential buffers into cells
        # of other names, so check placement for the rest only
        if site and case.site not in PIN_SITES | FOLLOW_NEXTPNR | {'clock'} and placed.get(name) != bel_name(case, site):
            problems.append(f'nextpnr placed it at {placed.get(name)}')
        if problems:
            res['status'] = 'invalid'
            res['why'] = problems
        else:
            gen = describe_generated(case, wiring[name], spec)
            dv, da = decoded['vendor'].describe(case, site), decoded['apicula'].describe(case, site)
            if not same(dv, da):
                res['status'] = 'mismatch'
            elif not same(da, gen):
                res['status'] = 'decode'
            if res['status'] != 'ok':
                res['generated'], res['vendor'], res['apicula'] = gen, dv, da
        results[name] = res
        if site:
            loc = (site[0], site[1])
        elif case.site in ('clock', 'lone', 'widelut'):
            continue  # clock and lone: alone in their design, own every difference (see below)
        else:
            loc = singleton_loc(db, case.prim, case.site)
        by_tile[loc].append(name)
        if site and site[2] == 'BSRAM':
            # a BSRAM's fuses are in its tile and the two tiles to its right:
            # BSRAM_AUX bels on GW1N/GW2A, tiles with BSRAM tables but no bel on GW5A
            for dc in (1, 2):
                if loc[1] + dc < db.cols:
                    aux = db[loc[0], loc[1] + dc]
                    if 'BSRAM_AUX' in aux.bels or ('BSRAM' not in aux.bels
                                                    and 'BSRAM_SP' in db.shortval.get(aux.ttyp, {})):
                        by_tile[(loc[0], loc[1] + dc)].append(name)
        if case.site in PIN_SITES:
            # bank settings are shared by every I/O in the bank
            bank = io_bank(db, site[0], site[1], site[2][-1])
            by_bank[bank].append(name)
            if bank in db.bank_tiles:
                by_tile[db.bank_tiles[bank]].append(name)
        if site and site[2] == 'DSP':
            # a DSP block's fuses are in its main tile and the DSP_AUX tiles to its right
            dc = 1
            while loc[1] + dc < db.cols and any(b.startswith('DSP_AUX') for b in db[loc[0], loc[1] + dc].bels):
                by_tile[(loc[0], loc[1] + dc)].append(name)
                dc += 1
        if site and site[2] == 'PLL':
            # an rPLL's fuses are in its RPLLA tile and the adjacent RPLLB tiles
            for dc in (-3, -2, -1, 1, 2, 3):
                if 0 <= loc[1] + dc < db.cols and 'RPLLB' in db[loc[0], loc[1] + dc].bels:
                    by_tile[(loc[0], loc[1] + dc)].append(name)
        if site:
            by_bel[(*loc, case_bel(case, site))] = name

    # GW5A PLLs: compare the slot bits and the slot's decoded PLL attributes
    for name, (case, site) in names.items():
        if case.site != 'plla' or results[name]['status'] != 'ok':
            continue
        slot = db.extra_func[(site[0], site[1])]['pll']['slot_idx']
        vs, as_ = vres.extra_slots.get(slot), aslots.get(slot)
        if vs is None or as_ is None:
            results[name]['status'] = 'mismatch'
            results[name]['why'] = [f'slot {slot}: vendor {"has" if vs else "lacks"} it, '
                                    f'apicula {"has" if as_ else "lacks"} it']
            continue
        bits = [(y, x, v) for y, row in enumerate(vs) for x, v in enumerate(row) if v != as_[y][x]]
        if bits:
            dec = [gowin_unpack.parse_attrvals(b, db.rev_logicinfo('PLL'), db.shortval[1024]['PLL'],
                                               attrids.pll_attrids, 'PLL') for b in (vs, as_)]
            results[name]['status'] = 'mismatch'
            results[name]['why'] = [f'slot {slot}: {len(bits)} bits differ']
            results[name]['slot_attrs'] = {
                k: (dec[0].get(k), dec[1].get(k)) for k in dec[0].keys() | dec[1].keys()
                if dec[0].get(k) != dec[1].get(k)}

    # Clock primitives: nextpnr ignores BEL on CLKDIV and CLKDIV2, and places
    # DHCEN by routing, so it may use another HCLK tile or section than the
    # vendor. The HCLK settings are then compared without their positions: names
    # without digits, and no HCLKDCS_SEL, which follows from the section. A
    # CLKDIV or CLKDIV2 must also select the bel nextpnr placed it on.
    hclk_tiles = set()

    def hclk_settings(tiles):
        strip = lambda t: re.sub(r'\d', '', t)
        return sorted((strip(k), v if k.endswith('_DIV') else strip(str(v)))
                      for av in hclk_attrs(db, tiles).values() for k, v in av.items()
                      if not k.startswith('HCLKDCS'))

    for name, (case, site) in names.items():
        if case.site != 'clock' or results[name]['status'] != 'ok':
            continue
        if case.prim in ('CLKDIV', 'CLKDIV2'):
            asite = vendor_clock_site(db, at, case)
            if asite is None and site is None:
                pass  # no fuses of its own (GW5A CLKDIV2)
            elif asite is None or placed.get(name) != bel_name(case, asite):
                results[name]['status'] = 'mismatch'
                results[name]['why'] = [f'Apicula fuses select {asite and bel_name(case, asite)}, '
                                        f'nextpnr placed it at {placed.get(name)}']
                continue
            elif asite == site:
                continue  # same bel: the fuse comparison applies
            else:
                results[name]['placed'] = {'vendor': site and bel_name(case, site), 'apicula': placed.get(name)}
        vh, ah = hclk_settings(vt), hclk_settings(at)
        if vh != ah:
            results[name]['status'] = 'mismatch'
            results[name]['why'] = [f'HCLK settings: vendor {vh}, apicula {ah}']
        hclk_tiles |= {k for k in vt if 'HCLK' in db.shortval.get(db[k].ttyp, {})}
    diffs = {k: v for k, v in diffs.items() if k not in hclk_tiles}

    # Unused I/Os are configured from their bank's settings, so differences in
    # an I/O tile with no case belong to the I/O cases of that bank.
    def bank_cases(r, c):
        if not any(b.startswith('IOB') for b in db[r, c].bels):
            return []
        banks = {io_bank(db, r, c, ab) for ab in 'AB'}
        return [n for b in banks for n in by_bank.get(b, [])]

    # a clock or lone case is alone in its design and placed by the tools, so
    # the differences left over belong to it
    alone = [n for n, (case, _) in names.items() if case.site in ('clock', 'lone')]
    unattributed = {}
    for (r, c), bits in sorted(diffs.items()):
        for bit, v in sorted(bits):
            bel = bit_owner(db, r, c, bit)
            owners = [by_bel[(r, c, bel)]] if (r, c, bel) in by_bel else by_tile.get((r, c)) or bank_cases(r, c) or alone
            detail = f'{bit} vendor={v} apicula={1 - v} {bel or ""} {fuse_tables(db, r, c, bit)}'
            if not owners:
                unattributed.setdefault(f'R{r + 1}C{c + 1}', []).append(detail)
            for name in owners:
                if results[name]['status'] == 'ok':
                    results[name]['status'] = 'mismatch'
                results[name].setdefault('diffs', {}).setdefault(f'R{r + 1}C{c + 1}', []).append(detail)
    report = {'cases': results, 'unattributed': unattributed}
    return report, diffs


_singleton_locs = {}


def singleton_loc(db, prim, kind):
    """Tile of a one-per-device bel, named after the primitive (OSCA) or the
    site kind (OSC)."""
    if prim not in _singleton_locs:
        _singleton_locs[prim] = find_bel(db, prim) or find_bel(db, kind.upper())
    return _singleton_locs[prim]


def vendor_pins(vendor_dir):
    """{port: pin} from the vendor's impl/pnr/top.io.cst, which lists every
    port, including those it placed itself."""
    pins = {}
    path = os.path.join(vendor_dir, 'impl/pnr/top.io.cst')
    if os.path.exists(path):
        with open(path) as f:
            for m in re.finditer(r'IO_LOC\s+"([^"]+)"\s+([^;\s]+)', f.read()):
                pins[m.group(1)] = m.group(2).split(',')[0]
    return pins


HCLK_VALS = {v: k for k, v in attrids.hclk_attrvals.items()}


def hclk_attrs(db, tiles):
    """Decoded HCLK attributes per tile: {(row, col): {attr: value}}."""
    out = {}
    for (r, c), bm in tiles.items():
        table = db.shortval.get(db[r, c].ttyp, {}).get('HCLK')
        if table:
            av = gowin_unpack.parse_attrvals(bm, db.rev_logicinfo('HCLK'), table, attrids.hclk_attrids, 'HCLK')
            if av:
                out[(r, c)] = {k: HCLK_VALS.get(v, v) for k, v in av.items()}
    return out


def vendor_clock_site(db, tiles, case):
    """Where the vendor put a CLKDIV or CLKDIV2, read from its HCLK fuses, as a
    (row, col, 'BEL', bel) site for nextpnr. The vendor reports no position for
    them. Other clock primitives return None and nextpnr places them."""
    for (r, c), av in hclk_attrs(db, tiles).items():
        clkdiv = db.extra_func.get((r, c), {}).get('clkdiv')
        if clkdiv:
            # GW5A: CLKDIV_<n> is configured by HCLKDIV<n>; CLKDIV2 has no fuses
            n = next((n for n in clkdiv['bels'] if f'HCLKDIV{n}_DIV' in av), None)
            if case.prim == 'CLKDIV' and n is not None:
                return (r, c, 'BEL', f'CLKDIV_{n}')
            continue
        for h in '01':
            if case.prim == 'CLKDIV' and f'HCLKDIV{h}_DIV' in av:
                bel = f'CLKDIV_HCLK{h}_SECT{1 if f"HCLKDCS{h}_SEL" in av else 0}'
            elif case.prim == 'CLKDIV2':
                sect = next((s for s in '01' if av.get(f'BK{s}MUX{h}_OUTSEL') == 'DIV2'), None)
                bel = sect and f'CLKDIV2_HCLK{h}_SECT{sect}'
            else:
                bel = None
            if bel and bel in db[r, c].bels:
                return (r, c, 'BEL', bel)
    return None


def find_bel(db, bel):
    return next(((r, c) for r in range(db.rows) for c in range(db.cols) if bel in db[r, c].bels), None)


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('-d', '--device', required=True, choices=sorted(DEVICES))
    ap.add_argument('-n', '--count', type=int, default=10, help='cases per primitive')
    ap.add_argument('--prims', nargs='*', help='primitives to fuzz (default: all supported)')
    ap.add_argument('--seed', type=int, default=0)
    ap.add_argument('--replay', nargs='*', help='case JSON files to run, one per design')
    ap.add_argument('-o', '--out', default='fuzz-out')
    ap.add_argument('-j', '--jobs', type=int, default=1, help='designs run at the same time')
    args = ap.parse_args(argv)

    vendor_device, part, package = DEVICES[args.device]
    db = chipdb.load_chipdb(os.path.join(os.path.dirname(chipdb.__file__), f'{args.device}.msgpack.xz'))
    prims = ps.Primitives(args.device, vendor_device)
    pins = pick_pins(db, vendor_device, args.device, package)
    rng = random.Random(args.seed)
    pinout = db.pinout.get(vendor_device, db.pinout[args.device])[package]
    sites = Sites(db, rng, pins, pinout)

    if args.replay:
        batches = []
        for path in args.replay:
            with open(path) as f:
                d = json.load(f)
            batches.append([(ps.Case.from_json(d['case']), tuple(d['site']) if d['site'] else None)])
    else:
        names = [p for p in args.prims or sorted(prims.spec) if p in prims.spec
                 and p not in ps.UNAVAILABLE.get(args.device, ()) and p not in ps.NOT_PRIMITIVES]
        cases = [c for p in names for c in set(ps.draw(prims.case(p), args.count, args.seed))]
        rng.shuffle(cases)
        batches = allocate(cases, sites)

    print(f'{sum(map(len, batches))} cases in {len(batches)} designs; pins {pins}')

    # Differences of the harness alone, with each harness I/O standard the
    # batches need. They are subtracted from the batches' differences.
    baselines = {}
    for vccio in dict.fromkeys(map(io_class, batches)):
        io_type = HARNESS_IO_TYPE.get(vccio)
        _, b = run_batch(args, db, prims.spec, pins, [], os.path.join(args.out, f'baseline_{io_type}'), None, io_type)
        if b is None:
            sys.exit(f'the harness alone ({io_type}) failed in the vendor flow')
        print(f'harness ({io_type or "default I/O"}) differences, ignored: {sum(map(len, b.values()))} bits in '
              f'{" ".join(f"R{r + 1}C{c + 1}" for r, c in sorted(b))}')
        baselines[vccio] = b

    def run(i, batch):
        report, _ = run_batch(args, db, prims.spec, pins, batch, os.path.join(args.out, i),
                              baselines[io_class(batch)], HARNESS_IO_TYPE.get(io_class(batch)))
        with open(os.path.join(args.out, i, 'report.json'), 'w') as f:
            json.dump(report, f, indent=1)
        return report

    totals = collections.Counter()

    def record(i, batch, report):
        """Count and print a batch's results; returns the halves to run when a
        design with several cases failed."""
        workdir = os.path.join(args.out, i)
        if 'error' in report:
            if len(batch) > 1:
                # an error stops the whole design: split it to find the case. If
                # Apicula fails on a design the vendor accepts, that is a failure
                # in itself, even when every case passes alone.
                half = len(batch) // 2
                print(f'{i}: {report["error"]}; splitting')
                for line in dict.fromkeys(report.get('why', [])):
                    print('    ', line)
                if 'Apicula' in report['error']:
                    totals['unsupported combinations'] += 1
                    with open(os.path.join(workdir, 'unsupported_combination.json'), 'w') as f:
                        json.dump({'cases': [(c.to_json(), s) for c, s in batch], 'why': report.get('why', [])},
                                  f, indent=1)
                return [(f'{i}a', batch[:half]), (f'{i}b', batch[half:])]
            case, site = batch[0]
            # unsupported is a failure to fix in Apicula, not a case to drop
            status = 'unsupported' if 'Apicula' in report['error'] else 'invalid'
            res = {'case': case.to_json(), 'site': site, 'status': status, 'why': report.get('why', [])}
            path = os.path.join(workdir, f'{status}_{case.prim}.json')
            with open(path, 'w') as f:
                json.dump(res, f, indent=1)
            print(f'{i} {status}: {case.to_json()} at {site} -> {path}')
            for line in dict.fromkeys(res['why']):
                print('    ', line)
            totals[status] += 1
            return []
        for name, res in report['cases'].items():
            totals[res['status']] += 1
            if res['status'] != 'ok':
                path = os.path.join(workdir, f'{res["status"]}_{name}.json')
                with open(path, 'w') as f:
                    json.dump(res, f, indent=1)
                print(f'{i} {name} {res["status"]}: {res["case"]} at {res["site"]} -> {path}')
                for side in ('generated', 'vendor', 'apicula'):
                    if side in res:
                        print(f'     {side:9}', res[side])
                for line in res.get('why', []):
                    print('    ', line)
                for tile, bits in res.get('diffs', {}).items():
                    print(f'     {tile}:', *bits, sep='\n       ')
        for tile, bits in report['unattributed'].items():
            totals['unattributed tiles'] += 1
            print(f'{i} unattributed {tile}:', *bits, sep='\n       ')
        return []

    with concurrent.futures.ThreadPoolExecutor(args.jobs) as pool:
        running = {pool.submit(run, i, b): (i, b) for i, b in ((f'batch{i}', b) for i, b in enumerate(batches))}
        while running:
            done, _ = concurrent.futures.wait(running, return_when=concurrent.futures.FIRST_COMPLETED)
            for fut in done:
                i, batch = running.pop(fut)
                for j, half in record(i, batch, fut.result()):
                    running[pool.submit(run, j, half)] = (j, half)
    print('summary:', dict(totals))
    # invalid cases are generator problems (a vendor rule to learn); the rest are failures
    return 1 if totals.keys() & {'mismatch', 'decode', 'unsupported', 'unsupported combinations',
                                 'unattributed tiles'} else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
