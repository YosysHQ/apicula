---
name: nextpnr-qor-benchmarking
description: "Use when measuring or tuning nextpnr place-and-route QoR."
version: 0.1.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [nextpnr, himbaechel, gowin, ecp5, router1, router2, placer, timing, qor, benchmark]
    related_skills: [apicula-fuzzer-burndown, memory-safe-builds, software-design]
---

# nextpnr QoR benchmarking and tuning

## When to Use

- "Did change X increase rip-ups / route time / hurt Fmax?"
- Tuning a uarch's `estimateDelay`/`predictDelay`, rip-up penalty, router or placer
  choice (Gowin himbaechel especially; ECP5 is the reference arch to borrow from).
- Judging an old or closed placement/routing PR (rebase it into its own worktree and run
  it through the same matrix as the baseline).

Asked to "consider results from a previous session": search session history, the
rebased branches' commit messages and BACKLOG.md; if nothing measured exists, say so
plainly and measure.

## Procedure

1. **Pin down which change is meant before bisecting.** "Recent timing improvements"
   can be upstream nextpnr commits, Apicula chipdb data (`tm_parser`/`chipdb_builder`),
   or his *unmerged local patches* (e.g. `~/code/apicula/nextpnr-timing-patches/*.diff`).
   List all three axes; measure upstream first, then each local patch on top. A
   regression that isn't on main usually lives in a local patch. When the culprit is a
   local patch, say so by its path or branch (`nextpnr-timing-patches/<x>.diff`, local
   branch `timing-local`), never as "the X PR": he doesn't recognise unpushed work by a
   nickname, and a decision about it means nothing until he knows it's local. Also
   report the merged PRs he likely meant, with their measured effect.
2. **Worktrees, never his checkout.** `git -C ~/code/apicula-wt/nextpnr-main worktree add
   --detach ../nextpnr-<slug> <rev>` per variant (baseline main, old rev, each patch,
   tune). Apicula data per revision: `git worktree add --detach ~/code/apicula-wt/apicula-<slug> <rev>`
   then `GOWINHOME=~/bin/Gowin_V1.9.10.03_linux python -m apycula.chipdb_builder <dev>`
   (≈20 s for three devices). Old data = the last master commit before the timing work
   (`git rev-list -1 --before=<date> origin/master`).
3. **Build** with `scripts/build-npnr.sh <nextpnr-src> <apicula-src>` inside a
   `systemd-run --user --scope -p MemoryMax=…` (see memory-safe-builds). It sets
   `PYTHONPATH=<apicula-src>` so the chipdb generator reads that revision's msgpacks.
   Rebuilds are ~1–2 min (ccache). `BUILD_PYTHON=ON` when you need `--post-route` hooks.
   To try other *data* without recompiling C++, `--chipdb <file.bin>` overrides the db.
   **Split a chipdb-generator patch into its parts** the same way: copy `gowin_arch_gen.py`
   to `gowin_arch_gen_exp.py` with an env toggle that disables one part, run it with
   `PYTHONPATH=<apicula-src>:<npnr>/himbaechel/himbaechel_dbgen:<npnr>/himbaechel/uarch/gowin
   python gowin_arch_gen_exp.py -d <dev> -o chipdb-<dev>.bba`, then
   `<build>/bba/bbasm --le x.bba chipdb-<dev>.bin` and `bench.py --chipdb-dir <dir>`.
   Seconds per variant, so attribute a regression to each part before tuning anything.
4. **Benchmark designs** that actually stress routing (70–80 % LUT): N× picorv32 behind
   a shift-register/xor wrapper so only 3 pins are used (`templates/rvx.v`):
   N=3 for GW1N-9C, N=7 for GW2A-18C and GW5A-25A, synth with `synth_gowin -family
   gw1n|gw2a|gw5a` using `/usr/local/bin/yosys`. Devices/pins:
   - GW1N-9C `GW1NR-LV9QN88PC6/I5`, clk 52; GW2A-18C `GW2AR-LV18QN88C8/I7`, clk 4;
   - GW5A-25A `GW5A-LV25MG121NC1/I0`, clk **E2**.
   Put clk on a global-capable pin: otherwise the clock is routed in fabric
   (thousands of "Failed to route net … using dedicated routing" + hold errors) and the
   run measures nothing useful. Grep the first run's log for that warning.
5. **Run the matrix** with `scripts/bench.py <tag> <binary> [--seeds 1,2,3,4,5] [--designs …] [-j N] [-- extra args]`;
   it appends to `results.jsonl`; `scripts/summary.py results.jsonl tag1,tag2` prints mean
   rip-ups, route s, Fmax mean/min/sd. ≥5 seeds per cell: seed-to-seed sd is ~10–25 % on
   rip-ups and 3–6 % on Fmax, so single-seed comparisons mislead. ~2 threads per job,
   ≤ ~15 concurrent jobs on this box.
