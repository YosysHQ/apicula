# HIL test designs: anatomy, batching, packing

Read the design files before proposing a restructure: what looks like "a UART with
self tests" often carries a CPU.

## Layout (batched)

- `examples/hil.v` is the one design: test modules in `examples/hil/*.v`, an
  `` `ifdef HIL_<name> `` instance block and an `` `ifdef `` block of report rows per test
  (names with dashes become underscores in the define). It prints
  `<test> <row> = 0x<72-bit hex>` per row, then `--- tick ---`, then gives the DSPs one
  registered clock pulse, so the block after tick n shows n DSP clocks.
- `examples/Makefile`: `HIL_BATCH_<batch> := tests...` and `HIL_BATCHES_<board>` sit at the
  **top** of the file, because board prerequisite lists expand at parse time. A rule
  `hil-%.v: hil.v` writes a two-line wrapper (`` `define``s + `` `include "hil.v" ``), so the
  ordinary `%-<board>-synth.json: %.v` rules build batches for every board unchanged.
- `hil_tests = $(or $(HIL_BATCH_$(1)),$(1))`: an undefined batch name is a test name, so
  every test is a batch of one (`make hil-dsp-padd9-tangnano9k`) — the isolation path
  when a test poisons its batch.
- The expected output is the selected tests' `hil-references/<test>.txt`, compared after
  `sort` on both sides: every line names its test, so print order carries no meaning and
  batch lists need no fixed order.
- Whole-system tests (`femto-riscv-18-test`) keep their own bitstream and an explicit rule,
  which overrides the `hil-%-<board>` pattern.
- Mark the top `(* top *)`: the included modules of disabled tests are otherwise
  top-level candidates for yosys' auto-top.
- Drive a fabric-generated clock (the DSP tick pulse) straight from one flip-flop, never
  from an OR/compare of a counter: several counter bits change at once and the LUT output
  can glitch an extra edge, putting accumulators off by one depending on placement.
- Pause (~0.25 s from `` `CPU_FREQ ``) before each tick line. The capture starts after
  openFPGALoader exits and `dd` flushes what already arrived; without a pause a fast
  reporter can lose tick 1, and tests whose values depend on the absolute tick count
  (accumulators) then read one tick late.
- `.PRECIOUS` (and `.SECONDARY`) patterns only match when they equal an implicit rule's
  target pattern literally (`%-tangnano9k.fs`, not `hil-%.fs`); check with a throwaway
  makefile that a single-test `.fs` survives, since `make -n` cannot show it.
- `hil-<test>-<board>-unpacked.v` also matches the `hil-%.v` wrapper rule, so the
  Makefile gives the unpack targets explicit rules over a list of names. Take the test
  names from `hil.v`'s `` `ifdef HIL_<name> `` lines (`tr _ -`), not from `hil/*.v`
  basenames (one module file can serve several tests). Check from a clean tree: `make -n
  <board>-unpacked` must print no `printf '`define HIL_…_unpacked'` line.

## Adding a test

1. Module in `hil/`, instance + rows blocks in `hil.v` with the next free slot number.
   Test names are at most 20 characters (`row_name` is 8*20 bits; a longer name is cut
   from the front and the diff fails). The repo's `.gitignore` has `*.txt`: add a new or
   renamed reference with `git add -f`, and check `git show --stat` lists it (otherwise the
   commit silently drops it and CI fails on a missing reference).
   References are shared by every family that runs the test: a new pass bit in one
   family's branch breaks the others' reference, so add the check to all branches (and
   run it on every rig board) or make it a separate test.
2. Build it alone for each HIL board and capture on the bench (`scripts/hil-run.sh`).
   Check the values make sense (derive at least one by hand); a captured reference only
   proves "unchanged". Accumulating primitives (ACC/CASI modes) change with the tick
   count, so capture at the Makefile's `HIL_SETTLE`.
3. **Prove the test can fail before trusting its pass:** build a throwaway variant that
   expects a wrong value or a neighbouring configuration (another divider, another
   FREQ_DIV) and confirm the pass bit drops on the board. A self-check that never fails
   is decoration.
4. Put it in a batch and re-check that the batch still places (packing below), over
   several seeds — CI builds with a random seed.

Validity rules for self-checks:
- A tolerance must still exclude the neighbouring configurations at the measured
  offset, not just at nominal: with an RC oscillator measured ±6% and a ±10% window,
  FREQ_DIV 16 cannot be told from 14 or 18; pick a setting whose neighbours sit ≥20%
  away, and write the arithmetic in the comment.
- A status that must "stay high" (PLL LOCK) needs its own sticky monitor sampled every
  cycle; a window-based checker only samples it at window ends and misses drops between.
- Expected values come from fabric logic independent of the primitive (a regenerated
  pattern function, clk-ratio constants), and a sequencer that never finishes must leave
  a `done` bit clear.
- Hold/compare checks need data that actually differs: at narrow widths (1 bit) chosen
  addresses can share data, making the check vacuous; verify per width.
- A combinational reference for a primitive Yosys infers (a gate-level ripple adder next to
  `a + b` on ALUs) gets proven equal by synthesis (abc9) and the check folds to constant
  pass. Build the expectation sequentially (bit-serial adder in flip-flops, rotating
  truth-table register) and confirm with `synth_gowin -top <test>; stat` that the DUT
  primitives (ALU, MUX2_LUT8, ROM16...) and the reference flip-flops survive.

## Examples once a test covers them

Pepijn's rule: when a HIL test covers a primitive, delete the plain example (a blinky that
only shows off one primitive) and its orphaned helpers; keep only examples that are useful
demos for users. This includes examples built only for boards that are not on the rig:
port them too, so someone plugging in such a board runs a self-test instead of eyeballing
an example; non-HIL boards build the single-test bitstreams (build coverage, no bench run;
say "build-only" in the PR). Tests needing pins wait for the rig's loopback (phase 2,
`io-loopback-pins.md`). GW5A has a Tang Primer 25K (DirtyJTAG serial `7c3e8265f4b7`),
first on Pepijn's desk, later on the rig; the other GW5A boards are build-only (loader
board name `tangprimer25k`; the desk's openFPGALoader 0.12.1 lacks `--usb-serial-num`,
so wrap it to drop that flag while it is the only DirtyJTAG). Leave examples with nothing observable
(e.g. bandgap) and whole-system demos (CPUs, emcu) alone.

