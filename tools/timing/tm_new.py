#!/usr/bin/env python3
"""Dump the TmModelNew block of a Gowin .tm file (IDE 1.9.10.03).

    tm_new.py DEVICE.tm [--lib libgowin.so] [--class LUT,XWIRE,...]

The format is described in apycula/tm_parser.py (parse_new_block).

Each value holds values_per_group floats per core type. Group order within a
quad is [min, min, max, max]. With --lib, variable names are decoded from the
STA::TmModelBase::get*VarName jump tables. Research aid; output not committed.
"""
import argparse
import re
import subprocess
import sys

from apycula.tm_parser import NEW_CLASSES as CLASSES, parse_new_block

# class -> name of the TmModelBase::get<X>VarName function used by TmModelBase::getVarName
NAMEFN = {'LUT': 'Lut', 'ALU': 'Alu', 'DFF': 'Dff', 'DL': 'Dl', 'SSRAM': 'Ssram', 'XWIRE': 'XWire',
          'FANOUT': 'Fanout', 'GLBSRC': 'Glbsrc', 'HCLK': 'XWire', 'IBUF': 'Ibuf', 'OBUF4mA': 'Obuf',
          'OBUF8mA': 'Obuf', 'BSRAM': 'Bsram'}


def var_names(lib):
    """{'Lut': {0: 'A_F', ...}, ...} from the get*VarName jump tables."""
    sys.path.insert(0, __file__.rsplit('/', 2)[0])
    from gowin_extract import Image
    image = Image(lib)
    syms = subprocess.run(['nm', '-SC', lib], capture_output=True, text=True).stdout
    names = {}
    for m in re.finditer(r'^([0-9a-f]+) ([0-9a-f]+) T STA::TmModelBase::get(\w+)VarName\(', syms, re.M):
        start, size = int(m[1], 16), int(m[2], 16)
        dis = subprocess.run(['objdump', '-d', '--no-show-raw-insn', f'--start-address={start}',
                              f'--stop-address={start + size}', lib], capture_output=True, text=True).stdout
        body = [(int(x[1], 16), x[2]) for x in (re.match(r'\s*([0-9a-f]+):\t(.*)', l) for l in dis.splitlines()) if x]
        index = {a: i for i, (a, _) in enumerate(body)}
        cases = table = None
        for _, text in body:
            c = re.search(r'cmp\s+\$0x([0-9a-f]+),%eax', text)
            if c and cases is None:
                cases = int(c[1], 16) + 1
            t = re.search(r'lea\s+0x[0-9a-f]+\(%rip\),%rax\s+# ([0-9a-f]+)', text)
            if t and cases and table is None:
                table = int(t[1], 16)
        found = {}
        for v in range(cases or 0):
            target = (table + image.i32(table + 4 * v)) & 0xffffffffffffffff
            for _, text in body[index.get(target, len(body)):index.get(target, len(body)) + 4]:
                s = re.search(r'lea\s+0x[0-9a-f]+\(%rip\),%rsi\s+# ([0-9a-f]+)', text)
                if s:
                    found[v] = image.cstr(int(s[1], 16)).rstrip(' :')
                    break
        names[m[3]] = found
    return names


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('tm')
    ap.add_argument('--lib')
    ap.add_argument('--class', dest='classes', default=','.join(CLASSES))
    args = ap.parse_args()
    new, per = parse_new_block(open(args.tm, 'rb').read())
    names = var_names(args.lib) if args.lib else {}
    for cls in args.classes.split(','):
        if cls not in new:
            continue
        print(f'== {cls}')
        for en, v in sorted(new[cls].items()):
            groups = ' | '.join(' '.join(f'{x:6.3f}' for x in v[g * per:(g + 1) * per]) for g in range(len(v) // per))
            print(f"  {names.get(NAMEFN[cls], {}).get(en, en)!s:28s} {groups}")


if __name__ == '__main__':
    main()