6. **Sweep knobs without rebuilding**: in a throwaway tune worktree read env vars in the
   uarch `init` (estimate/predict coefficients, `ctx->ripup_penalty`) and log them; drive
   per-family values with `scripts/sweep.sh`. Final code gets constants, never env vars.
7. **Calibrate from routed arcs** when fitting delay models: `--post-route
   scripts/arcdump.py` (env `ARCDUMP=out.jsonl`) dumps driver/sink loc+pin and
   `getNetinfoRouteDelay` per arc; fit medians per Manhattan distance /
   L1 regression of `c + m_near·Σmin(d,k) + m_far·Σmax(d−k,0)`. For the router's fast-mode
   view, temporarily skip `set_fast_pip_delays(false)` (env-guarded, experiment only).
8. **Explain a routing-effort change structurally** when a PR adds or reroutes a
   connection type: `--write routed.json` for baseline and variant (same seed) and run
   `scripts/pipcount.py routed.json` — it counts pip types from the nets' `ROUTING`
   attribute (pips are `XnYm/DST/SRC`), pass-through LUTs and LUT cells. Doubling of pips
   into a few-source wire (e.g. X0→SEL) names the bottleneck; quote those counts.
9. **Report** per item as bullets: metric deltas with the tag compared, what was rejected
   and why, next experiment. One decision at a time.

## Pitfalls

- **Fmax across timing-model versions is not comparable** — the delay model is the
  ruler. Compare rip-ups / iterations / route time across chipdb versions; compare Fmax
  only between variants sharing one model (or re-time both with the same STA).
- **himbaechel routes in fast-pip-delay mode**: the router and router-time STA ignore
  `drive_res*load_cap` (fanout), but node `cap` on the *destination* term still counts.
  So chipdb changes that add node cap (e.g. GW5A crossing classes) change routing;
  fanout-only changes don't. On Gowin fanout is ~3–5 % of routed arc delay.
- **Collapsing a vendor step function into nextpnr's linear fanout slope: use the vendor's
  low-fanout value, not a fitted one.** The GW5A vendor charges a per-load delay by load-count
  range (1–4 / 5–8 / 9–13, capped at 13); himbaechel has one `in_cap` slope per class. About
  96 % of routed connections sit on nets with 1–4 loads. A per-connection-weighted fit rounds
  to the 1–4 value anyway, while an n³-weighted fit lets the few big nets overcharge everyone and
  scores worse against the IDE's SDF. Take the 1–4 value directly, and note in the PR that big
  nets are undercharged and the router doesn't see the term. The exact step function would need
  a per-uarch delay override; leave that to a follow-up.
- **Himbaechel pip timing classes belong to the tile type, not the location.** A delay that depends on where a pip sits (e.g. GW5A loads past a crossing) needs tile types split by that signature, and tile types are ~99 % of a Gowin `.bba`. Count the split (distinct tile keys × pips) before promising "just more pip classes". Node classes are the only per-instance hook, and they can't tell a node's segments apart.
- **Cost generator-side options by what grows, not by class counts.** Classes are generated, so their number costs no code; the real costs are chipdb size, negative or odd delays the router sees, and diff size. Weigh those against the measured accuracy gain (from the reimplemented vendor model over the same routes). Pepijn's call: a few percent timing accuracy isn't worth a ~2× chipdb — prefer the simpler per-node charge and record the exact variant's numbers in the PR as the considered alternative.
- **A clock target only matters for `--tmg-ripup`.** Unconstrained, nextpnr times against
  12 MHz, so every slack is positive and `--tmg-ripup` rips up nothing. Heap placement and
  router1 use relative criticality: with `--freq` set, results were bit-identical
  (same rip-ups and Fmax per seed). So the unconstrained matrix is valid for those.
  On Gowin, `--tmg-ripup` with `--freq` gave +1–3 % Fmax for 2–8× route time
  (GW5A runaway: 475 k rip-ups).
- **Gowin supports only the heap and sa placers**: `--placer static` fails with "This uarch does
  not support the 'static' placer".
- **Rip-up count is deterministic per seed+binary**, route seconds are not (machine
  load); prefer rip-ups/iterations as the routing-effort metric.
- **router1 rip-up metric** = the last `IterCnt | w/ripup wo/ripup` row (cumulative);
  router1's default for himbaechel; `router/tmg_ripup` is off by default.
- **Don't assume a delay model calibrated to measured routes improves QoR.** A fitted
  Gowin `predictDelay` (with zero for dedicated F→D, MUX I0/I1, CIN) cut Fmax 7–9 % with
  heap placement; always A/B a model change on Fmax before adopting it.
