#!/usr/bin/env python3
"""Round trip: prove that what gowin_unpack reads back from a bitstream is the
design that was synthesised. No IDE, no board.

    python3 tools/roundtrip.py -d GW1N-9C -g logic [-n 10] [--seed 0] [-j 4] [-o roundtrip-out]
    python3 tools/roundtrip.py -d GW1N-9C --replay roundtrip-out/GW1N-9C/logic/3/design.json

Hypothesis draws small random RTL designs in four groups (GROUPS). Each goes
through Yosys synth_gowin, nextpnr (with a drawn seed and, for `ioreg`, one of
the *reg_in_iob options), gowin_pack and gowin_unpack. Then:

- the flip-flops are paired through nextpnr's NEXTPNR_BEL, and both netlists
  are cut there: Q becomes an input, D/CE/CLK/SR outputs; a pin one side lacks
  is its neutral constant. I/O buffers are cut the same way, keyed by the port
  bit they serve.
- both sides are elaborated with Yosys' cells_sim.v only, undriven nets become
  free ($anyseq), and a SAT miter proves them equal.

A differing point is classified (see classify()): `unpack-gap` when its value
on the unpacked side depends on an undriven net other than a carry-in,
`lost-iob-reg` when the gold
side reads a register nextpnr packed into I/O logic but the bitstream has no
register for. Classified points are dropped and the miter rerun, so a known
gap in one point cannot hide a miscompute in another. The design is in
doc/agent/roundtrip.md.

Tools: YOSYS and NEXTPNR environment variables, as in tiled_fuzzer.py.
"""
import argparse
import collections
import concurrent.futures
import dataclasses
import json
import os
import random
import re
import shutil
import subprocess
import sys
import threading

from hypothesis import strategies as st

TOOLS = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(TOOLS)
sys.path[:0] = [REPO, TOOLS]
import primitive_strategies as ps  # noqa: E402
import tiled_fuzzer as tf  # noqa: E402
from gowin_primitives import tool  # noqa: E402
from apycula import chipdb  # noqa: E402

GROUPS = ('logic', 'alu', 'ff', 'ioreg')
# nextpnr packs each only into its own buffer (pack_io.cc): IBUF, OBUF, IOBUF
IOB_VOPTS = ('ireg_in_iob', 'oreg_in_iob', 'ioreg_in_iob')
# the value of a flip-flop pin the flip-flop does not have
ABSENT = {'CE': '1', 'SET': '0', 'RESET': '0', 'PRESET': '0', 'CLEAR': '0'}
# gowin_unpack's name for a carry-in, the previous ALU's carry-out
CARRY_IN = re.compile(r'R\d+C\d+_CIN\d')


# ---------------------------------------------------------------- generator

@dataclasses.dataclass(frozen=True)
class Design:
    group: str
    verilog: str
    seed: int         # nextpnr --seed, and the pin shuffle
    vopt: str = None  # one of IOB_VOPTS, or None

    def to_json(self):
        return dataclasses.asdict(self)


