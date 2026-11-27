# Fuzzer evidence: finding the real cause and proving a fix

Read this when designing or reviewing a fix, triaging a new red, or proving a nextpnr change.

## Reading the failure
- **Diff line format:** `tile: (row, col) vendor=V apicula=A <bel>: <row> | <alt rows>`. The alternatives after `|` are other table rows that use the same fuse. The first row is a guess at which feature it is, not a decode.
- **The log shows only a sample of the failing cases, and truncates long parameter dicts.** Don't claim from the log alone which parameter value triggers a diff (which `READ_MODE`). Make that the card's first investigation step, using `results.json` from the CI artifact (`fuzz-<device>`) or a `--replay`.
- **`BROKEN` needs no per-device split.** `test_primitive` only xfails where the primitive actually fails, so a fixed device reports a pass while the entry stays in for another device. Remove the entry only when every device passes; otherwise update its reason string.
- **Value is what Yosys actually infers.** Check the parameters in `techlibs`/`brams_map.v` before ranking. Inferred SDPB uses `READ_MODE=0`, so a `READ_MODE=1` bug only hits hand-instantiated RAMs.

## Not every mismatch is an Apicula bug
The design stage rules out three other causes first.
- **Harness artefacts.** The fuzzer leaves data inputs undriven, and the vendor constant-folds them (e.g. an SSRAM `WRE` folded into the LSR mux rows). Undriven control nets also trigger vendor workarounds. Test by driving the input from a pin in an edited vendor netlist. The fix then goes in the fuzzer's kind (`source()`), not in `gowin_pack`.
- **Check the chipdb before calling it a nextpnr gap.** nextpnr can only route what Apicula's chipdb describes. When nextpnr takes general routing where the vendor uses a dedicated path, first check whether the chipdb has that path's nodes (e.g. `gw5_make_pin_to_hclk` described one of four GW5A HCLK-pair pins). If it's missing, the fix is an Apicula chipdb chain, not a nextpnr card. Control: a pin whose path *is* described should take it.
- **nextpnr gaps.** nextpnr may have the vendor's workaround but not call it for every primitive (`bsram_fix_outreg` for SP/DP but not SDPB). That becomes a nextpnr design card, and the `BROKEN` entry stays with an updated reason.
- **A neighbour's known bug.** The harness attributes fuses per tile, so another primitive's broken rows in a shared block land on its neighbour (e.g. MULT9X9's `AIRMUX`/`BIRMUX` in a DSP block). A primitive that passes alone but fails after a reshuffle usually has this. If the failing rows belong to an already-xfailed primitive, the `BROKEN` reason points at that root cause, marked inferred, not at a generic "combination bug".
- **A different DSP pair within the macro.** The `Dsp` kind pins only the macro (`DSP_R<row>[n][A]`), so the vendor and nextpnr can configure different pairs. It shows as whole-cell rows swapped between pairs (vendor `PRAD0*`/`AIRMUX0*`, Apicula `PRAD1*`/`AIRMUX1*`). That's a harness/placement difference, not a pack bug: give it a `BROKEN` reason saying so, and don't call it fixed by a DSP default fix until CI ran on top.

## Pinning DSP slots in a hand-made vendor run
- `INS_LOC "<inst>" R<row>C<col>[<macro>][A|B];` (the format the `.posp` prints) pins a GW1N/GW2A DSP primitive to one 18-bit slot. The fuzzer's `DSP_R<row>[n][A]` pins only the macro. A refused pin shows up as `CT1094` and a `PLACE_` instead of a `CST_` line in the `.posp` (`set_option -gen_posp 1`). For example, the vendor never puts a MULT18X18 SOA-chain head in slot B, even in an empty macro.
- The vendor netlist must be bit-blasted (1-bit wires in concatenations; a `wire [17:0]` on a port gets PA2060), and its pads need `IO_PORT … IO_TYPE=` (CT1136 otherwise). Tie the bus inputs to `gnd`. Undriven bus inputs leave hundreds of unrouted nets and no `.fs`.
- To decode the DSP rows per macro from any `.fs`, call `parse_attrvals(tile, db.rev_logicinfo('DSP'), db.shortval[ttyp][f'DSP{idx}'], attrids.dsp_attrids, 'DSP')` for each tile that has a `DSP*` bel. Then diff the vendor's and Apicula's lists for the same placement. A HIL failure in a DSP chain can come from a neighbour's per-macro row (#644: a PADD's `MATCH` redirected a MULT18X18 chain's shift-out). Check which cells share the failing cell's macro before you blame the chain or the placement.

## Default bugs (the fuzzer sets every parameter, so it can't see them)
1. Statically check every `parms.get(NAME, default)` in `gowin_pack.py` against primitive.xml's `INIT_VAL`. The GW1N/GW2A file is `$GOWINHOME/IDE/bin/primitive.xml`, and GW5A has its own at `IDE/bin/prim_syns/gw5a/primitive.xml`. Find a primitive with `grep -n '<name>SDPB</name>'`, then read `<PARAMETER ...>NAME<INIT_VAL>` below it.
2. Confirm Yosys/nextpnr pass only explicit parameters into the JSON, so `gowin_pack`'s default is what decides.
3. `--replay` each suspect as a pair against the vendor: the parameter omitted, and set explicitly to the XML default. A difference between the two is a default bug, and the pairs are its regression evidence.

Defaults can depend on the primitive. A shared default flipped for cells that lack the parameter (ODDR, `*_EMPTY`) is wrong for the cells that have it.

## Draw-changing changes
- **Ship fixes that don't change fuzzer draws separately from changes that do.** A new case strategy (e.g. omitting parameters) or a new harness pinout reshuffles every Hypothesis draw at the CI seed. That invalidates the CI evidence of every open fuzzer PR. Land the one-word fixes now, proven by replays. Park the draw-changing PR and merge it last, rebased, so it absorbs the reshuffle once.
- **A harness change needs the full suite before and after on every device**, not only the targeted run. The CI seed reshuffles on all of them, and moved pins can break primitives the targeted run never touched: a clock-side routing gap in nextpnr, or a special pin pool such as MIPI's only output pair.
  - Choose harness pins by a rule from chipdb data: skip locked banks, prefer clock-capable pins, keep special pools free. Never hard-code a pin.
  - A clock rule must also avoid dual-purpose clock pins (e.g. PLL inputs). Prefer rules that leave the other devices' pins where they were.
- **GW1N-9C pin facts (measured):**
  - Bank 3 is locked by the in-package PSRAM.
  - `mipi_ibuf` tiles sit in bank 1 and `mipi_obuf` in bank 2. Only the out_pad's bank matters to MIPI: the vendor fails MIPI buffers (PR1082) in the bank that holds it; harness inputs are harmless.
  - With a GCLKC clock, DHCEN routes via BRGMUX at the vendor but via HSBMUX in Apicula. Use a GCLKT pin.
- **Filtering pins out of the harness can starve a small package.** GW1NS-4 QFN48P (banks 0/3 SiP-locked, bank 2 MIPI) has 6 plain pins left; a filter left one harness input. Sort unwanted banks last instead of filtering, and print `pick_pins` for every device in `DEVICES` before and after.

## Fuzzing the devices CI doesn't run
CI fuzzes GW1N-9C, GW2A-18C, GW5A-25A only; the baseline nextpnr build has chipdbs for those (and GW1N-1). For the others:
- Build a chipdb from the worktree: `PYTHONPATH=<worktree> python nextpnr-main/himbaechel/uarch/gowin/gowin_arch_gen.py -d <dev> -o x.bba && nextpnr-main/build/bba/bbasm --l x.bba x.bin`, and point `NEXTPNR` at a wrapper that adds `--chipdb $CHIPDB_BIN`.
- The full suite doesn't run everywhere (IDE 1.9.10.03 tree, Nov 2026): `allocate` loops forever when a shared kind has cases but no sites (GW1NS-4 `PLL`/`rPLL`, GW1NZ-1 DSP), GW5AT-60B crashes in `pll_dividers` (no `PLL_LIMITS` entry), GW5AST-138C has no `GCLK*` pin so `pick_pins` raises. Use `tiled_fuzzer.py --prims <all but those> -n 2 --seed 7` (the suite's defaults) instead, before and after.

