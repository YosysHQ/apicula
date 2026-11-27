---
name: fpga-hardware-in-the-loop
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux]
description: "Use when FPGA HIL tests fail or HIL designs change."
metadata:
  hermes:
    tags: [fpga, apicula, hil, uart, gowin, ci]
    related_skills: [home-assistant, systematic-debugging, github]
---

# FPGA hardware-in-the-loop (HIL) debugging

Apicula's HIL CI loads example bitstreams onto real Gowin boards and diffs their UART
output against `examples/hil-references/*.txt` (`make -C examples hil-<board>`, rules near
the end of `examples/Makefile`). The self-hosted runner is a Home Assistant add-on; runner
and USB-host problems are in the `home-assistant` skill's add-ons reference.

## When to Use

- An apicula `hil (<board>)` CI job fails, or HIL output differs from the reference.
- Garbled, missing or stalled UART output from a Gowin board on the bench.
- Judging or replacing a Sipeed board's onboard debugger firmware (BL616 / BL702) for HIL.
- Adding, merging or restructuring HIL test designs (see `references/hil-test-designs.md`).

## Procedure

1. **Sort the CI failures into classes first.** `gh run view <id> -R YosysHQ/apicula
   --log-failed`, grepped for `error|fail|No cable|Process completed`:
   - `JTAG init failed with: No cable found`: the board is not on USB, so it's hardware.
   - Bitstream loads (`Load SRAM … DONE`) but `diff` shows extra or garbled lines: the UART
     path. Continue with step 2.
   - `Unable to read chipdb …`: a toolchain packaging problem, nothing to do with the board.
   - `Failed to claim FPGA device: can't parse file` (load log: `FsParser: checksum data
     is truncated`): deterministic per bitstream, not a flaky board. When fewer than three
     byte values are unused, the compressed bitstream carries 0x00 for the missing keys —
     the Gowin IDE does exactly the same (0 = key unused), and the FPGA keeps 0x00 literal.
     openFPGALoader's FsParser instead expanded literal 0x00 as a key: an odd count is
     refused, an even count parses to a wrong checksum silently. The fix is in
     openFPGALoader (0x00 is never a key), carried by the runner's pinned openFPGALoader
     build (see the `home-assistant` add-ons reference); `gowin_pack` is right. Read the
     keys from the header line starting `01010001`: bits 23..16/15..8/7..0 = 8Z/4Z/2Z.
     With `-r` placement each build draws anew, which makes it look flaky.
   - To test an openFPGALoader parser change without hardware, compile a harness of
     `FsParser(file, true, true).parse()` with `src/fsparser.cpp
     src/configBitstreamParser.cpp src/display.cpp` and compare its printed checksum with
     each file's `//CheckSum:` line (GW1N only; GW2A/GW5 checksums are unimplemented and
     skipped by the loader). To A/B a `gowin_pack` change, copy `apycula/` to scratch,
     patch it, re-pack the same nextpnr JSON with `PYTHONPATH=<copy> /usr/bin/python -m
     apycula.gowin_pack -c -d <dev> -o x.fs x.json`, and diff against the unpatched pack.
   - **Before "fixing" what apicula emits because a consumer rejects it, read what the
     IDE writes in the same case** (static analysis of `libgowin.so`, delegate it): if the
     vendor emits the same thing, the consumer is wrong and the fix goes upstream there.
   - Before calling any red "new", check whether it recurs across recent runs (one line
     per run, job name = conclusion):
     `for id in $(gh run list -R YosysHQ/apicula --workflow chipdb.yml --limit 15 --json
     databaseId -q '.[].databaseId'); do gh run view $id -R YosysHQ/apicula --json
     headBranch,jobs -q '.headBranch+" "+([.jobs[]|select(.name|test("hil|60k"))|
     .name+"="+.conclusion]|join(", "))'; done`. The HIL jobs live in `chipdb.yml`'s
     run (it calls `toolchain.yml`), so `--workflow toolchain.yml` finds nothing.
   - **Read a failed job's log before cancelling or superseding its run**: `gh run view
     --log` stream-errors on cancelled runs, and the cause is then lost. The reliable
     per-job fetch is `gh api --allow-escape-sequences
     repos/YosysHQ/apicula/actions/jobs/<job-id>/logs` (job ids from `gh run view <id>
     --json jobs`); without the flag gh refuses output that contains colour escapes.
   - **Asked whether a HIL stack is ready or "still flaky"**, classify before answering:
     read the failing master runs' logs (`dirtyJtag: No device found` = a board was off the rig,
     not a test failure), then list the residual sources of red separately — rig hardware (bridge
     wedge), build-only boards on a fixed nextpnr seed (break when nextpnr main moves, until the
     routing fix they work around lands), random-seed batches with a known placement-dependent
     nextpnr issue worked around by splitting, and `stable / hil` skipped. Give the merge order with it.
   - With `make -k`, one failing batch does not hide the rest: grep `PASS:|^[<>]|make:`
     to see which batches passed and the diff of the one that did not.
   - **A single-row HIL red on a board the PR doesn't touch:** rerun only that job
     (`gh run rerun <run> -R YosysHQ/apicula --job <job-id>`). It reuses the run's bitstream
     artifact, so the same placement loads again: a pass means a one-off (bridge or timing),
     a repeat of the same mask means a placement- or site-dependent fault in that build. File
     the latter like the existing BSRAM site issue, with the failing artifact, and don't hold
     the unrelated PR on it without asking.
2. **Reproduce with the exact CI bitstreams** before rebuilding anything:
   `gh run download <id> -R YosysHQ/apicula -n examples-{dev,stable}-<board>` into scratch.
   Load with the same `openFPGALoader` line the Makefile uses, then capture **raw**
   bytes, not the Makefile's awk-filtered output:
   `stty -F $D 115200 raw -echo; timeout 10 cat $D > out.bin`, with `$D` the
   `/dev/serial/by-id/…` path from the Makefile. Show it with `cat -v`. Count good and bad
   lines with `grep -cE '^(T[0-3]:PASS|--- tick ---)$'` against `wc -l`.
3. **Decode the corrupted bytes in binary.** Compare each wrong byte with the expected one:
   - received = expected << 1 (`:` 0x3A → `t` 0x74, `\n` 0x0A → `^T` 0x14): the receiver
     saw a false start bit one bit early. That means a low glitch on TX during stop/idle,
     i.e. a transmitter problem, not baud drift.
   - errors spread over random bytes, getting worse along long bursts: baud mismatch or
     the bridge MCU.
   - the stream stops entirely: the BL616 UART lockup (see the history below).
   Corruption that shifts between bitstreams (dev vs stable), but repeats at the same
   byte within one bitstream, points at routing-dependent logic in the design.
4. **A/B the suspected fix on the board.** Build both variants of the design in scratch
   with the Makefile's yosys / nextpnr-himbaechel / gowin_pack commands
   (`make -n -B <design>-<board>.fs` prints them). Load each twice and compare bad-line
   counts. Report the raw counts, not a conclusion alone.
5. **Ship the fix as a PR on apicula** (team repo, not push-to-main): `git worktree add -b
   <branch> $TMPDIR/<dir> origin/master`, commit, push the branch to `origin` (YosysHQ)
   so the PR's HIL job runs on the real boards, `gh pr create` with the measured table.

Boards without a `hil-*` Makefile rule: build `hil-latch-<board>.fs` (a batch of one)
with the board's `make -n -B` commands and capture from the bridge's UART by-id path (see
`references/bridge-firmware.md`).

Vendor-comparison (tiled fuzzer) failures are a different loop: see the
`apicula-fuzzer-burndown` skill.

## Batched tests

The HIL tests live in `examples/hil.v` and run in batches (`HIL_BATCH_*` at the top of
`examples/Makefile`); `make hil-<test>-<board>` runs one test alone. When a batch fails:
- Run its tests singly. A test that passes alone and fails in a batch is placement-dependent:
  rebuild the batch with fixed seeds (`NEXTPNR_FLAGS="--timing-allow-fail --seed N"`, per-target
  in a throwaway makefile that `include`s Makefile) and compare `NEXTPNR_BEL` of the test's
  cells in the routed JSON between passing and failing seeds.
- **Split toolchain from hardware before filing anything.** Load CI's `examples-dev-*` and
  `examples-stable-*` bitstreams of the failing run and a local build of the same commit on
  the bench (dev = yosys/nextpnr `main`, stable = pinned releases, see `chipdb.yml`):
  - fails in all builds, same bits: systematic (hardware or apicula);
  - fails only in dev, identical values across random seeds and both chips: a regression in
    yosys/nextpnr main. Bisect with `git log <local>..origin/main -- himbaechel/uarch/gowin`,
    a `git worktree` of nextpnr with the suspect commit reverted (`--no-commit`), built under
    a memory scope (`memory-safe-builds`), and `make NEXTPNR=<that binary>` from a throwaway
    makefile that `include`s Makefile; the revert passing on the bench is the proof.
    Configure that nextpnr with `-DPython3_EXECUTABLE=<apicula venv python>`: the chipdb
    generator imports `apycula` and `msgpack`. Then find the bug by reading the suspect
    diff against the primitive's ports **per family** (`$(yosys-config
    --datdir)/gowin/cells_xtra_<family>.v`; e.g. SDPB has RESETA/RESETB on GW1N/GW2A but
    one RESET on GW5A): `CellInfo::connectPort(port, nullptr)` silently does nothing, so
    a wrong port name leaves the new cell's input dangling instead of erroring. Fix on a
    nextpnr branch pushed to Pepijn's fork, bench it with both boards, and open a draft
    PR with a nextpnr-version × board table (with suspect / revert / fix);
  - varies with seed under one toolchain: placement-dependent (next bullet).
  Never label a failure placement-dependent from one local toolchain only: a dev-only
  regression looks exactly like an unlucky CI placement.
- **Decode a failing row before reasoning about it.** A `bsram_*` row packs four 16-bit
  pass masks, cfg0 in the low bits; map each lost bit to its check via the bit list at the
  top of `hil/bsram.v`, and the config via the `.CFGn` lines in `hil.v`.
- **Site-dependent faults: find the site, then pin it.** Decode which BSRAM/DSP site the failing
  config occupies in CI's own bitstream (`gowin_unpack`, the attribute decoder in the evidence
  dir's `sweep/`), then pin the cell there and at a neighbour with a `BEL` attribute and sweep
  seeds. Build the vendor's version at the same site with `INS_LOC` (BSRAM `BSRAM_R<row>[<n>]`)
  and diff function fuses first, then pin drivers: equal function fuses leave routing. To test
  one routed pin as the cause, drop its pips from the nextpnr JSON and repack, or drive the same
  path from the other constant. A fault at one site on the rig's only board is unresolved between
  die and site until a second board of the same part loads the same bitstreams.
  For that, build one bitstream with the test at *every* site (one shared sequencer, one
  DUT per site, each `BEL`-pinned; all 46 GW2A-18C BSRAMs fit at 36 % LUTs) that prints a
  plain per-site PASS/FAIL report over the UART, so an outsider needs only openFPGALoader
  and a terminal. Example: `fix-dp16-site-evidence/allsites/` (`rig-run.sh` = raw capture
  under the rig lock, for output without `--- tick ---` blocks). For an outsider: report in
  plain ASCII with a header naming the variant and a `done` marker, repeat it every second or
  so (they may attach late), add an LED summary, and write instructions for a **stock** board
  (the bridge's second serial port, SRAM load so a power cycle restores their design); flag in
  the handover that the rig board's custom bridge firmware can't confirm the stock port name
  or the LEDs (no camera).  It's a one-off tool, not a CI test.
  To keep a random-seed batch off a weak site meanwhile: nextpnr has no option to forbid a bel,
  so occupy it with an idle `(* keep, BEL = "X<x>Y<y>/BSRAM" *)` cell under an `ifdef` in hil.v,
  defined only for that board's batch via a target-specific variable on its `-synth.json` rule
  (not `YOSYS +=`: a command-line `YOSYS=` would silently drop it). Example: `HIL_BLOCK_X28Y9`.
- **Measure a failure rate with a rerun loop, not with loads.** A HIL test runs once per
  load, so 20 loads only bound a rate below 14 %. Wrap the test in a loop that resets and
  reruns it about 1000 times per load and counts the failing runs (BSRAM: count only the
  checks that don't depend on INIT). Freeze the counters when it finishes; UART runs on clk.
  For a frequency sweep with fixed routing, drive the test clock from an rPLL. Builds
  that differ only in divider parameters and use the same output (CLKOUT, or CLKOUTD)
  get identical placement and routing for the same seed. Check that with a pip-set diff
  of the routed JSONs. Example: `fix-dp16-site-evidence/sweep/char/` (`charloop.v`, `mk.py`).
- nextpnr places far fewer DSP tests together than the macros hold, and pairwise success does
  not predict triples: find batches by building candidates, not by counting slots.
- Run the full suite the CI way (container recipe under "Quick check") before pushing a
  batch change; a passing single test says nothing about its batch.
- A confirmed hardware or apicula fault that blocks merging goes on `HIL_BROKEN_<board>`
  (issue first, reference stays correct, `make hil-<board>-broken` re-checks); details
  under "Known-broken tests" in `references/hil-test-designs.md`.

## Quick check on the bench

Use `scripts/hil-run.sh <tangnano9k|tangnano20k|primer25k> <bitstream.fs> [settle_ticks] [reference.txt]`
for a sanity check in seconds, without CI. It copies the bitstream into the runner add-on container
(`ssh -p 22222 root@homeassistant.local`, `docker exec app_2dade7a1_github_actions_runner`),
loads it with the Makefile's `openFPGALoader` line and captures the UART the way `hil_capture`
does. It prints the tick block, or diffs it against a reference.
- It holds one rig-wide `flock` (every board on the rig) and refuses while a CI `Runner.Worker` is
  running. Exit codes name the failed step: 5 load, 6 stty, 7 no output. Subagents on the
  bench must use it, never their own loops over both boards.
- To run a whole board's HIL the way CI does, tar `examples/Makefile`,
  `examples/hil-references` and the prebuilt `examples/*.fs` (or the whole `examples/` of a
  `git ls-files` copy, closest to CI's checkout) into a scratch dir in the
  container (`tar czf - … | ssh … "docker exec -i $C tar xzf - -C /tmp/hil-pr"`) and run
  `make -k hil-<board>` there; tar keeps mtimes, so make does not try to rebuild. The
  container's `sh` has no `time`: time the ssh call from the outside.
- The refusal also fires for other PRs' CI runs (the rig is shared), and a push of your
  own triggers HIL jobs that hold it for minutes. Wrap bench runs in a retry loop (30 s
  sleep while the output says a CI job is running), as a background job, instead of
  reporting "busy".
- A hand-rolled `Runner.Worker` check inside `sh -c '…'` matches its own command line:
  use `grep '[R]unner.Worker'`, and cross-check with `gh run list --status in_progress`.
- A load failure that repeats on the same file is the file, not the copy: compare
  `md5sum` locally and in the container before blaming transport.
- Lasting verification is still the PR's `hil` job. A quick check is not evidence for a PR on its own.
- **A board plugged into Pepijn's own machine** (a new board before it moves to the rig) is not
  behind `hil-run.sh`: find it with `openFPGALoader --scan-usb` / `-c dirtyJtag --detect` and
  `ls -l /dev/serial/by-id/`, give it a `hil-%-<board>` section with its DirtyJTAG serial (the
  existing `hil_check` macro fits unchanged), and run the Makefile targets locally, one agent owning
  it. He tests locally first; the CI matrix entry follows when he moves the board to the rig, so
  keep such branches unpushed until then.
  When he asks whether he can unplug it, check before answering: the owning agent's report file
  and `pgrep -af '<serial>|openFPGALoader'` show whether a load or capture is in flight. If so,
  say what's running and how long it takes, and offer to steer the agent to pause after the
  current run and save state; unplugging mid-capture corrupts the batch results and makes the
  agent report the bridge as gone.
- ssh joins its arguments into one remote shell line, so a redirect in an unquoted `docker exec … sh
  -c "cat > f"` runs on the HA host, not in the container. The script quotes with `printf %q`.

## Building locally

- `gowin_pack` runs under `/usr/bin/python`, which usually has no `apycula` installed:
  build with `PYTHONPATH=<repo-root> make …` from `examples/` rather than installing a
  venv. Fallback if that fails: `python3 -m venv $TMPDIR/apicula-venv && …/bin/pip
  install -e ~/code/apicula/apicula`, then put the venv's `bin` first on `PATH`.
- A fresh `git worktree` of apicula lacks the chipdb data (`*.pickle`, `*.msgpack.xz`,
  `GW*_stage*.msgpack.gz`) — gitignored, only present in working checkouts. Copy them
  from the main checkout (into the worktree's `apycula/` and repo root) before the first
  build, or every pack step fails with a `FileNotFoundError` on the device's msgpack.
- The checkout is often on a feature branch with local commits: build in scratch dirs
  and never switch or stash the user's branch.
- The rig carries the primer25k (GW5A-25A, DirtyJTAG `7c3e8265f4b7`, loader board
  `tangprimer25k`) next to the 9K/20K; the runner's openFPGALoader (v1.2.0) has
  `--usb-serial-num`. GW5A HIL bitstreams build in `examples/` (from `gw5a/Makefile`), so the
  `example` artifact also globs `examples/hil-*-<board>.fs` (artifact root becomes `examples/`).
- The HIL board list lives in `.github/workflows/toolchain.yml` (job `hil`, one `make
  hil-<board>` per matrix board; bitstreams come from the `example` job's
  `examples-<name>-<target>` artifacts). Swapping a board is a matrix entry plus a
  `hil-<board>` section in `examples/Makefile` (bitstream rule, `hil_capture` with the
  board's by-id port, `HIL_SETTLE` overrides, aggregate target); reference outputs are
  shared per test name across the same device family.

## Pitfalls

- **Register every UART TX output.** A combinational TX such as
  `assign tx = data[0] | !(|data)` glitches low where one term falls as the other rises
  (end of stop bit); an FTDI receiver may tolerate it, the BL616 bridge does not.
  `examples/emitter_uart.v` is shared by `hil.v` and the femto-riscv designs.
- **Do not blame the Sipeed bridge firmware by reflex.** Its failures are lockups (no bytes,
  or every USB control request stalling), not garbled bytes. Chips, firmware, flashing
  routes and wedge signatures per board: `references/bridge-firmware.md`.
- **Claim on hardware only what actually ran on it.** A bitstream the loader refused
  never reached the FPGA, so it proves nothing about how the FPGA decodes it; list in a
  PR only the variants whose output was checked, and add the rest after the bench run.
- **Make every hardware loop fail-fast.** Check each step's exit status and stop at the
  first failure, naming the step; a loop that carries on after a failed load reports
  N empty captures and hides that the bridge wedged on the first access. Use
  `scripts/bridge-soak.sh`.
- When the user says the board still shows its old behaviour (e.g. still blinking), the load
  failed — read `load<i>.log` before anything else.
- **Never drive two rig boards at once.** The tangnano9k's BL702 DirtyJTAG port wedges when
  the tangnano20k loads at the same time: 0 of 30 loads failed alone, the 8th failed with
  both loading (`usb bulk write failed -7` at Load SRAM, no kernel message). Afterwards the
  device stays enumerated but answers no control request (`openFPGALoader --scan-usb`
  shows manufacturer/serial `none`); only a replug recovers it. CI never overlaps (one
  runner, one job at a time); `hil-run.sh` holds a rig-wide lock for the bench.
- **When the rig is called unstable, find the trigger with soaks before touching
  firmware:** first the dmesg history of the bridge's hub port and the transcripts of
  whoever used the bench at the wedge time, then a fail-fast soak of the board alone (30+
  loads), then the same soak with the other board loading concurrently. A wedge only under
  concurrency is a usage rule now (lock) plus a firmware fix that can wait for a bench
  session (draft PR, built for both chips, counters for the suspected path).
- **Bench instructions to the user carry polarity, a measurement and a photo.** Before
  telling them to bridge a strap pad, state which level it needs (from the schematic, not a
  guess), give a multimeter check that tells the pads apart, and link the reference photo;
  "short the test points" alone leads to grounding an active-high strap.
- **Check the device's state before asking for a physical step again.** A strap-bridged
  ISP session survives as long as the board stays powered: `lsusb | grep ffff:ffff` first,
  and if it is still there, keep using it (resident-helper config in
  `references/bridge-firmware.md`) and tell the user to leave the board plugged in.
- **Take a port's pin map and init from the stock firmware binary, not the vendor's repo.**
  Vendor pin tables can belong to another board revision; wrong JTAG pins show up as
  `TDO is stuck at 0`. Decompile the stock dump before the first reflash and before each
  fix attempt (recipe in `references/bridge-firmware.md`).
- **Prefer identifiers derived from the hardware over build options.** For per-board
  uniqueness (USB serial / by-id path) use the chip's factory MAC, one code path for all
  chips, rather than a per-board build variable.
- **Measure before redesigning bridge firmware.** When a port misbehaves, add counters
  (task tick/loop/state, FIFO levels, busy flags) and read them live; don't ship an
  architectural change (moving work out of an ISR, new buffering) on a hypothesis, since
  each wrong guess costs a strap-bridged reboot. Revise the plan openly when the data
  contradicts it.
- **Before each physical step, say what each outcome means** (e.g. after a replug:
  `1209:c0ca` = X, `ffff:ffff` = Y, nothing = Z), so one replug answers the question.
- **Prefer the plain path when proving a clever one costs bench work.** Each strap-bridged
  reboot is expensive for the user; choose the layout that needs the fewest of them (e.g.
  a straight app at 0x0 over an unproven bootloader) and file the clever one as a follow-up.
- **Ask before overwriting bridge firmware, and say when the approval prompt is coming.**
  The write to flash 0x0 needs the user's go-ahead and an approval prompt they must be
  present for; state what gets overwritten and where the backup is, then run it only
  after they confirm.
- Keep the stock bridge firmware backup (flash + efuse + SHA256SUMS) under
  `~/code/bl616_dirtyjtag/reference/<board>-<mcu>-stock/`, not in scratch (pruned after
  24 h); flashing `flash_stock.bin` back at 0x0 restores the board.
- **Build one batch for two boards in one make process, or pre-create `hil-<batch>.v`.**
  Separate parallel `make` runs share that intermediate wrapper and interleave its
  `printf`/`echo`, which yields a doubled `include` ("Re-definition of module"). (Branch
  hil-gw5a writes the wrapper via a temp file + `mv`, which removes the race.)
- **A wedged or vanished bridge needs a physical replug; report it, don't poke sysfs.**
  Signatures: `usb bulk write failed -7` then `No device found`, or no enumeration at all
  (`can't set config #1, error -71`, empty USB strings, no by-id link). Writing
  `authorized`/`bConfigurationValue` or disabling the hub port in sysfs on the HA host
  fails ("Protocol error") and can leave the device unconfigured. Check `ls
  /dev/serial/by-id/` on the host, keep testing on the other board, mark the board's
  results "not run", and ask the user for the replug. Sysfs pokes turn a firmware hang
  into a port that fails enumeration with -71 until the replug.
  When a card or CI reports `No device found`, confirm it yourself before asking:
  `ssh -p 22222 root@homeassistant.local 'ls /dev/serial/by-id/; docker exec $(docker ps
  --format "{{.Names}}" | grep github_actions_runner) openFPGALoader --scan-usb'`, then name
  the missing serial, the three replug outcomes, and what is waiting on the board.
  He may keep it off until he has flashed a firmware fix: then don't re-ask; record in
  `~/code/apicula-wt/BACKLOG.md` that the board is off and its HIL counts as "not run", and
  tell cards to report it that way.
- **Gowin user flash (FLASH608K) reads erased words as 0, programming sets 1s** (UG295
  states it only for FLASH96K). Don't assume NOR-style all-ones. Each load of the
  `userflash` HIL test erases a page: keep it out of batches and count bench runs.
- **"Unrouted" is not a constant on Gowin.** Every input mux has a zero-fuse pip (empty fuse
  set in the chipdb) that drives it when no fuse is set: LUT-position inputs take a same-tile
  F output, spans/X wires a Q output, CE/LSR/CLK/SEL take VCC. In BSRAM tiles F/Q are the
  block's own outputs, so an unrouted BSRAM pin reads its own DO (measured 20K and 9K). When
  decoding a bitstream's drivers, report the zero-fuse source instead of "unrouted"; to
  measure a default, drop the pip from the nextpnr JSON and repack (GW2A `gowin_pack` parks
  unused logic-tile inputs, so disable `get_unused_wire_fuses` in a scratch copy). In a
  BSRAM probe, use write-through (WRITE_MODE 1) and non-zero INIT, or a feedback input
  looks like a constant 0.
- Back-to-back UART bytes leave no idle gap, so any TX glitch at a byte boundary lands
  right where the receiver hunts for a start bit.

## Support files

- `references/bridge-firmware.md` — bridge MCU per board, custom-firmware routes (BL616
  signed bootloader vs BL702 test-point ISP, board revisions), reading flash/efuse in ISP,
  flashing the BL702 port (header FCFG transplant, write via resident helper), BL702 port
  pitfalls, reverse-engineering the stock image (layout, Ghidra, finding pins), which
  routes back into ISP were tried, reading the firmware's debug counters (and how to
  interpret them) to split USB from UART faults, wedge signatures, how to report
  reliability.
- `scripts/bridge-soak.sh` — fail-fast load/stty/capture soak loop for a board's bridge.
- `references/hil-test-designs.md` — the batched `hil.v` layout and Makefile mechanism,
  adding a test, porting examples to tests (survey, parallel subagents, merging their
  branches), packing batches by measurement, and debugging placement-dependent
  (seed-dependent) results.
- `scripts/hil-pack.py` — greedy/try search for HIL batches nextpnr can place.
- `references/io-loopback-pins.md` — header pins, bank VCCIO, true-LVDS pairs and loopback
  wiring rules for the 9K/20K I/O self-tests; how to dump pins/banks/diff flags from the chipdb.

## History

The HIL infrastructure, the per-board split and the custom-firmware switch are in the
apicula PRs titled "Add hardware-in-the-loop CI test infrastructure" and "make
tangnano20k HIL work with custom firmware". The firmware story is the "BL616
reliability" email thread with Sipeed (search the Proton index for `sipeed`).
