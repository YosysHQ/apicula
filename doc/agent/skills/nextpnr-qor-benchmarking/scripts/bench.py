#!/usr/bin/env python3
"""Run nextpnr on the benchmark matrix and collect router/timing metrics.

usage: bench.py <tag> <binary> [--chipdb-dir DIR] [--seeds 1,2,3] [--designs a,b] [-j N] [-- extra args]
Run from the bench dir (holds the synthesized JSONs and .cst files). Appends to results.jsonl.
Env vars (knobs) are inherited by nextpnr.
"""
import argparse, json, re, subprocess, os, time
from concurrent.futures import ThreadPoolExecutor

HERE = os.getcwd()
DESIGNS = {
    "rv3-9c": ("rv3-gw1n.json", "GW1NR-LV9QN88PC6/I5", "GW1N-9C", "gw1n.cst"),
    "rv7-2a": ("rv7-gw2a.json", "GW2AR-LV18QN88C8/I7", "GW2A-18C", "gw2a.cst"),
    "rv4-2a": ("rv4-gw2a.json", "GW2AR-LV18QN88C8/I7", "GW2A-18C", "gw2a.cst"),  # 45 % LUTs: utilisation control
    "rv7-5a": ("rv7-gw5a.json", "GW5A-LV25MG121NC1/I0", "GW5A-25A", "gw5a.cst"),
}
ROUTER1_ROW = re.compile(r"Info:\s+(\d+) \|\s+(\d+)\s+(\d+) \|\s+-?\d+\s+-?\d+ \|\s+(\d+)\|\s+[\d.]+\s+([\d.]+)\|")
ROUTER2_ITER = re.compile(r"iter=(\d+) wires=(\d+) overused=(\d+) overuse=(\d+)")
FMAX = re.compile(r"Max frequency for clock\s+'([^']+)': ([\d.]+) MHz")


def parse(log):
    m = {}
    rows = ROUTER1_ROW.findall(log)
    if rows:
        it, wr, wor, _, t = rows[-1]
        m.update(router="router1", iters=int(it), arcs_ripup=int(wr), arcs_noripup=int(wor), route_s=float(t))
    its = ROUTER2_ITER.findall(log)
    if its:
        m.update(router="router2", iters=int(its[-1][0]), wires=int(its[-1][1]))
        t = re.findall(r"Router2 time ([\d.]+)s", log)
        if t:
            m["route_s"] = float(t[-1])
    f = FMAX.findall(log)
    if f:
        m["fmax"] = float(f[-1][1])  # last report = post-route
    m["ok"] = "Program finished normally" in log
    return m


def run(tag, binary, chipdb_dir, design, seed, extra):
    js, dev, fam, cst = DESIGNS[design]
    out = os.path.join(HERE, "runs", tag)
    os.makedirs(out, exist_ok=True)
    logf = os.path.join(out, f"{design}-s{seed}.log")
    cmd = [binary, "--json", os.path.join(HERE, js), "--device", dev, "--vopt", f"family={fam}",
           "--vopt", f"cst={os.path.join(HERE, cst)}", "--seed", str(seed), "--threads", "2", "--log", logf] + extra
    if chipdb_dir:
        cmd += ["--chipdb", os.path.join(chipdb_dir, f"chipdb-{fam}.bin")]
    t0 = time.time()
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
    log = open(logf).read() if os.path.exists(logf) else p.stdout + p.stderr
    m = parse(log)
    m.update(tag=tag, design=design, seed=seed, wall_s=round(time.time() - t0, 1), rc=p.returncode, extra=extra)
    with open(os.path.join(HERE, "results.jsonl"), "a") as f:
        f.write(json.dumps(m) + "\n")
    return m


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("tag"); ap.add_argument("binary")
    ap.add_argument("--chipdb-dir")
    ap.add_argument("--seeds", default="1,2,3,4,5")
    ap.add_argument("--designs", default="rv3-9c,rv7-2a,rv7-5a")
    ap.add_argument("-j", type=int, default=6)
    ap.add_argument("extra", nargs="*")
    a = ap.parse_args()
    jobs = [(d, int(s)) for d in a.designs.split(",") for s in a.seeds.split(",")]
    with ThreadPoolExecutor(a.j) as ex:
        for m in ex.map(lambda j: run(a.tag, a.binary, a.chipdb_dir, j[0], j[1], a.extra), jobs):
            print(json.dumps(m), flush=True)


if __name__ == "__main__":
    main()
