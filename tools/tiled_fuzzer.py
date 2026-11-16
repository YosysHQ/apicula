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

- Both bitstreams are unpacked with gowin_unpack (tools/unpacked_netlist.py).
  The case's cell is described by type, parameters and the harness pin feeding
  each input, or for a LUT its truth table over those pins, which makes the
  vendor's LUT input permutation irrelevant. The vendor and Apicula
  descriptions must agree, and must agree with the generated case.
- The bitstreams are compared tile by tile on the bits that are not routing
  fuses, which catches fuses the unpacker does not decode. Differences also
  present in a design with no cases (the I/O harness) are subtracted.

Statuses: ok; partial (agrees, but some input could not be traced through the
unpacked routing); mismatch (vendor and Apicula differ); decode (they agree with
each other but not with the generated case: an unpacker bug, or a mistake both
make); invalid (the vendor rejected the case). Failing cases are written out on
their own for `--replay`.

Tools: YOSYS and NEXTPNR environment variables, else yosys/nextpnr-himbaechel,
else their yowasp- versions.
"""
import argparse
import collections
import json
import os
import random
import re
import shutil
import subprocess
import sys

TOOLS = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(TOOLS)
sys.path[:0] = [REPO, TOOLS]  # this checkout's apycula, not an installed one
import primitive_strategies as ps  # noqa: E402
import unpacked_netlist  # noqa: E402
from apycula import bslib, chipdb, codegen  # noqa: E402

# device: (vendor device, part number, package). From legacy/tiled_fuzzer.py.
DEVICES = {
    'GW1N-1': ('GW1N-1', 'GW1N-LV1LQ144C6/I5', 'LQFP144'),
    'GW1NZ-1': ('GW1NZ-1', 'GW1NZ-LV1QN48C6/I5', 'QFN48'),
    'GW1N-4': ('GW1N-4', 'GW1N-LV4PG256C6/I5', 'PBGA256'),
    'GW1N-9': ('GW1N-9', 'GW1N-LV9PG256C6/I5', 'PBGA256'),
    'GW1N-9C': ('GW1NR-9C', 'GW1NR-LV9QN88PC6/I5', 'QFN88P'),
    'GW1NS-4': ('GW1NSR-4C', 'GW1NSR-LV4CQN48PC7/I6', 'QFN48P'),
    'GW2A-18': ('GW2A-18', 'GW2A-LV18PG256C8/I7', 'PBGA256'),
    'GW2A-18C': ('GW2A-18C', 'GW2A-LV18PG256SC8/I7', 'PBGA256S'),
}

# Vendor log codes that make a case invalid rather than a mismatch.
INVALID_CODES = {'PA1002': 'invalid parameter value', 'CT1094': 'not placed at its constraint'}


def tool(env, *names):
    path = os.environ.get(env) or next(filter(None, map(shutil.which, names)), None)
    if not path:
        sys.exit(f'none of {names} found; set {env}')
    return path


# ---------------------------------------------------------------- sites

class Sites:
    """Free sites of each kind. A slice (CLS) holds two LUT cases or one DFF case,
    because the two flip-flops of a slice share clock, CE and set/reset modes."""

    def __init__(self, db, rng):
        self.cls = [(r, c, cls) for r in range(db.rows) for c in range(db.cols)
                    for cls in range(4)
                    if {f'LUT{2 * cls}', f'LUT{2 * cls + 1}', f'DFF{2 * cls}'} <= db[r, c].bels.keys()]
        rng.shuffle(self.cls)
        self.singletons = {'osc'}

    def capacity(self):
        return {'lut': 2 * len(self.cls), 'dff': len(self.cls), 'osc': 1}


def allocate(cases, sites):
    """Split cases into batches and give each a site. Returns [[(case, site), ...]]."""
    queues = collections.defaultdict(list)
    for case in cases:
        queues[case.site].append(case)
    batches = []
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


def netlist(batch, spec, pins):
    """One design: an I/O harness and the cases chained output to input."""
    mod, cst = codegen.Module(), codegen.Constraints()

    def inst(typ, name, conns, params=()):
        p = codegen.Primitive(typ, name)
        for port, (direction, width) in spec[typ]['ports'].items():
            if port in conns:
                p.portmap[port] = conns[port]
            elif direction == 'input':  # the vendor rejects unconnected or constant ports
                p.portmap[port] = ['gnd'] * width if width > 1 else 'gnd'
            else:
                wire = f'{name}_{port}'
                mod.wires.add(f'[{width - 1}:0] {wire}' if width > 1 else wire)
                p.portmap[port] = wire
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
        if pin != 'clk':
            data.append(pin)

    # Cases are independent: 1-bit inputs come from distinct input pins and
    # outputs are left unconnected. Chaining one case into the next lets the
    # vendor propagate constants between them; it keeps unloaded cells anyway.
    names, wiring = {}, {}
    for i, (case, site) in enumerate(batch):
        name = f'inst{i}_{case.prim}'
        names[name] = (case, site)
        ins = [p for p, (d, w) in spec[case.prim]['ports'].items() if d == 'input' and w == 1]
        conns, sources = {}, data[i % len(data):] + data[:i % len(data)]
        for port in ins:
            conns[port] = 'clk' if port == 'CLK' else sources.pop(0) if sources else 'gnd'
        inst(case.prim, name, conns, case.params)
        wiring[name] = conns
        if site:
            cst.cells[name] = (site[0] + 1, site[1] + 1, site[2], site[3])

    mod.outputs.add('out_pad')
    inst('OBUF', 'harness_ob', {'I': data[0], 'O': 'out_pad'})
    cst.ports['out_pad'] = pins['out']
    return mod, cst, names, wiring


def bel_name(case, site):
    r, c, cls, ab = site
    kind = 'DFF' if case.site == 'dff' else 'LUT'
    return f'X{c}Y{r}/{kind}{2 * cls + "AB".index(ab)}'


# ---------------------------------------------------------------- flows

def run_vendor(workdir, mod, cst, vendor_device, part):
    pnr = codegen.Pnr()
    pnr.device, pnr.partnumber, pnr.netlist, pnr.cst = vendor_device, part, mod, cst
    os.makedirs(workdir, exist_ok=True)
    with open(os.path.join(workdir, 'gw_sh.log'), 'w') as log:
        return pnr.run_pnr(workdir=workdir, stdout=log)


def run_apicula(workdir, mod, cst, names, device, part):
    os.makedirs(workdir, exist_ok=True)
    with open(os.path.join(workdir, 'top.v'), 'w') as f:
        mod.write(f)
    with open(os.path.join(workdir, 'top.cst'), 'w') as f:
        cst.write(f)
    log = open(os.path.join(workdir, 'tools.log'), 'w')
    # yowasp tools only see the working directory, so use relative paths
    subprocess.run([tool('YOSYS', 'yosys', 'yowasp-yosys'), '-q', '-p',
                    'read_verilog -lib +/gowin/cells_sim.v; read_verilog top.v; hierarchy -top top; '
                    'blackbox =A:whitebox; write_json syn.json'],
                   cwd=workdir, check=True, stdout=log, stderr=subprocess.STDOUT)
    path = os.path.join(workdir, 'syn.json')
    with open(path) as f:
        syn = json.load(f)
    for name, cell in syn['modules']['top']['cells'].items():
        if name in names and names[name][1]:
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
    return bslib.read_bitstream(os.path.join(workdir, 'top.fs'))[0], placed


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
        _masks[ttyp] = bits
    return _masks[ttyp]


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
        _owners[ttyp] = own
    return _owners[ttyp].get(bit)


def case_bel(case, site):
    r, c, cls, ab = site
    return f'LUT{2 * cls + "AB".index(ab)}' if case.site == 'lut' else f'CLS{cls}'


def fuse_tables(db, r, c, bit):
    ttyp = db.grid[r][c]
    owners = [f'{name}{key}' for name, rows in db.shortval.get(ttyp, {}).items()
              for key, bits in rows.items() if bit in bits]
    owners += [f'{bel}.{flag}' for bel, b in db[r, c].bels.items()
               for flag, bits in b.flags.items() if bit in bits]
    return owners[:4]


# ---------------------------------------------------------------- unpacked netlists

def literal_value(text):
    text = str(text).strip().strip('"')
    m = re.fullmatch(r"(\d+)'([bhd])([0-9a-fA-F_]+)", text)
    if m:
        return int(m.group(3).replace('_', ''), {'b': 2, 'h': 16, 'd': 10}[m.group(2)])
    return int(text) if re.fullmatch(r'-?\d+', text) else text.upper()


def truth_table(inputs, init):
    """Canonical LUT function: {frozenset of (net, value) for the nets it reads: out}.
    `inputs` are net labels per LUT input; VCC/VSS are constants. Inputs whose
    net is unknown must not change the output, else the result is None."""
    nets = sorted({n for n in inputs if n not in ('VCC', 'VSS')})
    table = {}
    for i in range(1 << len(nets)):
        env = {n: (i >> k) & 1 for k, n in enumerate(nets)}
        env.update(VCC=1, VSS=0)
        idx = sum(env[n] << k for k, n in enumerate(inputs))
        table[frozenset(env.items())] = (init >> idx) & 1
    # drop nets the function does not depend on
    for n in nets:
        if all(table[k] == table[k ^ {(n, 0), (n, 1)}] for k in table if (n, 0) in k):
            table = {k - {(n, 0), (n, 1)}: v for k, v in table.items()}
    if any(n.startswith('?') for k in table for n, _ in k):
        return None
    return {k - {('VCC', 1), ('VSS', 0)}: v for k, v in table.items()}


class Decoded:
    """A case as found in an unpacked bitstream."""

    def __init__(self, nl, spec, iob_nets):
        self.nl, self.iob_nets = nl, iob_nets
        nl.set_outputs({t: {p for p, (d, _) in v['ports'].items() if d == 'output'} for t, v in spec.items()})

    def net(self, wire):
        """Harness net label for a wire, following pass-through LUTs."""
        root = self.nl.find(wire)
        for _ in range(8):
            if root in self.iob_nets:
                return self.iob_nets[root]
            if root in ('VCC', 'VSS'):
                return root
            drv = self.nl.driver.get(root)
            if not drv or self.nl.cells[drv[0]]['type'] != 'LUT4':
                break
            cell = self.nl.cells[drv[0]]
            init = literal_value(cell['params'].get('INIT', 0))
            passthrough = [p for k, p in enumerate(('I0', 'I1', 'I2', 'I3'))
                           if all(((init >> i) & 1) == ((i >> k) & 1) for i in range(16))]
            if not passthrough:
                break
            root = self.nl.find(cell['ports'][passthrough[0]])
        return f'?{root}'

    def find(self, case, site):
        if site is None:
            return next((n for n, c in self.nl.cells.items() if c['type'].startswith(case.site.upper())), None)
        r, c, cls, ab = site
        if case.site == 'lut':
            name = f'R{r + 1}C{c + 1}_LUT4_{2 * cls + "AB".index(ab)}'
            return name if name in self.nl.cells else None
        prefix, suffix = f'R{r + 1}C{c + 1}_', f'_{2 * cls}'
        return next((n for n, cell in self.nl.cells.items() if n.startswith(prefix) and n.endswith(suffix)
                     and cell['type'].startswith(('DFF', 'DL'))), None)

    def describe(self, case, site):
        name = self.find(case, site)
        if name is None and case.site == 'lut':
            # constant LUTs are written as an assign of the F wire to VCC or VSS
            r, c, cls, ab = site
            const = self.nl.find(f'R{r + 1}C{c + 1}_F{2 * cls + "AB".index(ab)}')
            if const in ('VCC', 'VSS'):
                return {'cell': 'LUT', 'function': [f':{int(const == "VCC")}']}
        if name is None:
            return {'cell': None}
        cell = self.nl.cells[name]
        if case.site == 'lut':
            inputs = [self.net(cell['ports'][p]) for p in ('I0', 'I1', 'I2', 'I3')]
            return {'cell': 'LUT', 'function': table_str(truth_table(inputs, literal_value(cell['params']['INIT'])))}
        ins = {p: self.net(w) for p, w in cell['ports'].items() if self.nl.driver.get(self.nl.find(w)) != (name, p)}
        return canonical({'cell': cell['type'], 'params': {k: literal_value(v) for k, v in cell['params'].items()},
                          'inputs': ins})


def table_str(table):
    if table is None:
        return None
    return sorted(f'{",".join(f"{n}={v}" for n, v in sorted(k))}:{out}' for k, out in table.items())


_SR = {'S': 'SET', 'R': 'RESET', 'P': 'PRESET', 'C': 'CLEAR'}


def canonical(desc):
    """Flip-flops in one form: DFF without E has CE=VCC, and a set/reset input
    tied to VSS is no set/reset. The unpacker emits e.g. DFFPE with CE=VCC for
    a DFFP."""
    m = re.fullmatch(r'DFF(N?)([SRPC]?)(E?)', desc.get('cell') or '')
    if not m:
        return desc
    neg, sr, ce = m.groups()
    ins = dict(desc['inputs'])
    out = {'cell': 'DFF', 'params': desc['params'],
           'inputs': {'D': ins.get('D'), 'CLK': ins.get('CLK'), 'CE': ins.get('CE') if ce else 'VCC'},
           'edge': 'neg' if neg else 'pos', 'sr': None}
    if sr and ins.get(_SR[sr]) != 'VSS':
        out['sr'] = sr
        out['inputs']['SR'] = ins.get(_SR[sr])
    return out


def describe_generated(case, conns, spec):
    if case.site == 'lut':
        n = int(case.prim[3:])
        inputs = [conns[f'I{i}'] for i in range(n)]
        return {'cell': 'LUT', 'function': table_str(truth_table(inputs, literal_value(dict(case.params)['INIT'])))}
    ins = {p: conns.get(p, 'VSS') for p, (d, _) in spec[case.prim]['ports'].items() if d == 'input'}
    return canonical({'cell': case.prim, 'params': {k: literal_value(v) for k, v in case.params},
                      'inputs': {p: 'VSS' if n == 'gnd' else n for p, n in ins.items()}})


def compare(a, b):
    """(equal, partial). Only what both sides have is compared: the unpacker
    does not emit every parameter. Nets the unpacked netlist could not trace
    (labelled '?...', or a LUT function of None) match anything, and make the
    comparison partial."""
    partial = False
    for key in ('cell', 'edge', 'sr'):
        if a.get(key) != b.get(key):
            return False, partial
    fa, fb = a.get('function'), b.get('function')
    if fa is None or fb is None:
        partial = partial or a.get('cell') == 'LUT'
    elif fa != fb:
        return False, partial
    for key in ('params', 'inputs'):
        x, y = a.get(key) or {}, b.get(key) or {}
        for k in x.keys() & y.keys():
            if str(x[k]).startswith('?') or str(y[k]).startswith('?'):
                partial = True
            elif x[k] != y[k]:
                return False, partial
    return True, partial


def iob_net_map(db, nl, pins, pinout):
    """Root net of each harness input pin's IBUF output -> harness net label."""
    out = {}
    labels = {pins['clk']: 'clk', **{p: f'in{i}' for i, p in enumerate(pins['in'])}}
    for pin, label in labels.items():
        side, num, ab = re.fullmatch(r'IO([TBLR])(\d+)([A-Z])', pinout[pin][0]).groups()
        num = int(num)
        r, c = {'T': (1, num), 'B': (db.rows, num), 'L': (num, 1), 'R': (num, db.cols)}[side]
        cell = nl.cells.get(f'R{r}C{c}_IBUF_{ab}')
        if cell:
            out[nl.find(cell['ports']['O'])] = label
    return out


