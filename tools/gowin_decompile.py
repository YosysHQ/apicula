#!/usr/bin/env python3
"""Decompile selected libgowin.so functions with Gowin types applied.

    gowin_decompile.py --lib LIBGOWIN_SO --enums ENUMS_JSON --out DIR NAME [NAME...]

NAME is a substring of a demangled symbol, for example setPllAttrInPll_1N2.
Generate ENUMS_JSON with gowin_extract.py extract.

Ghidra imports the library once, without auto-analysis, into a reusable project.
Only the requested functions and the functions they call are defined, so a
decompile takes a short time rather than a full analysis of the library.
Static analysis only; the vendor library is never executed.
"""
import argparse
import json
import os
import re
import subprocess
import sys
import tempfile

from gowin_extract import RIP, Image

SCRIPT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ghidra')
HEADLESS = os.environ.get('GHIDRA_HEADLESS', '/opt/ghidra/support/analyzeHeadless')
CALL = re.compile(r'call\s+([0-9a-f]+)\s+<(.*)>$')
SET_ATTR = re.compile(r'set\w*Attr\(NETLIST::(\w+_ATTR), (?:NETLIST::)?(\w+)\)')
GET_ATTR = re.compile(r'get\w*Attr\(NETLIST::(\w+_ATTR)\)')

# Parameter objects: the ALL_INIT_TYPE range stored at each accessor's result.
INIT_STRUCTS = {'PllInit': {'accessor': 'NETLIST::Pll::getPllInitValue()', 'first': 0xb5, 'last': 0x15d}}


def symbols(lib):
    text = subprocess.run(['nm', '-SC', '--defined-only', lib], capture_output=True, text=True).stdout
    found = []
    for line in text.splitlines():
        parts = line.split(None, 3)
        if len(parts) == 4 and parts[2] in 'Tt':
            found.append((int(parts[0], 16), int(parts[1], 16), parts[3]))
    return found


def disassemble(lib, start, size):
    return subprocess.run(['objdump', '-d', '-C', '--no-show-raw-insn', f'--start-address={start}',
                           f'--stop-address={start + size}', lib], capture_output=True, text=True).stdout


def init_type_names(lib, image):
    """ALL_INIT_TYPE value -> parameter name, from VLGPARSE::getDefInitTypeString*."""
    names = {}
    for start, size, name in symbols(lib):
        if 'getDefInitTypeString' not in name:
            continue
        body = [(int(m[1], 16), m[2].strip()) for m in
                (re.match(r'\s*([0-9a-f]+):\t(.*)', x) for x in disassemble(lib, start, size).splitlines()) if m]
        index = {a: i for i, (a, _) in enumerate(body)}
        for i, (_, insn) in enumerate(body[:-1]):
            cmp_ = re.match(r'cmp[lw]?\s+\$0x([0-9a-f]+),%eax', insn)
            if not cmp_ or not body[i + 1][1].startswith('ja'):
                continue
            sub = re.match(r'sub\s+\$0x([0-9a-f]+),%eax', body[i - 1][1])
            base = int(sub[1], 16) if sub else 0
            table = next((int(r[2], 16) for _, x in body[i + 1:i + 8] if (r := RIP.search(x))), None)
            if table is None:
                continue
            for k in range(int(cmp_[1], 16) + 1):
                target = (table + image.i32(table + 4 * k)) & 0xffffffff
                for _, x in body[index[target]:index[target] + 10] if target in index else ():
                    rip = RIP.search(x)
                    if rip and rip[1] == 'rsi':
                        names[k + base] = image.cstr(int(rip[2], 16))
                        break
                    if x.startswith('jmp'):
                        break
    return names


def strip_templates(name):
    previous = None
    while previous != name:
        previous = name
        name = re.sub(r'<[^<>]*>', '', name)
    return name


def short_name(demangled):
    """A Ghidra-safe label from a demangled C++ name."""
    for op, label in (('operator==', 'string_equals'), ('operator!=', 'string_differs')):
        if op + '<char' in demangled:
            return label
    name = strip_templates(demangled.replace('@plt', ''))
    name = name.split('(')[0].split()[-1] if name.split('(')[0].split() else name
    return re.sub(r'\W', '_', name.replace('::', '_')) or 'unnamed'


