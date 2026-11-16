#!/usr/bin/env python3
"""Run every primitive in the IDE's primitive.xml through the vendor alone.

    GOWINHOME=... python3 tools/vendor_sweep.py -d GW1N-9C GW5A-25A [-n 4] [-j 3] [-o sweep-out]

For each device, every primitive of its family's primitive.xml is instantiated
in its own design: one case with all defaults plus n-1 random cases from
tools/primitive_strategies.py. Nothing is placed and Apicula is not run. The
vendor's log says which primitives the device accepts, which parameter values
it rejects despite the XML (PA1002), and which rules across parameters exist
(for example PA2078, the PLL VCO range). When a design with several cases
fails, each case is rerun alone.

Writes <out>/<device>.json with every case and its vendor messages, and prints
a summary per primitive. See doc/agent/vendor-sweep.md.
"""
import argparse
import collections
import json
import os
import re
import sys
from multiprocessing.dummy import Pool

TOOLS = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(TOOLS)
sys.path[:0] = [REPO, TOOLS]
import primitive_strategies as ps  # noqa: E402
from apycula import codegen  # noqa: E402

# device: (vendor device, part number)
DEVICES = {
    'GW1N-1': ('GW1N-1', 'GW1N-LV1LQ144C6/I5'),
    'GW1NZ-1': ('GW1NZ-1', 'GW1NZ-LV1QN48C6/I5'),
    'GW1N-4': ('GW1N-4', 'GW1N-LV4PG256C6/I5'),
    'GW1N-9': ('GW1N-9', 'GW1N-LV9PG256C6/I5'),
    'GW1N-9C': ('GW1NR-9C', 'GW1NR-LV9QN88PC6/I5'),
    'GW1NS-4': ('GW1NSR-4C', 'GW1NSR-LV4CQN48PC7/I6'),
    'GW2A-18': ('GW2A-18', 'GW2A-LV18PG256C8/I7'),
    'GW2A-18C': ('GW2A-18C', 'GW2A-LV18PG256SC8/I7'),
    'GW5A-25A': ('GW5A-25A', 'GW5A-LV25MG121NC1/I0'),
    'GW5AST-138C': ('GW5AST-138C', 'GW5AST-LV138PG484AC1/I0'),
}

SKIP = {'GND', 'VCC'}
_io_buffer = re.compile(r'(I|O|T|IO)BUF')
_log = re.compile(r'^(WARN|ERROR)\s+\((\w+)\)\s*:\s*(.*)$')
IGNORED = {'PA1000'}  # dangling nets: the sweep leaves inputs undriven on purpose


def cases_for(prims, prim, n, seed):
    spec = prims.spec[prim]
    defaults = []
    for name, param in spec['params'].items():
        fixed = prims.fixed(prim, name, param)
        if fixed is None:
            fixed = f'"{param["default"]}"' if param['type'] == 'string' else param['default']
        defaults.append((name, fixed))
    out = [ps.Case(prim, tuple(sorted(defaults)))]
    if n > 1 and spec['params']:
        out += [c for c in dict.fromkeys(ps.draw(prims.case(prim), n - 1, seed)) if c != out[0]]
    return out


def netlist(cases, spec):
    """Cases of one primitive. Inout ports, and the pad side of I/O buffers, are
    top-level ports. Ports with CLK in their name share a clock input. Other
    1-bit inputs are undriven, bus inputs are tied to GND, and outputs go to
    dummy wires. The vendor reads netlists per bit: a bus must be a
    concatenation of 1-bit wires (a `wire [7:0]` is rejected with PA2060)."""
    mod, cst = codegen.Module(), codegen.Constraints()
    mod.wires.add('gnd')
    g = codegen.Primitive('GND', 'sweep_gnd')
    g.portmap = {'G': 'gnd'}
    mod.primitives[g.inst] = g
    mod.inputs.add('clk')
    names = {}
    for i, case in enumerate(cases):
        name = f'inst{i}_{case.prim}'
        names[name] = case
        p = codegen.Primitive(case.prim, name)
        io_buffer = bool(_io_buffer.search(case.prim))
        for port, (direction, width) in spec[case.prim]['ports'].items():
            wires = [f'{name}_{port}' + (f'_{b}' if width > 1 else '') for b in range(width)]
            pad = direction == 'inout' or io_buffer and (
                direction == 'input' and port in ('I', 'IB') or direction == 'output' and port in ('O', 'OB'))
            if pad:
                getattr(mod, {'input': 'inputs', 'output': 'outputs', 'inout': 'inouts'}[direction]).update(wires)
            elif direction == 'input' and 'CLK' in port and width == 1:
                wires = ['clk']
            elif direction == 'input' and width > 1:
                wires = ['gnd'] * width
            else:
                mod.wires.update(wires)
            p.portmap[port] = wires[0] if width == 1 else wires[::-1]
        p.params = dict(case.params)
        mod.primitives[name] = p
    return mod, cst, names