## GW5A family reach
Base-class (`Device`) changes in `gowin_pack.py`/`gowin_unpack.py` reach the whole GW5A family. GW5AT-60B and GW5AST-138C inherit the `Device` handlers; only GW5A-25A overrides some of them (I/O logic), and nothing overrides e.g. `get_SDP_fuses`.
- **Measure GW5A; don't scope it away** (Pepijn: "ehh so check them for gw5a?"). "GW5A keeps the parent's output" only proves nothing changed, not that GW5A is right. The parent's GW5A code was often measured wrong (I/O logic LSR rows). Check the rule on GW5A-25A with vendor runs and vendor code. Scoping to GW1N/GW2A (`is_GW5_family`, or an emptied class attribute) is a stopgap that needs an explicit follow-up, not the default.
- GW5A vendor bitstreams can be decoded even where nextpnr can't place the primitive, and also for GW5AST-138C. GW5AT-60B decode is unreliable (bslib reads 917 rows, the chipdb has 918).
- **GW5AT-60B/GW5AST-138C clocks (Nov 2026):** their chipdbs have no GW5 HCLK network (`fse_create_hclk_nodes` and the `gw5_*` helpers are GW5A-25A only), so any FCLK user (OSER/IDES/VIDEO) is unroutable. ODDR/IDDR on PCLK route fine. 138C also has a single BUFG that most pins can't reach, so even a plain DFF clocked from those pins fails; `--vopt disable_gp_clock_routing` works around it. nextpnr turns both into crashes (`dict::at()`, a router1 assert) rather than errors. CI's 60B/138C examples have no I/O logic and use a working clock pin, so CI can't see any of this.
- **GW5A I/O logic LSR rule (measured, vendor code `setIolAttrInIologic`):** GSREN/LSREN don't exist on GW5A, and the vendor rejects them. The LSR mux row is set iff the primitive has a reset port that isn't tied to GND, so the *net* decides, not a parameter. GSR is always enabled.
- **`decode` is not a pass.** A case whose vendor cell lands entirely in "unattributed" (e.g. GW5A-25A B-site I/O logic, written into the wrong tile table) shows as `decode`, hiding a whole-cell bug. Count `decode` cases as unverified, and look at what they are before calling a primitive clean.
- **GW5 B cells live in the IOBB `fuse_cell_offset` tile** (IOB *and* IOLOGIC; vendor `setFseTableFuse` @0x3016fac reads tables 22/24 from the head grid). A B-site case whose fuses land there shows as `decode` plus `unattributed` bits, not `mismatch`. Check the harness's `tiles()` covers that tile before trusting a GW5 B-site status.
  - How the packer finds fuses, so you can tell a lookup fix from a data fix: the chipdb carries the vendor fse tables per tile type (`dev.shortval[ttyp][table]`, attribute set → fuse coords). `gowin_pack` builds the attribute set and calls `get_shortval_fuses(db, get_ttyp(x, y), av, 'IOLOGIC<idx>')`. `fuse_cell_offset` is a hand-measured per-ttyp table in `chipdb.py` (`_gw5_fuse_cell_offset`). When the right table already exists in the offset tile's ttyp, the fix is in the lookup (pack, unpack and harness all apply the offset), not in chipdb generation. Say which it is when presenting the design: he'll ask.