def signature_for(name, enums):
    """Parameter types for the attribute accessors we know about."""
    for struct, spec in INIT_STRUCTS.items():
        if spec['accessor'] in name:
            return {'returns': f'{struct}*', 'params': [['this', 'void*']]}
    if (m := SET_ATTR.search(name)) and m[1] in enums:
        value = m[2] if m[2] in enums else 'short'
        return {'returns': 'void', 'params': [['this', 'void*'], ['attr', m[1]], ['value', value]]}
    if (m := GET_ATTR.search(name)) and m[1] in enums:
        return {'returns': 'short', 'params': [['this', 'void*'], ['attr', m[1]]]}
    return None


def enum_labels(values):
    """Ghidra enum members need unique, valid names."""
    labels, seen = {}, set()
    for number, name in values.items():
        label = re.sub(r'\W', '_', name) or f'v{number}'
        if label[0].isdigit():
            label = f'v_{label}'
        if label in seen:
            label = f'{label}_{number}'
        seen.add(label)
        labels[number] = label
    return labels


def build_config(lib, image, enums, wanted):
    table = symbols(lib)
    targets, callees, strings = [], {}, set()
    for pattern in wanted:
        matches = [s for s in table if pattern in s[2]]
        if not matches:
            sys.exit(f'no symbol matches {pattern!r}')
        for start, size, name in matches:
            label = short_name(name)
            targets.append({'address': start, 'size': size, 'name': label,
                            'file': f'{label}_{start:x}.c', 'demangled': name})
            for line in disassemble(lib, start, size).splitlines():
                if (rip := RIP.search(line)):
                    try:
                        text = image.cstr(int(rip[2], 16))
                    except KeyError:
                        text = ''
                    if all(32 <= ord(c) < 127 for c in text):
                        strings.add(int(rip[2], 16))
                call = CALL.search(line.split('\t')[-1].strip())
                if call and int(call[1], 16) != start:
                    entry = {'address': int(call[1], 16), 'name': short_name(call[2])}
                    if (sig := signature_for(call[2], enums)):
                        entry['signature'] = sig
                    callees[entry['address']] = entry
    names = init_type_names(lib, image)
    structs = {}
    for struct, spec in INIT_STRUCTS.items():
        fields = {str((kind - spec['first']) * 8): re.sub(r'\W', '_', names[kind])
                  for kind in range(spec['first'], spec['last'] + 1) if kind in names}
        structs[struct] = {'size': (spec['last'] - spec['first'] + 1) * 8, 'fields': fields}
    return {'enums': {k: enum_labels(v) for k, v in enums.items()}, 'structs': structs,
            'callees': list(callees.values()), 'targets': targets, 'strings': sorted(strings)}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--lib', required=True)
    parser.add_argument('--enums', required=True)
    parser.add_argument('--out', required=True)
    parser.add_argument('--project', default=os.path.expanduser('~/.cache/apicula-ghidra'))
    parser.add_argument('names', nargs='+')
    args = parser.parse_args()

    with open(args.enums) as f:
        enums = json.load(f)
    enums = {k: v for k, v in enums.items() if k.endswith(('_ATTR', '_VALUE')) or k == 'INS_TYPE'}
    config = build_config(args.lib, Image(args.lib), enums, args.names)
    os.makedirs(args.project, exist_ok=True)
    fd, path = tempfile.mkstemp(suffix='.json')
    with os.fdopen(fd, 'w') as f:
        json.dump(config, f)
    print(f"{len(config['targets'])} targets, {len(config['callees'])} callees")

    source = os.path.basename(args.lib)
    if os.path.exists(os.path.join(args.project, 'gowin.gpr')):
        mode = ['-process', source]
    else:
        mode = ['-import', args.lib]
    command = [HEADLESS, args.project, 'gowin', *mode, '-noanalysis', '-scriptPath', SCRIPT_DIR,
               '-postScript', 'GowinDecompile.java', path, os.path.abspath(args.out)]
    status = subprocess.run(command).returncode
    os.unlink(path)
    return status


if __name__ == '__main__':
    sys.exit(main())