class Rtl:
    """A module under construction: ports, registers and statements."""

    def __init__(self, draw, width):
        self.draw, self.w = draw, width
        self.ports, self.body, self.names, self.bits = [], [], [], []

    def port(self, direction, name, width=None):
        width = self.w if width is None else width
        self.ports.append(f'{direction} {f"[{width - 1}:0] " if width > 1 else ""}{name}')
        return name

    def inputs(self, n):
        self.names += [self.port('input', f'i{k}') for k in range(n)]

    def const(self):
        return f"{self.w}'d{self.draw(st.integers(0, (1 << self.w) - 1))}"

    def leaf(self):
        if self.draw(st.integers(0, 4)) == 0:
            return self.const()
        return self.draw(st.sampled_from(self.names))

    def bit(self):
        name = self.draw(st.sampled_from(self.names))
        return f'{name}[{self.draw(st.integers(0, self.w - 1))}]' if self.w > 1 else name

    def expr(self, ops, depth):
        if depth == 0 or self.draw(st.integers(0, 5)) == 0:
            return self.leaf()
        op = self.draw(st.sampled_from(ops))
        a = lambda: self.expr(ops, depth - 1)
        if op == '~':
            return f'(~{a()})'
        if op == '?:':
            return f'({self.bit()} ? {a()} : {a()})'
        if op == '>>':  # by a variable: a mux tree
            return f'({a()} >> {self.bit()})'
        if op == 'table':  # a function of up to 8 bits: wide LUTs
            n = self.draw(st.integers(5, 8))
            sel = ', '.join(self.bit() for _ in range(n))
            table = self.draw(st.integers(0, (1 << (1 << n)) - 1))
            return f"({1 << n}'h{table:x} >> {{{sel}}})"
        if op in ('<', '>=', '=='):
            return f'(({a()} {op} {a()}) ? {a()} : {a()})'
        if op == 'cnst':  # constant operand, for nextpnr's constant ALU rewrite
            return f'({a()} {self.draw(st.sampled_from(["+", "-"]))} {self.const()})'
        return f'({a()} {op} {a()})'

    def output(self, ops, depth, k):
        self.port('output', f'o{k}')
        self.body.append(f'assign o{k} = {self.expr(ops, depth)};')

    def register(self, name, d, kind, edge, init, control):
        """Register `name`. kind: plain or ce; sreset, sset, areset or aset
        (sync or async), optionally with _ce."""
        decl = f'reg {f"[{self.w - 1}:0] " if self.w > 1 else ""}{name}'
        self.body.insert(0, f'{decl}{"" if init is None else f" = {init}"};')
        en, rst, val = control
        sens = f'{edge} clk'
        stmt = f'{name} <= {d};'
        if kind.endswith('ce'):
            stmt = f'if ({en}) {stmt}'
        if kind.startswith(('s', 'a')):
            if kind.startswith('a'):
                sens += f' or posedge {rst}'
            stmt = f'if ({rst}) {name} <= {val}; else {stmt}'
        self.body.append(f'always @({sens}) {stmt}')

    def control(self):
        ctl = [f'c{k}' for k in range(3)]
        return self.draw(st.sampled_from(ctl)), self.draw(st.sampled_from(ctl)), self.const()

    def reg_kind(self, kinds):
        return (self.draw(st.sampled_from(kinds)), self.draw(st.sampled_from(['posedge', 'negedge'])),
                self.draw(st.one_of(st.none(), st.integers(0, (1 << self.w) - 1).map(lambda v: f"{self.w}'d{v}"))))

    def verilog(self):
        return 'module top(\n  ' + ',\n  '.join(self.ports) + ');\n  ' + '\n  '.join(self.body) + '\nendmodule\n'


LOGIC_OPS = ['&', '|', '^', '~^', '~', '?:', '>>', 'table', '==']
ALU_OPS = ['+', '-', '<', '>=', '==', 'cnst', '&', '^', '?:']
FF_KINDS = ['plain', 'ce', 'sreset', 'sreset_ce', 'sset', 'sset_ce', 'areset', 'areset_ce', 'aset', 'aset_ce']


def registers(rtl, ops, n, depth, reg_kinds):
    """`n` registers fed by expressions of the inputs and the registers."""
    regs = [f'r{k}' for k in range(n)]
    rtl.names += regs
    control = [rtl.control() for _ in regs]
    for r, ctl in zip(regs, control):
        kind, edge, init = rtl.reg_kind(reg_kinds)
        if kind.startswith(('s', 'a')):
            init = None  # synth_gowin's dfflegalize takes a reset only with init = reset value ('r')
        rtl.register(r, rtl.expr(ops, depth), kind, edge, init, ctl)


@st.composite
def design(draw, group):
    # alu: wider operands, so that more arithmetic becomes carry chains than
    # LUTs. At most 33 port bits: GW1N-9C's package has 34 plain pins.
    rtl = Rtl(draw, draw(st.integers(1, 4) if group != 'alu' else st.integers(3, 6)))
    vopt = None
    if group != 'logic':
        rtl.port('input', 'clk', 1)
        for k in range(3):
            rtl.port('input', f'c{k}', 1)
    rtl.inputs(draw(st.integers(1, 3)))
    if group == 'logic':
        for k in range(draw(st.integers(1, 3))):
            rtl.output(LOGIC_OPS, 4, k)
    elif group == 'alu':
        registers(rtl, ALU_OPS, draw(st.integers(1, 3)), 3, ['plain', 'ce', 'sreset', 'areset_ce'])
        for k in range(draw(st.integers(1, 2))):
            rtl.output(ALU_OPS, 2, k)
    elif group == 'ff':
        registers(rtl, LOGIC_OPS[:5], draw(st.integers(1, 4)), 2, FF_KINDS)
        for k in range(draw(st.integers(1, 2))):
            rtl.output(LOGIC_OPS[:5], 1, k)
    else:
        vopt = draw(st.sampled_from(IOB_VOPTS))
        ioregs(draw, rtl)
    return Design(group, rtl.verilog(), draw(st.integers(1, 1 << 16)), vopt)


