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

## Adding a primitive

Add it to `SITES` in `primitive_strategies.py`, with a site kind. For a new site
kind, `Sites` and `allocate` need to know the sites, and `bel_name` and
`case_bel` need the bel names used by nextpnr and the bel that owns its fuses.
`Decoded.find` needs the name `gowin_unpack` gives the cell.
Device-dependent parameter values go in `Primitives.fixed`. Rules involving several
parameters, such as the PLL VCO range in `gowin_pll.py`, are filters on the
strategy.
