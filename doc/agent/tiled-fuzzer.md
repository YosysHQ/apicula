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
   placed there. Differences that a design with no cases also shows (the I/O harness) are
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
  reordered.
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
- **Not followed: clock routing and long wires.** In the unpacked netlist, nets
  do not reach from the GCLK input pin to the clock spines (`SPINEn`), and
  long-wire taps (`LBO0` → `LTnn` → `LBnn`) are not joined. The fuzzer does not
  trace nets, so this does not affect it.
- Constant LUTs are written as an assign of the `F` wire to VCC or VSS, not as
  a cell. The fuzzer accounts for this.

## Results so far (GW1N-9C)

- All 20 DFF types, LUT1–LUT4 and OSC (`FREQ_DIV` across its range) match:
  167 cases in 27 designs, `-n 40 --seed 3`, by fuses only.
- With undriven data inputs and exact comparison, `-n 40 --seed 7`: all 168
  cases in 28 designs ok. The only vendor warnings were dangling nets and the
  unused clock pin.
- With the unpacked comparison, `-n 3`: all 55 cases ok. Given the master
  unpacker's netlist instead, all 20 negative-edge DFF cases fail, and a LUT INIT
  off by one bit is rejected, so the check can fail.
- The harness alone (IBUFs, one OBUF and GND, on the QFN88P pins chosen by
  `pick_pins`) differs in 24 non-routing bits, in I/O and corner tiles R1C1, R1C2,
  R1C47, R15C1, R16C1, R21C1, R22C1, R25C1, R26C1 and R29C1. They are subtracted
  from every comparison and have not been explained. I/O is the next thing to
  fuzz.
- The segment-isolation fuses (`alonenode_6`, wires `LT00`/`LT10`) differ in some
  designs: Apicula isolates half-spine segments in row 19 that the vendor leaves
  alone. These are routing fuses, so they are masked out. Whether the difference
  matters has not been checked.

## BSRAM (GW1N-9C)

BSRAM cases are placed with `INS_LOC "x" BSRAM_R<row>[n]` (the n-th BSRAM of
the row, see SUG935) and nextpnr's BEL `X<c>Y<r>/BSRAM`. `gowin_unpack` does not
decode BSRAM parameters, so BSRAM is compared on fuses over the BSRAM tile and
its two `BSRAM_AUX` tiles. `INIT_RAM_*` stays at its default, because the vendor
bitstream is built without BSRAM contents (`bit_incl_bsram_init` is 0). Yosys
must also read `cells_xtra_<family>.v`, where `DPB`, `SDPB` and the ROMs are.

First run, `-n 3` over the 11 types nextpnr lists as BSRAM: 33 cases, 16 ok.

- **Unsupported (9 cases):** nextpnr stops with "Unsupported BSRAM type" for `SDP`,
  `DP` and `ROM`, although `type_is_bsram` in `gowin.h` lists them.
- **Mismatch (7 cases), all with `READ_MODE=1'b1`:** the differing fuses are the
  output register rows `SPA/SPB_REGMODE`, `SDPA/SDPB_REGMODE` and
  `ROMA/ROMB_REGMODE = OUTREG`. They are at (25, 11) and (25, 13) of the BSRAM
  tile, and (25, 18) for one `SPX9`. `gowin_pack` sets both halves whenever
  `READ_MODE` is 1. The vendor does not follow that rule:
  - for `pROM` (`BIT_WIDTH` 2), `pROMX9` (9) and `SDPB`, it sets neither;
  - for `SP` (16, `WRITE_MODE 2'b10`) and `SPX9` (18 and 36), it sets bits that
    Apicula leaves clear.

  Other pipelined cases match: `SP` 16 with `WRITE_MODE 2'b00`, `SDPX9B`, and
  `DPB`. Two mismatches were rerun alone with `--replay` and reproduced. The
  vendor's rule has not been read from `libgowin`.
- **Decode (1 case):** a `DPX9B` with `READ_MODE0=1'b1` produced no BSRAM cell
  from `gowin_unpack` for either bitstream, though the fuses agree.

## rPLL (GW1N-9C)