def ioregs(draw, rtl):
    """Registers next to pads: an input pad into a register, a register onto an
    output pad, or both on one inout pad. One bit each: a register in I/O
    logic is one bit."""
    one = Rtl(draw, 1)
    one.names, one.body, one.ports = rtl.names, rtl.body, rtl.ports
    for k in range(draw(st.integers(1, 3))):
        side = draw(st.sampled_from(['in', 'out', 'inout']))
        kind, edge, init = one.reg_kind(['plain', 'ce', 'sreset', 'areset', 'aset_ce'])
        if kind != 'plain':
            init = None
        ctl = one.control()
        if side in ('in', 'inout'):
            pad = one.port('input' if side == 'in' else 'inout', f'p{k}', 1)
            one.register(f'q{k}', pad, kind, edge, init, ctl)
        if side in ('out', 'inout'):
            d = one.expr(['&', '^', '~'], 1)
            if side == 'out':
                one.port('output', f'p{k}', 1)
                one.register(f'p{k}', d, kind, edge, init, ctl)
            else:
                one.register(f'd{k}', d, kind, edge, init, ctl)
                one.port('input', f'oe{k}', 1)
                one.body.append(f"assign p{k} = oe{k} ? d{k} : 1'bz;")
        if side != 'out':
            one.names.append(f'q{k}')
    qs = [f'q{k}' for k in range(10) if f'q{k}' in one.names]
    if qs:
        one.port('output', 'o0', 1)
        one.body.append(f'assign o0 = {" ^ ".join(qs)};')


# ---------------------------------------------------------------- flow

def run(cmd, cwd, log):
    subprocess.run(cmd, cwd=cwd, check=True, stdout=log, stderr=subprocess.STDOUT,
                   env={**os.environ, 'PYTHONPATH': REPO})


def yosys(script, cwd, log):
    run([tool('YOSYS', 'yosys', 'yowasp-yosys'), '-q', '-p', script], cwd, log)


def constraints(device, seed, ports):
    """IO_LOC lines: clk on a clock pin, every other port bit on a random
    plain pin."""
    vendor_device, _, package = tf.DEVICES[device]
    db = _db(device)
    pins = tf.package_pins(db, vendor_device, device, package)
    clk = tf.pick_pins(db, pins)['clk']
    plain = sorted((p for p, (_, funcs) in pins.items() if not funcs and p != clk), key=str)
    random.Random(seed).shuffle(plain)
    out = []
    for name, p in ports.items():
        for i in range(len(p['bits'])):
            pin = clk if name == 'clk' else plain.pop()
            out.append(f'IO_LOC "{name if len(p["bits"]) == 1 else f"{name}[{i}]"}" {pin};')
    return '\n'.join(out) + '\n'


_dbs = {}


def _db(device):
    if device not in _dbs:
        _dbs[device] = chipdb.load_chipdb(os.path.join(os.path.dirname(chipdb.__file__), f'{device}.msgpack.xz'))
    return _dbs[device]


