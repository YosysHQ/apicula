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
4. **Compare through the unpacker.** The chipdb exists by the time the fuzzer
   runs, so both bitstreams are unpacked with `gowin_unpack`.
   `tools/unpacked_netlist.py` joins the `assign` and `` `define `` statements
   into nets. Each case's cell is described the same way for the vendor, for
   Apicula and for the generated case: cell type, parameters, and the harness
   pin feeding each input. Tracing passes through the pass-through LUTs
   (`16'hff00`) both tools put in front of a DFF's D input. A LUT is described
   by its truth table over the harness pins, which makes the vendor's input
   permutation irrelevant. Flip-flops are put in one form: no E means CE=VCC,
   and a set/reset input tied to VSS means no set/reset.
   - vendor ≠ Apicula: **mismatch**, a packer difference;
   - vendor = Apicula ≠ generated: **decode**, an unpacker bug or a mistake both
     make;
   - an input that could not be traced in the unpacked routing is a wildcard,
     and the case is **partial** rather than ok.
5. **Compare fuses.** As a backstop for fuses the unpacker does not decode, both
   bitstreams are also split into tiles. Routing fuses are masked: `pips`,
   `clock_pips`, `alonenode` and `alonenode_6`. Each remaining difference is
   assigned to a bel (LUT INIT fuses, the `CLSn` slice table) and so to the case
   placed there. LUT INIT fuses are skipped, because of the permutation.
   Differences that a design with no cases also shows (the I/O harness) are
   subtracted.

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
  input permutations. The 16th was the constant propagation above. This is why
  LUTs are compared as truth tables over the traced input pins.
- **The netlist dialect.** Every port must be connected (PA2058), and sized
  constants on ports are rejected (PA2000). Unused inputs go to a `GND` cell's
  net. `PA1002` (invalid parameter value) and `CT1094` mark a case invalid rather
  than a mismatch.
- **Bus outputs.** The vendor rejected a `wire [7:0]` connected to the output
  bus of `DLL` with PA2060, "crosses the bits border". Primitives with bus
  outputs will need a different way of leaving outputs unconnected.
- **The `.posp` file has no cell placements** in this IDE version, so vendor
  placement is checked through the `CT1094`/`CT1005` warnings instead.

## Unpacker findings

- **Fixed: negative-edge flip-flops decoded as latches.** In the `CLSn` tables,
  the rows `(REGMODE=FF, CLKMUX_CLK=INV)` and `(REGMODE=LATCH, CLKMUX_CLK=SIG)`
  have the same single fuse, so `parse_attrvals` kept both and reported LATCH.
  Every `DFFN*` came out as `DL*E`, and those with set/reset produced no cell at
  all. Only the row `REGMODE=LATCH` alone has a fuse of its own. `parse_attrvals`
  now rejects a candidate row if one of its attribute values has its own
  single-key row whose fuses are not set. This follows the vendor's matching
  rule in [primitive-to-fuse.md](primitive-to-fuse.md): every row whose keys hold
  contributes its fuses.
  - Checked on six fuzzer bitstreams, by comparing unpacked cells (type and
    parameters) from master and from the fix. The only changes are latches
    becoming the generated `DFFN*` types.
  - Checked on a vendor design with all 12 latch types `DL[N][C|P][E]`. Each
    decodes the same before and after the fix.
  - Text comparison of unpacked Verilog is useless here: unpacking the same file
    twice differs by hundreds of lines, because of set ordering.
- **Not fixed: negative-gate latches decode as positive ones.** `DLN`, `DLNE`,
  `DLNC`, `DLNCE`, `DLNP` and `DLNPE` from the vendor unpack as `DLE`, `DLCE` or
  `DLPE`, before and after the fix. Latches are not fuzzed yet, because the
  vendor calls the gate port `G` while Yosys' cell library calls it `CLK`.
- **Not followed: clock routing and long wires.** Nets do not reach from the
  GCLK input pin to the clock spines (`SPINEn`), and the long-wire taps
  (`LBO0` → `LTnn` → `LBnn`) that nextpnr uses are not joined in the unpacked
  netlist. These inputs are wildcards, so such cases report **partial**.
- Constant LUTs are written as an assign of the `F` wire to VCC or VSS, not as
  a cell. The fuzzer accounts for this.

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
`Decoded.find` needs the name `gowin_unpack` gives the cell.
Device-dependent parameter values go in `DEVICE_PARAMS`. Rules involving several
parameters, such as the PLL VCO range in `gowin_pll.py`, are filters on the
strategy.
