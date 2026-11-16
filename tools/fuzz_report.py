#!/usr/bin/env python3
"""Summarise a tiled_fuzzer output directory.

    python3 tools/fuzz_report.py -d GW1N-9C fuzz-out

Prints the number of cases per primitive and status. For mismatches, it groups
differing fuses by the fuse table rows they belong to, named by attribute, so a
pattern across cases is visible. For unsupported cases, it lists Apicula's
error messages.
"""
import argparse
import collections
import glob
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from apycula import attrids, chipdb  # noqa: E402

# fuse table -> (logicinfo table, attribute ids, value ids)
TABLES = {
    'IOBA': ('IOB', attrids.iob_attrids, attrids.iob_attrvals),
    'IOBB': ('IOB', attrids.iob_attrids, attrids.iob_attrvals),
    'BANK': ('IOB', attrids.iob_attrids, attrids.iob_attrvals),
    'CLS': ('SLICE', attrids.cls_attrids, attrids.cls_attrvals),
    'BSRAM': ('BSRAM', attrids.bsram_attrids, attrids.bsram_attrvals),
    'PLL': ('PLL', attrids.pll_attrids, attrids.pll_attrvals),
    'IOLOGIC': ('IOLOGIC', attrids.iologic_attrids, attrids.iologic_attrvals),
    'DSP': ('DSP', attrids.dsp_attrids, attrids.dsp_attrvals),
    '5A_DSP': ('5A_DSP', attrids.dsp_5a_attrids, attrids.dsp_5a_attrvals),
}


def row_names(db, ttyp, bit):
    """Fuse table rows containing `bit`, as 'TABLE: ATTR=VAL,...', shortest first."""
    out = []
    for kind, tables in (('shortval', db.shortval), ('longval', db.longval)):
        for name, rows in tables.get(ttyp, {}).items():
            prefix = next((p for p in TABLES if name.startswith(p)), None)
            if not prefix:
                continue
            li_name, an, av = TABLES[prefix]
            li = db.rev_logicinfo(li_name)
            ids = {v: k for k, v in an.items()}
            vals = {v: k for k, v in av.items()}
            for key, bits in rows.items():
                if bit in bits:
                    terms = []
                    for k in key:
                        if k and abs(k) in li:
                            a, v = li[abs(k)]
                            terms.append(('!' if k < 0 else '') + f'{ids.get(a, a)}={vals.get(v, v)}')
                    out.append(f'{name}: ' + ','.join(terms))
    return sorted(set(out), key=len)[:3]


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('-d', '--device', required=True)
    ap.add_argument('out')
    ap.add_argument('--rows', type=int, default=15, help='fuse rows to show per primitive')
    args = ap.parse_args(argv)
    db = chipdb.load_chipdb(os.path.join(os.path.dirname(chipdb.__file__), f'{args.device}.msgpack.xz'))

    status = collections.Counter()
    fuse_rows = collections.defaultdict(collections.Counter)
    decode = collections.Counter()
    for path in glob.glob(os.path.join(args.out, '*', 'report.json')):
        with open(path) as f:
            report = json.load(f)
        for res in report.get('cases', {}).values():
            prim = res['case']['prim']
            status[(prim, res['status'])] += 1
            if res['status'] == 'decode':
                decode[(prim, str(res.get('vendor', {}).get('cell')))] += 1
            for tile, bits in res.get('diffs', {}).items():
                r, c = (int(x) - 1 for x in re.match(r'R(\d+)C(\d+)', tile).groups())
                for detail in bits:
                    m = re.match(r'\((\d+), (\d+)\) vendor=(\d)', detail)
                    bit = (int(m.group(1)), int(m.group(2)))
                    names = row_names(db, db.grid[r][c], bit) or ['(no table row)']
                    fuse_rows[prim][(f'vendor={m.group(3)}', ' | '.join(names))] += 1
    reasons = collections.Counter()
    for path in glob.glob(os.path.join(args.out, '*', 'unsupported_*.json')):
        with open(path) as f:
            res = json.load(f)
        why = res.get('why')
        log = os.path.join(os.path.dirname(path), 'apicula', 'tools.log')
        if not why and os.path.exists(log):  # older runs missed bare 'Exception:' lines
            with open(log, errors='replace') as f:
                why = [line.strip() for line in f if 'ERROR' in line or re.match(r'\w*(Error|Exception): ', line)]
        why = why or ['(no message)']
        prim = 'combination' if 'cases' in res else res['case']['prim']
        for line in dict.fromkeys(why):
            reasons[(prim, re.sub(r'X\d+Y\d+/IOB[AB] \(\w+\)|inst\d+_\w+', '…', line)[:160])] += 1

    print('cases per primitive and status:')
    for (prim, st), n in sorted(status.items()):
        print(f'  {prim:14} {st:12} {n}')
    for prim, rows in sorted(fuse_rows.items()):
        print(f'differing fuses, {prim} (count, side, rows):')
        for (side, names), n in rows.most_common(args.rows):
            print(f'  {n:4} {side} {names}')
    if decode:
        print('decode (primitive, vendor cell):', dict(decode))
    if reasons:
        print('Apicula errors:')
        for (prim, line), n in sorted(reasons.items()):
            print(f'  {n:4} {prim}: {line}')


if __name__ == '__main__':
    main(sys.argv[1:])