def flow(device, d, workdir):
    """synth.json, pnr.json and gate.json (the unpacked netlist) in `workdir`."""
    os.makedirs(workdir, exist_ok=True)
    with open(os.path.join(workdir, 'design.json'), 'w') as f:
        json.dump(d.to_json(), f, indent=1)
    with open(os.path.join(workdir, 'top.v'), 'w') as f:
        f.write(d.verilog)
    with open(os.path.join(workdir, 'flow.log'), 'w') as log:
        yosys(f'read_verilog top.v; synth_gowin -family {ps.family(device)} -nodsp -nobram -nolutram '
              f'-top top -json synth.json', workdir, log)
        with open(os.path.join(workdir, 'synth.json')) as f:
            ports = json.load(f)['modules']['top']['ports']
        with open(os.path.join(workdir, 'top.cst'), 'w') as f:
            f.write(constraints(device, d.seed, ports))
        run([tool('NEXTPNR', 'nextpnr-himbaechel', 'yowasp-nextpnr-himbaechel-gowin'),
             '--json', 'synth.json', '--write', 'pnr.json', '--device', tf.DEVICES[device][1],
             '--vopt', f'family={device}', '--vopt', 'cst=top.cst', '--seed', str(d.seed)]
            + (['--vopt', d.vopt] if d.vopt else []), workdir, log)
        run([sys.executable, '-m', 'apycula.gowin_pack', '-d', device, '-o', 'top.fs', 'pnr.json'], workdir, log)
        run([sys.executable, '-m', 'apycula.gowin_unpack', '-d', device, '-o', 'unpacked.v', 'top.fs'], workdir, log)
        yosys('read_verilog unpacked.v; write_json gate.json', workdir, log)


# ---------------------------------------------------------------- cut

class Cut:
    """Both netlists cut at registers and buffers, with the same port names.
    `points` describes each cut for the report, `problems` lists (kind, text)
    of what could not be paired, and `lost` maps the Q ports of gold registers
    the bitstream has no register for to their kind."""

    def __init__(self, gold, gate, pnr):
        self.gold, self.gate = gold['cells'], gate['cells']
        self.points, self.problems, self.lost = {}, [], {}
        self.fresh = max(b for m in (gold, gate) for c in m['cells'].values()
                         for bits in c['connections'].values() for b in bits if isinstance(b, int))
        self.ports = {'gold': {}, 'gate': {}}
        self.registers(pnr)
        self.buffers(pnr)
        for name in self.ports['gate'].keys() - self.ports['gold'].keys():
            self.port('gold', name, 'input', self.new())
        gold['ports'], gate['ports'] = self.ports['gold'], self.ports['gate']

    def new(self):
        self.fresh += 1
        return self.fresh

    def port(self, side, name, direction, bit):
        self.ports[side][name] = {'direction': direction, 'bits': [bit]}

    def cut(self, side, cell, key, pins, ins=()):
        """Remove `cell` from `side`. Its `pins` become ports `<key>_<pin>`:
        inputs if in `ins`, else outputs. A pin the cell lacks is its neutral
        value."""
        conns = (self.gold if side == 'gold' else self.gate).pop(cell)['connections']
        for p in pins:
            bit = conns[p][0] if p in conns else ABSENT.get(p, 'x')
            self.port(side, f'{key}_{p.lower()}', 'input' if p in ins else 'output', bit)

    def problem(self, kind, text):
        self.problems.append((kind, text))

    def registers(self, pnr):
        gold, gate = self.gold, self.gate
        iob_regs = sum('IREG_TYPE' in c['attributes'] or 'OREG_TYPE' in c['attributes']
                       for c in pnr['cells'].values())
        for name, c in pnr['cells'].items():
            m = re.fullmatch(r'X(\d+)Y(\d+)/DFF(\d)', c['attributes'].get('NEXTPNR_BEL', ''))
            if not m or name not in gold:
                continue
            x, y, k = map(int, m.groups())
            twin = f'R{y + 1}C{x + 1}_DFFE_{k}'
            if twin not in gate:
                self.problem(None, f'{name} ({gold[name]["type"]}): placed at {m[0]}, no register there '
                                   f'in the unpacked netlist')
                continue
            key = f"ff{len(self.points)}"  # only registers so far
            gt, tt = gold[name]['type'], gate[twin]['type']
            if gt.startswith('DFFN') != tt.startswith('DFFN'):
                self.problem(None, f'{name}: {gt} unpacked as {tt} at {twin}')
            self.points[key] = f'register {name} ({gt}, {_src(gold[name])}) / {twin} ({tt})'
            pins = set(gold[name]['connections']) | set(gate[twin]['connections'])
            self.cut('gold', name, key, pins, {'Q'})
            self.cut('gate', twin, key, pins, {'Q'})
        for name in [n for n, c in gold.items() if c['type'].startswith('DFF')]:
            # no register in the bitstream: Q is free on both sides, D is not checked
            key = f'lost{len(self.lost)}_q'
            self.points[key] = f'register {name} ({gold[name]["type"]}, {_src(gold[name])})'
            self.port('gold', key, 'input', gold.pop(name)['connections']['Q'][0])
            self.port('gate', key, 'input', self.new())
            if name in pnr['cells']:
                self.lost[key] = None
                self.problem(None, f'{name}: register placed at '
                                   f'{pnr["cells"][name]["attributes"].get("NEXTPNR_BEL")}, not in a slice')
            else:
                # nextpnr merged it into an I/O logic cell (IREG_TYPE/OREG_TYPE)
                self.lost[key] = 'lost-iob-reg' if iob_regs else None
                self.problem(self.lost[key], f'{name}: no register in the bitstream; nextpnr packed '
                                             f'{iob_regs} into I/O logic')

    def buffers(self, pnr):
        """Pair the I/O buffers through their IOB bels; key them by port bit."""
        bit_of = {b: (p, i, len(port['bits'])) for p, port in pnr['ports'].items() for i, b in enumerate(port['bits'])}
        gold, gate = self.gold, self.gate
        for name, c in pnr['cells'].items():
            m = re.fullmatch(r'X(\d+)Y(\d+)/IOB([AB])', c['attributes'].get('NEXTPNR_BEL', ''))
            if not m or c['type'] not in tf.IO_PAD:
                continue
            pad = tf.IO_PAD[c['type']]
            x, y, ab = m.groups()
            twin = f'R{int(y) + 1}C{int(x) + 1}_{c["type"]}_{ab}'
            port, i, width = bit_of[c['connections'][pad][0]]
            key = f'pad_{port}' + (f'_{i}' if width > 1 else '')
            self.points[key] = f'pad {port}{f"[{i}]" if width > 1 else ""} / {twin}'
            if name not in gold or twin not in gate:
                self.problem(None, f'{name} ({c["type"]}) at {m[0]}: '
                                   + ('added by nextpnr' if name not in gold else f'no {twin} in the unpacked netlist'))
                continue
            pins = (set(gold[name]['connections']) | set(gate[twin]['connections'])) - {pad}
            self.cut('gold', name, key, pins, {'O'})
            self.cut('gate', twin, key, pins, {'O'})
        for name in [n for n, c in gold.items() if c['type'] in tf.IO_PAD]:
            self.problem(None, f'{name} ({gold.pop(name)["type"]}): buffer not placed on a pad')
        # unused pads become inputs of their own, so reading a wrong pad is a difference, not a free net
        for name in [n for n, c in gate.items() if c['type'] in tf.IO_PAD]:
            if gate[name]['type'] != 'IBUF':
                self.problem(None, f'{name}: an output buffer the design does not have')
            self.cut('gate', name, name, {'O'}, {'O'})


