"""nextpnr --pre-pack script: nextpnr's routing delay for vendor routes.

    ROUTES_DIR=dir nextpnr-himbaechel --device ... --json any.json --pre-pack npnr_eval.py

Reads ROUTES_DIR/routes.json (from routes.py), binds each vendor net's pips so
nextpnr's fanout terms see the real load, sums getPipDelay along every
connection and writes ROUTES_DIR/npnr_delays.json. Exits before packing.
"""
import collections
import json
import os

d = os.environ['ROUTES_DIR']
R = json.load(open(f'{d}/routes.json'))
by_net = collections.defaultdict(list)
for i, r in enumerate(R):
    by_net[tuple(r['net_pips'])].append(i)
out, missing = {}, collections.Counter()
for k, (pips, idxs) in enumerate(by_net.items()):
    net = ctx.createNet(f'vendor_net{k}')
    src = ctx.getPipSrcWire(R[idxs[0]]['pips'][0])
    ctx.bindWire(src, net, STRENGTH_WEAK)
    bound = []
    for p in pips:
        try:
            ctx.bindPip(p, net, STRENGTH_WEAK)
            bound.append(p)
        except Exception:
            missing[p.split('/', 1)[1]] += 1
    for i in idxs:
        out[i] = sum(ctx.getPipDelay(p).maxDelay() for p in R[i]['pips']) / 1000.0
    for p in bound:
        ctx.unbindPip(p)
    ctx.unbindWire(src)
json.dump(out, open(f'{d}/npnr_delays.json', 'w'))
with open(f'{d}/npnr_eval.log', 'w') as f:
    print('evaluated', len(out), 'connections; pips nextpnr does not have:', dict(missing), file=f)
os._exit(0)
