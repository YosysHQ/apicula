#!/usr/bin/env python3
"""Read the IDE's primitive descriptions: ports, parameters and allowed values.

    python3 tools/gowin_primitives.py [--family gw1n|gw5a] [-o spec.json]

The IDE ships `IDE/bin/primitive.xml` (GW1N and GW2A) and
`IDE/bin/prim_syns/gw5a/primitive.xml`. Each primitive lists its ports with
widths, and each parameter its default (`INIT_VAL`) and, optionally, allowed
values (`PARAM_VAL`). `classify` turns the values into a domain; see
doc/agent/primitive-params.md.
"""
import argparse
import json
import os
import re
import shutil
import sys
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


def tool(env, *names):
    """Path of a tool: the environment variable `env`, else the first of `names`
    on PATH."""
    path = os.environ.get(env) or next(filter(None, map(shutil.which, names)), None)
    if not path:
        sys.exit(f'none of {names} found; set {env}')
    return path


def read_cell_library(family):
    """Yosys commands that read Yosys' Gowin cell library as black boxes."""
    return f'read_verilog -lib +/gowin/cells_sim.v; read_verilog -lib +/gowin/cells_xtra_{family}.v; '


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--family', choices=sorted(XML_PATHS), default='gw1n')
    ap.add_argument('--gowinhome', default=os.environ.get('GOWINHOME'))
    ap.add_argument('-o', '--output')
    args = ap.parse_args(argv)
    if not args.gowinhome:
        sys.exit('GOWINHOME not set')
    prims = load(os.path.join(args.gowinhome, XML_PATHS[args.family]))
    text = json.dumps(prims, indent=1, sort_keys=True)
    if args.output:
        with open(args.output, 'w') as f:
            f.write(text)
    else:
        print(text)


if __name__ == '__main__':
    main(sys.argv[1:])
