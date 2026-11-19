# Testing

How to meet the rules in [`AGENTS.md`](../../AGENTS.md#testing).

## Regression tests

Run it once without the fix to see it fail.

- Python logic: a test in `tests/`, like `tests/test_bslib.py`, run with
  `python -m unittest discover tests`. It may load the committed chipdbs but not
  the IDE.
- Vendor mismatches: the fuzzer case, rerun with `--replay`.
- Hardware-only bugs: a HIL test.

## Vendor tests

See "Adding a primitive" in [tiled-fuzzer.md](tiled-fuzzer.md). Values the XML
allows but the vendor rejects go in `RULES`; never narrow a strategy to hide a
mismatch. Report the command, seed and status totals per device:

    python3 tools/tiled_fuzzer.py -d GW1N-9C -n 20 --seed 1 --prims NEWPRIM

## Hardware-in-the-loop tests

The boards are in the `hil` matrix of `.github/workflows/toolchain.yml`. A test is
a self-checking design in `examples/`, like `examples/latch.v`, that prints
`PASS`/`FAIL` lines and `--- tick ---` over UART, a reference frame in
`examples/hil-references/`, and its `hil-<name>-<board>` entry in
`examples/Makefile`. Prefer `PASS`/`FAIL` to raw values: a reference captured from
Apicula's own bitstream only proves the output did not change.

## Comparing by hand

- Constrain every pin to the IDE's choice (`impl/pnr/top.pin.html`). The IDE picks
  PLL input selects from the clock pin, so unconstrained designs differ for reasons
  unrelated to your change.
- Check the vendor log and netlist (`impl/gwsynthesis/top.vg`) to confirm your
  parameters took effect. A later `defparam` silently overrides an earlier one.
- `gowin_unpack.parse_attrvals` can misreport overlapping table rows, so confirm a
  surprising difference against the fuses.

## Checking a chipdb change

Back up `apycula/*.msgpack.xz`, rebuild, then compare by content:

    PYTHONPATH=. python3 tools/chipdb_compare.py BACKUP_DIR apycula

Rebuilt files never match byte for byte, because sets serialize in a different
order on each run.
