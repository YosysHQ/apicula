# Testing and verifying changes

How to meet the testing rules in [`AGENTS.md`](../../AGENTS.md#testing). Each
section says where a kind of test lives, how to run it and what to report.

## Regression tests for fixes

A regression test reproduces the bug: it fails on `master` and passes with the
fix. Check both, for example by running it once with the fix stashed. Put it at
the cheapest level that shows the bug:

- **Python logic** in `gowin_pack`, `gowin_unpack`, `bslib`, `chipdb` or the
  parsers: a test in `tests/`, in the style of `tests/test_bslib.py`. Run them
  with `python -m unittest discover tests`. The committed chipdbs
  (`apycula/*.msgpack.xz`) can be loaded, so a test can call the function that was
  wrong, such as a `get_…_fuses` method, with the failing parameters and check the
  fuses or attributes it returns. Tests in `tests/` must not need the IDE.
- **Fuses that differ from the vendor:** the fuzzer case that shows it, rerun
  with `--replay` before and after (see below). If the primitive or parameter was
  not generated before, extend `tools/primitive_strategies.py` so that it is. Add a
  `tests/` test as well when the wrong value can be checked without the IDE.
- **Only visible on hardware:** a hardware-in-the-loop test (see below).
- **Chipdb builder:** the content comparison below, plus a `tests/` test on the
  rebuilt table where practical.

Name the test after the behaviour, not the issue number, and say in a comment
what used to go wrong.

## Vendor tests for primitives: `tools/tiled_fuzzer.py`

The fuzzer draws random parameter sets for a primitive from the IDE's
`primitive.xml`, builds them with the vendor and with Apicula, and compares the
unpacked cells and the non-routing fuses. It is described, with its pitfalls, in
[tiled-fuzzer.md](tiled-fuzzer.md).

For a new primitive, or a new parameter of an existing one:

1. Check availability with `tools/vendor_sweep.py`
   ([vendor-sweep.md](vendor-sweep.md)) and add PA2085 devices to
   `UNAVAILABLE`.
2. Add the primitive to `SITES` in `tools/primitive_strategies.py`, with a site
   kind. A new site kind needs the changes listed under "Adding a primitive" in
   [tiled-fuzzer.md](tiled-fuzzer.md).
3. Parameters must cover the full range the vendor accepts. Values the XML allows
   but the vendor rejects become `RULES`, with the vendor message; rules across
   parameters (frequency ranges, ordering) become filters on the strategy. Do not
   narrow a strategy to hide a mismatch.
4. Run every device in `tiled_fuzzer.DEVICES` that has the primitive, with a fixed
   seed and at least `-n 20` cases:

       GOWINHOME=... python3 tools/tiled_fuzzer.py -d GW1N-9C -n 20 --seed 1 --prims NEWPRIM

5. Every case must be `ok`. `invalid` cases mean a rule is missing from the
   generator. A `mismatch`, `decode` or `unsupported` case that is not fixed must
   be explained, and listed in the gaps in [tiled-fuzzer.md](tiled-fuzzer.md).

Report the commands, seeds and the status totals per device. For a fix to an
existing primitive, rerun that primitive the same way and compare the totals with
`master`.

Features that are not one primitive (routing, clock networks, timing, several
primitives that share a resource) need the same: many random configurations,
built by the vendor and by Apicula, compared automatically. Where the fuzzer
cannot generate them yet, extend it with a new site kind or case shape, or write
a comparison of the same kind next to it (for timing, `tools/timing/` already
compares IDE, reimplemented vendor and nextpnr delays). Building that is part of
the change.

## Hardware-in-the-loop tests

The HIL job in `.github/workflows/toolchain.yml` runs on a self-hosted runner with
a Tang Nano 9K (GW1N-9C) and a Tang Nano 20K (GW2A-18C); a GW5A board is on
order. It programs each
bitstream, reads the board's UART at 115200 baud, and `diff`s one frame against a
reference. CI runs it after the examples build; pull requests from forks wait for
a maintainer's approval.

A HIL test is:

- **A self-checking design** in `examples/`, like `examples/latch.v`. It drives
  the primitive with runtime data (a counter, an LFSR) so that nothing is folded
  into constants, computes the expected result in ordinary logic, and prints one
  `PASS`/`FAIL` line per check, using `emitter_uart.v`. Each frame ends with a
  `--- tick ---` line. Prefer this to printing raw values: a reference full of
  numbers captured from Apicula's own bitstream proves only that the output did
  not change.
- **A reference** in `examples/hil-references/<name>.txt`: one frame, as captured
  from the board. Check that it is what the design should print; where the
  design prints values, check them against simulation or the vendor's bitstream
  on the same board.
- **Makefile entries** in `examples/Makefile`: the `<name>-tangnano9k.fs` and/or
  `<name>-tangnano20k.fs` targets in the examples list, and `hil-<name>-<board>`
  in `hil-tangnano9k`/`hil-tangnano20k`. Raise `HIL_SETTLE` for designs that need
  more frames to settle.

Run it locally, with the board attached, with
`make -C examples hil-<name>-tangnano9k`. Without a board, say so in the pull
request; CI runs it.

Cover at least one configuration of each new primitive, and the failing
configuration of a hardware bug, on a board of the primitive's family. If the
rig has no board for the family, say so in the pull request. A GW5A board is
coming, so check the `hil` matrix in `toolchain.yml` for the current boards
before deciding there is none.

## Comparing with the vendor by hand

Useful while investigating a difference, but not a replacement for the automated
vendor tests above. Build a design with the IDE and with Apicula, decode both
bitstreams and compare the attributes or fuses, with non-default values for the
parameters in question.

Before trusting a comparison (these apply to the fuzzer's harness too):

- Constrain every pin to the IDE's choice (`impl/pnr/top.pin.html`). The IDE picks
  PLL input selects from the clock pin, so unconstrained designs differ for reasons
  unrelated to your change.
- Check the vendor log and netlist (`impl/gwsynthesis/top.vg`) to confirm your
  parameters took effect. A later `defparam` silently overrides an earlier one.
- `gowin_unpack.parse_attrvals` can misreport overlapping table rows, so confirm a
  surprising difference against the fuses.

## Comparing with `master`

Pack the same nextpnr JSON with `master` and with your branch, and `cmp` the two
bitstreams for designs that do not use the feature, such as the examples.
Explain every difference.

## Checking a chipdb change

Back up `apycula/*.msgpack.xz`, rebuild, then compare by content:

    PYTHONPATH=. python3 tools/chipdb_compare.py BACKUP_DIR apycula

Rebuilt files never match byte for byte, because sets serialize in a different
order on each run. A raw msgpack comparison shows thousands of false differences.