rPLLs are placed with `INS_LOC "x" PLL_L` or `PLL_R`, and nextpnr's BEL
`X<c>Y<r>/PLL` (not `RPLLA`, the chipdb bel name). `CLKIN` is driven from the
clock pin. Fuses are compared over the `RPLLA` tile and its `RPLLB` neighbours.
Random dividers almost never meet the vendor's frequency checks (PA2078), so
`pll_dividers` in `primitive_strategies.py` draws FCLKIN, IDIV_SEL, FBDIV_SEL
and ODIV_SEL within PFD 3–400 MHz, VCO 400–1200 MHz and output 3.125–600 MHz.
The VCO range is from the vendor's message for GW1NR-9C.

`-n 8 --seed 5` (8 cases) and an earlier pair:

- **Packing matches.** The decoded PLL attributes are identical in the vendor's
  and Apicula's bitstreams in all 10 cases, and the fuse comparison is clean.
- **Decoding does not.** Every case is **decode**: the unpacker's reverse
  mapping (`pll_attrs_refine` in `gowin_unpack.py`) does not give back the
  generated `PSDA_SEL`, `DUTYDA_SEL`, `DYN_SDIV_SEL`, `CLKOUT_DLY_STEP` or
  `CLKOUTP_DLY_STEP`. Some examples: `DYN_SDIV_SEL` 16 → 32, 56 → 120, 34 → 58;
  `CLKOUT_DLY_STEP` 4 → 1; `CLKOUTP_DLY_STEP` 0 → 1.5. Part of this is
  don't-care values: with `DYN_DA_EN` true both tools write `PSDA_SEL` and
  `DUTYDA_SEL` as `1111`. The static cases are not explained.
- `DEVICE` is left out of the comparison. It sets no fuse, and the unpacker
  writes the family name (`GW1N-9C` for `GW1NR-9C`).

## I/O buffers (GW1N-9C)

`IBUF`, `OBUF`, `TBUF` and `IOBUF` cases carry IO_PORT attributes, not
parameters: an `IO_TYPE` (single-ended standards for now) and a random subset of
`PULL_MODE` and `HYSTERESIS` (inputs) and `DRIVE`, `SLEW_RATE`, `OPEN_DRAIN`
(outputs). The values are those the chipdb's IOB logicinfo knows.

- **Placement and wiring.** Each buffer goes on a plain package pin with
  `IO_LOC`, which nextpnr honours, so no BEL attribute is needed. Its pad is a
  top-level port. Its data and enable inputs come from the harness pins.
- **Bank voltage.** Cases are grouped by the voltage their `IO_TYPE` needs. The
  harness pins use the matching LVCMOS standard, and each voltage class gets its
  own baseline.
- **Fuse ownership.**
  - bits only in the `IOBA` or `IOBB` longval table belong to that buffer;
  - bank-tile bits belong to every I/O case in the bank;
  - differences in I/O tiles with no case go to the I/O cases of the same bank,
    because unused I/Os follow the bank settings.
- **Combination failures.** When Apicula fails on a whole design that the vendor
  accepts, that counts as a failure ("unsupported combinations"), even if every
  case passes alone.

### Results: `-n 15 --seed 11`, 60 cases

| | Count |
|---|---|
| mismatch | 22 |
| decode | 16 |
| unsupported (single case) | 22 |
| unsupported combinations | 48 designs |

None ok. Each finding below was seen in at least one case. None has been
checked against `libgowin`.

**Apicula refuses designs the vendor builds**
- **One `IO_TYPE` per bank.** `gowin_pack` raises "IO_TYPE conflict" when two
  standards with the same voltage share a bank: SSTL18 with HSTL18, SSTL with a
  LVCMOS33 or LVCMOS18 harness pin. The vendor accepts these. This causes all 48
  combination failures and most single-case ones.
- **Missing standards.** `PCI33` and `HSTL15_I` raise `KeyError` in `gowin_pack`,
  and so does `HSTL18_II`, as `'HSTL'` after the alias.

**Fuse differences**
- **CLAMP:** for `IBUF`s with LVCMOS15, LVCMOS25 and PCI33, the vendor sets a fuse
  in the `CLAMP=ON` / `CLAMP=PCI` rows that Apicula never sets. `gowin_pack`'s
  input defaults have `CLAMP=OFF`.
