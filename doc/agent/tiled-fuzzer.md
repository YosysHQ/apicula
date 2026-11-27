# Tiled fuzzer: comparing Apicula with the vendor on random primitives

`tools/tiled_fuzzer.py` revives the idea of the old tiled fuzzer
(`legacy/tiled_fuzzer.py`, and its earlier version before commit `d350cb7`). That
fuzzer placed many independent test cases in one design, one per site, so a single
vendor run answered many questions. Here the cases are random primitive
configurations, and the question is whether Apicula and the vendor produce the
same fuses for them. IDE **1.9.10.03**.

## Gaps found, for future work

Trivial ones were fixed on the way; these were not. The failing cases, with
the fuse table rows that differ, are in the test output of
`tests/test_fuzz.py`, whose `KNOWN` list holds these bugs (see "Known bugs"
below).

A failing case with omitted parameters may be a default bug. Replay it as a
pair, once with the parameters omitted and once with them set to their
`primitive.xml` defaults (`--replay`). If only the omitted one fails, the default
in `gowin_pack` is wrong; if both fail, the default is not the cause.

**`gowin_pack`**
- **I/O:**
  - one `IO_TYPE` per bank, where the vendor allows any standards of one
    voltage (SSTL18 with HSTL18, SSTL33 with LVCMOS33), and inputs of another
    voltage (`IO_BANK` cases);
  - an output without `IO_TYPE` gets LVCMOS12 in `gowin_pack` (#433)
    (`Device.get_default_io_type`; only `GW5AST_138C` overrides it, with
    LVCMOS33), LVCMOS18 in the vendor on GW1N/GW2A and LVCMOS33 on GW5A-25A
    (its `top.io.cst`), so bank and `DRIVE` rows differ, and on GW5A-25A
    gowin_pack stops with "Default IO_TYPE (LVCMOS12) and BANK_VCCIO
    conflict" on a `BANK_VCCIO=3.3` the vendor accepts;
  - attribute values the vendor calls illegal for the buffer's `IO_TYPE`
    (CT1108: `DRIVE`, `OPEN_DRAIN`, `HYSTERESIS`, `PULL_MODE`, `BANK_VCCIO`)
    are packed rather than rejected (status `accepted`);
  - unused-I/O `BANK_VCCIO` fuses, and bank-tile `IO_TYPE=…,IO_BANK` /
    `BLVDS…` rows;
  - `DRIVE,OPENDRAIN`, `ODMUX`, `PULLMODE`;
  - GW5A output `ODMUX`/`DRIVE` rows (check `fuse_cell_offset` first).
- **I/O logic:** `ODDR` `OUTMODE`; GW5A-25A `FCLKSEL*` and a standalone
  `IODELAY` without its `INDEL`/`IDEL_*` rows and with LSR mux rows the vendor
  leaves off. A flip-flop packed into I/O logic (`IOB_IREG`/`IOB_OREG`/
  `IOB_IOREG`, #668) lacks the `CLKIMUX`/`CLKOMUX`, `SRMODE`, CE mux,
  `OUTMODE=OREG` and register mode rows (on GW5A-25A also `IREG_REGSET`/
  `OREG_REGSET` and IOB rows), and sets LSR mux rows the vendor leaves off.
  Fixed: on GW5 the B-site
  cells are in the IOBB `fuse_cell_offset` tile (see `gw5-devices.md`). Fixed:
  on GW5 the LSR mux
  (`LSRIMUX_0`/`LSROMUX_0`) follows the reset net, off for GND or no reset port
  (`setIolLsrmux @0x308e660`, see `gw5-devices.md`), and OSER8 has no aux
  cell. Fixed: the second half of a two-site primitive (an
  `IOLOGIC_DUMMY`, as in `OSER8`/`OSER10`) took `GSR` from its own, empty
  parameters instead of the main cell's `GSREN`, and `LSREN=false` left
  `LSROMUX_0=1` on `OSER4` and on the `DDRENABLE` half of `OSER8`/`OSER10`
  (`fusegenMem::setIolODDR @0x308ac42`). `IDES16`/`OSER16` take `GSR` and the LSR mux
  on their two pin sites from `GSREN`/`LSREN`, which nextpnr copies onto those
  cells (YosysHQ/nextpnr#1919); the helper site in the next tile stays at
  `ENGSR` and mux 1.
- **BSRAM:**
  - GW5A `SDPB`/`SDPX9B` with a 32/36-bit read port (`BIT_WIDTH_1`) and a
    narrower write port: Apicula sets `DBLWB=X36`, the vendor does not (4 of 4
    such cases on GW5A-25A; equal widths pass);
  - GW5A-25A: nextpnr rejects `BIT_WIDTH_0` of 32/36 with a different
    `BIT_WIDTH_1` ("The fix for SDP when ports A and B have different bit
    widths has not yet been implemented");
  - byte enables (`BELB`/`BEHB`) of the 16/18-bit port of a `DPB`/`DPX9B`
    with mixed port widths: Apicula enables them, the vendor does not. Seeds 2
    and 3 (`-n 20`) on GW1N-9C and GW2A-18C: 14 of 14 such cases differ per
    device, while the 4 mixed-width `DPB` cases without a 16-bit port and all
    equal-width cases pass.
- **PLL:** GW2A `rPLL` `FBSEL`; GW5A `PLLA` phase/duty, charge pump, loop
  filter, `KVCO`, `ODIVn`, dynamic enables.
- **DSP:**
  - GW1N/GW2A input register muxes (`AIRMUX`/`BIRMUX`), `RSTGEN*MUX`, and the
    pre-adder `PRAD_MUXA1`/`PRAD_MUXB`/`PRAD_FBB1`/`IRMATCH` rows;
  - `ALU54D` on GW1N-9C: CI's all-default case differs in the `DSP1`
    `IRMATCH`/`PRAD` rows on every run, but the same case and 9 others pass
    in a seed-2 run with ALU54D and DCS alone, so the trigger is not in the
    parameters (inferred: the site or the other cases of the design). On
    GW2A-18C `ALU54D` matches: 4 distinct cases in CI and 10 at seed 2. With
    the IOB register cases added, CI's draw (seed 7) puts an `ALU54D` in the
    same DSP block as a `MULT18X18`, and both get the same nine differing
    `DSP1` `AIRMUX`/`BIRMUX`/`IRMATCH` bits, attributed to both by tile
    (inferred: the `MULT18X18`'s); the same `ALU54D` case passes on GW1N-9C
    in that run;
  - `MULTALU36X18` on GW2A-18C: CI's draw (seed 7) puts one in DSP block
    (18, 37) with a `PADD18`, and it gets the `PADD18`'s `PRAD_MUXA1`,
    `PRAD_FBB1` and `IRMATCH` rows, attributed by tile (inferred: the
    `PADD18`'s); the same case passes in another block of the same run;
  - GW5A `MULT27X36` `MULT_RESET_MODE`, `CASO`, CE muxes;
  - GW5A `MULTALU27X18` `PRELOAD_BIT`/`DYN_P_ADDSUB`;
  - GW5A `MULTADDALU12X12`/`MULTALU27X18` with `ACC_SEL` or `C_SEL` omitted: the
    vendor sets the `ACC_SEL=0`/`C_SEL=1` rows, Apicula's integer defaults set
    none.
- **Missing handler, fixed:** `FLASH96K` had no `get_…_fuses` method, so GW1N-1
  stopped with `AttributeError`. The vendor sets no fuses outside routing for it.
- **GW5A `TLVDS_IBUF_ADC`** on the vendor's pins raises "IO(0, 0) has ADC bus 0,
  but used in bus 2". `ADC` itself matches the vendor in every case since the
  fuzzer omits parameters (bd8c167); an earlier `5A_PCLK_ENABLE` difference
  did not come back in the 6 distinct cases the vendor has accepted since
  (CI's seed 7 and a seed-3 run on GW5A-25A; it rejected 7 more).
- **`I3C_IOBUF`** (GW1N-9C): the vendor sets `DRIVE`/`OPENDRAIN` rows in IOBB that
  Apicula does not. **`MIPI_OBUF`**: Apicula sets an `IO_TYPE=…` IOB row and the
  vendor a bank row instead.
- **Rejects legal settings:**
  - `ALU_MODE=5` (no chipdb mode);
  - GW5A `OSCA` `FREQ_DIV=3`;
  - constant `CIN` is done with a head ALU, where the vendor folds it into the
    ALU's LUTs.

**nextpnr**
- `INS_LOC` is parsed but never applied.
- `SDP`, `DP` and `ROM` give "Unsupported BSRAM type".
- A constrained `rPLL` on GW2A-18C is bound twice.
- `IODELAY` on GW5A-25A failed an internal check (`DLYSTEP` port); fixed in
  YosysHQ/nextpnr#1923, which rejects dynamic and adaptive delay.
- A BEL attribute on `RAM16SDP2/4` crashes nextpnr, and on `RAM16SDP1` or a DSP
  leaves helper cells unplaced. ALU clusters ignore BEL.
- No bel for `RAM16S1/2/4`.
- No bel for the GW1N/GW2A `PLL` primitive, only `rPLL`.
- `DCS_MODE` is read from attributes only (`globals.cc`), so a `defparam` is ignored and every DCS is packed as `RISING`. The
  HIL test `examples/hil/dcs.v` sets it as an attribute.
- `DCS` on GW5A-25A with inputs from I/O pins crashes in "Routing globals".
- No cell for `LUT5`–`LUT8`, `MUX2`, `IDES14`, `IDES32`, `OSER14`, `DDRDLL`,
  `DHCE`, `DCE`, `OTP`, `SAMB`, `CMSERA`, `ELVDS_IBUF_MIPI`, `IBUF_R`,
  `IOBUF_R`, `ELVDS_IBUF_R`/`ELVDS_IOBUF_R`, `MIPI_IBUF_HS`/`_LP`.
- `DPX9`, `SDPX9` and `ROMX9`: "Bel … of type 'BSRAM' does not match cell".
- MIPI and I3C buffers on the pins the vendor chose: "Can't place MIPI … at
  X36Y0/IOBA", "Not I3C capable"; `MIPI_OBUF_A`: "ports IL and I are in different
  networks". GW5A `DLLDLY` cannot take its clock from an input pin.
- Around user flash (`FLASH96K`, `FLASH608K`, `FLASH64KZ`) nextpnr adds LUTs and
  flip-flops that the vendor does not.
- BEL is ignored on `CLKDIV`/`CLKDIV2`; on GW5A-25A there is no `CLKDIV_1` bel
  where the vendor uses `HCLKDIV1`. No bel for `BUFS`.

**Yosys cell library**
- Latches use `CLK`/`CE` where the vendor has `G`/`GE`.
- `DLP*`/`DLNP*` `INIT` default 0, vendor 1.
- Missing primitives: `rROM`, `rROMX9`, `rSDP`, `rSDPX9`, `IODELAYA`, `IODELAYC`,
  `DLL`, `DCC`, `MUX4`–`MUX32`, `ADC_DB` (Yosys fails with "Failed to get
  direction for port").

**`gowin_unpack`**
- SSTL/HSTL `IBUF` decode as `OBUF`; `TBUF` as `IOBUF`; differential buffers as
  their single-ended or tristate forms.
- `IDDR`/`ODDR`/`IODELAY` and several `OSER`/`IDES` give no cell or the wrong one.
- PLL reverse mapping: `PSDA_SEL`, `DUTYDA_SEL`, `DYN_SDIV_SEL`, delay steps.
- No `rPLL` cell on GW2A.
- `OSCA` written as `OSC`.
- No BSRAM parameters.

**Fuzzer coverage still missing** (harness limits; the vendor rejects these cases)
- `_MEM` I/O logic (`IDDR_MEM`, `IDES4/8_MEM`, `ODDR_MEM`, `OSER4/8_MEM`) needs a
  DQS-driven clock (PR2060); `DHCENC` needs I/O logic on `CLKOUTN` (PR0026);
  `IEM` needs a buffer (PR0018); `OSIDES32/64` need differential fast clocks
  (PR1113); `MUX2_MUX8`+ need `MUX4`… drivers (PA2068); `GW_JTAG` takes the JTAG
  pins (PR1079).
- GW1N-9C `MIPI_IBUF*`: the vendor fails to place MIPI buffers (PR1082) when
  the harness output pin shares a bank with them. On QFN88 bank 1 holds the MIPI
  inputs, bank 2 the MIPI outputs and bank 3 is SiP-locked, so one of them pays;
  the harness takes bank 1. nextpnr rejects `MIPI_IBUF*` anyway.
- SiP-locked banks (GW1N-9C, GW1NS-4) get no I/O cases: the vendor moved
  outputs constrained there to other pins (CT1136, #622).
- I/O attributes beyond IO_TYPE, BANK_VCCIO, PULL_MODE, HYSTERESIS, DRIVE,
  SLEW_RATE, OPEN_DRAIN and DIFF_RESISTOR.

## Pipeline

1. **Generate.** `tools/primitive_strategies.py` builds Hypothesis strategies from
   `primitive.xml` (see [primitive-params.md](primitive-params.md)). One example is
   one primitive instance (a "case"). Cases are drawn per primitive, so each gets
   equal coverage. Hypothesis is used only to generate values; nothing is
   shrunk, because a case is already a single primitive.
   - **Parameters are set or omitted** at random, as in real designs, so the
     defaults `gowin_pack` falls back on are tested too. Always set: the fixed
     parameters (`DEVICE`, `INIT_RAM_*`) and a LUT's `INIT`, without which the
     LUT is folded away. Fixups and `RULES` see an omitted parameter at its
     `primitive.xml` default.
2. **Batch.** Each case gets a site of its kind (a `Kind` class in
   `tiled_fuzzer.py`; see "Site kinds"). A slice holds two LUT cases or one DFF
   case. Cases that must be alone get a design each.
3. **Run.** The same netlist and `.cst` go to both flows, at the same time unless
   one needs the other's placement. `-j` runs several designs at once.
   - vendor: `codegen.Pnr.run_pnr`, with placement fixed by `INS_LOC`;
   - Apicula: Yosys (read only, no synthesis), nextpnr, then `gowin_pack`.
     Placement is fixed by `BEL` attributes added to the Yosys JSON.
4. **Compare through the unpacker.** The chipdb exists by the time the fuzzer
   runs, so both bitstreams are unpacked with `gowin_unpack`.
   Each case sits on a known bel, so only the cell found there is compared:
   type, parameters (LUT INIT included), and which inputs are tied to a
   constant. Nets are not traced. `tools/unpacked_netlist.py` joins the
   `assign` and `` `define `` statements only to see whether an input is VCC or
   VSS. Flip-flops are put in one form: no E means CE=VCC, and a set/reset
   input tied to VSS means no set/reset.
   - vendor ≠ Apicula: **mismatch**, a packer difference;
   - vendor = Apicula, but Apicula ≠ generated: **decode**, an unpacker bug or a
     mistake both make.
5. **Compare fuses.** As a backstop for fuses the unpacker does not decode, both
   bitstreams are also split into tiles. Routing fuses are masked: `pips`,
   `clock_pips`, `alonenode` and `alonenode_6`. Each remaining difference is
   assigned to a bel (LUT INIT fuses, the `CLSn` slice table) and so to the case
   placed there, else to the case on the tile, its I/O bank, or the case alone
   in its design. Differences that a design with no cases also shows (the I/O
   harness) are subtracted. Reports name the fuse table rows of each bit.
6. **Split.** A design that fails in either flow is split in half until the
   failing case is alone. A design Apicula fails although each of its cases
   passes alone is a failure of its own (a "combination").

`--replay` reruns saved failing cases (`<status>_<name>.json`), one per
design, to confirm a failure in isolation.

## Things the harness must get right (checked by running both flows)

- **nextpnr ignores `INS_LOC`.** Its `cst.cc` parses the line but has no
  `case insloc` handler. "Placed 0 cells based on constraints" in the log means
  this happened. A `BEL` attribute such as `X22Y3/LUT2` works.
- **The two flip-flops of a slice share clock, CE and set/reset modes.** Giving
  them different DFF types makes the vendor drop one with `CT1094 can't be
  placed according to constraint`.
- **Dummy nets, as in the old tiled fuzzer.** Data inputs (LUT `I0`–`I3`, DFF
  `D`) get their own undriven wire, and outputs are left unconnected. The vendor
  keeps cells whose outputs are unused: a LUT4's INIT fuses were identical with
  and without a load. Two earlier wirings failed:
  - Chaining one case's output into the next let the vendor propagate a
    constant, turning `LUT1` INIT `2'b10` into a constant `ffff`.
  - Driving LUT inputs from input pins made the vendor's router connect them to
    A–D in its own order and rewrite INIT to match. 15 of 16 LUT differences were
    exact input permutations. With undriven inputs the vendor's INIT matched the
    generated one exactly in 12 of 12 LUTs.
- **Slice control inputs are driven.** Undriven CE and set/reset inputs become
  constants in both flows, so a DFFRE decodes as a DFFR with CE=VCC, and the
  flip-flop type cannot be checked. CLK, CE and SET/RESET/PRESET/CLEAR therefore
  come from input pins. They use dedicated slice ports, so nothing can be
  reordered. SSRAM `WRE` comes from a pin too: the vendor folds a constant
  `WRE` into the slice's LSR mux rows, which Apicula does not.
- **The netlist dialect.** Every port must be connected (PA2058), and sized
  constants on ports are rejected (PA2000). Bus inputs go to a `GND` cell's net.
  Bit-vector parameters must be written in the radix of their default in
  `primitive.xml`: LUT3 INIT `8'b10010101` and DFF INIT `1'h1` are both rejected
  with PA1002 (invalid parameter value), while `8'h95` and `1'b1` are accepted.
  `CT1094` marks a case invalid rather than a mismatch; `PA1002` is a
  rejection (see "Reject agreement").
- **`codegen.Pnr.read_err_log` recorded nothing** until this branch. It kept only
  lines starting with `Warning` or `Error`, while 1.9.10.03 writes `WARN` and
  `ERROR`.
- **Buses are per bit.** The vendor rejected a `wire [7:0]` on the output bus of
  `DLL` with PA2060, "crosses the bits border". A concatenation of eight 1-bit
  wires is accepted, so bus ports are wired that way.
- **The `.posp` file has no cell placements** in this IDE version, so vendor
  placement is checked through the `CT1094`/`CT1005` warnings instead.
- **SiP-locked banks get neither harness pins nor I/O cases** (`package_pins`,
  banks in `db.sip_cst`). The vendor moved outputs constrained to banks wired to
  in-package memory to other pins (CT1136, #622), which showed up as
  unattributed fuses and as I/O rows spilling into cases. Which VCCIO the
  in-package memory sets on those banks is not traced.
- **Harness pins in MIPI-output banks come last** (`pick_pins`): the vendor fails
  to place `MIPI_OBUF` (PR1082) when the harness output pin shares its bank;
  harness inputs there did not stop it (GW1N-9C). Sorting rather than filtering
  keeps five harness inputs on GW1NS-4 QFN48P, which then has no plain pin left
  for I/O cases (banks 0 and 3 are SiP-locked, bank 2 holds MIPI outputs).
- **No I/O case shares a tile with a harness pin** (`Sites`): nextpnr places
  most I/O logic only with the other pin of its tile free
  (`check_iologic_placement`), and `IDES16`/`OSER16` also need both pins of
  the AUX tile (`check_io16_placement`). Before, some seeds put `IDES4`,
  `IDES8`, `IDES16`, `OSER16` or `IVIDEO` next to a harness pin, and nextpnr
  stopped with "already taken by harness_ib_in4". The sites are filtered after
  the shuffle, so the random state and the cases are unchanged; only I/O
  cases can land on other pins.
- **The harness clock goes on a clock-only true clock pin**: one whose only
  functions are `GCLK*`, so no PLL input or feedback and no config pin, and
  `GCLKT` before `GCLKC`. Measured on one pair only: on GW1N-9C pin 51
  (`GCLKC_3`) made `DHCEN` differ from the vendor, while pin 52 (`GCLKT_3`)
  matches. The PLL/config exclusion is a precaution, not a measured failure.
- **The ECLK select is routing.** nextpnr takes an I/O logic `FCLK` over HCLK
  lane 1 (`HCLK_OUT2/3`) and the vendor over lane 0. The vendor sets
  `CLKODDRMUX_ECLK`/`CLKIDDRMUX_ECLK` from the block's HCLK source
  (`fusegenMem::getIoblkHclkSrc`, called from `setIolODDR`, `setIolIDDR` and
  `setIolLargeODDRAttr`), so the `ECLK1` rows only follow that choice. Their
  fuses are masked like the HCLK pips, except those another row also uses. The
  mask also hides a wrong ECLK select, and nextpnr's lane-1 route has not been
  tested on hardware with an `OSER`.

## Unpacker findings

- **Fixed: negative-edge flip-flops decoded as latches, and negative-gate
  latches as positive ones.** In the `CLSn` tables, the rows `(REGMODE=FF,
  CLKMUX_CLK=INV)` and `(REGMODE=LATCH, CLKMUX_CLK=SIG)` have the same single
  fuse, so `parse_attrvals` kept both and reported LATCH. Only the row
  `REGMODE=LATCH` alone has a fuse of its own. `parse_attrvals` now rejects a
  candidate row if one of its attribute values has its own single-key row
  whose fuses are not set, following the vendor's matching rule in
  [primitive-to-fuse.md](primitive-to-fuse.md). Checked on fuzzer bitstreams and
  on a vendor design with all 12 latch types; text comparison of unpacked
  Verilog is useless for this, as unpacking twice differs by set ordering.
- I/O logic `GSREN` comes from the row `GSR=DISGSR`, `LSREN` from the presence
  of `LSRIMUX_0`/`LSROMUX_0`. For OSER8 and wider, `LSROMUX_0` sits in the
  `DDRENABLE` partner cell; an unused partner reports both LSR muxes.
- Clock routing and long wires are not followed in the unpacked netlist; the
  fuzzer does not trace nets. Constant LUTs are an assign of `F` to VCC or VSS.

## Site kinds

What each kind relies on, checked by running both flows (IDE 1.9.10.03):

- **Placement.** nextpnr ignores `INS_LOC`, so it gets `BEL` attributes. It
  ignores BEL, or crashes, for ALU clusters, SSRAM and DSP (`placement =
  'nextpnr'`): nextpnr places them and the vendor gets the same place. The
  vendor reports no position for `CLKDIV`/`CLKDIV2`, so nextpnr gets the bel
  read from the vendor's HCLK fuses; it ignores it, so HCLK settings are then
  compared without positions. Pads of other primitives (`lone`) get the pins
  the vendor chose, from its `impl/pnr/top.io.cst`.
- **Wiring rules of the vendor:** I/O logic needs a buffer on its pin (PR0018);
  `CLKDIV2`, `DHCEN`, `DHCENC`, `DHCE` and `DCC` may only drive HCLK loads
  (PR2060) and not dangle (PA2099), so a harness `CLKDIV` follows them;
  `DLLSTEP` needs a DLL (PR2015, PR0015) and `DQSIN` a buffer (PR0014);
  `OSCEN` must be driven, or the vendor clears `OSCZ` power rows.
- **Fuse footprints:** BSRAM also uses the two tiles to its right, DSP its
  `DSP_AUX` tiles, an rPLL its `RPLLB` tiles, a GW5A PLL a bitstream slot, and
  I/O its bank tile.
- **Wide LUTs** are `MUX2_LUT5`–`8` trees with distinct leaf INITs; each leaf
  must reach one root through the mux inputs its index selects, following the
  MUX2 cells `gowin_unpack` writes (each tile's OF3 feeds two `MUX2_LUT8`s).
- **ROM16** becomes a LUT in nextpnr. **INV** becomes a LUT in nextpnr and is
  removed by the vendor.
- **IOB registers** (`IOB_IREG`, `IOB_OREG`, `IOB_IOREG`) are pseudo-primitives:
  a flip-flop of any `DFFS` type the device has, fed by an `IBUF`, driving an
  `OBUF`, or one of each on an `IOBUF`. A design with them runs the vendor
  with `-ireg_in_iob 1`, `-oreg_in_iob 1` or `-ioreg_in_iob 1` (`pnr.opt`) and
  nextpnr with the matching `--vopt`. Both tools pack each such flip-flop into
  the pad's I/O logic and no other case's (measured on GW1N-9C, GW2A-18C and
  GW5A-25A), so the fuses are compared at the `IOLOGIC` bel. The register's Q
  of `IOB_IREG` is left unconnected; both tools still pack it.
- **I/O standards.** A single-ended buffer may omit `IO_TYPE`; the vendor then
  uses LVCMOS18 on GW1N/GW2A and LVCMOS33 on GW5A (read from its
  `top.io.cst` with an `OBUF` on GW1N-9C, GW2A-18C and GW5A-25A), and the
  case is batched by that voltage. It may also set `BANK_VCCIO`, which
  batches it by that voltage when it has no `IO_TYPE`. A case with no
  attributes gets no `IO_PORT` line: the vendor rejects one without
  attributes (CT2000).
- **`IO_BANK`** is a pseudo-primitive: two or three single-ended buffers, each
  with its own type and attributes, on pins of one bank that holds no harness
  pin (`Sites.iobank`, at least three free pins). Buffer n is the param `IO<n>`
  and its attributes `IO<n>_<attribute>`. It is alone in its design, so every
  difference in its bank belongs to it. Outputs of different voltages in one
  bank are rejected by the vendor (CT1136), as is a `BANK_VCCIO` that
  contradicts an `IO_TYPE` (CT1108); see "Reject agreement".

## Running

    GOWINHOME=... pytest tests/test_fuzz.py --device GW1N-9C [--fuzz-jobs 4] -rxX
    GOWINHOME=... python3 tools/tiled_fuzzer.py -d GW1N-9C [-n 20] [--prims LUT4 DFFRE] [-j 4]

One fuzzer run per device makes all designs; `tests/test_fuzz.py` has a test
per primitive, plus one for unattributed tiles, one for failing combinations
and one per pinned case. Known bugs are in its `KNOWN` list (see below); their
failures are logged as xfail. Cases the vendor rejects for the harness or the
netlist (`invalid`) are skipped: a generator limit, not an Apicula failure.
Cases it rejects as illegal must fail in Apicula too (see "Reject
agreement"). Reports are in
`--fuzz-out/<device>`, with `results.json` holding every case.

CI (the `fuzz` job in `.github/workflows/toolchain.yml`) runs the tests for
GW1N-9C, GW2A-18C and GW5A-25A in the `pepijndevos/apicula:1.9.10.03` image,
with the dev Yosys and nextpnr that workflow builds in the same image, the
chipdb from the `python-dist` wheel, pinned Hypothesis and a fixed seed.

## Known bugs

A property test marks a known bug by the region of inputs that triggers it,
not by its symptom. Each `KNOWN` entry has the shape of `RULES` in
`primitive_strategies.py`: a primitive regex (whole name), a device regex
(prefix), a predicate over the case's parameters (Verilog literals, omitted
ones at their `primitive.xml` default) and the reason, with the issue number
where there is one.

- A failing case that no entry matches fails the test, even if its primitive
  has other known bugs. So a new bug in a primitive with known bugs is no
  longer hidden, unless its cases fall in a known bug's region.
- A passing case that an entry matches is reported as a warning: the entry is
  stale, or broader than its bug.
- A bug whose trigger is not known yet gets `any_params`, every case of the
  primitive on those devices, until someone narrows it. nextpnr and Yosys
  gaps keep `any_params` too.
- Where CI shows a primitive passing on a device, its entries leave that device
  out, so a regression there fails.
- It is an allowlist of known vendor mismatches, not a change-detector: the
  expected value stays the vendor's bitstream, and fixing a bug never fails the
  test, it only turns the entry's cases into warnings.
- CI draws the same cases on every run (fixed seed and count). A change that
  alters the draw (a new primitive, a generator change) must update `KNOWN` in
  the same pull request. The failure message lists the cases outside `KNOWN`
  with their parameters.

Unattributed tiles and failing combinations are not per case, and keep a
single reason each.

## Reject agreement

When the vendor rejects a case's settings as illegal, Apicula must reject them
too. A case is *rejected* when the vendor log has one of `REJECT_CODES` about
it (the instance, or a net or pad named after it): `PA1002` (invalid
parameter value), `CT1108` (illegal port attribute, e.g. a `BANK_VCCIO` that
contradicts the `IO_TYPE`) or `CT1136` (a bank voltage that conflicts with a
locked or constrained one; the vendor moves the pad). The vendor writes a
bitstream after these warnings anyway; Pepijn decided that Apicula must not
accept illegal values. If Yosys, nextpnr or `gowin_pack` then stops with an
error, the case is `rejected`, which passes; if Apicula makes a bitstream, it
is `accepted`, a failure.

- Both flows run for a design of a single case even when one of them fails, so
  a rejection can be checked against the other flow. A design of several cases
  that fails in a flow is split as before, and so is one in which the vendor
  rejects any case: a rejection can name an innocent case. `CT1136` names the
  pad that loses the bank voltage, not the case that set it (seen with an
  `IBUF` `BANK_VCCIO=1.2` next to an `OBUF` without `IO_TYPE`, which the
  vendor makes LVCMOS18, on GW1N-9C). A message that names only a harness pad
  names no case: it neither rejects a case nor splits the design.
- Every other vendor error stays `invalid` and is skipped: those are rules of
  the harness or the netlist (PR2060, PR0018, PR1113, PA2085, ...).
- A failing combination does not count if the vendor rejected one of its cases.

### Pinned cases

`PINNED` in `tests/test_fuzz.py` holds cases the generator does not reach,
taken from bug reports: (device, primitive, params, pads, issue, status).
`test_pinned` runs each in a design of its own, at the given pins (in any bank,
SiP-locked ones too) or on the first site of its kind. The status is the one
the case must get: `ok` or `rejected` for a case that must pass, else the
failing status its issue explains, which xfails. Any other status fails, and a
known failure that passes is a warning, as with `KNOWN`. The vendor decides at
run time whether a case passes; the status of a known bug only says how it
fails.

| Issue | Device | Case | Vendor (IDE 1.9.10.03) | Status |
| --- | --- | --- | --- | --- |
| #409 | GW1N-9C, GW2A-18C | rPLL `ODIV_SEL=3` | PA1002 | accepted |
| #622 | GW1N-9C | IBUF LVCMOS33 on pin 80 (bank 3) | sets bank 3 to 1.8 V | mismatch |
| #622 | GW1N-9C | OBUF LVCMOS33 on pin 80 | CT1136, moves the pad | accepted |
| #433 | GW2A-18C | OBUF on IOL47A, `BANK_VCCIO=3.3` without `IO_TYPE` | CT1108 | rejected |
| #433 | GW2A-18C | OBUF on IOL47A, LVCMOS33 with `BANK_VCCIO=1.8` | CT1108 | rejected |
| #433 | GW2A-18C, GW1N-9C | OBUF on IOL47A or pin 26, `BANK_VCCIO=1.8` without `IO_TYPE` | accepts (LVCMOS18) | unsupported |
| — | GW1N-9C, GW2A-18C | `IO_BANK`: OBUF, IBUF and IOBUF, all LVCMOS33, on the first free bank | accepts | ok |

## Adding a primitive

Add it to `SITES` in `primitive_strategies.py`, with a site kind; without one it
runs as `lone`. Each site kind is a `Kind` subclass in `tiled_fuzzer.py`, which
says how its cases are batched (`batch`) and placed (`placement`: INS_LOC and
BEL, a pin, or one tool following the other), its INS_LOC and nextpnr bel, the
bel and tiles its fuses belong to, how its inputs are driven and any extra
netlist, and how a case is described from the unpacked bitstream and from the
generated parameters. A new kind with a pool of sites also needs it in `Sites`.
Device-dependent parameter values go in `Primitives.fixed`. Rules involving several
parameters, such as the PLL VCO range in `gowin_pll.py`, are filters on the
strategy.

## Evidence for the I/O cases and reject agreement

How these cases work is in "Site kinds", "Reject agreement" and "Pinned
cases". Measured with IDE 1.9.10.03, nextpnr b4faf934 and master e6dc4a6,
through the fuzzer's own flow (`--replay` or `run_batch`) unless marked
inferred.

### IOB registers (#668)

- On GW1N-9C, GW2A-18C and GW5A-25A, with DFF, DFFR, DFFRE, DFFNCE, DFFPE and
  DFFNS, both tools pack the flip-flop into the same IOLOGIC. Apicula lacks
  `CLKIMUX`/`CLKOMUX=ENABLE`, `SRMODE=LSR_OVER_CE`, `CEIMUX_1`/`CEOMUX_1`,
  `OUTMODE=OREG`, `OREG_REGSET` and the `*_INREGMODE`/`OUTREGMODE` rows, and
  sets a stray `LSRxMUX_0`. No vendor DRC fired.
- nextpnr's `ioreg_in_iob` packs only IOBUFs, `ireg_in_iob` only IBUFs and
  `oreg_in_iob` only OBUFs; the vendor's options pack the same way, so they
  are passed for the whole design.
- KNOWN: `IOB_IREG|IOB_OREG|IOB_IOREG`, all devices → #668.

### Reject agreement (#409, #433, #622)

- The vendor errors that stay `invalid`, all seen in CI: PR2060, PR0018,
  PR0026, PR1113, PR1016, PR1079, PA2068, PA2050, PA2067, PR1082, PR0003/4,
  PA2085, CT1094.
- The pinned cases' vendor results are in the table under "Pinned cases". The
  generator can't reach them: `ODIV_SEL` is an enum in `primitive.xml`,
  `package_pins` avoids locked banks, and #433's cases need one fixed pin.
- #622's IBUF: the vendor sets bank 3 to 1.8 V, Apicula to 3.3 V (the bank row
  plus 70 IOB rows).
- Harness bugs fixed on the way:
  - `allocate()` looped forever (9.6 GB measured) on a device with no DSP
    (GW1N-1, GW1NZ-1): a shared kind with an empty site pool never empties its
    queue. Such kinds are skipped, as the I/O path already did. No CI device
    lacks a site kind, so no test covers this.
  - A case without `IO_PORT` attributes wrote `IO_PORT "x" ;`, which the
    vendor rejects (CT2000). No line is written.

### I/O standards and IO_BANK

- Without `IO_TYPE` the vendor uses LVCMOS18 on GW1N/GW2A and LVCMOS33 on
  GW5A-25A (its `top.io.cst`, with an `OBUF` on GW1N-9C, GW2A-18C and
  GW5A-25A). `gowin_pack` uses LVCMOS12 (#433): bank and IOB `DRIVE` rows
  differ, and with a `BANK_VCCIO` that fits the vendor's default (1.8 on
  GW1N-9C and GW2A-18C, 3.3 on GW5A-25A) it stops with "Default IO_TYPE
  (LVCMOS12) and BANK_VCCIO conflict". Covered by the generic I/O entry and
  the `IO_BANK` entry; the 1.8 V cases are pinned.
- The vendor accepts, and `gowin_pack` stops with `IO_TYPE conflict` on,
  LVCMOS33 + SSTL33_I + PCI33 in one bank, an LVCMOS33 output with an LVCMOS18
  input, and an LVDS25 output with LVCMOS33 and LVCMOS25 inputs.
- `IO_BANK` has KNOWN entries of its own: explicit `IO_TYPE`s that differ (one
  `IO_TYPE` per bank), an output without `IO_TYPE` (#433), and any attribute
  besides `IO_TYPE` (the attribute rows and the untraced CT1108 legality
  table). Buffers that share one explicit `IO_TYPE` and set nothing else must
  pass on GW1N and GW2A: an `OBUF`, `IBUF` and `IOBUF`, all LVCMOS33, replay
  `ok` on GW1N-9C and GW2A-18C. On GW5A-25A the same case, two LVCMOS33
  `IBUF`s and two `IBUF`s without `IO_TYPE` all differ: a bank row of the
  input-only bank, the outputs' IOB `PULLMODE`/`SLEWRATE`/`IOB_UNKNOWN67`
  rows, and without `IO_TYPE` the `LVDS_OUT` rows of the bank's unused pins.
  So `IO_BANK` keeps an `any_params` entry on GW5A.
- `Sites.iobank` needs a bank with no harness pin and three free pins; on
  GW1N-9C only bank 2 qualifies.

### Bugs not given a new test

- #534: TLVDS_OBUF LVDS25 @ IOT16A/B with the clock LVCMOS33 @ IOT27A
  differs in fuses on GW2A-18 and GW2A-18C alike: the vendor sets bank 0 to
  3.3 V, Apicula to 1.2 V (`get_lvds_bank_vccio`) with a `BANK_VCCIO` row on
  every IOB of the bank. The existing `TLVDS_(OBUF|TBUF|IOBUF)` / `GW2A` KNOWN
  entry tracks it.
- #547: OBUF LVCMOS33 @ IOB7A on GW1N-1 passes on master; the same nextpnr
  JSON packed before #548 differs on `IOBA: DRIVE=8,OPENDRAIN=OFF`. Fixed;
  only hardware confirmation is open.

### Devices

No new CI device: every tracked bug except the fixed #547 shows on GW1N-9C,
GW2A-18C or GW5A-25A. Local full runs at `-j 2` (count 2, seed 7): GW1N-9C
635 s (156 designs, 12–13 min in CI), GW1N-1 586 s (195 designs), GW2A-18
847 s (222 designs); inferred CI cost from the 9C ratio ≈1.2: GW1N-1 ≈12 min,
GW2A-18 ≈17 min. Adding one later needs an `UNAVAILABLE` list first: 79 of 89
GW1N-1 invalids and 58 of 85 GW2A-18 invalids are PA2085 (no resource).
