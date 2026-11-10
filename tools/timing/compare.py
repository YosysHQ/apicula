"""Compare nextpnr, the vendor SDF and the reimplemented vendor model: compare.py ROUTES_DIR"""
import json, sys, statistics as st, collections, re
d = sys.argv[1]
R = json.load(open(f'{d}/routes.json')); N = json.load(open(f'{d}/npnr_delays.json'))
rows = [(R[int(i)], v) for i, v in N.items()]
sdf = sum(r['sdf'] for r, _ in rows); npn = sum(v for _, v in rows); vm = sum(r['vendor_model'] for r, _ in rows)
print(f'{len(rows)} connections; total SDF {sdf:.2f} ns, vendor-model {vm:.2f}, nextpnr {npn:.2f} ({100*(npn/sdf-1):+.1f}%)')
ratio = [v / r['sdf'] for r, v in rows if r['sdf'] > 0.05]
print('nextpnr/SDF per connection: median %.3f  p10 %.3f  p90 %.3f' % (st.median(ratio), *[sorted(ratio)[int(len(ratio)*q)] for q in (0.1, 0.9)]))
ve = sorted(abs(r['vendor_model'] - r['sdf']) for r, _ in rows)
print('|vendor-model - SDF|: median %.4f p90 %.4f max %.4f' % (st.median(ve), ve[int(len(ve)*.9)], ve[-1]))
# error attribution by hop count
by = collections.defaultdict(list)
for r, v in rows:
    by[len(r['pips'])].append((r['sdf'], v))
for h in sorted(by):
    a = by[h]
    print(f'  {h:2d} pips: n={len(a):4d}  SDF mean {st.mean(x for x,_ in a):.3f}  nextpnr mean {st.mean(y for _,y in a):.3f}')
