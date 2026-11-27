#!/usr/bin/env python3
"""Count pip types in nextpnr routed JSONs (from --write).

usage: pipcount.py routed.json [more.json ...]
Prints LUT cells, pass-through LUTs, and the most frequent DST<-SRC pip types
(wire names collapsed to their class prefix, e.g. X0, E26, SEL). Use it to show which
few-source wire a change concentrates traffic on.
"""
import json, re, sys
from collections import Counter


def cls(w):
    # SEL3 -> SEL, XD0 -> XD, X05 -> X0, E261 -> E26
    base = re.match(r"[A-Z]+", w)
    if base and base.group(0) in ("SEL", "XD", "A", "B", "C", "D", "CE", "LSR", "CLK", "F", "Q"):
        return base.group(0)
    m = re.match(r"[A-Z]+\d?\d?", w)
    return m.group(0)[:-1] if m and len(m.group(0)) > 2 else w


for f in sys.argv[1:]:
    top = json.load(open(f))["modules"]["top"]
    cells, nets = top["cells"], top["netnames"]
    pips = Counter()
    for v in nets.values():
        for p in v["attributes"].get("ROUTING", "").split(";")[1::3]:
            s = p.split("/")
            if len(s) >= 3:
                pips[f"{cls(s[1])}<-{cls(s[2])}"] += 1
    luts = sum(1 for c in cells.values() if c["type"].startswith("LUT"))
    pt = sum(1 for n in cells if "_passthrough_lut$" in n)
    print(f"{f}: LUT cells {luts}, pass-through LUTs {pt}")
    for k, n in pips.most_common(20):
        print(f"  {n:7d} {k}")