def run_batch(args, db, spec, pins, batch, workdir, baseline):
    vendor_device, part, _ = DEVICES[args.device]
    mod, cst, names, wiring = netlist(batch, spec, pins)
    vres = run_vendor(os.path.join(workdir, 'vendor'), mod, cst, vendor_device, part)
    if vres is None:
        return {'error': 'vendor produced no bitstream; see vendor/impl/pnr/top.log'}, None
    abm, placed = run_apicula(os.path.join(workdir, 'apicula'), mod, cst, names, args.device, part)
    vt = chipdb.tile_bitmap(db, vres.bitmap, empty=True)
    at = chipdb.tile_bitmap(db, abm, empty=True)
    diffs = diff_bits(db, vt, at)
    decoded = {}
    if batch:
        pinout = db.pinout.get(vendor_device, db.pinout[args.device])[DEVICES[args.device][2]]
        for side, fs in (('vendor', os.path.join(workdir, 'vendor/impl/pnr/top.fs')),
                         ('apicula', os.path.join(workdir, 'apicula/top.fs'))):
            nl = unpacked_netlist.unpack(args.device, fs, os.path.join(workdir, f'{side}_unpack.v'), REPO)
            decoded[side] = Decoded(nl, spec, iob_net_map(db, nl, pins, pinout))
    if baseline is not None:
        diffs = {k: v - baseline.get(k, set()) for k, v in diffs.items()}
        diffs = {k: v for k, v in diffs.items() if v}

    results = {}
    by_bel = {}  # (row, col, bel) -> case name
    by_tile = collections.defaultdict(list)
    for name, (case, site) in names.items():
        res = {'case': case.to_json(), 'site': site, 'status': 'ok'}
        problems = [f'{code} {INVALID_CODES[code]}' for (n, code) in vres.errs if n == name and code in INVALID_CODES]
        if site and placed.get(name) != bel_name(case, site):
            problems.append(f'nextpnr placed it at {placed.get(name)}')
        if problems:
            res['status'] = 'invalid'
            res['why'] = problems
        else:
            gen = describe_generated(case, wiring[name], spec)
            dv, da = decoded['vendor'].describe(case, site), decoded['apicula'].describe(case, site)
            equal, partial_va = compare(dv, da)
            decoded_ok, partial_vg = compare(dv, gen)
            if not equal:
                res['status'] = 'mismatch'
            elif not decoded_ok:
                res['status'] = 'decode'
            elif partial_va or partial_vg:
                res['status'] = 'partial'
            if res['status'] != 'ok':
                res['generated'], res['vendor'], res['apicula'] = gen, dv, da
        results[name] = res
        if site:
            loc = (site[0], site[1])
        else:
            loc = SINGLETON_LOCS.setdefault(case.site, find_bel(db, case.site.upper()))
        by_tile[loc].append(name)
        if site:
            by_bel[(*loc, case_bel(case, site))] = name

    unattributed = {}
    for (r, c), bits in sorted(diffs.items()):
        for bit, v in sorted(bits):
            bel = bit_owner(db, r, c, bit)
            if bel and bel.startswith('LUT') and (r, c, bel) in by_bel:
                continue  # the vendor permutes LUT inputs; compared through the unpacked netlists
            owners = [by_bel[(r, c, bel)]] if (r, c, bel) in by_bel else by_tile.get((r, c), [])
            detail = f'{bit} vendor={v} apicula={1 - v} {bel or ""} {fuse_tables(db, r, c, bit)}'
            if not owners:
                unattributed.setdefault(f'R{r + 1}C{c + 1}', []).append(detail)
            for name in owners:
                if results[name]['status'] == 'ok':
                    results[name]['status'] = 'mismatch'
                results[name].setdefault('diffs', {}).setdefault(f'R{r + 1}C{c + 1}', []).append(detail)
    report = {'cases': results, 'unattributed': unattributed}
    return report, diffs


