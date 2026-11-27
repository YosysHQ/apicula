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
make); invalid (the vendor rejected the case for its harness or netlist: a
rule the generator should learn); rejected (the vendor rejected the case's
settings as illegal, REJECT_CODES, and the Apicula flow failed on it too);
accepted (the vendor rejected the settings, but Apicula made a bitstream: a
failure); unsupported (the Apicula flow failed on it: a failure to fix, like a
mismatch). The exit status is 1 if any case failed. A design that fails in
either flow, or with settings the vendor rejects, is split in half and rerun
until the case is alone. Failing cases are written out on
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
import itertools
import json
import os
import random
import re
import subprocess
import sys
import types

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
INVALID_CODES = {'CT1094': 'not placed at its constraint'}
# Vendor warnings that reject a case's settings as illegal. The vendor still
# writes a bitstream; Apicula must stop with an error instead.
REJECT_CODES = {'PA1002': 'invalid parameter value', 'CT1108': 'illegal port attribute',
                'CT1136': 'bank voltage conflicts with a locked or constrained one; the pad is moved'}


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
        # Most I/O logic needs the other pin of its tile free (nextpnr's
        # check_iologic_placement: "already taken by harness_ib_in4"), so no
        # case shares a tile with a harness pin. Filtered after the shuffle,
        # which leaves the random draw as it was.
        harness_tiles = {gowin_unpack.tbrl2rc(db, pinout[pin][0])[:2] for pin in harness}
        self.iob = [s for s in self.iob if s[:2] not in harness_tiles]
        # IDES16/OSER16 need an "X16 location" (vendor PR2046): pin A of a tile
        # whose io16 role is MAIN; both pins of the AUX tile beside it must be
        # free as well (nextpnr's check_io16_placement)
        def x16(s):
            io16 = db.extra_func.get(s[:2], {}).get('io16', {})
            return io16.get('role') == 'MAIN' and (s[0] + io16['pair'][0], s[1] + io16['pair'][1]) not in harness_tiles
        self.iob16 = [s for s in self.iob if s[2] == 'IOBA' and x16(s)]
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
        # banks without harness pins and with at least three free pins, for
        # IO_BANK: (row, col, 'IOBA'|'IOBB', [pin, ...]) with the place of the
        # first pin. Taken in the order of the shuffled pins, without a draw of
        # its own, which leaves the random state as it was.
        harness_banks = {db.pin_bank.get(pinout[pin][0]) for pin in harness}
        by_bank = collections.defaultdict(list)
        for s in self.iob:
            by_bank[io_bank(db, s[0], s[1], s[2][-1])].append(s)
        self.iobank = [(*s[0][:3], [p[3] for p in s[:3]]) for bank, s in by_bank.items()
                       if bank not in harness_banks and len(s) >= 3]


def io_bank(db, r, c, ab):
    """Bank of the I/O at row, col, 'A'|'B'."""
    return db.pin_bank.get(chipdb.rc2tbrl_0(db, r, c, ab))


HARNESS_IO_TYPE = {'3.3': 'LVCMOS33', '2.5': 'LVCMOS25', '1.8': 'LVCMOS18', '1.5': 'LVCMOS15', '1.2': 'LVCMOS12'}
IO_PAD = {'IBUF': 'I', 'OBUF': 'O', 'TBUF': 'O', 'IOBUF': 'IO'}
DIFF_PAD = {'IBUF': ['I', 'IB'], 'OBUF': ['O', 'OB'], 'TBUF': ['O', 'OB'], 'IOBUF': ['IO', 'IOB']}
IOL_INPUT = {'D', 'DI'}  # I/O logic port fed by the input buffer
IOL_OUTPUT = {'Q', 'Q0', 'DO'}  # port that feeds the output buffer


def io_pads(case, site):
    """[(port, pin)] of an I/O case: one pad, or the positive and negative pads
    of a differential buffer."""
    if case.site == 'diob':
        return list(zip(DIFF_PAD[case.prim.rpartition('_')[2]], site[3]))
    return [(IO_PAD[case.prim], site[3])]


def io_class(batch, device):
    """Bank voltage shared by the I/O cases of a batch, or None."""
    return next((ps.io_vccio(c, device) for c, _ in batch if KINDS[c.site].batch == 'io'), None)


def allocate(cases, sites, device):
    """Split cases into batches and give each a site. Returns [[(case, site), ...]]."""
    queues = collections.defaultdict(list)
    for case in cases:
        queues[case.site].append(case)
    by_batch = lambda b: [k for k, kind in KINDS.items() if kind.batch == b]
    # alone: one per design, placed by the tools
    batches = [[(case, None)] for k in by_batch('alone') for case in queues.pop(k, [])]
    # bank: one per design, on pins of a bank of its own
    for k in by_batch('bank'):
        group, free = queues.pop(k, []), getattr(sites, k)
        if group and not free:
            print(f'no {k} sites for {sorted({c.prim for c in group})}; {len(group)} cases not run')
        elif group:
            batches += [[(case, free[i % len(free)])] for i, case in enumerate(group)]
    # wide LUT trees: in designs of their own, with no LUT INIT used twice in a design
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
    for k in by_batch('own'):  # these use slices too, so in designs of their own
        group, free = queues.pop(k, []), getattr(sites, k)
        for i in range(0, len(group), len(free) or 1):
            batches.append(list(zip(group[i:i + len(free)], free)))
    # I/O cases: one bank voltage per design, since a bank has one VCCIO
    by_vccio = collections.defaultdict(list)
    for case in (case for k in by_batch('io') for case in queues.pop(k, [])):
        pool = (case.prim.split('_')[0].lower() if case.site == 'diob'
                else 'iob16' if case.prim in ('IDES16', 'OSER16') else 'iob')
        by_vccio[(ps.io_vccio(case, device), pool)].append(case)
    for (_, pool), group in by_vccio.items():
        free = getattr(sites, pool)
        if not free:
            print(f'no {pool} sites for {sorted({c.prim for c in group})}; {len(group)} cases not run')
            continue
        for i in range(0, len(group), len(free)):
            batches.append(list(zip(group[i:i + len(free)], free)))
    # the rest share designs: two LUTs or one flip-flop per slice, one case per
    # site of the other kinds, and one of each single kind. A kind without
    # sites on this device (DSP on GW1N-1) would never empty its queue.
    for k in by_batch('shared'):
        if k not in ('lut', 'dff') and queues.get(k) and not getattr(sites, k):
            print(f'no {k} sites for {sorted({c.prim for c in queues[k]})}; {len(queues.pop(k))} cases not run')
    while any(queues.values()):
        batch = []
        luts, dffs = queues['lut'], queues['dff']
        for r, c, cls in sites.cls:
            if dffs and (not luts or len(dffs) * 2 >= len(luts)):
                batch.append((dffs.pop(), (r, c, cls, 'A')))
            elif luts:
                batch.append((luts.pop(), (r, c, cls, 'A')))
                if luts:
                    batch.append((luts.pop(), (r, c, cls, 'B')))
            else:
                break
        for k in by_batch('shared'):
            if k not in ('lut', 'dff'):
                batch += [(queues[k].pop(), site) for site in getattr(sites, k) if queues[k]]
        batch += [(queues[k].pop(), None) for k in by_batch('single') if queues[k]]
        batches.append(batch)
    return batches


# ---------------------------------------------------------------- netlist

def package_pins(db, vendor_device, device, package):
    """The package's pins, without the banks wired to in-package memory: the
    vendor moved outputs constrained there to other pins (CT1136)."""
    pins = db.pinout.get(vendor_device, db.pinout[device])[package]
    locked = {io_bank(db, r, c, ab) for _, r, c, ab, _ in db.sip_cst.get(vendor_device, {}).get(package, [])}
    return {p: (name, funcs) for p, (name, funcs) in pins.items() if db.pin_bank.get(name) not in locked}