- **Unused I/Os:** with a PCI33 `IBUF` in bank 2, Apicula sets the
  `BANK_VCCIO=1.2/1.8` row fuses on every unused I/O in the bank and the vendor
  does not. Also, with the harness alone at LVCMOS33, 168 bits differ across the
  unused I/O tiles of several banks; at LVCMOS18, 22 bits.
- **DRIVE:** `OBUF` LVCMOS12 `DRIVE=16` gets different fuses in the
  `IO_TYPE,DRIVE,OPENDRAIN` rows.
- **Output mux, slew and pull:** for `OBUF` and `IOBUF` LVCMOS15, the `ODMUX_1`,
  `SLEWRATE` and `PULLMODE` row fuses differ, in both directions depending on
  the case.

**Unpacker**
- SSTL and HSTL `IBUF`s decode as `OBUF`, from both bitstreams.
  `gowin_unpack` calls a buffer `OBUF` whenever `ODMUX` decodes; LVTTL33 and
  LVCMOS `IBUF`s decode correctly.
- `TBUF` decodes as `IOBUF`.
- Some `TBUF`/`IOBUF` cases produce no buffer cell.

### Differential buffers (GW1N-9C)

`TLVDS_*` cases go on true-LVDS pairs and `ELVDS_*` on the other differential
pairs. The pairs come from the chipdb flags `is_diff` and `is_true_lvds`, and A
is the positive pin. Each side of the pair is a top-level port with its own
`IO_LOC` and `IO_PORT`. The Apicula flow runs `iopadmap` as `synth_gowin` does:
nextpnr expects an `OBUF`/`IBUF` on each differential pad and merges it. The
enables are not inverted, because an inverter would need synthesis to map.
`TLVDS_IOBUF` does not exist on GW1N-9C (PA2085).

`-n 4 --seed 5`, 40 cases. Use `tools/fuzz_report.py` for details.

- **Unused I/Os:** with a `TLVDS` buffer in a bank, Apicula sets the
  `BANK_VCCIO=1.2/1.5/1.8` row fuses on about 175 unused I/O bits that the
  vendor leaves clear.
- **Bank tile:** the vendor sets bank-tile fuses in `IO_TYPE=BLVDS…` combination
  rows (`BLVDS25,SSTL`, `BLVDS_E,LVDS25,BANK_VCCIO=2.5`, …) that Apicula does not,
  and the other way round for `IO_TYPE=BLVDS25,BANK_VCCIO=1.2`.
- **ELVDS fuses:** for `ELVDS_*` the `DRIVE,OPENDRAIN` and `ODMUX` row fuses
  differ.
- **Unpacker:** `TLVDS_OBUF` decodes as `TLVDS_TBUF`; `ELVDS_OBUF` as
  `ELVDS_IOBUF`; `ELVDS_IBUF` and `TLVDS_IBUF` as `IBUF`.
- **Bank voltage of `LVCMOS12D`–`LVCMOS25D`:** added to `gowin_pack`'s table.
  `ELVDS_OBUF` designs with each of the four pack to bitstreams identical to
  master's, so the new entries change nothing there. Their bank tiles differ
  from the vendor's in the same places with and without the change.

### I/O logic (GW1N-9C)

`IDDR`, `ODDR`, `IDES*`, `OSER*`, `IODELAY`, `IVIDEO` and `OVIDEO` cases are
placed with an LVCMOS33 buffer on a pin: an `IBUF` feeds `D`/`DI`, or the
`Q`/`Q0`/`DO` output feeds an `OBUF`. The vendor requires this connection
(PR0018). `CLK`, `PCLK` and `FCLK` come from the harness clock pin.

`-n 3 --seed 1`, 45 cases: none ok; 24 mismatch, 14 decode, 7 invalid.

- **Fast clock select:** Apicula sets `CLKIDDRMUX_ECLK=ECLK1` /
  `CLKODDRMUX_ECLK=ECLK1` in nearly every IDES/OSER/IVIDEO/OVIDEO case, and the
  vendor does not. It may depend on how `FCLK` is routed from the clock pin.
  This has not been separated from the harness.
- **GSR and LSR:** the vendor sets `GSR=DISGSR` and rows with `!LSROMUX_0`, so
  `GSREN`/`LSREN` handling differs.