- `tools/gowin_decompile.py --project` must not have a path element starting with a dot, so `$TMPDIR` (under `~/.hermes`) fails. Put the Ghidra project under `~/code/apicula-wt/`.
- Reviewers walk the class hierarchy for each changed method. A "GW5A unchanged" claim without that walk is a blocker.
- When one review finds a leak, audit every open PR for the same pattern with one report-only card before merging any of them: per PR × method, the classes reached, where it was tested, the `cmp` result, and a verdict (ok, scope or justify). Record the head SHA checked per PR, so verdicts on heads already scoped by a rework can be discounted.
- **Unpack:** a fuse row that exists on GW5A doesn't necessarily encode the parameter there. If GW5A's packer writes that row as a constant, decoding it reports garbage. Diff the unpack output of GW5A designs against the parent, because the fuzzer doesn't compare most decoded parameters.

## Comparing two revisions
- **Revisions without the sorted-ports fix in `codegen.Module.write` aren't reproducible per seed:** they
  emitted `inputs`/`outputs`/`wires` sets in hash order, so the same `--seed` gave a different `top.v` port order
  per process, and vendor or nextpnr placement followed it. When comparing against such a revision, export one
  `PYTHONHASHSEED` for both runs. A claim like "the fuzzer generates different designs between runs" on a
  current revision is a harness bug to report, not an explanation.
- Copy each revision's `apycula/` into `$TMPDIR/<rev>/`, then `cd` somewhere neutral and run `PYTHONPATH=$TMPDIR/<rev> python -m apycula.gowin_unpack`. `-m` puts the cwd ahead of `PYTHONPATH`: run from a worktree, every "revision" silently uses the worktree's code, and every comparison comes out identical.
- Include a positive control: one file where the revisions must differ.
- For the unchanged-output `cmp` on `examples/`, pass `NEXTPNR_FLAGS="--timing-allow-fail --seed 1"`. The Makefile's `-r` randomises placement, so bitstreams, and sometimes routability, differ anyway.

## nextpnr crashes on omitted parameters
- An inventory of `params.at()` calls on optional parameters goes stale as soon as another nextpnr change lands. A later fix can add a new read on a path that never defaulted the parameter (e.g. `bsram_fix_outreg` reading `READ_MODE`/`RESET_MODE` from `pack_SDPB`). When the omission fuzzer still crashes after a defaults fix, grep `params.at(` along the crashing primitive's whole pack path on current nextpnr main, not the old inventory.
- Fix it by adding the missing `if (!ci->params.count(X)) ci->setParam(X, <primitive.xml default>);` next to the neighbouring primitive's identical block, then build and run that primitive's omitted cases baseline vs fix. Keep the parameter required in the fuzzer only until the nextpnr fix merges. Don't xfail a primitive that passes today just to absorb a nextpnr crash.