def pick_pins(db, pins):
    """Harness pins: an output, five inputs and a clock. Pins in banks with MIPI
    output buffers come last: with the harness output in such a bank the vendor
    fails to place MIPI_OBUF (PR1082). Inputs there are fine (GW1N-9C)."""
    def mipi(name):
        r, c, _ = gowin_unpack.tbrl2rc(db, name)
        return 'mipi_obuf' in db.extra_func.get((r, c), {})

    mipi_banks = {db.pin_bank.get(name) for name, _ in pins.values() if mipi(name)}
    def in_mipi_bank(p):
        return db.pin_bank.get(pins[p][0]) in mipi_banks

    plain = sorted((p for p, (_, funcs) in pins.items() if not funcs),
                   key=lambda p: (in_mipi_bank(p), int(p) if p.isdigit() else p))
    # clock-only pins (no PLL or config function) first, then GCLKT before GCLKC:
    # on GW1N-9C DHCEN differs from the vendor with the clock on pin 51 (GCLKC_3)
    # and matches on pin 52 (GCLKT_3). Keeping the clock out of MIPI-output banks
    # is a precaution, not a measured failure.
    clocks = sorted((p for p, (_, funcs) in pins.items() if any(f.startswith('GCLK') for f in funcs)),
                    key=lambda p: (in_mipi_bank(p), not all(f.startswith('GCLK') for f in pins[p][1]),
                                   not any(f.startswith('GCLKT') for f in pins[p][1])))
    return {'clk': clocks[0], 'out': plain[0], 'in': plain[1:6]}


class Design:
    """A netlist and its constraints, built for the vendor's netlist reader."""

    def __init__(self, spec):
        self.spec, self.mod, self.cst = spec, codegen.Module(), codegen.Constraints()

    def inst(self, typ, name, conns, params=()):
        p = codegen.Primitive(typ, name)
        for port, (direction, width) in self.spec[typ]['ports'].items():
            if port in conns:
                p.portmap[port] = conns[port]
            elif direction == 'input':  # the vendor rejects unconnected or constant ports
                p.portmap[port] = ['gnd'] * width if width > 1 else 'gnd'
            else:
                # the vendor reads netlists per bit: a `wire [7:0]` on a port is
                # rejected with PA2060, a concatenation of 1-bit wires is not
                wires = [f'{name}_{port}' + (f'_{b}' if width > 1 else '') for b in range(width)]
                self.mod.wires.update(wires)
                p.portmap[port] = wires[0] if width == 1 else wires[::-1]
        p.params = dict(params)
        self.mod.primitives[name] = p
        return p


def netlist(batch, spec, pins, harness_io_type=None):
    """One design: an I/O harness and the cases. I/O cases get a top-level pad
    with IO_LOC and their attributes as IO_PORT; the harness pins then use
    `harness_io_type`, so that banks agree on VCCIO."""
    d = Design(spec)
    mod, cst = d.mod, d.cst
    mod.wires.add('gnd')
    d.inst('GND', 'harness_gnd', {'G': 'gnd'})
    data = []
    for i, pin in enumerate(['clk'] + [f'in{n}' for n in range(len(pins['in']))]):
        mod.inputs.add(f'{pin}_pad')
        mod.wires.add(pin)
        d.inst('IBUF', f'harness_ib_{pin}', {'I': f'{pin}_pad', 'O': pin})
        cst.ports[f'{pin}_pad'] = pins['clk'] if pin == 'clk' else pins['in'][i - 1]
        if harness_io_type:
            cst.attrs[f'{pin}_pad'] = {'IO_TYPE': harness_io_type}
        if pin != 'clk':
            data.append(pin)

    # As in the old tiled fuzzer, data inputs get their own undriven dummy wires
    # and outputs are left unconnected. Nothing is routed to a LUT, so neither
    # tool reorders its inputs, and no constant reaches a case. The vendor keeps
    # cells whose outputs are unused. Control inputs (clock, CE, set/reset)
    # come from input pins: left undriven they become constants, which hides the
    # flip-flop type. They use dedicated slice ports, so they cannot be reordered.
    names, wiring = {}, {}
    for i, (case, site) in enumerate(batch):
        kind = KINDS[case.site]
        name = f'inst{i}_{case.prim}'
        names[name] = (case, site)
        conns, sources = {}, data[i % len(data):] + data[:i % len(data)]
        wiring[name] = conns
        if kind.wire(d, name, case, site, conns, sources):
            continue
        ports = spec[case.prim]['ports']
        for port, (direction, width) in ports.items():
            if direction != 'input' or width != 1 or port in conns:
                continue
            src = kind.source(case, port, conns)
            if src == 'data' and sources:
                conns[port] = sources.pop(0)
            elif src in ('clk', 'gnd'):
                conns[port] = src
            else:
                conns[port] = f'{name}_{port}'
                mod.wires.add(conns[port])
        if 'DLLSTEP' in ports:
            # DLLSTEP must come from a DLL (PR2015; DDRDLL on GW5A, PR0015)
            d.inst('DLL' if 'DLL' in spec else 'DDRDLL', f'{name}_dll', {'CLKIN': 'clk'})
            conns['DLLSTEP'] = [f'{name}_dll_STEP_{b}' for b in range(ports['DLLSTEP'][1])][::-1]
        if 'DQSIN' in ports:
            # DQSIN must come from an input buffer (PR0014)
            mod.inputs.add(f'{name}_dqs_pad')
            mod.wires.add(f'{name}_dqs')
            d.inst('IBUF', f'{name}_dqs_buf', {'I': f'{name}_dqs_pad', 'O': f'{name}_dqs'})
            conns['DQSIN'] = f'{name}_dqs'
        d.inst(case.prim, name, conns, case.params if kind.cell_params else ())
        loc = site and kind.ins_loc(case, site)
        if loc:
            cst.cells[name] = loc

    mod.outputs.add('out_pad')
    # a clock primitive drives the output; otherwise it would have no load
    clock_out = next((f'{name}_{port}' for name, (case, _) in names.items() if case.site == 'clock'
                      for port, (direction, _) in spec[case.prim]['ports'].items() if direction == 'output'), None)
    for name, (case, _) in names.items():
        if case.prim in DIVIDER_LOAD:
            # these may only drive HCLK loads (vendor PR2060 on an OBUF), and
            # no output may dangle (PA2099): a CLKDIV with default settings on
            # each clock output passes it on
            outs = [p for p, (direction, _) in spec[case.prim]['ports'].items() if direction == 'output' and 'CLK' in p]
            for k, port in enumerate(outs):
                d.inst('CLKDIV', f'harness_div{k}', {'HCLKIN': f'{name}_{port}', 'RESETN': data[0]})
            clock_out = 'harness_div0_CLKOUT'
    d.inst('OBUF', 'harness_ob', {'I': clock_out or data[0], 'O': 'out_pad'})
    cst.ports['out_pad'] = pins['out']
    if harness_io_type:
        cst.attrs['out_pad'] = {'IO_TYPE': harness_io_type}
    return mod, cst, names, wiring


# ---------------------------------------------------------------- flows

def run_vendor(workdir, mod, cst, vendor_device, part, iob_regs=()):
    pnr = codegen.Pnr()
    pnr.device, pnr.partnumber, pnr.netlist, pnr.cst = vendor_device, part, mod, cst
    for mode in iob_regs:
        pnr.opt.options[f'{mode}_in_iob'] = '1'
    os.makedirs(workdir, exist_ok=True)
    with open(os.path.join(workdir, 'gw_sh.log'), 'w') as log:
        return pnr.run_pnr(workdir=workdir, stdout=log)