Tests with side effects that wear hardware (user flash erase/program) go in no batch:
note the run command in a Makefile comment and cap bench runs.

Porting a set of examples:
1. Survey first (delegate it, structured output): per example the primitives, boards,
   how it is observed, class (internal self-test / needs loopback / device without a HIL
   board / demo worth keeping), a self-test sketch, and files shared with others.
2. `examples/gw5a/` symlinks many example sources and its Makefile reads `../` files:
   when deleting, `git mv` the files gw5a needs into it (replacing the symlinks) and
   `make -n -C examples/gw5a` its targets.
3. Replace each deleted `<example>-<board>.fs` in the board lists and the `-unpacked`
   lists (CI's sanity check builds those) by `hil-<test>-<board>.fs`, then `make -n` all
   nine board targets and their `-unpacked` targets.
4. Build-only rules for small boards (`hil-%-<board>-synth.json` with `HIL_SMALL`) must
   still pass the board's defines (`OSC_TYPE_*`, `CPU_FREQ`, `NUM_HCLK`); other tests in
   the same build need them.
5. Run an independent review of the stacked diff (validity of each self-check first),
   then the full suite per board in the runner container.
6. Before the PR leaves draft, run a **coverage review** (`delegate_task(option="review")`,
   read-only): for every deleted example, list each non-default parameter, port mode and
   dynamic input it used (`git show <base>:examples/<dir>/<file>`), and find the test that
   both exercises it on that family *and* observes it. A primitive instantiated with the mode
   but not checked doesn't count, and the GW5A branch of a shared test is checked
   separately. Porters keep the headline configs and silently drop the rest (dynamic
   ADDSUB/CASISEL, pre-adder paths, SYNC reset, DCS SELFORCE, BEL-pinned region crossings).
   Deleting the example removes that coverage, so close the real gaps in the same PR. File the
   minor leftovers as one follow-up issue. The same review catches stale pins in `.cst` files
   and comments that cite the deleted examples.

Parallel porting by subagents: give each its own worktree off a common base, a disjoint
slot range and a batch-name prefix, and forbid `make hil-<board>` in the container (only
the locked `hil-run.sh`). Merging their branches conflicts as unions in `hil.v` and the
Makefile; a hunk boundary can swallow the shared `` `endif `` lines. After resolving, check
`` `ifdef `` depth returns to 0, that no `HIL_<test>` block nests inside another, and that
every line of each parent's `hil.v` survives (`sort -u | comm -23`), then build every
batch before the bench run.

## Clock tests

- Measure clocks with `hil/clock-meter.v`: a prescaler in the measured domain, its MSB
  synchronised into `clk`, edges counted per 2^WIN window; `hil_clock_check` skips the
  first window and keeps a sticky fail. Report pass masks; raw counts only under
  `` `define HIL_RAW `` (not in references). Derive expected counts from `` `CPU_FREQ ``.
- A `CLKDIV2` may only drive HCLK loads: measure the `CLKDIV` behind it. Gating tests
  (DQCE/DHCEN/DCS) switch CE/CLKSEL per window and check on- and off-windows separately.
- nextpnr runs out of global clock routing when `clkdiv` (one CLKDIV per HCLK) shares a
  batch with other clock tests, and crashes on `dhcen` next to `dqce` (router1 assert) or
  `dcs` (`dcs_bel != BelId()`). Build candidate batches over several seeds.
- GW5A: with many PLLA clocks on globals (plla + dcs, or all 7 PLLA outputs measured)
  nextpnr prints `Failed to route net <sysclk> ... using dedicated routing` and `routed
  using global resources partially`, builds fine, and the reporter's UART text comes out
  bit-garbled (or rows go missing) on the board. Grep every GW5A build log for
  `resources partially` before blaming hardware; keep PLL-heavy tests in their own
  batches (plla split into CLKOUT0-3 / 4-6 took it from ~1/6 builds to 0/20).

## Small devices and memory tests

- GW1N-1 / GW1NZ-1 (1152 LUT, 864 FF) cannot hold the reporter (~400 FF in the line
  buffer) next to a multi-configuration test; nextpnr fails placement at ~80% LUT on
  DFF control sets. Those boards only build the tests: `hil.v` has `HIL_SMALL` (no
  UART, rows folded into TXD) and the cst puts TXD on an LED, since nextpnr refuses
  an unconstrained TXD.
- For BSRAM-like tests, generate INIT contents with a constant function of the word
  index (`init_row()` calling `pat()`), and compute the expected read in fabric from
  the same `pat()`; one first-failure capture under a debug define
  (`BSRAM_DEBUG`: cat, address, data) turns a bad pass bit into a diagnosis in one load.
- A result can depend on the bitstream loaded before (seen: 32/36-bit pROM word 0 after
  another BSRAM design). When a failure does not repeat, reload the same .fs after a
  different design before calling it placement-dependent.

## Packing batches: measure, don't count

- Yosys `stat` gives primitive counts in seconds, and the nextpnr utilisation report
  lists each DSP type against its own total, but those types share physical sites: the
  real budget is DSP macros (GW1N-9: 5, GW2A-18: 12, = MULT36X36 capacity).
- Capacity is not the limit in practice: nextpnr places far fewer chained DSP tests
  together than the macros hold, and pairwise compatibility does not predict triples.
  Find batches with `scripts/hil-pack.py BOARD greedy <tests, largest first>` and probe
  alternatives with `hil-pack.py BOARD try "a b" "c d"`; each build takes seconds.
- A big case-table mux of all rows costs ~25 LUT per 72-bit row; a single test is
  ~300 LUT without the old CPU (~750).

## Placement-dependent results

`NEXTPNR_FLAGS` contains `-r` (random seed): every build places differently, so a test
that passes alone or on the bench can fail inside a batch, or in one CI run. When a
result flips:

1. If CI found it, download the run's `examples-<name>-<board>` artifact and load that
   exact `.fs` 2-3 times: a repeat means the bitstream, not the bench. Then load the
   run's **other** toolchain artifact (dev vs stable) and a local build: a fault only in
   dev, with the same values across runs, is a toolchain regression, not placement (see
   SKILL.md "Split toolchain from hardware"). CI keeps only the `.fs`, so its placement
   is lost — find a failing placement locally.
2. Rebuild with fixed seeds, `NEXTPNR_FLAGS="--timing-allow-fail --seed N"` per target
   (a throwaway makefile that `include`s the Makefile and sets target-specific
   `NEXTPNR_FLAGS` and `HIL_BATCH_*` builds 8 seeds in parallel without name clashes);
   shrink the batch to the failing tests first so seeds explore their sites.
3. Run each on the bench and tabulate pass/fail per seed.
4. Read placements from the nextpnr JSON: `cells[<inst>].attributes.NEXTPNR_BEL`
   (e.g. `X10Y18/MULT18X1811`, the last two digits being macro/slot; BSRAM bels end in
   `/BSRAM`). Tabulate the failing configuration's site per seed: a fault that follows
   one site (or one link, e.g. a cascade crossing a DSP macro boundary) and other
   configurations passing at that same site name the feature that is mis-mapped there.
5. Compare across device families before generalising; the same crossing can work on one.

6. **Pin and bisect instead of sweeping.** A site that 40 random seeds never hit is reached by adding
   `attributes.BEL = "X28Y9/BSRAM"` to the cell in the synth JSON. Run the vendor on the *same* Yosys
   netlist, pinned with `INS_LOC "<cell>" BSRAM_R<row+1>[n]`: `read_json; splitnets; write_verilog -noattr
   -noexpr -decimal -defparam`, then rewrite BSRAM params as `BIT_WIDTH = 18;` / `N'b…` (the IDE rejects
   Yosys' `N'h` literals with PA1002 and silently uses defaults); `set_device -name GW2AR-18C GW2AR-LV18QN88C8/I7`.
   Vendor passes → bisect Apicula's bitstream: repack the same nextpnr JSON with function fuses changed,
   or with single wires dropped from a net's `ROUTING` (wire;pip;strength triples). Scripts:
   `~/code/apicula-wt/fix-dp16-site-evidence/sweep/` (pin2.py, vendor.sh, unroute.py, pindrv.py, tilediff.py).
   Pick the most specific pip when decoding (pip fuse sets nest). Found this way: nextpnr routing GND to
   unused BSRAM AD[3:2] broke 18-bit byte enables at GW2A X28Y9; the vendor leaves them unrouted.

An isolated test landing in a lucky spot is not proof the primitive works: file the
placement bug with the seed/site table and keep the affected test in its own batch only
as a stopgap. Site faults that can land anywhere cannot be batched around; whether HIL
builds should pin a seed is the owner's call, not a silent fix.

**Build-only boards gate every bench run.** The `hil` job `needs: [example]`, so one
build-only target that fails to route (the 60K/138K boards, random seed) skips HIL on
every real board, and the run looks like a toolchain red. When a CI run shows
`hil: skipped`, read the `example` job failures first. Before pushing a PR that adds
build-only targets, build each one over 5+ seeds. A target that routes only on some
seeds is a nextpnr bug to diagnose (apicula-fuzzer-burndown `references/fuzzer-evidence.md`,
"Diagnosing a nextpnr Failed to find a route") and to fix upstream. Until that lands, the
stopgap is a fixed `--seed` for the build-only boards only (rig boards keep `-r`), named
in the PR: pick it by sweeping seeds 1-5 over all build-only targets with both the local
nextpnr and CI's `tools-dev` artifact (Ubuntu binaries: run them in an `ubuntu:24.04`
container with the boost 1.83 libs, tools mounted at /usr/local). Drop the fixed seed once
the nextpnr fix is in main.

## Known-broken tests

Mechanism (in the Makefile): a test that fails on a board because of a known bug leaves
that board's `HIL_BATCH_*` lists for `HIL_BROKEN_<board>`, with the issue named in a
comment above it. Its reference keeps the *correct* value. `make hil-<board>-broken` runs
each alone and prints XFAIL/XPASS without failing; on XPASS, move the name back into a
batch (no `hil.v` edit). A `*-bugs` test that now passes also drops the suffix: rename the
`` `ifdef HIL_* ``, wire, instance and `ROW` strings in `hil.v`, the comment in its module,
and the reference file (contents too, `git add -f`), then run the whole batch it joins on
the rig, since an extra test can change placement. A load or rig failure also prints XFAIL, so read the output
above the verdict.
- File the issue first, so the list entry can name it.
- A whole test leaves the batch, taking its healthy configurations with it. Split a
  failing configuration into a `*-bugs` test in `hil.v` only when the rest is worth
  keeping in CI; `*-bugs` tests go on the broken list like any other. Configurations
  are shared by all boards, so a split for one board's fault needs its own test.
- Never put observed (wrong) values in references: they encode the bug and flake for
  placement-dependent faults.
- Never mark a toolchain-main regression broken: catching it is the HIL's job — report or
  fix it upstream instead.
Tests that were never run on a board (bridge offline while writing them) count as
unverified there, not passing: run every new batch on every rig board before the PR
claims it.