SINGLETON_LOCS = {}


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
    args = ap.parse_args(argv)

    vendor_device, part, package = DEVICES[args.device]
    db = chipdb.load_chipdb(os.path.join(os.path.dirname(chipdb.__file__), f'{args.device}.msgpack.xz'))
    prims = ps.Primitives(args.device, vendor_device)
    pins = pick_pins(db, vendor_device, args.device, package)
    rng = random.Random(args.seed)
    sites = Sites(db, rng)

    if args.replay:
        batches = []
        for path in args.replay:
            with open(path) as f:
                d = json.load(f)
            batches.append([(ps.Case.from_json(d['case']), tuple(d['site']) if d['site'] else None)])
    else:
        names = args.prims or [p for p in ps.SITES if p in prims.spec]
        cases = [c for p in names for c in set(ps.draw(prims.case(p), args.count, args.seed))]
        rng.shuffle(cases)
        batches = allocate(cases, sites)

    print(f'{sum(map(len, batches))} cases in {len(batches)} designs; pins {pins}')
    _, baseline = run_batch(args, db, prims.spec, pins, [], os.path.join(args.out, 'baseline'), None)
    if baseline is None:
        sys.exit('the harness alone failed in the vendor flow')
    if baseline:
        print(f'harness differences, ignored: {sum(map(len, baseline.values()))} bits in '
              f'{" ".join(f"R{r + 1}C{c + 1}" for r, c in sorted(baseline))}')

    totals = collections.Counter()
    for i, batch in enumerate(batches):
        workdir = os.path.join(args.out, f'batch{i}')
        report, _ = run_batch(args, db, prims.spec, pins, batch, workdir, baseline)
        with open(os.path.join(workdir, 'report.json'), 'w') as f:
            json.dump(report, f, indent=1)
        if 'error' in report:
            print(f'batch{i}: {report["error"]}')
            totals['batch errors'] += 1
            continue
        for name, res in report['cases'].items():
            totals[res['status']] += 1
            if res['status'] not in ('ok', 'partial'):
                path = os.path.join(workdir, f'{res["status"]}_{name}.json')
                with open(path, 'w') as f:
                    json.dump(res, f, indent=1)
                print(f'batch{i} {name} {res["status"]}: {res["case"]} at {res["site"]} -> {path}')
                for side in ('generated', 'vendor', 'apicula'):
                    if side in res:
                        print(f'     {side:9}', res[side])
                for line in res.get('why', []):
                    print('    ', line)
                for tile, bits in res.get('diffs', {}).items():
                    print(f'     {tile}:', *bits, sep='\n       ')
        for tile, bits in report['unattributed'].items():
            totals['unattributed tiles'] += 1
            print(f'batch{i} unattributed {tile}:', *bits, sep='\n       ')
    print('summary:', dict(totals))


if __name__ == '__main__':
    main(sys.argv[1:])