def run_apicula(workdir, mod, cst, names, device, part, iob_regs=()):
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
        case, site = names.get(name, (None, None))
        bel = site and KINDS[case.site].bel(case, site)
        if bel:
            cell['attributes']['BEL'] = bel  # nextpnr ignores INS_LOC
    with open(path, 'w') as f:
        json.dump(syn, f)
    subprocess.run([tool('NEXTPNR', 'nextpnr-himbaechel', 'yowasp-nextpnr-himbaechel-gowin'),
                    '--json', 'syn.json', '--write', 'pnr.json', '--device', part,
                    '--vopt', f'family={device}', '--vopt', 'cst=top.cst',
                    *(arg for mode in iob_regs for arg in ('--vopt', f'{mode}_in_iob'))],
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
        bits |= eclk_select_bits(db, ttyp)
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


def eclk_select_bits(db, ttyp):
    """Fuses of the IOLOGIC rows that pick ECLK1 as the fast clock
    (CLKODDRMUX_ECLK, CLKIDDRMUX_ECLK), less any fuse another row uses. That
    follows from routing: nextpnr reaches FCLK over HCLK lane 1 (HCLK_OUT2/3),
    the vendor over lane 0."""
    li = db.rev_logicinfo('IOLOGIC') if 'IOLOGIC' in db.logicinfo else {}
    eclk = {attrids.iologic_attrids['CLKODDRMUX_ECLK'], attrids.iologic_attrids['CLKIDDRMUX_ECLK']}
    out, other = set(), set()
    for tables in (db.shortval, db.longval):
        for table, rows in tables.get(ttyp, {}).items():
            for key, bits in rows.items():
                ours = table.startswith('IOLOGIC') and any(k > 0 and li[k][0] in eclk for k in key)
                (out if ours else other).update(bits)
    return out - other


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


# fuse table -> (logicinfo table, attribute ids, value ids), to name table rows
ROW_TABLES = {
    'IOBA': ('IOB', attrids.iob_attrids, attrids.iob_attrvals),
    'IOBB': ('IOB', attrids.iob_attrids, attrids.iob_attrvals),
    'BANK': ('IOB', attrids.iob_attrids, attrids.iob_attrvals),
    'CLS': ('SLICE', attrids.cls_attrids, attrids.cls_attrvals),
    'BSRAM': ('BSRAM', attrids.bsram_attrids, attrids.bsram_attrvals),
    'PLL': ('PLL', attrids.pll_attrids, attrids.pll_attrvals),
    'IOLOGIC': ('IOLOGIC', attrids.iologic_attrids, attrids.iologic_attrvals),
    'DSP': ('DSP', attrids.dsp_attrids, attrids.dsp_attrvals),
    '5A_DSP': ('5A_DSP', attrids.dsp_5a_attrids, attrids.dsp_5a_attrvals),
    'HCLK': ('HCLK', attrids.hclk_attrids, attrids.hclk_attrvals),
}
_row_names = {}


def fuse_rows(db, r, c, bit):
    """The fuse table rows a bit is in, by attribute names where known, such
    as 'IOBA: IO_TYPE=LVCMOS18,DRIVE=8'; the shortest three."""
    out = []
    ttyp = db.grid[r][c]
    for tables in (db.shortval, db.longval):
        for name, rows in tables.get(ttyp, {}).items():
            prefix = next((p for p in ROW_TABLES if name.startswith(p)), None)
            for key, bits in rows.items():
                if bit not in bits:
                    continue
                if prefix is None or ROW_TABLES[prefix][0] not in db.logicinfo:
                    out.append(f'{name}{key}')
                    continue
                if prefix not in _row_names:
                    li, an, av = ROW_TABLES[prefix]
                    _row_names[prefix] = (db.rev_logicinfo(li), {v: k for k, v in an.items()},
                                          {v: k for k, v in av.items()})
                li, ids, vals = _row_names[prefix]
                terms = [('!' if k < 0 else '') + f'{ids.get(li[abs(k)][0], li[abs(k)][0])}='
                         f'{vals.get(li[abs(k)][1], li[abs(k)][1])}' for k in key if k and abs(k) in li]
                out.append(f'{name}: ' + ','.join(terms))
    out += [f'{bel}.{flag}' for bel, b in db[r, c].bels.items() for flag, bits in b.flags.items() if bit in bits]
    return sorted(set(out), key=len)[:3]


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
    """Cells of an unpacked bitstream; site kinds look up their case in it."""

    def __init__(self, nl, spec):
        self.nl, self.spec = nl, spec
        self.luts = collections.defaultdict(list)  # INIT -> [LUT4 cell names]
        for name, cell in nl.cells.items():
            if cell['type'] == 'LUT4' and 'INIT' in cell['params']:
                self.luts[literal_value(cell['params']['INIT'])].append(name)

    def named(self, site, suffix):
        """The cell R<r>C<c>_<suffix> on a site's tile, or None."""
        return self.nl.cells.get(f'R{site[0] + 1}C{site[1] + 1}_{suffix}')

    def first(self, match, site=None, suffix=''):
        """The first cell whose type matches, named R<r>C<c>_..<suffix> when a site is given."""
        prefix = f'R{site[0] + 1}C{site[1] + 1}_' if site else ''
        return next((cell for n, cell in self.nl.cells.items()
                     if n.startswith(prefix) and n.endswith(suffix) and match(cell['type'])), None)

    def on_tile(self, typ, site):
        """A cell gowin_unpack names by a counter (BSRAM, rPLL), found by its ports' tile."""
        prefix = f'R{site[0] + 1}C{site[1] + 1}_'
        return next((cell for cell in self.nl.cells.values() if cell['type'] == typ
                     and any(str(w).startswith(prefix) for w in cell['ports'].values())), None)

    def canonical(self, cell):
        """A decoded cell as canonical() describes it, with constant inputs."""
        if cell is None:
            return {'cell': None}
        ports = self.spec.get(cell['type'], {'ports': {}})['ports']
        inputs = {}
        for port, wire in cell['ports'].items():
            if ports.get(port, ('input',))[0] == 'input':
                root = self.nl.find(wire)
                inputs[port] = root if root in ('VCC', 'VSS') else 'sig'
        return canonical(cell['type'], literals(cell['params'].items()), inputs)


def same(a, b):
    """Compare descriptions. Parameters are compared where both sides have them,
    because the unpacker does not emit every parameter."""
    if a.keys() != b.keys():
        return False
    if any(a[k] != b[k] for k in a.keys() - {'params'}):
        return False
    x, y = a.get('params') or {}, b.get('params') or {}
    return all(x[k] == y[k] for k in x.keys() & y.keys())


# ---------------------------------------------------------------- site kinds
#
# Each kind says how its cases are batched, placed, wired and compared. A site
# is (row, col, cls, ab); what cls and ab hold depends on the kind.

class Kind:
    # how cases are put in designs: shared (with other kinds), own (designs of
    # their own, from a pool of sites), io (grouped by bank voltage), alone (one
    # case per design), widelut, or single (one per shared design, at no site)
    batch = 'shared'
    # bel: INS_LOC for the vendor and a BEL attribute for nextpnr; pin: IO_LOC;
    # nextpnr: nextpnr places it and the vendor gets the same place; vendor:
    # the other way round; free: both tools place it
    placement = 'bel'
    compare_fuses = True
    cell_params = True  # False: the params are IO_PORT attributes, not cell parameters

    # Methods a kind overrides, with their defaults. The vendor's INS_LOC and
    # nextpnr's BEL attribute for a site, or None:
    def ins_loc(self, case, site):
        return None

    def bel(self, case, site):
        return None

    # the bel, and the tiles, whose fuse differences belong to the case
    def owner(self, case, site):
        return site[2]

    def tiles(self, db, case, site):
        return [site[:2]] if site else []

    # (site, INS_LOC) of where nextpnr placed the case (placement 'nextpnr'),
    # and the site the vendor chose, from its bitstream (placement 'vendor')
    def from_placed(self, db, case, bel):
        return None

    def vendor_site(self, db, vt, case):
        return None

    # the driver of an unconnected 1-bit input: 'clk', 'data', 'gnd', or None
    # for a dummy wire
    def source(self, case, port, conns):
        if port in ('CLK', 'G'):
            return 'clk'
        if port == 'CLKIN' or port in CONTROL_PORTS:
            return 'data'
        return None

    # extra netlist for the case; returns True if it instantiated the case
    def wire(self, d, name, case, site, conns, sources):
        return False

    # the case as decoded from a bitstream, and as generated; by default the
    # kind is compared on fuses only
    def describe(self, dec, case, site):
        return self.generated(case, None, None)

    def generated(self, case, conns, spec):
        return {'cell': case.prim}

    # comparison beyond cells and fuses; returns the tiles it accounts for
    def check(self, b, name, case, site, res):
        return set()


def slice_index(site):
    """LUT/DFF/ALU number of a slice site: 2 * cls, plus 1 for B."""
    return 2 * site[2] + 'AB'.index(site[3])


def slice_ins_loc(site):
    row, col, cls, ab = site
    return (row + 1, col + 1, cls, ab)


def slice_site(row, col, n):
    """The slice site of LUT/DFF/ALU n, and its INS_LOC."""
    site = (row, col, n // 2, 'AB'[n % 2])
    return site, slice_ins_loc(site)


def generated_cell(case, conns, spec):
    """A flip-flop, latch or other cell as generated, with the inputs tied to GND."""
    inputs = {p: 'VSS' if conns.get(p, 'gnd') == 'gnd' else 'sig'
              for p, (d, _) in spec[case.prim]['ports'].items() if d == 'input'}
    return canonical(case.prim, literals(case.params), inputs)


class Slice(Kind):
    """A LUT (two per slice) or a flip-flop or latch (one per slice, as the two
    flip-flops of a slice share clock, CE and set/reset modes): (row, col, cls,
    'A'|'B')."""
    bel_type = None

    def ins_loc(self, case, site):
        return slice_ins_loc(site)

    def bel(self, case, site):
        row, col = site[:2]
        return f'X{col}Y{row}/{self.bel_type}{slice_index(site)}'


class Lut(Slice):
    bel_type = 'LUT'

    def owner(self, case, site):
        return f'LUT{slice_index(site)}'

    def describe(self, dec, case, site):
        cell = dec.named(site, f'LUT4_{slice_index(site)}')
        if cell:
            return {'cell': 'LUT', 'init': literal_value(cell['params']['INIT'])}
        # constant LUTs are written as an assign of the F wire to VCC or VSS
        row, col = site[:2]
        const = dec.nl.find(f'R{row + 1}C{col + 1}_F{slice_index(site)}')
        return {'cell': 'LUT', 'init': {'VCC': 0xffff, 'VSS': 0}.get(const)}

    def generated(self, case, conns, spec):
        return {'cell': 'LUT', 'init': lut_init(case)}


class Dff(Slice):
    bel_type = 'DFF'

    def owner(self, case, site):
        return f'CLS{site[2]}'

    def describe(self, dec, case, site):
        is_ff = lambda typ: typ.startswith(('DFF', 'DL'))
        return dec.canonical(dec.first(is_ff, site, f'_{2 * site[2]}'))

    def generated(self, case, conns, spec):
        return generated_cell(case, conns, spec)


class Alu(Kind):
    """An ALU in ALU1 (CLS0, B): with CIN tied to GND, nextpnr puts a carry-in
    head in ALU0 of the same chain. ALU clusters ignore BEL, so nextpnr places
    them."""
    batch = 'own'
    placement = 'nextpnr'

    def ins_loc(self, case, site):
        return slice_ins_loc(site)  # until nextpnr has placed it

    def owner(self, case, site):
        return f'CLS{site[2]}'

    def from_placed(self, db, case, bel):
        m = re.fullmatch(r'X(\d+)Y(\d+)/(?:ALU|LUT)(\d)', bel or '')
        if not m:
            return None
        col, row, n = map(int, m.groups())
        return slice_site(row, col, n)

    def source(self, case, port, conns):
        if port == 'CIN':
            return 'gnd'
        return super().source(case, port, conns)

    def describe(self, dec, case, site):
        cell = dec.named(site, f'ALU_{slice_index(site)}')
        if cell is None:
            return {'cell': None}
        return {'cell': 'ALU', 'params': {'ALU_MODE': literal_value(cell['params'].get('ALU_MODE'))}}

    def generated(self, case, conns, spec):
        # omitted: primitive.xml's default
        return {'cell': 'ALU', 'params': {'ALU_MODE': literal_value(dict(case.params).get('ALU_MODE', '0'))}}


class Ssram(Kind):
    """A whole logic tile, (row, col, 'RAM16', '-'). A BEL makes nextpnr crash
    (RAM16SDP2/4) or leave its blocker cells unplaced (RAM16SDP1), so nextpnr
    places it. ROM16 becomes a LUT, at a slice site."""
    batch = 'own'
    placement = 'nextpnr'

    def ins_loc(self, case, site):
        row, col, cls, _ = site
        if cls == 'RAM16':
            return f'R{row + 1}C{col + 1}'
        return slice_ins_loc(site)

    def owner(self, case, site):
        if site[2] == 'RAM16':
            return 'RAM16'
        return f'CLS{site[2]}'

    # an undriven WRE is a constant, which the vendor folds into the LSR mux
    def source(self, case, port, conns):
        return 'data' if port == 'WRE' else super().source(case, port, conns)

    def from_placed(self, db, case, bel):
        m = re.fullmatch(r'X(\d+)Y(\d+)/(RAM16SDP4|LUT)(\d?)', bel or '')
        if not m:
            return None
        col, row = int(m.group(1)), int(m.group(2))
        if m.group(3) == 'RAM16SDP4':
            return (row, col, 'RAM16', '-'), f'R{row + 1}C{col + 1}'
        return slice_site(row, col, int(m.group(4)))

    def describe(self, dec, case, site):
        if site[2] == 'RAM16':
            # gowin_unpack writes every SSRAM as RAM16SDP4; compare the case's INITs
            cell = dec.named(site, 'RAM16')
            params = {k: v for k, v in literals(cell['params'].items()).items()
                      if k in dict(case.params)} if cell else {}
        else:
            # nextpnr implements ROM16 as a LUT; its INIT is the ROM contents
            cell = dec.named(site, f'LUT4_{slice_index(site)}')
            params = {'INIT_0': literal_value(cell['params']['INIT'])} if cell else {}
        return {'cell': 'SSRAM' if cell else None, 'params': params}

    def generated(self, case, conns, spec):
        return {'cell': 'SSRAM', 'params': literals(case.params)}


class Dsp(Kind):
    """A DSP block, (row, col, 'DSP', n): the n-th of its row, as the vendor's
    DSP_R<row>[n]. DSP clusters get DUMMY_CELLs that stay unplaced with a BEL,
    so nextpnr places them. gowin_unpack decodes fuse-level modes only."""
    placement = 'nextpnr'

    def ins_loc(self, case, site):
        row, n = site[0], site[3]
        return f'DSP_R{row + 1}[{n}][A]'

    def tiles(self, db, case, site):
        # the main tile and the DSP_AUX tiles to its right
        row, col = site[:2]
        out = [(row, col)]
        while col + len(out) < db.cols and any(b.startswith('DSP_AUX') for b in db[row, col + len(out)].bels):
            out.append((row, col + len(out)))
        return out

    def from_placed(self, db, case, bel):
        m = re.fullmatch(r'X(\d+)Y(\d+)/(\w+)', bel or '')
        if not m:
            return None
        col, row = int(m.group(1)), int(m.group(2))
        cols = [c for c in range(db.cols) if 'DSP' in db[row, c].bels]
        if col not in cols:
            return None
        n = cols.index(col)
        # DSP_R<row>[n][A|B]: the macro is the digit after the primitive name
        macro = m.group(3)[len(case.prim):][:1]
        loc = f'DSP_R{row + 1}[{n}]'
        if macro:
            loc += f'[{"AB"[int(macro)]}]'
        return (row, col, 'DSP', n), loc


class Bsram(Kind):
    """(row, col, 'BSRAM', n): the n-th BSRAM of a row, as the vendor numbers
    them in INS_LOC. gowin_unpack does not decode BSRAM parameters."""

    def ins_loc(self, case, site):
        row, n = site[0], site[3]
        return f'BSRAM_R{row + 1}[{n}]'

    def bel(self, case, site):
        row, col = site[:2]
        return f'X{col}Y{row}/BSRAM'

    def tiles(self, db, case, site):
        # the BSRAM tile and the two to its right: BSRAM_AUX bels on GW1N/GW2A,
        # tiles with BSRAM tables but no bel on GW5A
        row, col = site[:2]
        out = [(row, col)]
        for c in (col + 1, col + 2):
            if c < db.cols:
                tile = db[row, c]
                if 'BSRAM_AUX' in tile.bels or ('BSRAM' not in tile.bels
                                                and 'BSRAM_SP' in db.shortval.get(tile.ttyp, {})):
                    out.append((row, c))
        return out

    def describe(self, dec, case, site):
        return {'cell': 'BSRAM' if dec.on_tile('BSRAM', site) else None}

    def generated(self, case, conns, spec):
        return {'cell': 'BSRAM'}


class PllSite(Kind):
    """(row, col, 'PLL' or 'PLLA', side): the vendor calls it PLL_<side>, nextpnr
    X<col>Y<row>/PLL."""

    def ins_loc(self, case, site):
        return f'PLL_{site[3]}'

    def bel(self, case, site):
        row, col = site[:2]
        return f'X{col}Y{row}/PLL'


class Pll(PllSite):
    """An rPLL (GW1N/GW2A)."""

    def tiles(self, db, case, site):
        # the RPLLA tile and the adjacent RPLLB tiles
        row, col = site[:2]
        return [(row, col)] + [(row, c) for c in range(col - 3, col + 4)
                               if c != col and 0 <= c < db.cols and 'RPLLB' in db[row, c].bels]

    def describe(self, dec, case, site):
        cell = dec.on_tile('rPLL', site)
        if cell is None:
            return {'cell': None, 'params': {}}
        # DEVICE is not a fuse; it is unpacked as the family name
        return {'cell': 'rPLL', 'params': literals(cell['params'].items(), skip={'DEVICE'})}

    def generated(self, case, conns, spec):
        return {'cell': 'rPLL', 'params': literals(case.params, skip={'DEVICE'})}


class Plla(PllSite):
    """A GW5A PLL, configured through a bitstream slot, which is compared."""

    def check(self, b, name, case, site, res):
        slot = b.db.extra_func[(site[0], site[1])]['pll']['slot_idx']
        vs, as_ = b.vslots.get(slot), b.aslots.get(slot)
        if vs is None or as_ is None:
            res['status'] = 'mismatch'
            res['why'] = [f'slot {slot}: vendor {"has" if vs is not None else "lacks"} it, '
                          f'apicula {"has" if as_ is not None else "lacks"} it']
            return set()
        bits = sum(v != as_[y][x] for y, row in enumerate(vs) for x, v in enumerate(row))
        if bits:
            dec = [gowin_unpack.parse_attrvals(s, b.db.rev_logicinfo('PLL'), b.db.shortval[1024]['PLL'],
                                               attrids.pll_attrids, 'PLL') for s in (vs, as_)]
            res['status'] = 'mismatch'
            res['why'] = [f'slot {slot}: {bits} bits differ']
            res['slot_attrs'] = {k: (dec[0].get(k), dec[1].get(k)) for k in dec[0].keys() | dec[1].keys()
                                 if dec[0].get(k) != dec[1].get(k)}
        return set()


class Osc(Kind):
    """An oscillator: one per device, at no site. Its bel is named after the
    primitive (OSCA) or the kind (OSC)."""
    batch = 'single'
    placement = 'free'

    def tiles(self, db, case, site):
        return [singleton_loc(db, case.prim, 'osc')]

    def describe(self, dec, case, site):
        return dec.canonical(dec.first(lambda typ: typ.startswith('OSC')))

    def generated(self, case, conns, spec):
        return generated_cell(case, conns, spec)


class Io(Kind):
    """An I/O buffer on a plain pin: (row, col, 'IOBA'|'IOBB', pin), or for a
    differential buffer the A side and [pin, pin]. Its params are IO_PORT
    attributes, compared on fuses (gowin_unpack writes them to a .cst)."""
    batch = 'io'
    placement = 'pin'
    cell_params = False

    def source(self, case, port, conns):
        return 'data'  # buffer data and enable inputs

    def wire(self, d, name, case, site, conns, sources):
        ports = d.spec[case.prim]['ports']
        for k, (pad, pin) in enumerate(io_pads(case, site)):
            conns[pad] = f'{name}_pad' + ('_n' if k else '')
            getattr(d.mod, PORT_LISTS[ports[pad][0]]).add(conns[pad])
            d.cst.ports[conns[pad]] = pin
            if case.params:  # the vendor rejects an IO_PORT line without attributes (CT2000)
                d.cst.attrs[conns[pad]] = dict(case.params)

    def describe(self, dec, case, site):
        cell = dec.first(lambda typ: typ.endswith('BUF'), site, f'_{site[2][-1]}')
        return {'cell': cell['type'] if cell else None}


class Iol(Kind):
    """I/O logic, (row, col, 'IOBA'|'IOBB', pin), with an I/O buffer on its pin
    (vendor PR0018): an IBUF feeding its data input, or an OBUF fed by its
    output."""
    batch = 'io'
    placement = 'pin'

    def owner(self, case, site):
        return f'IOLOGIC{site[2][-1]}'

    def tiles(self, db, case, site):
        # the pair's B cell, which wide primitives use too, has its fuses in
        # the IOBB fuse_cell_offset tile on GW5
        iobb = db[site[0], site[1]].bels.get('IOBB')
        off = iobb.fuse_cell_offset if iobb else None
        return [site[:2]] + ([(site[0] + off[0], site[1] + off[1])] if off and any(off) else [])

    def source(self, case, port, conns):
        if port in ('CLK', 'PCLK', 'FCLK'):
            return 'clk'
        return super().source(case, port, conns)

    def wire(self, d, name, case, site, conns, sources):
        ports = d.spec[case.prim]['ports']
        pad = f'{name}_pad'
        data_in = next((p for p in ports if p in IOL_INPUT), None)
        if data_in:
            conns[data_in] = f'{name}_in'
            d.mod.wires.add(conns[data_in])
            d.mod.inputs.add(pad)
            d.inst('IBUF', f'{name}_buf', {'I': pad, 'O': conns[data_in]})
        else:
            data_out = next(p for p in ports if p in IOL_OUTPUT)
            conns[data_out] = f'{name}_out'
            d.mod.wires.add(conns[data_out])
            d.mod.outputs.add(pad)
            d.inst('OBUF', f'{name}_buf', {'I': conns[data_out], 'O': pad})
        d.cst.ports[pad] = site[3]
        d.cst.attrs[pad] = {'IO_TYPE': ps.IOL_IO_TYPE}

    def describe(self, dec, case, site):
        cell = dec.first(lambda typ: ps.SITES.get(typ) == 'iol', site, f'_{site[2][-1]}')
        if cell is None:
            return {'cell': None, 'params': {}}
        return {'cell': cell['type'], 'params': literals(cell['params'].items())}

    def generated(self, case, conns, spec):
        return {'cell': case.prim, 'params': literals(case.params)}


class IobReg(Kind):
    """A flip-flop (IOB_IREG, IOB_OREG, IOB_IOREG) that both tools pack into
    the I/O logic of its pad, (row, col, 'IOBA'|'IOBB', pin). Compared on
    fuses, like a primitive without a decoder."""
    batch = 'io'
    placement = 'pin'
    owner, tiles = Iol.owner, Iol.tiles  # the I/O logic it is packed into

    def wire(self, d, name, case, site, conns, sources):
        params = dict(case.params)
        typ = params.pop('TYPE', d.spec[case.prim]['params']['TYPE']['default'])
        pad = f'{name}_pad'
        d.cst.ports[pad] = site[3]
        d.cst.attrs[pad] = {'IO_TYPE': ps.IOL_IO_TYPE}
        # clock and control inputs, each from its own pin; D and Q below
        src = iter(sources)
        ctrl = {port: 'clk' if port == 'CLK' else next(src)
                for port, (direction, _) in d.spec[typ]['ports'].items()
                if direction == 'input' and port != 'D'}
        d_in, q = f'{name}_d', f'{name}_q'
        if case.prim == 'IOB_IREG':
            d.mod.inputs.add(pad)
            d.inst('IBUF', f'{name}_buf', {'I': pad, 'O': d_in})
        elif case.prim == 'IOB_OREG':
            d_in = next(src)
            d.mod.outputs.add(pad)
            d.inst('OBUF', f'{name}_buf', {'I': q, 'O': pad})
        else:  # IOB_IOREG: an input and an output flip-flop on one IOBUF
            oq = f'{name}_oq'
            d.mod.inouts.add(pad)
            d.mod.wires.add(oq)
            d.inst('IOBUF', f'{name}_buf', {'IO': pad, 'O': d_in, 'I': oq, 'OEN': next(src)})
            d.inst(typ, f'{name}_oreg', {**ctrl, 'D': next(src), 'Q': oq}, params.items())
        d.mod.wires.update([d_in, q])
        d.inst(typ, name, {**ctrl, 'D': d_in, 'Q': q}, params.items())
        return True


class IoBank(Kind):
    """IO_BANK: two or three buffers on pins of one bank, (row, col,
    'IOBA'|'IOBB', [pin, ...]) with the place of the first pin. Buffer n is
    the param IO<n>, its IO_PORT attributes IO<n>_<attribute>. Alone in its
    design and compared on fuses; differences on the bank's other pins belong
    to it as the bank's only I/O case."""
    batch = 'bank'
    placement = 'pin'
    cell_params = False

    def wire(self, d, name, case, site, conns, sources):
        params, src = dict(case.params), itertools.cycle(sources)
        bufs = [prim for k, prim in sorted(params.items()) if re.fullmatch(r'IO\d', k)]
        for n, (prim, pin) in enumerate(zip(bufs, site[3])):
            ports, pad_port, pad = d.spec[prim]['ports'], IO_PAD[prim], f'{name}_io{n}_pad'
            getattr(d.mod, PORT_LISTS[ports[pad_port][0]]).add(pad)
            inputs = {port: next(src) for port, (direction, _) in ports.items()
                      if direction == 'input' and port != pad_port}
            d.inst(prim, f'{name}_io{n}', {pad_port: pad, **inputs})
            d.cst.ports[pad] = pin
            attrs = {k.split('_', 1)[1]: v for k, v in params.items() if k.startswith(f'IO{n}_')}
            if attrs:
                d.cst.attrs[pad] = attrs
        return True


class Clock(Kind):
    """A clock buffer, divider or selector, alone in its design and driving the
    harness output. The vendor reports no position for CLKDIV and CLKDIV2, so
    nextpnr gets a BEL, (row, col, 'BEL', bel), read from the vendor's HCLK
    fuses. nextpnr ignores it, and places DHCEN by routing, so HCLK settings
    are compared without their positions."""
    batch = 'alone'
    placement = 'vendor'

    def bel(self, case, site):
        row, col, _, bel = site
        return f'X{col}Y{row}/{bel}'

    def owner(self, case, site):
        return site[3]

    def source(self, case, port, conns):
        # the first clock input from the clock pin, the rest from data pins
        if port in CLOCK_INPUTS and 'clk' not in conns.values():
            return 'clk'
        # DCS: every clock input from the clock pin (nextpnr crashes routing
        # GW5A DCS inputs from plain pins)
        if case.prim == 'DCS' and port.startswith('CLK') and port != 'CLKSEL':
            return 'clk'
        return 'data'

    def vendor_site(self, db, vt, case):
        site = vendor_clock_site(db, vt, case)
        # GW5A-25A: the vendor uses HCLKDIV1 on X0Y1, where nextpnr has no
        # CLKDIV_1 bel; compared without positions instead
        if site and re.fullmatch(r'CLKDIV_\d', site[3]):
            return None
        return site

    def check(self, b, name, case, site, res):
        placed = b.placed.get(name)
        if case.prim in ('CLKDIV', 'CLKDIV2'):
            # Apicula's fuses must select the bel nextpnr placed it on
            asite = vendor_clock_site(b.db, b.at, case)
            selected = asite and self.bel(case, asite)
            if asite is None and site is not None or asite is not None and selected != placed:
                res['status'] = 'mismatch'
                res['why'] = [f'Apicula fuses select {selected}, nextpnr placed it at {placed}']
                return set()
            if asite is not None and asite == site:
                return set()  # the same bel: the fuse comparison applies
            res['placed'] = {'vendor': site and self.bel(case, site), 'apicula': placed}
        vendor, apicula = hclk_settings(b.db, b.vt), hclk_settings(b.db, b.at)
        if vendor != apicula:
            res['status'] = 'mismatch'
            res['why'] = [f'HCLK settings: vendor {vendor}, apicula {apicula}']
        return {tile for tile in b.vt if 'HCLK' in b.db.shortval.get(b.db[tile].ttyp, {})}


class Lone(Kind):
    """Any other primitive: alone in its design, placed by both tools. Pads
    become top-level ports; the vendor picks their pins, and nextpnr gets them."""
    batch = 'alone'
    placement = 'vendor'

    def source(self, case, port, conns):
        if 'CLK' in port:
            return 'clk'
        return super().source(case, port, conns)

    def wire(self, d, name, case, site, conns, sources):
        ports = d.spec[case.prim]['ports']
        for pad in lone_pads(ports, case.prim):
            conns[pad] = f'{name}_{pad}'
            getattr(d.mod, PORT_LISTS[ports[pad][0]]).add(conns[pad])


class WideLut(Kind):
    """A MUX2_LUTn tree over LUT4 leaves, placed by both tools and compared on
    where its leaves end up (widelut_tree). Leaf inputs are dummy wires; each
    mux level selects from its own data pin."""
    batch = 'widelut'
    placement = 'free'
    compare_fuses = False

    def wire(self, d, name, case, site, conns, sources):
        def tree(level, leaves, path):
            if level == 4:
                out = f'{name}_f{path}'
                ins = {p: f'{name}_l{path}_{p}' for p in ('I0', 'I1', 'I2', 'I3')}
                d.mod.wires.update([out, *ins.values()])
                d.inst('LUT4', f'{name}_l{path}', {'F': out, **ins}, [('INIT', leaves[0])])
                return out
            half = len(leaves) // 2
            i0 = tree(level - 1, leaves[:half], path + '0')
            i1 = tree(level - 1, leaves[half:], path + '1')
            out = f'{name}_o{path}'
            d.mod.wires.add(out)
            select = sources[(level - 5) % len(sources)]
            d.inst(f'MUX2_LUT{level}', f'{name}_m{path}' if path else name,
                   {'I0': i0, 'I1': i1, 'S0': select, 'O': out})
            return out

        tree(int(case.prim[-1]), widelut_inits(case), '')
        return True

    def describe(self, dec, case, site):
        return {'cell': 'WIDELUT', 'tree': widelut_tree(dec.nl, dec.luts, case)}

    def generated(self, case, conns, spec):
        return {'cell': 'WIDELUT', 'tree': 'ok'}


# in allocation order within each batch class
KINDS = {'clock': Clock(), 'lone': Lone(), 'widelut': WideLut(), 'alu': Alu(), 'ssram': Ssram(),
         'iob': Io(), 'diob': Io(), 'iol': Iol(), 'iobreg': IobReg(), 'iobank': IoBank(), 'lut': Lut(), 'dff': Dff(),
         'bsram': Bsram(), 'pll': Pll(), 'plla': Plla(), 'dsp': Dsp(), 'osc': Osc()}


def vendor_errors(workdir):
    """{(name, code): [messages]} of the vendor log, for a run that wrote no bitstream."""
    log = os.path.join(workdir, 'vendor/impl/pnr/top.log')
    return codegen.Pnr.read_err_log(log) if os.path.exists(log) else {}


def vendor_failed(workdir):
    log = os.path.join(workdir, 'vendor/impl/pnr/top.log')
    why = []
    if os.path.exists(log):
        with open(log, errors='replace') as f:
            why = [line.strip() for line in f if line.startswith('ERROR')]
    return {'error': 'vendor produced no bitstream', 'why': why}, None


def rejections(errs, name):
    """The vendor's REJECT_CODES messages about case `name`: about the
    instance, or a net or pad named after it (CT1108 names the pad)."""
    return [msg for (n, code), msgs in errs.items() if code in REJECT_CODES
            and (n == name or n.startswith(name + '_')) for msg in msgs]


_apicula_error = re.compile(r'\w*(Error|Exception): ')


def apicula_errors(log):
    """Error lines of an Apicula flow log (Yosys, nextpnr, gowin_pack)."""
    with open(log, errors='replace') as f:
        return [line.strip() for line in f if 'ERROR' in line or _apicula_error.match(line)]


def run_batch(device, db, spec, pins, batch, workdir, baseline, harness_io_type=None):
    vendor_device, part, _ = DEVICES[device]
    mod, cst, names, wiring = netlist(batch, spec, pins, harness_io_type)
    # IOB_* cases: ask both tools to pack registers into I/O logic. Only those
    # cases put a flip-flop next to a buffer, so no other case is affected.
    iob_regs = sorted({case.prim[4:].lower() for case, _ in batch if case.site == 'iobreg'})
    vendor = functools.partial(run_vendor, os.path.join(workdir, 'vendor'), mod, cst, vendor_device, part, iob_regs)

    def apicula():
        try:
            return run_apicula(os.path.join(workdir, 'apicula'), mod, cst, names, device, part, iob_regs)
        except subprocess.CalledProcessError:
            return None

    # With kinds nextpnr places, Apicula runs first and the vendor gets the
    # location nextpnr chose; with kinds the vendor places, the vendor runs
    # first and nextpnr gets its pins and sites. Otherwise the two flows are
    # independent and run at the same time. A flow that fails stops the other
    # one, unless the design is a single case, which the vendor may reject:
    # then both run, and Apicula must fail too.
    placements = {KINDS[case.site].placement for case, _ in names.values()}
    follow = 'nextpnr' in placements
    alone = len(names) == 1
    if follow:
        ares = apicula()
        for name, (case, site) in list(names.items()):
            placement = ares and KINDS[case.site].from_placed(db, case, ares[2].get(name))
            if placement:
                names[name] = (case, placement[0])
                cst.cells[name] = placement[1]
        vres = vendor() if ares or alone else None
    elif 'vendor' in placements:
        vres = vendor()
        if vres:
            cst.ports.update(vendor_pins(os.path.join(workdir, 'vendor')))
            vt = chipdb.tile_bitmap(db, vres.bitmap, empty=True)
            for name, (case, site) in list(names.items()):
                names[name] = (case, KINDS[case.site].vendor_site(db, vt, case) or site)
        ares = apicula() if vres or (alone and any(rejections(vendor_errors(workdir), n) for n in names)) else None
    else:
        with concurrent.futures.ThreadPoolExecutor(2) as pool:
            vfut, afut = pool.submit(vendor), pool.submit(apicula)
            vres, ares = vfut.result(), afut.result()
    errs = vres.errs if vres else vendor_errors(workdir)
    rejected = {name: why for name in names if (why := rejections(errs, name))}
    if rejected and not alone:
        # judge each case alone: a rejection can name an innocent case (CT1136
        # names the pad that loses the bank voltage, not the one that set it)
        return {'error': 'the vendor rejected settings', 'why': [m for ms in rejected.values() for m in ms]}, None
    # a case with settings the vendor rejects is judged by whether Apicula
    # failed too, not by bitstreams: the vendor may have moved its pad
    if vres is None or ares is None or rejected:
        if not alone:  # split the design to find the case
            if ares is None and (vres or follow):
                return {'error': 'the Apicula flow failed', 'why': apicula_errors(os.path.join(workdir, 'apicula/tools.log'))}, None
            return vendor_failed(workdir)
        (name, (case, site)), = names.items()
        if name in rejected:
            status, why = 'accepted' if ares else 'rejected', rejected[name]
        elif vres is None:  # a design the vendor rejects is invalid, whatever Apicula does with it
            status, why = 'invalid', vendor_failed(workdir)[0]['why']
        else:  # unsupported is a failure to fix in Apicula, not a case to drop
            status, why = 'unsupported', apicula_errors(os.path.join(workdir, 'apicula/tools.log'))
        return {'cases': {name: {'case': case.to_json(), 'site': site, 'status': status, 'why': why}},
                'unattributed': {}}, None
    abm, aslots, placed = ares
    b = types.SimpleNamespace(db=db, placed=placed, vslots=vres.extra_slots, aslots=aslots,
                              vt=chipdb.tile_bitmap(db, vres.bitmap, empty=True),
                              at=chipdb.tile_bitmap(db, abm, empty=True))
    diffs = diff_bits(db, b.vt, b.at)
    decoded = {}
    if batch:
        fs = {'vendor': os.path.join(workdir, 'vendor/impl/pnr/top.fs'), 'apicula': os.path.join(workdir, 'apicula/top.fs')}
        with concurrent.futures.ThreadPoolExecutor(2) as pool:
            nls = {side: pool.submit(unpacked_netlist.unpack, device, path,
                                     os.path.join(workdir, f'{side}_unpack.v'), REPO) for side, path in fs.items()}
            decoded = {side: Decoded(nl.result(), spec) for side, nl in nls.items()}
    if not all(KINDS[case.site].compare_fuses for case, _ in names.values()):
        diffs = {}
    if baseline is not None:
        diffs = {k: v - baseline.get(k, set()) for k, v in diffs.items()}
        diffs = {k: v for k, v in diffs.items() if v}

    results = {}
    by_bel = {}  # (row, col, bel) -> case name
    by_tile = collections.defaultdict(list)
    by_bank = collections.defaultdict(list)  # I/O cases per bank
    accounted = set()  # tiles whose differences a kind's check covers
    for name, (case, site) in names.items():
        kind = KINDS[case.site]
        res = {'case': case.to_json(), 'site': site, 'status': 'ok'}
        problems = [msg for (n, code), msgs in vres.errs.items() if n == name
                    for msg in msgs if code in INVALID_CODES or msg.startswith('ERROR')]
        if site and kind.placement == 'bel' and placed.get(name) != kind.bel(case, site):
            problems.append(f'nextpnr placed it at {placed.get(name)}')
        if problems:
            res['status'] = 'invalid'
            res['why'] = problems
        else:
            gen = kind.generated(case, wiring[name], spec)
            dv, da = (kind.describe(decoded[side], case, site) for side in ('vendor', 'apicula'))
            if not same(dv, da):
                res['status'] = 'mismatch'
            elif not same(da, gen):
                res['status'] = 'decode'
            if res['status'] != 'ok':
                res['generated'], res['vendor'], res['apicula'] = gen, dv, da
            else:
                accounted |= kind.check(b, name, case, site, res)
        results[name] = res
        for tile in kind.tiles(db, case, site):
            by_tile[tile].append(name)
        if site:
            by_bel[(*site[:2], kind.owner(case, site))] = name
        if kind.placement == 'pin':
            # bank settings are shared by every I/O in the bank
            bank = io_bank(db, site[0], site[1], site[2][-1])
            by_bank[bank].append(name)
            if bank in db.bank_tiles:
                by_tile[db.bank_tiles[bank]].append(name)
    diffs = {k: v for k, v in diffs.items() if k not in accounted}

    # Unused I/Os are configured from their bank's settings, so differences in
    # an I/O tile with no case belong to the I/O cases of that bank.
    def bank_cases(r, c):
        if not any(b.startswith('IOB') for b in db[r, c].bels):
            return []
        return [n for bank in {io_bank(db, r, c, ab) for ab in 'AB'} for n in by_bank.get(bank, [])]

    # a case alone in its design and placed by the tools owns the differences left over
    alone = [n for n, (case, _) in names.items() if KINDS[case.site].batch == 'alone']
    unattributed = {}
    for (r, c), bits in sorted(diffs.items()):
        for bit, v in sorted(bits):
            bel = bit_owner(db, r, c, bit)
            owners = [by_bel[(r, c, bel)]] if (r, c, bel) in by_bel else by_tile.get((r, c)) or bank_cases(r, c) or alone
            detail = f'{bit} vendor={v} apicula={1 - v} {bel or ""} {" | ".join(fuse_rows(db, r, c, bit))}'
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


def hclk_settings(db, tiles):
    """Decoded HCLK attributes of all tiles without their positions: names
    without digits, and no HCLKDCS_SEL, which follows from the section."""
    strip = lambda t: re.sub(r'\d', '', t)
    return sorted((strip(k), v if k.endswith('_DIV') else strip(str(v)))
                  for av in hclk_attrs(db, tiles).values() for k, v in av.items() if not k.startswith('HCLKDCS'))


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


class Run:
    """Results of a fuzzer run: `cases` has one result per case ('case',
    'status', and for failures 'why', 'diffs' and the descriptions);
    `unattributed` maps (design, tile) to differing bits no case owns;
    `combinations` lists failing designs of several cases, each as
    {'cases', 'why', 'alone_ok'}, where alone_ok means every case passed alone."""

    def __init__(self):
        self.cases, self.unattributed, self.combinations = [], {}, []

    def failures(self, prim=None):
        """Results that are neither ok, nor rejected by both flows, nor
        invalid (a case the vendor rejected for its harness or netlist)."""
        return [r for r in self.cases if r['status'] not in ('ok', 'rejected', 'invalid')
                and (prim is None or r['case']['prim'] == prim)]


def primitives(device):
    """The primitives a run on `device` tries: all of its family's
    primitive.xml that the device has."""
    prims = ps.Primitives(device, DEVICES[device][0])
    return [p for p in sorted(prims.spec) if p not in ps.UNAVAILABLE.get(device, ()) and p not in ps.NOT_PRIMITIVES]


def load_db(device):
    return chipdb.load_chipdb(os.path.join(os.path.dirname(chipdb.__file__), f'{device}.msgpack.xz'))


def load_case(path):
    """The (case, site) pair of a saved case, <status>_<name>.json."""
    with open(path) as f:
        d = json.load(f)
    return ps.Case.from_json(d['case']), tuple(d['site']) if d['site'] else None


def pinned_case(device, prim, params, pads=None):
    """The (case, site) pair of a case at a chosen place: on `pads` (pin
    numbers or names, in any bank, SiP-locked ones too), else on the first
    site of its kind. The device's fixed parameters (DEVICE) are added."""
    vendor_device, _, package = DEVICES[device]
    db, spec = load_db(device), ps.Primitives(device, vendor_device)
    fixed = {name: v for name, p in spec.spec[prim]['params'].items() if (v := spec.fixed(name, p)) is not None}
    case = ps.Case(prim, tuple(sorted({**fixed, **params}.items())))
    if pads is None:
        pinout = package_pins(db, vendor_device, device, package)
        return case, min(getattr(Sites(db, random.Random(0), pick_pins(db, pinout), pinout), case.site))
    pinout = db.pinout.get(vendor_device, db.pinout[device])[package]
    numbers = {name: num for num, (name, _) in pinout.items()}
    places = []
    for pad in pads:
        num = pad if pad in pinout else numbers[pad]
        row, col, ab = gowin_unpack.tbrl2rc(db, pinout[num][0])
        places.append((row, col, f'IOB{ab}', num))
    return case, places[0] if len(places) == 1 else (*places[0][:3], [p[3] for p in places])


def fuzz(device, out, count=2, seed=0, jobs=1, prims=None, replay=None, log=print):
    """Run the fuzzer on `device`: `count` cases of each primitive (default
    all, see primitives()), or the (case, site) pairs of `replay`, one per
    design. Writes reports to `out` and returns a Run."""
    vendor_device, part, package = DEVICES[device]
    db = load_db(device)
    spec = ps.Primitives(device, vendor_device)
    pinout = package_pins(db, vendor_device, device, package)
    pins = pick_pins(db, pinout)
    rng = random.Random(seed)
    sites = Sites(db, rng, pins, pinout)
    if replay:
        batches = [[pair] for pair in replay]
    else:
        names = [p for p in prims or primitives(device) if p in spec.spec]
        # dict.fromkeys drops repeated draws and, unlike a set, keeps their order
        cases = [c for p in names for c in dict.fromkeys(ps.draw(spec.case(p), count, seed))]
        rng.shuffle(cases)
        batches = allocate(cases, sites, device)
    log(f'{sum(map(len, batches))} cases in {len(batches)} designs; pins {pins}')

    # Differences of the harness alone, with each harness I/O standard the
    # batches need. They are subtracted from the batches' differences.
    baselines = {}
    for vccio in dict.fromkeys(io_class(b, device) for b in batches):
        io_type = HARNESS_IO_TYPE.get(vccio)
        _, b = run_batch(device, db, spec.spec, pins, [], os.path.join(out, f'baseline_{io_type}'), None, io_type)
        if b is None:
            raise RuntimeError(f'the harness alone ({io_type}) failed in the vendor flow')
        baselines[vccio] = b

    def run(i, batch):
        vccio = io_class(batch, device)
        report, _ = run_batch(device, db, spec.spec, pins, batch, os.path.join(out, i),
                              baselines[vccio], HARNESS_IO_TYPE.get(vccio))
        with open(os.path.join(out, i, 'report.json'), 'w') as f:
            json.dump(report, f, indent=1)
        return report

    result = Run()

    def record(i, batch, report):
        """Record a design's results; returns the halves to run when a design
        with several cases failed."""
        if 'error' in report:
            # an error stops the whole design: split it to find the case. If
            # Apicula fails on a design the vendor accepts, that is a failure
            # in itself, even when every case passes alone.
            log(f'{i}: {report["error"]}; splitting')
            if 'Apicula' in report['error']:
                result.combinations.append({'design': i, 'cases': [c.to_json() for c, _ in batch],
                                            'why': report.get('why', [])})
            half = len(batch) // 2
            return [(f'{i}a', batch[:half]), (f'{i}b', batch[half:])]
        for name, res in report['cases'].items():
            res['design'] = i
            result.cases.append(res)
            if res['status'] != 'ok':
                # on its own, for --replay
                with open(os.path.join(out, i, f'{res["status"]}_{name}.json'), 'w') as f:
                    json.dump(res, f, indent=1)
                log(f'{i} {res["status"]}: {describe_result(res)}')
        for tile, bits in report['unattributed'].items():
            result.unattributed[(i, tile)] = bits
        return []

    with concurrent.futures.ThreadPoolExecutor(jobs) as pool:
        running = {pool.submit(run, i, b): (i, b) for i, b in ((f'batch{i}', b) for i, b in enumerate(batches))}
        while running:
            done, _ = concurrent.futures.wait(running, return_when=concurrent.futures.FIRST_COMPLETED)
            for fut in done:
                i, batch = running.pop(fut)
                for j, half in record(i, batch, fut.result()):
                    running[pool.submit(run, j, half)] = (j, half)

    # a combination does not fail if one of its cases fails alone, or if the
    # vendor rejected one of them
    failed_alone = {json.dumps(r['case'], sort_keys=True) for r in result.cases
                    if r['status'] in ('unsupported', 'rejected', 'accepted')}
    for combo in result.combinations:
        combo['alone_ok'] = not any(json.dumps(c, sort_keys=True) in failed_alone for c in combo['cases'])
    with open(os.path.join(out, 'results.json'), 'w') as f:
        json.dump({'cases': result.cases, 'combinations': result.combinations,
                   'unattributed': {f'{d} {t}': bits for (d, t), bits in result.unattributed.items()}}, f, indent=1)
    return result


def describe_result(res):
    """A failed case's result, for logs: case, why, descriptions and the
    differing fuses with their table rows."""
    lines = [f'{res["case"]["prim"]} {res["case"]["params"]} at {res.get("site")} in {res.get("design")}']
    lines += [f'  {side}: {res[side]}' for side in ('generated', 'vendor', 'apicula') if side in res]
    lines += [f'  {why}' for why in dict.fromkeys(res.get('why', []))]
    lines += [f'  {tile}: {bit}' for tile, bits in res.get('diffs', {}).items() for bit in bits]
    return '\n'.join(lines)


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('-d', '--device', required=True, choices=sorted(DEVICES))
    ap.add_argument('-n', '--count', type=int, default=10, help='cases per primitive')
    ap.add_argument('--prims', nargs='*', help='primitives to fuzz (default: all the device has)')
    ap.add_argument('--seed', type=int, default=0)
    ap.add_argument('--replay', nargs='*', help="failing cases' JSON files (<status>_<name>.json) to run, one per design")
    ap.add_argument('-o', '--out', default='fuzz-out')
    ap.add_argument('-j', '--jobs', type=int, default=1, help='designs run at the same time')
    args = ap.parse_args(argv)
    replay = args.replay and [load_case(path) for path in args.replay]
    result = fuzz(args.device, args.out, args.count, args.seed, args.jobs, args.prims, replay)
    print('summary:', dict(collections.Counter(r['status'] for r in result.cases)),
          f'unattributed tiles: {len(result.unattributed)},',
          f'failing combinations whose cases pass alone: {sum(c["alone_ok"] for c in result.combinations)}')
    # invalid cases are generator problems (a vendor rule to learn); the rest are failures
    return 1 if result.failures() or result.unattributed or any(c['alone_ok'] for c in result.combinations) else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