- **Router estimate and rip-up penalty are tied to the delay scale** (ECP5 scales both
  with speed grade), but A/B before blaming them: on Gowin a fitted estimate changed
  nothing, and doubling the rip-up penalty cut rip-ups ~25 % at a ~7 % Fmax cost. A higher
  penalty trades QoR for effort; it is not a free fix for a rip-up regression.
- **router2 vs router1 on Gowin**: plain router2 routes 5–7× faster but loses ~20–25 %
  Fmax, because Gowin has many 0 ps pips (LUT_IN, SEL, DI). ECP5 fixed the same thing
  with a criticality-weighted epsilon in `Router2Cfg::get_base_cost`
  (`delay + 20·crit_weight·getDelayEpsilon()`); A/B that before judging router2. router2's
  log has no rip-up counter; compare route time and Fmax instead. Measured on Gowin: 20×
  is the best weight (5× ≈ plain, 50×/150× worse); router2+20× is still ~11 % below router1
  on Fmax at 7–10× less route time, so it is an opt-in fast mode at best, not a new default.
- **Route seconds are only comparable on an otherwise idle box.** With ~15 jobs running,
  wall/route time inflates 2–3×; judge effort on rip-ups and keep timing claims for a
  quiet rerun.
- **Gowin structural notes**: wire IDs sit at the node root (driving) tile, so
  `estimateDelay` sees no progress until the pip off a long wire; SEL inputs have 9
  sources (4 X0, 4 X2 taps from one axis only: even SELs E/W, odd N/S, plus VCC) vs 28
  on LUT inputs, and 0 ps delay in the model. Routing FF D via SEL (#505) costs 2.3–2.8×
  rip-ups at both 45 % and 76 % utilisation, and a per-tile cap on SEL-fed FFs doesn't
  help. So the cost is SEL access, not density or per-tile overload. Tile connectivity in
  `references/gowin-logic-tile.md`.
- **LUT/FF pairing is decided in placement, so steer it there.** By routing time the
  slice contents are fixed, and a fixed-path pip (e.g. SEL→XD) is the only way in. A
  delay on that pip makes STA honest but changes nothing about pairing; say so when
  someone proposes a router-side incentive. On heap, even a `predictDelay` penalty on
  DFF.D arcs not fed by their own LUT barely moved pairing, nor did a per-tile cap
  inside `slice_valid`: the legaliser packs by density, not timing. A real change
  needs the legaliser or a pack-time rule.
- **Read pip counts out of the chipdb before quoting them** (`load_chipdb(...).tiles[...]
  .pips[dst]`); counts recalled from memory or a single glance come out wrong, and the
  number goes straight into his mental model.
- **When he lacks a mental model of the hardware, draw it** rather than explaining in
  prose: Graphviz recipe in `references/gowin-logic-tile.md`.
- Pepijn has READ on YosysHQ/nextpnr, so he can't reopen a closed nextpnr PR; that needs
  gatecat or a maintainer. A closed apicula PR from a fork whose head conflicts and has
  "allow maintainer edits" off can be reopened but not updated: point to a rebased port
  branch. His unpushed timing work lives in per-issue worktrees `~/code/apicula-wt/nextpnr-<slug>`
  (branch names in `~/code/apicula-wt/BACKLOG.md`); older experiments are on local branch
  `timing-local` in `~/code/apicula/nextpnr` and in `~/code/apicula/nextpnr-timing-patches/`.
- Upstream etiquette (no agent PRs to nextpnr/Yosys; commits/pushes only to his fork on his
  say-so, Claude as co-author, he opens the PR) is in apicula-fuzzer-burndown's Pitfalls.
- **Standing bench workspace**: `~/code/apicula-wt/qor-bench` (designs, csts,
  `results.jsonl` with every tag measured so far, `patches/` with the env-knob experiment
  diffs for estimate/predict/ripup, router2 epsilon, and #505 SEL cap/penalty). Baseline
  build: `~/code/apicula-wt/nextpnr-qor` (main 60c30d6c) against `apicula-qor`. Reuse
  them; re-apply a knob diff to a fresh worktree instead of rewriting it.

## Support files

- `scripts/build-npnr.sh` — configure+build a gowin himbaechel tree against an apicula tree.
- `scripts/bench.py`, `scripts/summary.py`, `scripts/sweep.sh` — matrix runner, aggregation, per-family knob sweeps.
- `scripts/arcdump.py` — post-route per-arc delay dump for model fitting.
- `scripts/pipcount.py` — pip-type / pass-through-LUT counts from a routed json.
- `references/gowin-logic-tile.md` — LUT/FF/MUX/SEL connectivity, pass-through LUTs, how to draw the tile.
- `templates/rvx.v` — N×picorv32 3-pin benchmark wrapper (needs apicula `examples/attosoc/picorv32.v`).
