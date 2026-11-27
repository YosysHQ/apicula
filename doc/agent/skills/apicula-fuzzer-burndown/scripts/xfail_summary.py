#!/usr/bin/env python3
"""Summarise xfails from a `gh run view <id> --log` dump of apicula's Tiled fuzzer.

    xfail_summary.py fuzzlog.txt                 # one line per xfailed device-prim
    xfail_summary.py fuzzlog.txt --all           # include nextpnr/Yosys-blocked ones
    xfail_summary.py fuzzlog.txt --show GW1N-9C-OSER4 GW2A-18C-SDPB
"""
import argparse
import collections
import re

ap = argparse.ArgumentParser()
ap.add_argument('log')
ap.add_argument('--all', action='store_true')
ap.add_argument('--show', nargs='*', default=[])
args = ap.parse_args()

# gh log lines are 'job<TAB>step<TAB>timestamp text'
lines = [re.sub(r'^[^\t]*\t[^\t]*\t\S+ ', '', l) for l in open(args.log).read().splitlines()]
for l in lines:
    if re.match(r'=+ .*(passed|xfailed).* =+$', l):
        print(l)

blocks, cur = [], None
for l in lines:
    m = re.match(r'XFAIL tests/test_fuzz.py::test_(\w+)\[([^\]]+)\] - (.*)', l)
    if m:
        cur = dict(test=m[1], id=m[2], why=m[3], body=[])
        blocks.append(cur)
    elif re.match(r'(PASSED|SKIPPED|FAILED|XPASS|=+)', l):
        cur = None
    elif cur is not None:
        cur['body'].append(l)

if args.show:
    for b in blocks:
        if b['id'] in args.show:
            print(f"== {b['id']}: {b['why']}")
            print('\n'.join(x[:300] for x in b['body']))
    raise SystemExit

blocked = ('Yosys cell', 'nextpnr')
for b in blocks:
    if b['test'] != 'primitive':
        print(f"{b['test']} {b['id']}: {b['why'][:80]}")
        continue
    if not args.all and any(s in b['why'] for s in blocked):
        continue
    cases = sum(1 for x in b['body'] if re.match(r'^\S+ \{', x))
    rows = collections.Counter(x.split('apicula=')[1][2:].split('|')[0].strip()
                               for x in b['body'] if x.startswith('  R') and 'apicula=' in x)
    errors = sorted({x.strip()[:100] for x in b['body'] if re.search(r'Error|Exception|ERROR', x)})
    print(f"{b['id']:28} cases={cases} diffs={sum(rows.values()):3} rows={len(rows):2} "
          f"{list(rows)[:4]} {errors[:1]}")
