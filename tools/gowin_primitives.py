#!/usr/bin/env python3
"""Read the IDE's primitive descriptions: ports, parameters and allowed values.

    python3 tools/gowin_primitives.py dump [--family gw1n|gw5a] [-o spec.json]
    python3 tools/gowin_primitives.py compare-yosys --family gw1n|gw2a|gw5a

The IDE ships `IDE/bin/primitive.xml` (GW1N and GW2A) and
`IDE/bin/prim_syns/gw5a/primitive.xml`. Each primitive lists its ports with
widths, and each parameter its default (`INIT_VAL`) and, optionally, allowed
values (`PARAM_VAL`). `classify` turns the values into a domain; see
doc/agent/primitive-params.md.

`compare-yosys` checks the XML against Yosys' Gowin cell library, which Apicula
designs are synthesised against. It needs `yosys` or `yowasp-yosys` on PATH.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET

XML_PATHS = {
    'gw1n': 'IDE/bin/primitive.xml',
    'gw2a': 'IDE/bin/primitive.xml',
    'gw5a': 'IDE/bin/prim_syns/gw5a/primitive.xml',
}

_num = re.compile(r'-?\d+(\.\d+)?')
_sized = re.compile(r"(-?)(\d+)'([bhdo])([0-9a-fA-FxXzZ_]+)")


def load(path):
    """Return {primitive: {'ports': {name: (dir, width)}, 'params': {name: param}}}."""
    prims = {}
    for mod in ET.parse(path).getroot().iter('module'):
        name = mod.findtext('name').strip()
        if name.startswith('VLG_'):  # generic RTL operators with variable widths, not primitives
            continue
        ports = {p.text.strip(): (p.tag.lower(), int(p.get('width')))
                 for p in mod if p.tag in ('INPUT', 'OUTPUT', 'INOUT')}
        params = {}
        for p in mod.findall('PARAMETER'):
            vals = [(v.text or '').strip() for v in p.findall('PARAM_VAL')]
            param = {'type': p.get('type'), 'default': (p.findtext('INIT_VAL') or '').strip()}
            param.update(classify(param['default'], vals))
            params[(p.text or '').strip()] = param
        prims[name] = {'ports': ports, 'params': params}
    return prims


def classify(default, vals):
    """Turn PARAM_VAL entries into a domain.

    Entries `min, max, normal|even` are an inclusive range, with step 1 or 2;
    any entries after those are allowed values outside the range.
    Other lists are enumerations. Without entries, a sized default such as 16'h0000
    means any value of that width, and a real default (FCLKIN) is unconstrained.
    """
    if len(vals) >= 3 and _num.fullmatch(vals[0]) and _num.fullmatch(vals[1]) \
            and vals[2] in ('normal', 'even'):
        # entries after the range tag are allowed too (GW5A OSCA FREQ_DIV: 2..126 even, and 3)
        return {'kind': 'range', 'min': int(vals[0]), 'max': int(vals[1]),
                'step': 2 if vals[2] == 'even' else 1, 'extra': [int(v) for v in vals[3:]]}
    if vals:
        return {'kind': 'enum', 'values': vals}
    m = _sized.fullmatch(default)
    if m:
        return {'kind': 'bits', 'width': int(m.group(2))}
    if _num.fullmatch(default):
        return {'kind': 'real'}
    return {'kind': 'unknown'}


def yosys_cells(family):
    yosys = shutil.which('yosys') or shutil.which('yowasp-yosys')
    if not yosys:
        sys.exit('yosys not found')
    with tempfile.TemporaryDirectory(dir='.') as tmp:
        out = os.path.join(os.path.basename(tmp), 'cells.json')  # yowasp only sees the cwd
        subprocess.run([yosys, '-q', '-p',
                        f'read_verilog -lib +/gowin/cells_sim.v; read_verilog -lib +/gowin/cells_xtra_{family}.v; '
                        f'blackbox =A:whitebox; write_json {out}'], check=True)
        with open(out) as f:
            return json.load(f)['modules']


def value(text):
    """Integer value of an XML default or a Yosys parameter string, else the string."""
    text = text.strip().strip('"')
    m = _sized.fullmatch(text)
    if m and not re.search('[xXzZ]', m.group(4)):
        v = int(m.group(4).replace('_', ''), {'b': 2, 'h': 16, 'd': 10, 'o': 8}[m.group(3)])
        return -v if m.group(1) else v
    if re.fullmatch(r'[01]{32}', text):  # Yosys integer parameters
        v = int(text, 2)
        return v - (1 << 32) if v >> 31 else v
    if re.fullmatch(r'[01]+', text):
        return int(text, 2)
    if re.fullmatch(r'-?\d+', text):
        return int(text)
    return text.lower()


def compare_yosys(prims, family):
    ymods = yosys_cells(family)
    ignore = lambda n: n.startswith(('$', '__'))
    report = {
        'only in primitive.xml': sorted(n for n in prims.keys() - ymods.keys() if not ignore(n)),
        'only in yosys': sorted(n for n in ymods.keys() - prims.keys() if not ignore(n)),
        'parameters only in primitive.xml': [], 'parameters only in yosys': [],
        'different defaults': [], 'different ports': [],
    }
    for name in sorted(prims.keys() & ymods.keys()):
        xp, yp = prims[name]['params'], ymods[name].get('parameter_default_values', {})
        report['parameters only in primitive.xml'] += [f'{name}.{p}' for p in xp.keys() - yp.keys()]
        report['parameters only in yosys'] += [f'{name}.{p}' for p in yp.keys() - xp.keys()]
        for p in sorted(xp.keys() & yp.keys()):
            if value(xp[p]['default']) != value(yp[p]):
                report['different defaults'].append(f'{name}.{p}: xml={xp[p]["default"]} yosys={yp[p].strip()}')
        xports = {p: w for p, (_, w) in prims[name]['ports'].items()}
        yports = {p: len(d['bits']) for p, d in ymods[name]['ports'].items()}
        if xports != yports:
            diff = sorted(f'{p}:{xports.get(p)}/{yports.get(p)}' for p in xports.keys() | yports.keys()
                          if xports.get(p) != yports.get(p))
            report['different ports'].append(f'{name} (xml/yosys width): {" ".join(diff)}')
    for title, items in report.items():
        print(f'{title} ({len(items)}):')
        for item in items:
            print('   ', item)


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('command', choices=['dump', 'compare-yosys'])
    ap.add_argument('--family', choices=sorted(XML_PATHS), default='gw1n')
    ap.add_argument('--gowinhome', default=os.environ.get('GOWINHOME'))
    ap.add_argument('-o', '--output')
    args = ap.parse_args(argv)
    if not args.gowinhome:
        sys.exit('GOWINHOME not set')
    prims = load(os.path.join(args.gowinhome, XML_PATHS[args.family]))
    if args.command == 'dump':
        text = json.dumps(prims, indent=1, sort_keys=True)
        if args.output:
            with open(args.output, 'w') as f:
                f.write(text)
        else:
            print(text)
    else:
        compare_yosys(prims, args.family)


if __name__ == '__main__':
    main(sys.argv[1:])
