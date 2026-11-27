#!/usr/bin/env python3
"""usage: summary.py [results.jsonl] [tag1,tag2,...] -- per tag/design means over seeds."""
import json, sys, statistics as st
from collections import defaultdict

rows = [json.loads(l) for l in open(sys.argv[1] if len(sys.argv) > 1 else "results.jsonl")]
tags = sys.argv[2].split(",") if len(sys.argv) > 2 else list(dict.fromkeys(r["tag"] for r in rows))
g = defaultdict(list)
for r in rows:
    g[r["tag"], r["design"]].append(r)
print(f"{'tag':16} {'design':8} {'n':>2} {'fail':>4} {'ripup':>8} {'rip sd':>7} {'route s':>8} {'fmax':>7} {'min':>7} {'sd':>5}")
for d in sorted({k[1] for k in g}):
    for t in tags:
        rs = g.get((t, d))
        if not rs:
            continue
        ok = [r for r in rs if r.get("ok") and "fmax" in r]
        if not ok:
            print(f"{t:16} {d:8} {len(rs):2} {len(rs):4} all failed")
            continue
        rip = [r.get("arcs_ripup", r.get("iters", 0)) for r in ok]
        fm = [r["fmax"] for r in ok]
        print(f"{t:16} {d:8} {len(rs):2} {len(rs) - len(ok):4} {st.mean(rip):8.0f} {st.pstdev(rip):7.0f} "
              f"{st.mean(r['route_s'] for r in ok):8.1f} {st.mean(fm):7.2f} {min(fm):7.2f} {st.pstdev(fm):5.2f}")
