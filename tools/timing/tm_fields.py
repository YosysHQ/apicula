#!/usr/bin/env python3
"""List the field offsets of the old .tm record's sub-models (IDE 1.9.10.03).

    tm_fields.py libgowin.so [--class IddrOddrTmModel,...] [--json out.json]

STA::TmModel is read verbatim from a 0x3cc0-byte record. Its sub-models sit at
fixed offsets (STA::TmModel::init_dlt) and each STA::<X>TmModel::get<Name>(float*)
copies four floats from `this + disp + 4 * k`. This prints `disp + 4 * k` per
getter, which is the field's offset within the sub-model's block of the record.
Getters with other signatures (DSP sub-models, IODELAY) are not covered.
Research aid; used to write the parse_* field tables in apycula/tm_parser.py.
"""
import argparse
import collections
import json
import re
import subprocess


def getter_offsets(lib):
    syms = subprocess.run(['nm', '-SC', lib], capture_output=True, text=True).stdout
    out, odd = collections.defaultdict(dict), []
    for m in re.finditer(r'^([0-9a-f]+) ([0-9a-f]+) [TW] STA::(\w+TmModel)::get(\w+)\(float\*\)$', syms, re.M):
        start, size, cls, name = int(m[1], 16), int(m[2], 16), m[3], m[4]
        dis = subprocess.run(['objdump', '-d', '--no-show-raw-insn', f'--start-address={start}',
                              f'--stop-address={start + size}', lib], capture_output=True, text=True).stdout
        # the loop index is offset by `add $k` (or `sub $-k`) before the scaled load
        k = [int(x, 16) for x in re.findall(r'add\s+\$0x([0-9a-f]+),%r[cd]x', dis)]
        k += [(1 << 64) - int(x, 16) for x in re.findall(r'sub\s+\$0x([0-9a-f]+),%r[cd]x', dis)]
        disp = re.findall(r'mov\s+(?:0x([0-9a-f]+))?\(%r\w+,%r\w+,4\),%eax', dis)
        if len(disp) != 1 or len(k) > 1 or 'call' in dis:
            odd.append(f'{cls}::get{name}')
            continue
        out[cls][name] = int(disp[0] or '0', 16) + 4 * (k[0] if k else 0)
    return {c: dict(sorted(v.items(), key=lambda x: x[1])) for c, v in sorted(out.items())}, odd


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('lib')
    ap.add_argument('--class', dest='classes')
    ap.add_argument('--json')
    args = ap.parse_args()
    fields, odd = getter_offsets(args.lib)
    if args.classes:
        fields = {c: fields[c] for c in args.classes.split(',')}
    if args.json:
        json.dump(fields, open(args.json, 'w'), indent=1)
    for cls, f in fields.items():
        print(f'== {cls}')
        for name, off in f.items():
            print(f'  {off:#06x} {name}')
    print('not decoded (different shape):', ', '.join(odd))


if __name__ == '__main__':
    main()
