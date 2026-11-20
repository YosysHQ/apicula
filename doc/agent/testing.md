# Testing

How to meet the rules in [`AGENTS.md`](../../AGENTS.md#testing).

## Regression tests

Run it once without the fix to see it fail.

- Python logic: a test in `tests/`, like `tests/test_bslib.py`, run with
  `python -m pytest tests`. CI runs it in `.github/workflows/chipdb.yml`, after
  building the chipdbs. It may load the chipdbs but not the IDE.
- Vendor mismatches: the fuzzer case, rerun with `--replay`.
- Hardware-only bugs: a HIL test.

## Vendor tests

See "Adding a primitive" in [tiled-fuzzer.md](tiled-fuzzer.md). Values the XML
allows but the vendor rejects go in `RULES`; never narrow a strategy to hide a
mismatch. Report the command, seed and status totals per device:

    python3 tools/tiled_fuzzer.py -d GW1N-9C -n 20 --seed 1 --prims NEWPRIM

## Hardware-in-the-loop tests

The boards are in the `hil` matrix of `.github/workflows/toolchain.yml`. Place
and route and the upload are the slow part, so the tests share one design,
`examples/hil.v`, and run in batches: one bitstream per batch, with the tests
selected by `` `define HIL_<name> ``. A test is a module in `examples/hil/`,
`` `include ``d by `hil.v`, an `` `ifdef `` block in `hil.v` that instantiates it
and one that lists its report rows, and a reference in
`examples/hil-references/<name>.txt`. Add it to a batch
in `examples/Makefile` (`HIL_BATCH_*`), and check that nextpnr still places the
batch.

`make hil-<name>-<board>` runs a single test, which finds the culprit when a batch
fails as a whole. Prefer self-checks to raw values, like `latch`'s pass mask: a
reference captured from Apicula's own bitstream only proves the output did not
change.

Drive a primitive under test from plain logic in `hil.v`, not from a CPU.
Designs that test a whole system, like `femto-riscv-18-test`, keep their own
bitstream and rule.

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