def _src(cell):
    return cell['attributes'].get('src', '?').split('|')[0]


# ---------------------------------------------------------------- prove

CELLS = 'read_verilog -lib +/gowin/cells_xtra_{family}.v; read_verilog +/gowin/cells_sim.v; '


def elaborate(workdir, side, module, family):
    """Flatten `module` onto cells_sim.v; returns the flat netlist, or raises
    CalledProcessError with Yosys' log in `output`."""
    path = os.path.join(workdir, f'{side}_cut.json')
    with open(path, 'w') as f:
        json.dump({'modules': {'top': module}}, f)
    out = os.path.join(workdir, f'{side}_flat.json')
    r = subprocess.run([tool('YOSYS', 'yosys', 'yowasp-yosys'), '-q', '-p',
                        f'read_json {path}; {CELLS.format(family=family)}hierarchy -check -top top; proc; flatten; '
                        f'opt_clean; write_json {out}'], capture_output=True, text=True)
    if r.returncode:
        raise subprocess.CalledProcessError(r.returncode, 'yosys', r.stdout + r.stderr)
    with open(out) as f:
        return json.load(f)['modules']['top']


def prove(workdir, outputs, tag):
    """SAT miter of gold_flat.json and gate_flat.json restricted to `outputs`;
    None if equal, else the counterexample {port: (gold, gate)} plus the
    inputs under 'in'."""
    script = ''
    for side in ('gold', 'gate'):
        drop = [p for p in outputs['all'] if p not in outputs['keep']]
        script += (f'read_json {os.path.join(workdir, side + "_flat.json")}; '
                   + ''.join(f'delete -port top/{p}; ' for p in drop) +
                   f'setundef -undriven -anyseq; rename top {side}; design -stash {side}; ')
    script += ('design -copy-from gold -as gold gold; design -copy-from gate -as gate gate; '
               'miter -equiv -flatten -make_outputs -ignore_gold_x gold gate miter; hierarchy -top miter; '
               'sat -verify -prove trigger 0 -show-ports -set-init-zero miter')
    log = os.path.join(workdir, f'sat_{tag}.log')
    r = subprocess.run([tool('YOSYS', 'yosys', 'yowasp-yosys'), '-q', '-l', log, '-p', script],
                       capture_output=True, text=True)
    with open(log) as f:
        text = f.read()
    if r.returncode == 0:
        return None
    if 'proof did fail' not in text:
        raise RuntimeError(f'SAT run failed: {(r.stdout + r.stderr)[-2000:]}')
    vals = dict(re.findall(r'^\s+\\(\S+)\s+\S+\s+\S+\s+([01xz]+)\s*$', text, re.M))
    diff = {k[5:]: (v, vals.get('gate_' + k[5:])) for k, v in vals.items()
            if k.startswith('gold_') and vals.get('gate_' + k[5:]) != v}
    diff['in'] = {k[3:]: v for k, v in vals.items() if k.startswith('in_')}
    return diff