def read_log(path, names):
    """Vendor messages per instance name, and those naming no instance."""
    per, other = collections.defaultdict(list), []
    if not os.path.exists(path):
        return per, ['no log']
    with open(path, errors='replace') as f:
        for line in f:
            m = _log.match(line.strip())
            if not m or m.group(2) in IGNORED:
                continue
            msg = f'{m.group(1)} {m.group(2)}: {m.group(3)}'
            msg = re.sub(r'"[^"]*top\.v":\d+ \| ', '', msg)
            hit = [n for n in names if re.search(rf"\b{re.escape(n)}\b", msg)]
            for n in hit:
                per[n].append(msg)
            if not hit:
                other.append(msg)
    return per, other


def run(job):
    device, workdir, cases, spec = job
    vendor_device, part = DEVICES[device]
    mod, cst, names = netlist(cases, spec)
    pnr = codegen.Pnr()
    pnr.device, pnr.partnumber, pnr.netlist, pnr.cst = vendor_device, part, mod, cst
    os.makedirs(workdir, exist_ok=True)
    with open(os.path.join(workdir, 'gw_sh.log'), 'w') as log:
        res = pnr.run_pnr(workdir=workdir, stdout=log)
    per, other = read_log(os.path.join(workdir, 'impl/pnr/top.log'), names)
    return {'bitstream': res is not None, 'per': per, 'other': other, 'names': names}


def sweep(device, prims, args, pool):
    names = [p for p in sorted(prims.spec) if p not in SKIP and (not args.prims or p in args.prims)]
    jobs = [(device, os.path.join(args.out, device, p), cases_for(prims, p, args.count, args.seed), prims.spec)
            for p in names]
    results = {}
    for (dev, workdir, cases, spec), r in zip(jobs, pool.imap(run, jobs)):
        prim = cases[0].prim
        if not r['bitstream'] and len(cases) > 1:
            # find out which cases the design failed for
            singles = pool.map(run, [(dev, f'{workdir}/case{i}', [c], spec) for i, c in enumerate(cases)])
            per_case = [(c, s['bitstream'], s['per'].get('inst0_' + prim, []), s['other'])
                        for c, s in zip(cases, singles)]
        else:
            per_case = [(c, r['bitstream'], r['per'].get(f'inst{i}_{prim}', []), r['other'])
                        for i, c in enumerate(cases)]
        results[prim] = [{'params': dict(c.params), 'bitstream': ok, 'messages': msgs, 'design_messages': other}
                         for c, ok, msgs, other in per_case]
        print(f'{device} {prim}: ' + ' '.join(
            'ok' if x['bitstream'] and not x['messages'] else ('warn' if x['bitstream'] else 'FAIL')
            for x in results[prim]), flush=True)
    return results


def summary(device, results):
    lines = [f'## {device}', '', '| primitive | ok | warned | failed | messages |', '|---|---|---|---|---|']
    for prim, cases in sorted(results.items()):
        ok = sum(c['bitstream'] and not c['messages'] for c in cases)
        warn = sum(c['bitstream'] and bool(c['messages']) for c in cases)
        fail = sum(not c['bitstream'] for c in cases)
        codes = collections.Counter()
        for c in cases:
            msgs = c['messages'] + (c['design_messages'] if not c['bitstream'] else [])
            codes.update(dict.fromkeys(m.split(':')[0] for m in msgs))
        lines.append(f'| {prim} | {ok} | {warn} | {fail} | {", ".join(f"{k} ×{v}" for k, v in sorted(codes.items()))} |')
    return '\n'.join(lines) + '\n'


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('-d', '--devices', nargs='+', required=True, choices=sorted(DEVICES))
    ap.add_argument('-n', '--count', type=int, default=4, help='cases per primitive, the first with defaults')
    ap.add_argument('--prims', nargs='*')
    ap.add_argument('--seed', type=int, default=0)
    ap.add_argument('-j', '--jobs', type=int, default=3)
    ap.add_argument('-o', '--out', default='sweep-out')
    args = ap.parse_args(argv)
    with Pool(args.jobs) as pool:
        for device in args.devices:
            prims = ps.Primitives(device, DEVICES[device][0])
            results = sweep(device, prims, args, pool)
            with open(os.path.join(args.out, f'{device}.json'), 'w') as f:
                json.dump(results, f, indent=1)
            with open(os.path.join(args.out, f'{device}.md'), 'w') as f:
                f.write(summary(device, results))


if __name__ == '__main__':
    main(sys.argv[1:])
