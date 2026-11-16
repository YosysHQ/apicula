# Tiled fuzzer: comparing Apicula with the vendor on random primitives

`tools/tiled_fuzzer.py` revives the idea of the old tiled fuzzer
(`legacy/tiled_fuzzer.py`, and its earlier version before commit `d350cb7`). That
fuzzer placed many independent test cases in one design, one per site, so a single
vendor run answered many questions. Here the cases are random primitive
configurations, and the question is whether Apicula and the vendor produce the
same fuses for them. IDE **1.9.10.03**.

## Pipeline

1. **Generate.** `tools/primitive_strategies.py` builds Hypothesis strategies from
   `primitive.xml` (see [primitive-params.md](primitive-params.md)). One example is
   one primitive instance (a "case"). Cases are drawn per primitive, so each gets
   equal coverage. Hypothesis is used only to generate values; nothing is
   shrunk, because a case is already a single primitive.
2. **Batch.** Each case gets a site. A slice holds two LUT cases or one DFF case.
   Primitives that exist once per chip, such as OSC, get one design each.
3. **Run.** The same netlist and `.cst` go to both flows:
   - vendor: `codegen.Pnr.run_pnr`, with placement fixed by `INS_LOC`;
   - Apicula: Yosys (read only, no synthesis), nextpnr, then `gowin_pack`.
     Placement is fixed by `BEL` attributes added to the Yosys JSON.
4. **Compare.** Both bitstreams are split into tiles. Routing fuses are masked:
   `pips`, `clock_pips`, `alonenode` and `alonenode_6`. Each remaining difference
   is assigned to a bel (LUT INIT fuses, the `CLSn` slice table) and so to the case
   placed there. Differences that a design with no cases also shows (the I/O
   harness) are subtracted.

`--replay` reruns saved cases, one per design, to confirm a mismatch in
isolation.

## Things the harness must get right (checked by running both flows)

- **nextpnr ignores `INS_LOC`.** Its `cst.cc` parses the line but has no
  `case insloc` handler. "Placed 0 cells based on constraints" in the log means
  this happened. A `BEL` attribute such as `X22Y3/LUT2` works.
- **The two flip-flops of a slice share clock, CE and set/reset modes.** Giving
  them different DFF types makes the vendor drop one with `CT1094 can't be
  placed according to constraint`.
- **Cases must not drive each other.** With one case's output chained into the
  next, the vendor propagated a constant and turned `LUT1` INIT `2'b10` into a
  constant `ffff`. The vendor keeps cells whose outputs are unused (a LUT4's INIT
  fuses were identical with and without a load), so outputs are left unconnected
  and inputs come from input pins.
- **The vendor permutes LUT inputs.** It connects the nets to A–D in its own order
  and rewrites INIT to match. 15 of 16 LUT mismatches in the first run were exact
  input permutations. The 16th was the constant propagation above. LUT INIT is
  therefore compared up to an input permutation for the vendor, and exactly for
  Apicula. nextpnr keeps the pin order, and Apicula's INIT matched the expected
  value in every case.
- **The netlist dialect.** Every port must be connected (PA2058), and sized
  constants on ports are rejected (PA2000). Unused inputs go to a `GND` cell's
  net. `PA1002` (invalid parameter value) and `CT1094` mark a case invalid rather
  than a mismatch.
- **The `.posp` file has no cell placements** in this IDE version, so vendor
  placement is checked through the `CT1094`/`CT1005` warnings instead.

## Results so far (GW1N-9C)

- All 20 DFF types, LUT1–LUT4 and OSC (`FREQ_DIV` across its range) match:
  167 cases in 27 designs, `-n 40 --seed 3`.
- The harness alone (IBUFs, one OBUF and GND, on the QFN88P pins chosen by
  `pick_pins`) differs in 24 non-routing bits, in I/O and corner tiles R1C1, R1C2,
  R1C47, R15C1, R16C1, R21C1, R22C1, R25C1, R26C1 and R29C1. They are subtracted
  from every comparison and have not been explained. I/O is the next thing to
  fuzz.
- The segment-isolation fuses (`alonenode_6`, wires `LT00`/`LT10`) differ in some
  designs: Apicula isolates half-spine segments in row 19 that the vendor leaves
  alone. These are routing fuses, so they are masked out. Whether the difference
  matters has not been checked.

## Adding a primitive

Add it to `SITES` in `primitive_strategies.py`, with a site kind. For a new site
kind, `Sites` and `allocate` need to know the sites, and `bel_name` and
`case_bel` need the bel names used by nextpnr and the bel that owns its fuses.
Device-dependent parameter values go in `DEVICE_PARAMS`. Rules involving several
parameters, such as the PLL VCO range in `gowin_pll.py`, are filters on the
strategy.
