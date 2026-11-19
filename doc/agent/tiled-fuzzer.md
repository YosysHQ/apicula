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
`tests/test_fuzz.py`, where these are the known broken primitives.

**`gowin_pack`**
- **I/O:**
  - one `IO_TYPE` per bank, where the vendor allows any standards of one
    voltage (SSTL18 with HSTL18, SSTL33 with LVCMOS33);
  - unused-I/O `BANK_VCCIO` fuses, and bank-tile `IO_TYPE=…,IO_BANK` /
    `BLVDS…` rows;
  - input `CLAMP`;
  - `DRIVE,OPENDRAIN`, `ODMUX`, `PULLMODE`;
  - GW5A output `ODMUX`/`DRIVE` rows (check `fuse_cell_offset` first).
- **I/O logic:** `CLKIDDRMUX_ECLK`/`CLKODDRMUX_ECLK=ECLK1`, `GSR=DISGSR`,
  `LSRIMUX`/`LSROMUX`, `ODDR` `OUTMODE`; GW5A `FCLKSEL*`.
- **BSRAM:**
  - GW5A `SDPB`/`SDPX9B` `DBLWB=X36`;
  - GW5A-25A: nextpnr rejects `BIT_WIDTH_0` of 32/36 with a different
    `BIT_WIDTH_1` ("The fix for SDP when ports A and B have different bit
    widths has not yet been implemented").
- **PLL:** GW2A `rPLL` `FBSEL`; GW5A `PLLA` phase/duty, charge pump, loop
  filter, `KVCO`, `ODIVn`, dynamic enables.
- **DSP:**
  - GW1N/GW2A input register muxes (`AIRMUX`/`BIRMUX`), `RSTGEN*MUX`, and the
    pre-adder `PRAD_MUXA1`/`PRAD_FBB1`/`MATCH` rows;
  - GW5A `MULT27X36` `MULT_RESET_MODE`, `CASO`, CE muxes;
  - GW5A `MULTALU27X18` `PRELOAD_BIT`/`DYN_P_ADDSUB`.
- **Missing handler, fixed:** `FLASH96K` had no `get_…_fuses` method, so GW1N-1
  stopped with `AttributeError`. The vendor sets no fuses outside routing for it.
- **Missing handler:** `RAM16SDP1` has no `get_…_fuses` method.
- **GW5A `ADC`:** Apicula sets a `5A_PCLK_ENABLE` fuse the vendor does not.
  `TLVDS_IBUF_ADC` on the vendor's pins raises "IO(0, 0) has ADC bus 0, but used
  in bus 2".
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
- `IODELAY` on GW5A-25A fails an internal check (`DLLSTEP` port).
- A BEL attribute on `RAM16SDP2/4` crashes nextpnr, and on `RAM16SDP1` or a DSP
  leaves helper cells unplaced. ALU clusters ignore BEL.
- No bel for `RAM16S1/2/4`.
- No bel for the GW1N/GW2A `PLL` primitive, only `rPLL`.
- `DCS_MODE` is read from attributes only (`globals.cc`), so a `defparam`, as in
  `examples/dcs.v`, is ignored and every DCS is packed as `RISING`.
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
- I/O attributes beyond IO_TYPE, PULL_MODE, HYSTERESIS, DRIVE, SLEW_RATE,
  OPEN_DRAIN and DIFF_RESISTOR.

## Pipeline

1. **Generate.** `tools/primitive_strategies.py` builds Hypothesis strategies from
   `primitive.xml` (see [primitive-params.md](primitive-params.md)). One example is
   one primitive instance (a "case"). Cases are drawn per primitive, so each gets
   equal coverage. Hypothesis is used only to generate values; nothing is
   shrunk, because a case is already a single primitive.
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
  `PA1002` and `CT1094` mark a case invalid rather than a mismatch.
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
- **The harness clock goes on a clock-only true clock pin**: one whose only
  functions are `GCLK*`, so no PLL input or feedback and no config pin, and
  `GCLKT` before `GCLKC`. Measured on one pair only: on GW1N-9C pin 51
  (`GCLKC_3`) made `DHCEN` differ from the vendor, while pin 52 (`GCLKT_3`)
  matches. The PLL/config exclusion is a precaution, not a measured failure.

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

## Running

    GOWINHOME=... pytest tests/test_fuzz.py --device GW1N-9C [--fuzz-jobs 4] -rxX
    GOWINHOME=... python3 tools/tiled_fuzzer.py -d GW1N-9C [-n 20] [--prims LUT4 DFFRE] [-j 4]

One fuzzer run per device makes all designs; `tests/test_fuzz.py` has a test
per primitive, plus one for unattributed tiles and one for failing
combinations. Known broken primitives are in its `BROKEN` table, with a
reason; their failures are logged as xfail. Cases the vendor rejects are
skipped: a generator limit, not an Apicula failure. Reports are in
`--fuzz-out/<device>`, with `results.json` holding every case.

CI (the `fuzz` job in `.github/workflows/toolchain.yml`) runs the tests for
GW1N-9C, GW2A-18C and GW5A-25A in the `pepijndevos/apicula:1.9.10.03` image,
with the dev Yosys and nextpnr that workflow builds in the same image, the
chipdb from the `python-dist` wheel, pinned Hypothesis and a fixed seed.

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
