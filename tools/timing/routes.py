"""Rebuild vendor routes from its bitstream and evaluate the IDE 1.9.10.03 old TmModel wire formula.

routes.py DEVICE SPEED IMPL_PNR_DIR VPIPS.json OUT.json

Model (STA::TmModel::getWiresDlyNew, FanoutTmModel::addWiresFanoutDly): a connection's delay is
the sum, over every routing node from the net root to the sink, of
    base(node type) + n_used_out_edges(node) * Fan(type) / FanNum(type)
Nodes in the outermost rows and columns contribute nothing.
"""
import importlib.resources, json, re, sys
from collections import defaultdict
from apycula import chipdb
from apycula.chipdb import load_chipdb

dev, speed, pnr, vp, out = sys.argv[1:6]
with importlib.resources.path('apycula', f'{dev}.msgpack.xz') as p:
    db = load_chipdb(p)
tm = db.timing[speed]
W, F = tm['wire'], tm['fanout']

def vtype(w):
    """Vendor NODE_TYPE for a tile-local wire name."""
    if re.fullmatch(r'F\d', w): return 'LUTOUT'
    if re.fullmatch(r'Q\d', w): return 'REGOUT'
    if re.fullmatch(r'OF\d', w): return 'OF'
    if re.fullmatch(r'X0\d', w): return 'X0'
    if re.fullmatch(r'[ABCD]\d', w): return 'LUTIN'
    if re.fullmatch(r'(SN|EW)[12]0', w): return 'X1_0'
    m = re.fullmatch(r'[NESW]([128])\d(\d)', w)
    if m:
        l, s = m[1], int(m[2])
        if l == '1': return 'X1_0' if s == 0 else 'X1_1'
        if l == '2': return f'X2_{s}'
        return {0: 'X8_0', 4: 'X8_1', 8: 'X8_2'}[s]
    if re.fullmatch(r'(CLK|LSR|CE|SEL)\d', w): return 'CTL'
    return 'OTHER:' + re.sub(r'\d+', '#', w)

ZERO = [0.0] * 4
def fan(key, n):
    return [n * v / F[key + 'Num'] for v in F[key]]
def node_delay(t, n):
    """Quad delay of one node with n used outgoing edges (vendor formula)."""
    add = lambda a, b: [x + y for x, y in zip(a, b)]
    if t == 'X0':     return add(W['X0'], fan('X0Fan', n))
    if t == 'X1_0':   return add(W['FX1'], fan('X1Fan', n))
    if t == 'X1_1':   return fan('X1Fan', n)
    if t == 'X2_0':   return add(W['X2'], fan('X2Fan', n))
    if t in ('X2_1', 'X2_2'): return fan('X2Fan', n)
    if t == 'X8_0':   return list(W['X8'])
    if t in ('X8_1', 'X8_2'): return fan('X8Fan', n)
    if t == 'LUTOUT': return fan('FFan', n)
    if t == 'REGOUT': return fan('QFan', n)
    if t == 'OF':     return fan('OFFan', n)
    if t == 'LUTIN':  return list(W['ISB'])
    return ZERO

# used pips: tile-local nodes (row, col, wire), zero-based
V = json.load(open(vp))
down = defaultdict(list)
for name in V['pips'] + V['clock_pips']:
    m = re.fullmatch(r'X(\d+)Y(\d+)/([^/]+)/([^/]+)', name)
    c, r, d, s = int(m[1]), int(m[2]), m[3], m[4]
    down[(r, c, s)].append(((r, c, d), name))

def glob(n):
    r, c, w = n
    return chipdb.wire2global(r + 1, c + 1, db, w)
# segments of the same physical wire, by global name
alias = defaultdict(set)
for (r, c, s), lst in list(down.items()):
    alias[glob((r, c, s))].add((r, c, s))
    for (dn, _) in lst:
        alias[glob(dn)].add(dn)
# SN/EW centre wires: N1x1 one row up and S1x1 one row down are taps of SNx0 (as in gowin_unpack)
for (r, c, w) in [n for v in alias.values() for n in v]:
    m = re.fullmatch(r'([NSEW])1([12])1', w)
    if m:
        d, i = m[1], m[2]
        dr, dc = {'N': (1, 0), 'S': (-1, 0), 'W': (0, 1), 'E': (0, -1)}[d]
        centre = (r + dr, c + dc, f"{'SN' if d in 'NS' else 'EW'}{i}0")
        alias[glob(centre)].add((r, c, w)); alias[glob(centre)].add(centre)
        alias[glob((r, c, w))].add(centre)

def seg_index(w):
    m = re.fullmatch(r'[NESW][128]\d(\d)', w)
    return int(m[1]) if m else 0

def is_edge(n):
    r, c, _ = n
    return r == 0 or c == 0 or r == db.rows - 1 or c == db.cols - 1

def trace(src):
    """DFS over used pips. Returns parent map node -> (prev_node, pip_name or None)."""
    parent = {src: (None, None)}
    stack = [src]
    while stack:
        n = stack.pop()
        nxt = [(d, p) for d, p in down.get(n, [])]
        nxt += [(a, None) for a in alias.get(glob(n), ()) if a != n]
        for d, p in nxt:
            if d not in parent:
                parent[d] = (n, p)
                stack.append(d)
    return parent

def nused(n):
    return len(down.get(n, []))