- **ODDR:** `OUTMODE` rows differ, and so do `ODMUX`/`TRI_MUX` in the IOB.
- **Unnamed bits:** many differing bits are in no table that
  `tools/fuzz_report.py` names yet.
- **Placement rules, vendor `invalid`:** `IDES16`/`OSER16` must be on an "X16
  location" (PR2046), the `io16` role in `extra_func`. `OSER8` and `OVIDEO` could
  not be placed on some pins (CT1094). Sites need restricting for these.
- **Unpacker:**
  - `IDDR`, `IDDRC`, `ODDR`, `ODDRC` and `IODELAY` decode wrongly or not at all.
  - It compared instead of assigning the decoded `CLKODDRMUX_ECLK` and
    `CLKIDDRMUX_ECLK` (`eclk == val`); now fixed.

### I/O on GW2A-18C and GW5A-25A

`-n 3`, single-ended, differential and I/O logic (`IDES16`/`OSER16` excluded
on GW2A-18C, where they do not exist).

**GW2A-18C**

63 cases: 2 ok, 26 mismatch, 22 decode, 13 unsupported, and 25 unsupported
combinations. It shows the GW1N patterns:

- `BANK_VCCIO` row fuses on unused I/Os with an `ELVDS` buffer in the bank;
- bank-tile `IO_TYPE=…,IO_BANK=I50/I55` and `IO_TYPE=BLVDS_E,…` rows;
- input `CLAMP`;
- `DRIVE,OPENDRAIN` rows;
- I/O logic `CLKIDDRMUX_ECLK=ECLK1` set only by Apicula, and `GSR=DISGSR` /
  `LSRIMUX`/`LSROMUX` rows set only by the vendor.

The unsupported cases are the one-`IO_TYPE`-per-bank check.

**GW5A-25A**

- **Output buffers:** in nearly every output, tristate and bidirectional
  buffer case (22 per type), the vendor sets `ODMUX_1` and several
  `IO_TYPE=…,DRIVE=…` / `LVDS_OUT` row fuses on the A side that Apicula does not.
  On GW5A a B bel's fuses are in a neighbouring cell (`fuse_cell_offset`), and
  the fuzzer's IOBA/IOBB attribution does not model that yet. Check this before
  reading it as a packer bug.
- **Inputs:** the vendor sets `PULLMODE` and `IO_TYPE=…,HYSTERESIS=ON` row fuses
  for inputs.
- **I/O logic:** `FCLKSEL*` rows differ (fast clock source).
- **`IODELAY`:** crashes nextpnr: "INTERNAL CHECK FAILED", after "net
  '$PACKER_GND' user port 'DLYSTEP[0]' missing".
- **Unpacker:** `OSER4`, `OSER8`, `IDDR`, `ODDR` and `IDES8` produce no cell;
  `IDDR`/`ODDR` decode as `IDDRC`/`ODDRC`.

## PLLs and oscillators on GW2A-18C and GW5A-25A

**GW2A-18C rPLL**
- Apicula's chipdb marks the two row-10 PLLs disabled, and nextpnr does not
  offer them, so cases use row 46 as `PLL_L[1]`/`PLL_R[1]`. Whether the vendor
  can use the row-10 PLLs has not been checked.
- **nextpnr binds a constrained rPLL twice:** "Cell 'inst0_rPLL' cannot be bound
  to bel 'X55Y45/PLL' since it is already bound to cell 'inst0_rPLL'". This
  happens even with `CLKIN` on a plain pin; GW1N-9C does not do it.
- **`FBSEL` differs** in cases that got through, and `gowin_unpack` finds no
  `rPLL` cell on GW2A.

**GW5A-25A PLLA**
- Six PLLs, configured through bitstream slots rather than tiles. The vendor
  names them by side and row order. Checked by placing one PLL per name and
  seeing which slot has data:

  | Name | Slot | Tile (row, col) |
  |---|---|---|
  | `PLL_L[0]` | 5 | (0, 0) |
  | `PLL_L[1]` | 6 | (27, 0) |
  | `PLL_R[0]` | 3 | (0, 91) |
  | `PLL_R[1]` | 2 | (27, 91) |
  | `PLL_T` | 4 | (0, 45) |
  | `PLL_B` | 8 | (36, 45) |

  nextpnr's BEL is `X<c>Y<r>/PLL`.