def drivers(module):
    """bit -> the cell that drives it."""
    return {b: c for c in module['cells'].values() for p, bits in c['connections'].items()
            if c['port_directions'].get(p) == 'output' for b in bits}


def cone(module, port):
    """Input ports and undriven named nets in the fan-in cone of `port`."""
    named = {}
    for name, n in module['netnames'].items():
        if not n.get('hide_name'):
            for b in n['bits']:
                named.setdefault(b, name)
    inputs = {b: p for p, d in module['ports'].items() if d['direction'] == 'input' for b in d['bits']}
    driver = drivers(module)
    seen, todo, ins, undriven = set(), list(module['ports'][port]['bits']), set(), set()
    while todo:
        b = todo.pop()
        if not isinstance(b, int) or b in seen:
            continue
        seen.add(b)
        if b in inputs:
            ins.add(inputs[b])
        elif b in driver:
            c = driver[b]
            todo += [x for p, bits in c['connections'].items() if c['port_directions'].get(p) == 'input' for x in bits]
        else:
            undriven.add(named.get(b, f'${b}'))
    return ins, undriven


def dependent(workdir, points):
    """The `points` whose value on the unpacked side depends on its undriven
    nets: two copies of it, each with its own free values for them, differ.
    An undriven carry-in is the same in both copies: nothing in #585 leaves
    one undriven, the head of a chain must not read it (#541's 0x505a head
    did), so a point that depends on it is not an unpack gap."""
    with open(os.path.join(workdir, 'gate_flat.json')) as f:
        gate = json.load(f)['modules']['top']
    driven = drivers(gate).keys() | {b for p in gate['ports'].values() for b in p['bits']}
    for name, n in gate['netnames'].items():
        if CARRY_IN.fullmatch(name) and not driven & set(n['bits']):
            gate['ports'][name] = {'direction': 'input', 'bits': n['bits']}
    flat = os.path.join(workdir, 'gate_dep.json')
    with open(flat, 'w') as f:
        json.dump({'modules': {'top': gate}}, f)
    script = ''.join(f'read_json {flat}; setundef -undriven -anyseq; rename top {s}; design -stash {s}; '
                     for s in 'ab')
    script += ('design -copy-from a -as a a; design -copy-from b -as b b; '
               'miter -equiv -flatten -make_outputs a b m; hierarchy -top m; '
               + ''.join(f'sat -prove gold_{p} gate_{p} m; ' for p in points))
    log = os.path.join(workdir, 'dependent.log')
    subprocess.run([tool('YOSYS', 'yosys', 'yowasp-yosys'), '-q', '-l', log, '-p', script],
                   check=True, capture_output=True)
    with open(log) as f:
        found = re.findall(r'SAT proof finished - (no model found|model found)', f.read())
    return {p for p, r in zip(points, found) if r == 'model found'}