def path_to(parent, sink):
    nodes, pips = [], []
    n = sink
    while n is not None:
        nodes.append(n)
        prev, p = parent[n]
        if p: pips.append(p)
        n = prev
    return nodes[::-1], pips[::-1]

def vendor_delay(nodes):
    """Sum node delays; for a physical wire include all segments up to the exit tap."""
    tot = [0.0] * 4
    seen = set()
    i = 0
    while i < len(nodes):
        n = nodes[i]
        # collapse alias runs (segments of one physical wire)
        j = i
        while j + 1 < len(nodes) and glob(nodes[j + 1]) == glob(n):
            j += 1
        segs = nodes[i:j + 1]
        exitseg = max(seg_index(s[2]) for s in segs)
        phys = sorted(alias.get(glob(n), {n}) | set(segs), key=lambda s: seg_index(s[2]))
        for s in phys:
            if seg_index(s[2]) > exitseg:
                continue
            if s[2].startswith(('SN', 'EW')) or re.fullmatch(r'[NSEW]1[12]1', s[2]):
                # centre wire: only the centre and the taps on the path
                if s not in segs and not s[2].startswith(('SN', 'EW')):
                    continue
            if is_edge(s) or s in seen:
                continue
            seen.add(s)
            tot = [a + b for a, b in zip(tot, node_delay(vtype(s[2]), nused(s)))]
        i = j + 1
    return tot

# instance locations from the text timing report
loc = {}
for line in open(f'{pnr}/syn.tr'):
    m = re.match(r'\s+[\d.]+\s+[-\d.]+\s+t\w+\s+\w*\s+\d+\s+(R\d+C\d+\[\d\]\[[AB]\])\s+(\S+)/(\w+)\s*$', line)
    if m:
        loc[m[2]] = m[1]

def parse_loc(s):
    m = re.fullmatch(r'R(\d+)C(\d+)\[(\d)\]\[([AB])\]', s)
    r, c, sl, ab = int(m[1]) - 1, int(m[2]) - 1, int(m[3]), m[4]
    return r, c, sl, 2 * sl + (ab == 'B')

SRC = {'F': 'F', 'Q': 'Q', 'O': 'OF', 'SUM': 'F'}
def sink_cands(pin, sl, n):
    if re.fullmatch(r'I\d', pin): return [f'{x}{n}' for x in 'ABCD'] + [f'SEL{n}']
    if pin == 'S0': return [f'SEL{n}']
    if pin == 'D': return [f'{x}{n}' for x in 'ABCD'] + [f'XD{n}']
    if pin == 'CE': return [f'CE{sl}']
    if pin == 'CLK': return [f'CLK{sl}']
    if pin in ('RESET', 'SET', 'CLEAR', 'PRESET'): return [f'LSR{sl}']
    return []

res, skipped = [], defaultdict(int)
traces = {}
for line in open(f'{pnr}/syn.sdf'):
    m = re.search(r'\(INTERCONNECT (\S+)/(\w+) (\S+)/(\w+) \(([\d.]+):([\d.]+):([\d.]+)\)\)', line)
    if not m:
        continue
    si, sp, di, dp = m[1].replace('\\', ''), m[2], m[3].replace('\\', ''), m[4]
    sdf = float(m[7])
    if si not in loc or di not in loc:
        skipped['no loc'] += 1; continue
    if sp not in SRC:
        skipped[f'src pin {sp}'] += 1; continue
    sr, sc, ssl, sn = parse_loc(loc[si])
    dr, dc, dsl, dn = parse_loc(loc[di])
    src = (sr, sc, f'{SRC[sp]}{sn}')
    if src not in traces:
        traces[src] = trace(src)
    par = traces[src]
    cands = [(dr, dc, w) for w in sink_cands(dp, dsl, dn) if (dr, dc, w) in par]
    if not cands:
        skipped[f'sink not reached ({dp})'] += 1; continue
    best = None
    for cnd in cands:
        nodes, pips = path_to(par, cnd)
        if pips and (best is None or len(pips) < len(best[1])):
            best = (nodes, pips)
    if best is None:
        skipped['no pips'] += 1; continue
    nodes, pips = best
    vd = vendor_delay(nodes)
    sw = nodes[-1][2]
    if dp == 'D' and sw[0] in 'ABCD':
        # STA::TmAnalyzer::addLutBufDelay: D reached through the LUT, add LutIn_F for that input
        vd = [a + b for a, b in zip(vd, tm['lut'][sw[0].lower() + '_f'])]
    res.append(dict(src=f'{si}/{sp}', dst=f'{di}/{dp}', sdf=sdf, vendor_model=max(vd[2], vd[3]),
                    nodes=[f'X{c}Y{r}/{w}:{vtype(w)}:{nused((r, c, w))}' for r, c, w in nodes], pips=pips,
                    net_pips=sorted({p for n in par for p in [par[n][1]] if p})))
json.dump(res, open(out, 'w'))
print(len(res), 'connections;', dict(skipped))
err = [r['vendor_model'] - r['sdf'] for r in res]
exact = sum(abs(e) < 0.0015 for e in err)
print(f'vendor model reproduces SDF max within 1.5 ps: {exact}/{len(err)}')
others = defaultdict(int)
for r in res:
    for n in r['nodes']:
        if ':OTHER' in n: others[n.split(':')[1]] += 1
print('unclassified node kinds on paths:', dict(others))
