#!/usr/bin/env python3
"""List every fusegen attribute assignment in libgowin.so, with its context.

    gowin_attr_sites.py LIBGOWIN_SO ENUMS_JSON OUT_JSON

Each record is one call to a `set*Attr(ATTR, VALUE)` method: the enclosing
function, the attribute and value (named from enums.json when they are
constants), the primitives of an enclosing INS_TYPE switch case, and the branches
guarding the call.

This is a research aid. The guards are approximate: `call` is the nearest earlier
call, which can be unrelated to the condition being tested. ENUMS_JSON comes from
gowin_extract.py extract. Static analysis only; the vendor library is never
executed.
"""
import json
import re
import subprocess
import sys
from collections import Counter

from gowin_extract import HEADER, INSN, NAME_FN, RIP, Image

# Numeric values such as PLL dividers go through overloads taking a short.
SETTER = re.compile(r'<(?:NETLIST::)?([\w:~]*?::)?(set\w*Attr)\(NETLIST::(\w+_ATTR), (NETLIST::\w+_VALUE|short)\)')
COND_JUMP = re.compile(r'j(e|ne|a|ae|b|be|g|ge|l|le|s|ns)\s+([0-9a-f]+)')
JUMP = re.compile(r'jmp\s+([0-9a-f]+)')
CONST_ARG = re.compile(r'mov[lw]?\s+\$(-?0x[0-9a-f]+),%(esi|edx)$')
ARG_WRITE = re.compile(r'\S+\s+.*,%(esi|edx|rsi|rdx)$')


def setter_functions(lib):
    """Yield (name, [(addr, text)]) for functions that call an attribute setter."""
    proc = subprocess.Popen(['objdump', '-d', '-C', '--no-show-raw-insn', '-j', '.text', lib],
                            stdout=subprocess.PIPE, text=True, errors='replace', bufsize=1 << 20)
    name, body, keep = None, [], False
    for line in proc.stdout:
        header = HEADER.match(line)
        if header:
            if keep:
                yield name, body
            name, body, keep = header[2], [], False
        elif name is not None and (insn := INSN.match(line)):
            body.append((int(insn[1], 16), insn[2].strip()))
            keep = keep or (not NAME_FN.match(name) and bool(SETTER.search(insn[2])))
    if keep:
        yield name, body
    if proc.wait():
        raise RuntimeError(f'objdump failed with status {proc.returncode}')


def switches(image, body):
    found = []
    for n, (_, text) in enumerate(body[:-1]):
        cmp_ = re.match(r'cmp[lw]?\s+\$0x([0-9a-f]+),%eax', text)
        if not cmp_ or not n or not body[n + 1][1].startswith('ja'):
            continue
        sub = re.match(r'sub\s+\$0x([0-9a-f]+),%eax', body[n - 1][1])
        base = int(sub[1], 16) if sub else 0
        table = next((int(r[2], 16) for _, x in body[n + 1:n + 8] if (r := RIP.search(x))), None)
        if table is None:
            continue
        # A virtual call right before the switch is how the instance type is fetched.
        typed = any('call' in x and ('*%rax' in x or 'getType' in x or 'InsType' in x)
                    for _, x in body[max(0, n - 5):n])
        targets = {}
        for k in range(int(cmp_[1], 16) + 1):
            targets.setdefault((table + image.i32(table + 4 * k)) & 0xffffffff, []).append(k + base)
        found.append({'targets': sorted(targets.items()), 'typed': typed})
    return found


def guard(body, n):
    call = next((x for _, x in reversed(body[max(0, n - 12):n]) if x.startswith('call')), None)
    return {'call': re.sub(r'@plt>|^call\s+\S+\s+<', '', call)[:90] if call else None,
            'test': body[n - 1][1][:40] if n else ''}


def sites_in(fn, body, image, enums, stats):
    def named(enum, kind, value):
        return enums.get(f'{enum}_{kind}', {}).get(str(value), value)

    types = enums['INS_TYPE']
    sw = switches(image, body)
    end = body[-1][0] + 1
    branches = []
    for n, (addr, text) in enumerate(body):
        if cond := COND_JUMP.match(text):
            branches.append((addr, int(cond[2], 16), n, True))
        elif jump := JUMP.match(text):
            branches.append((addr, int(jump[1], 16), n, False))

    args = {}
    for addr, text in body:
        if const := CONST_ARG.match(text):
            args[const[2]] = int(const[1], 16)
            continue
        if write := ARG_WRITE.match(text):
            args[write[1].replace('r', 'e', 1)] = None
        if not text.startswith('call'):
            continue
        setter = SETTER.search(text)
        if not setter:
            args = {}
            continue
        enum = setter[3][:-5]
        attr, val = args.get('esi'), args.get('edx')
        args = {}

        low, high, case = body[0][0], end, None
        for s in sw:
            starts = [t for t, _ in s['targets']]
            for j, (target, values) in enumerate(s['targets']):
                following = starts[j + 1] if j + 1 < len(starts) else end
                if target <= addr < following and target >= low:
                    low, high, case = target, following, (values, s['typed'])

        guards = [guard(body, n) if conditional else {'else_of_branch_at': hex(at)}
                  for at, target, n, conditional in branches
                  if low <= at < addr < min(target, high)]
        primitives = [types.get(str(v), f'INS_{v}') for v in case[0]] if case and case[1] else None
        stats['total'] += 1
        stats['constant_args'] += attr is not None and val is not None
        stats['under_ins_type_switch'] += bool(primitives)
        stats['no_guard'] += not guards
        yield {'function': fn, 'address': hex(addr), 'enum': enum,
               'attr': attr, 'attr_name': None if attr is None else named(enum, 'ATTR', attr),
               'value': val, 'value_name': None if val is None else named(enum, 'VALUE', val),
               'primitives': primitives, 'guards': guards}


def main(argv):
    if len(argv) != 4:
        print(__doc__)
        return 2
    image = Image(argv[1])
    with open(argv[2]) as f:
        enums = json.load(f)
    stats = Counter()
    rows = [row for name, body in setter_functions(argv[1])
            for row in sites_in(name, body, image, enums, stats)]
    with open(argv[3], 'w') as f:
        json.dump(rows, f, indent=0)
        f.write('\n')
    print(dict(stats))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