def classify(cut, gold, gate, point, dependent):
    """Why a cut point differs, with the evidence: 'lost-iob-reg' (the gold
    side reads a register nextpnr packed into I/O logic), 'unpack-gap' (the
    unpacked side depends on an undriven net), or None."""
    ins, _ = cone(gold, point)
    lost = sorted((ins | {point}) & cut.lost.keys())
    if lost:
        return ('lost-iob-reg' if all(cut.lost[k] for k in lost) else None), lost
    _, undriven = cone(gate, point)
    if point in dependent:
        return 'unpack-gap', sorted(undriven)
    return None, sorted(undriven)


def check(device, workdir, mutate=False):
    """Check a design whose flow ran in `workdir`. Returns {'status': 'proved'
    | 'failed' | 'error', 'points': [...], 'problems': [...], 'error', 'kind'}.
    Each point and problem has a 'kind'; None means unexplained."""
    load = lambda n: json.load(open(os.path.join(workdir, n)))['modules']['top']
    gold, gate = load('synth.json'), load('gate.json')
    cut = Cut(gold, gate, load('pnr.json'))
    luts = sorted(n for n, c in gate['cells'].items() if re.fullmatch(r'LUT[1-4]', c['type']))
    res = {'problems': [{'kind': k, 'text': t} for k, t in cut.problems], 'points': [], 'luts': len(luts)}
    # #288: gowin_unpack gives ALU an I2 port, which Yosys' ALU does not have.
    # Drop it, so that the rest of the design is still checked.
    i2 = [n for n, c in gate['cells'].items() if c['type'] == 'ALU' and c['connections'].pop('I2', None)]
    if i2:
        res['problems'].append({'kind': 'alu-i2', 'text': f'{len(i2)} ALUs with an I2 port, as {i2[0]}'})
    if mutate:
        # a control: invert a LUT, and the check must fail
        params = gate['cells'][luts[0]]['parameters']
        params['INIT'] = ''.join('1' if b == '0' else '0' for b in params['INIT'])
        res['mutated'] = luts[0]
    family = ps.family(device)
    try:
        gold = elaborate(workdir, 'gold', gold, family)
        gate = elaborate(workdir, 'gate', gate, family)
    except subprocess.CalledProcessError as e:
        m = re.search(r'ERROR: .*', e.output)
        return {**res, 'status': 'error', 'error': m[0] if m else e.output[-500:]}
    outputs = {'all': [p for p, d in gold['ports'].items() if d['direction'] == 'output']}
    outputs['keep'] = list(outputs['all'])
    # drop the explained points and prove again, until equal or unexplained
    for i in range(len(outputs['all']) + 1):
        diff = prove(workdir, outputs, i)
        if diff is None:
            break
        inputs = diff.pop('in')
        dep = dependent(workdir, sorted(diff))
        for point, (g, t) in sorted(diff.items()):
            kind, evidence = classify(cut, gold, gate, point, dep)
            res['points'].append({'point': point, 'what': cut.points.get(point.rsplit('_', 1)[0], point),
                                  'kind': kind, 'evidence': evidence, 'gold': g, 'gate': t, 'in': inputs})
            outputs['keep'].remove(point)
        if mutate or any(p['kind'] is None for p in res['points']):
            break
    res['status'] = 'failed' if res['points'] or res['problems'] else 'proved'
    return res


# ---------------------------------------------------------------- driver

def kinds(res):
    """The kinds of failure in a result; None among them if any is unexplained."""
    return {p['kind'] for p in res['points'] + res['problems']} | ({None} if res['status'] == 'error' else set())


def run_design(device, d, workdir):
    try:
        flow(device, d, workdir)
        res = check(device, workdir)
    except subprocess.CalledProcessError as e:
        with open(os.path.join(workdir, 'flow.log')) as f:
            tail = f.read()[-1500:]
        res = {'status': 'error', 'error': f'flow: {os.path.basename(e.cmd[0])} {e.cmd[1:3]} failed\n{tail}',
               'points': [], 'problems': []}
    with open(os.path.join(workdir, 'result.json'), 'w') as f:
        json.dump(res, f, indent=1)
    return res