- **Comparison:** the fuzzer compares the slot bits, and the slot decoded with
  `parse_attrvals` on `shortval[1024]['PLL']`.
- **Rules,** all from vendor messages:
  - PFD `FCLKIN/IDIV_SEL` 19–400 MHz;
  - VCO `FCLKIN·FBDIV_SEL·(MDIV_SEL+MDIV_FRAC_SEL/8)/IDIV_SEL` 800–1600 MHz;
  - `CLKOUTn_PE_COARSE < ODIVn_SEL`. The PA2096 message says "less than or
    equal", but all 7 cases with equal values were rejected;
  - channel n disabled when `CLKn_OUT_SEL=1'b1`;
  - `DEn_EN` and `DYN_PEn_SEL` FALSE unless `DYN_DPA_EN`.
- **Results,** `-n 8`: 7 of 8 cases decode differently from the two bitstreams.
  - phase and duty (`CLKOUTn_PE_COARSE/FINE`, `DT_DIR`, `DT_STEP`);
  - charge pump and loop filter (`ICP_SEL`, `LPF_RES_SEL`, `LPF_CAP_SEL`) and
    `KVCO`;
  - `ODIVn_SEL` rows that only Apicula's decode shows;
  - `DEn_EN`/`DYN_PEn_SEL` set by Apicula, and `DYN_DPA_EN`/`SSC_EN`/
    `FLDCOUNT` set by the vendor.

  Apicula's PLLA encoding needs work. The decode of overlapping rows should be
  checked against the fuses first, as AGENTS.md advises.

**GW5A-25A OSCA**
- `FREQ_DIV` is 2..126 even, plus 3. The vendor accepts 3, but `gowin_pack`
  raises "Divisor ... must be even".
- `gowin_unpack` writes an OSCA as `OSC`. `FREQ_DIV` decodes the same from both
  bitstreams.

## Latches and ALUs (GW1N-9C)

**Latches.** The 12 `DL*` types use the flip-flop slots.
- The vendor names the gate `G` (and `GE` on `DLCE`), where Yosys' cell library
  has `CLK` (and `CE`), so a vendor-style netlist with latches does not go
  through Yosys. The fuzzer's Apicula side renames the ports to test the fuses.
- `-n 2`: packing matches in all 24 cases.
- The unpacker decoded every negative-gate latch as positive, because
  `get_latch_type` defaulted `CLKMUX_CLK` to `SIG`. The CLS fuse of
  `(LATCH, SIG)` is the one of `(FF, INV)`, so a latch without it has an inverted
  gate. Fixed. Only the `DLN*` cells change in unpacked fuzzer bitstreams.

**ALU.**
- **Placement:** nextpnr places ALU clusters itself and ignores `BEL`, so ALU
  cases run through Apicula first, and the vendor gets nextpnr's location as
  `INS_LOC Rr Cc[cls][A|B]` (`FOLLOW_NEXTPNR`). `CIN` is tied to GND.
- **Results,** `-n 10`: 1 ok, 8 mismatch, and 1 unsupported (plus its 4
  combinations).
  - **Constant carry-in:** the vendor folds a constant `CIN` into the ALU's own
    LUT configuration, which decodes as a raw LUT ALU (54 LUT fuses). nextpnr
    instead inserts a carry-in head ALU.
  - **`ALU_MODE=5`** is allowed by `primitive.xml` and accepted by the vendor,
    but the chipdb's ALU modes are 0–4, 6–9, `C2L`, `ONE2C` and `hadder`. So
    `gowin_pack` raises `KeyError: '5'`.

## Adding a primitive

Add it to `SITES` in `primitive_strategies.py`, with a site kind. For a new site
kind, `Sites` and `allocate` need to know the sites, and `bel_name` and
`case_bel` need the bel names used by nextpnr and the bel that owns its fuses.
`Decoded.find` needs the name `gowin_unpack` gives the cell.
Device-dependent parameter values go in `Primitives.fixed`. Rules involving several
parameters, such as the PLL VCO range in `gowin_pll.py`, are filters on the
strategy.