## Diagnosing a nextpnr "Failed to find a route"
An unroutable arc on a nearly empty device is rarely congestion. Find who holds the sink before blaming placement or the chipdb.
1. **Reproduce with fixed seeds.** CI's logged random seed doesn't reproduce under a different nextpnr build. Synthesize once (the Makefile's yosys line from `make -n -B`), then loop `nextpnr-himbaechel --seed N` for N = 1..8 on the synth JSON, and keep a failing N.
2. **Probe the placed design with `--pre-route probe.py`.** The Python `ctx` has no `getWireByName`, so reach wires from a bel pin with `ctx.getBelPinWire(cell.bel, port)`. Useful calls: `getPipsUphill`/`getPipsDownhill`, `getPipSrcWire`/`getPipDstWire`, `getWireBelPins`, `getBoundWireNet`, `checkPipAvail`. First map every placed input pin to its wire and look for a wire wanted by two nets. If there is one, the placer let two pins share a wire.
3. **Run `--router router2 --verbose`.** The line `Failed to bind wire W to net A, bound to net B` names the net that holds the sink. A run that ends with `overused=0` but `archfail>0` (then a `w2n_entry == nullptr` assert) means a pre-routed net owns the wire. A congested route would show overuse instead.
4. **Check what the held wire drives.** Look at its `getPipsDownhill`. On Gowin, a downhill pip into a long-wire segment (`LT*`) means `route_segmented` in `globals.cc` used the wire as a segment *gate*. Its gate selection (`get_segment_*_gate_wires`, first non-null) doesn't check for bel pins already in use. On GW5A BSRAM rows the gate `B7` is also a BSRAM `DI`/`DIB` pin, so the failure depends on the seed.

Report the mechanism with the probe output (wire, both nets, the segment pip) and say which parts are traced and which are inferred.

5. **`--pre-route` runs before the uarch's own pre-route (globals and segments), so no segment wire is bound yet when the probe runs.** To see what the segment router used, run with `--debug` and parse its `routed` pip lists (`tile/dst/src`) and `gate wire:` lines. Compare them against a pre-route dump of every placed-cell input pin (`ctx.getWires()` + `getWireBelPins` + `getBoundBelCell`; about 1.5M wires on 60B, which takes a minute). Python wire arguments are plain name strings (`ctx.getWireBelPins('X108Y37/B7')`), and `getBelPinType` stringifies as `PortType.PORT_IN`. To find reach, enumerate gate wires from `db.segments` and ask nextpnr's chipdb for their bel pins: Apicula portmaps use alias names for neighbour-cell pins (`BSRAMDIB6B7`), so a same-tile portmap scan misses them. Worked example: `~/code/apicula-wt/nextpnr-segment-gate-evidence/` (`probe_seeds.sh`, `scan_all.sh`).

## Proving a nextpnr change, baseline vs fix
**Identical baseline-vs-fix numbers prove nothing until you've shown the draws hit the trigger.** A crash that needs a parameter combination (e.g. `READ_MODE` omitted *and* read width < 16 on a device needing the OUTREG fix) may never be drawn at the seed you ran. Count the trigger in the generated designs first: parse `batch*/apicula/top.v` (`^<PRIM> <inst>` plus its `defparam <inst>.<P> = …;` lines). If it's absent, write a direct reproducer instead of raising `-n`:
- Run the design through the fuzzer's own Yosys flow, not `synth_gowin`. `synth_gowin` puts IBUFs on a blackboxed primitive's ports. The flow is `read_cell_library(family)` + `read_verilog t.v; hierarchy -top top; iopadmap -bits -inpad IBUF O:I -outpad OBUF I:O top; blackbox =A:whitebox; write_json`.
- Constrain every port with a cst (nextpnr refuses unconstrained I/O). Take the pins from a batch's `top.cst` for that device, and keep the design's port count at or below what's there.
- Run baseline and fix, then add an explicit-parameter control whose routed JSON must be identical apart from the version string (`diff` without the `creator` line). Finally, `gowin_pack` the fixed output with the device that matches the JSON.

Fuzzer batches mix cases, so a few unrelated DSP cases flip ok↔mismatch between runs (neighbours in one DSP block). Separate those from the patch's effect:
- Replay each changed case on its own. A replay JSON is `{"case": ..., "site": r['site']}`, with the site taken from `results.json`; `site: None` crashes BSRAM `describe()`.
- As a control, rerun the same case on the baseline nextpnr with the omitted parameter written out at its default. The same fuse diff means the mismatch isn't the patch's.