def control(device, workdir):
    """The mutation control on a design that proved, in a copy of its
    directory: a LUT inverted, so the check must fail."""
    copy = workdir + '-control'
    os.makedirs(copy, exist_ok=True)
    for name in ('synth.json', 'pnr.json', 'gate.json'):
        shutil.copy(os.path.join(workdir, name), copy)
    res = check(device, copy, mutate=True)
    with open(os.path.join(copy, 'result.json'), 'w') as f:
        json.dump(res, f, indent=1)
    return copy, res


def tidy(workdir):
    """Keep only what replays and reports a design: about 12 MB less each."""
    for name in os.listdir(workdir):
        if name not in ('design.json', 'top.v', 'result.json'):
            os.remove(os.path.join(workdir, name))


def roundtrip(device, group, out, count=10, seed=0, jobs=1, replay=None, keep=False):
    """Run `count` designs of `group`, or the `replay` design files. Returns
    [(workdir, result)] and the mutation control (workdir, result) on the
    first design to prove with a LUT, or None. Unless `keep`, a design that
    proved, and a control that failed, keep only their small files."""
    # dict.fromkeys drops repeated draws and keeps their order
    designs = ([Design(**json.load(open(p))) for p in replay] if replay
               else list(dict.fromkeys(ps.draw(design(group), count, seed))))
    dirs = [os.path.join(out, device, d.group, str(i)) for i, d in enumerate(designs)]
    ctl, lock = [], threading.Lock()

    def one(d, workdir):
        res = run_design(device, d, workdir)
        if res['status'] == 'proved':
            with lock:
                mine = bool(res['luts'] and not replay and not ctl)
                if mine:
                    ctl.append(None)  # claimed; filled in below
            if mine:
                ctl[0] = control(device, workdir)
                if not keep and None in kinds(ctl[0][1]):
                    tidy(ctl[0][0])
            if not keep:
                tidy(workdir)
        return res

    with concurrent.futures.ThreadPoolExecutor(jobs) as pool:
        results = list(pool.map(one, designs, dirs))
    return list(zip(dirs, results)), (ctl[0] if ctl else None)


def describe(workdir, res):
    """A design's result, for logs: the problems and each differing point with
    its kind and evidence (undriven nets, lost registers)."""
    lines = [f'{workdir}: {res["status"]}' + (f' (UNEXPLAINED: {res["error"]})' if res.get('error') else '')]
    lines += [f'  {p["kind"] or "UNEXPLAINED"}: {p["text"]}' for p in res['problems']]
    for p in res['points']:
        ev = ', '.join(p['evidence'][:6]) + (' ...' if len(p['evidence']) > 6 else '')
        lines.append(f'  {p["kind"] or "UNEXPLAINED"}: {p["point"]}: {p["what"]}: gold {p["gold"]} gate {p["gate"]}'
                     + (f'; {ev}' if ev else ''))
    if any(p['kind'] is None for p in res['points']):
        lines.append(f'  inputs: {res["points"][0]["in"]}')
    return '\n'.join(lines)


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('-d', '--device', required=True, choices=sorted(tf.DEVICES))
    ap.add_argument('-g', '--group', choices=GROUPS, default='logic')
    ap.add_argument('-n', '--count', type=int, default=10)
    ap.add_argument('--seed', type=int, default=0)
    ap.add_argument('-j', '--jobs', type=int, default=1)
    ap.add_argument('-o', '--out', default='roundtrip-out')
    ap.add_argument('--replay', nargs='*', help="designs' design.json files")
    ap.add_argument('--keep', action='store_true', help='keep the netlists of designs that proved')
    args = ap.parse_args(argv)
    results, ctl = roundtrip(args.device, args.group, args.out, args.count, args.seed, args.jobs, args.replay,
                             args.keep)
    for w, r in results:
        print(describe(w, r))
    if ctl:
        print(f'control: {ctl[0]} with {ctl[1]["mutated"]} inverted: {ctl[1]["status"]}')
    print('summary:', dict(collections.Counter(r['status'] for _, r in results)))
    return 0 if all(r['status'] == 'proved' for _, r in results) else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
