# Timing: how the IDE computes delays, compared with Apicula and nextpnr

IDE **1.9.10.03**. Addresses are in `IDE/lib/libgowin.so` of that version.
Evidence labels: **code** = read from decompiled or disassembled vendor code,
**data** = checked against vendor output (SDF, timing report), **inferred** =
neither.

## Summary

The comparison runs on vendor routes. picorv32 attosoc was placed and routed by
the IDE. Its routes were decoded from the IDE bitstream, then evaluated with the
vendor formula reimplemented here and with nextpnr's pip delays. Each result was
compared with the delay of the same connection in the IDE's SDF.

| Device, speed | Connections | Vendor formula vs SDF | nextpnr vs SDF, total | nextpnr/SDF per connection, p10 / median / p90 |
|---|---|---|---|---|
| GW1N-9C C6/I5 | 897 | median 0.3 ps, max 22 ps | +0.7% | 0.97 / 1.02 / 1.07 |
| GW2A-18C C8/I7 | 735 | median 0.4 ps, max 46 ps | −6.4% | 0.89 / 0.96 / 0.99 |
| GW5A-25A C1/I0 | 1305 | old formula does not apply | −1.9% | 0.76 / 1.03 / 1.23 |

Fmax from the same netlist and constraints, with the IDE and nextpnr each doing
their own placement:

| Device | IDE | nextpnr |
|---|---|---|
| GW1N-9C | 57.9 MHz | 58.1 MHz |
| GW2A-18C | 112.8 MHz | 115.0 MHz |
| GW5A-25A C1/I0 | 101.3 MHz | 113.7 MHz |

Findings, most important first:

1. **GW5A timing data was wrong.** `tm_parser` read GW5A files as if they used
   the old fixed layout. The old-format records at the start of
   `GW5A-25A.tm` are placeholders. Their first 14,136 bytes are identical to
   `GW2A-18C.tm`. The IDE reads GW5A delays from a different block, described
   below. Compared with the real GW5A-25A values, Apicula's GW5A cell delays are
   off in both directions. The IDE also scales the slow corner by 1.25 for
   C1/I0. Cell delays now come from the real block. Routing still uses the
   placeholder values; see "What Apicula uses for GW5A". (code, data)
2. **The `_LV` speed grades are the typical corner** (25 °C, nominal Vcc).
   They are not a low-voltage variant. Several other record labels are also
   wrong. See "Record index". (code; data partly consistent)
3. **The quad is `[min, min, max, max]`**, probably rise/fall within each
   pair. It is not FF/FR/RR/RF as `doc/delay_calculations.md` assumes.
   nextpnr takes min and max over all four, so its numbers are unaffected.
   (code)
4. **nextpnr routing on GW1N and GW2A has two small systematic errors.** The
   source-node fanout term (F, Q, OF) is dropped. The fanout term divides by
   the FanNum of the upstream pip's class instead of the node's own class.
   Together these make GW2A about 4% optimistic. (data)
5. **The DFF D pass-through LUT is invisible to the placer.** When a DFF's D
   comes from routing, the IDE adds the LUT input→F delay (`addLutBufDelay`).
   That is 0.2–0.6 ns depending on family. nextpnr inserts the pass-through LUT
   in `postPlace`, so the final report includes the delay but placement does
   not. (code, data)
6. **IO and some special blocks are not parsed.** DL, IDDR/ODDR, IREG/OREG,
   PLL, DLL, CLKDIV and DSP (except MULTADDSUM) are parsed. IO, DQS, DLLDLY,
   DQCE and DCS are not.
   Register-to-register Fmax on one clock does not depend on them. IO paths,
   PLL-derived clocks and DSP paths do. (code)

## Which model the IDE uses

`STA::TmAnalyzer::getWiresDly` (0x2c2df46) dispatches on
`isDeviceBeforeGW5AT138` (0x300c97f). That predicate is true for every GW1N*,
GW2A*, GW1NZ-2, GW1AN device type and false for every GW5A* device type. (code)

- **True:** `STA::TmModel` is used. It is a fixed-layout struct, read verbatim
  from one 0x3cc0-byte record of `DEVICE.tm`. This is the format `tm_parser`
  reads.
- **False:** `STA::TmModelNew` is used. It is a self-describing block read by
  `TmModelNew::readTmData(path, 0x3cc0)`, which seeks to `3 * 0x3cc0`.

`readTimingDataByReportOpt` (0x2c19bc4) always reads one old record at
`index * 0x3cc0` and then, for GW5A, the new block. (code)

### Old record layout (`STA::TmModel::init_dlt`, 0x2d8f0a4)

| Offset | Group | tm_parser |
|---|---|---|
| 0x0 | LUT | parsed |
| 0xb0 | ALU | parsed |
| 0x130 | SSRAM | parsed |
| 0x240 | DFF | parsed |
| 0x390 | DL | parsed |
| 0x4a0 | IDDR/ODDR | parsed |
| 0x7cc | PLL | parsed |
| 0x81c | DLL | parsed |
| 0x85c | CLKDIV | parsed |
| 0x8bc | BSRAM | parsed |
| 0xc8c | DSP (MULT, MULT36X36, MAC, MULTADD, MULTADDSUM, PADD, ALU54) | parsed except MULTADDSUM |
| 0x306c | IREG/OREG | parsed |
| 0x3278 | IO | stub |
| 0x3728 | IODELAY | parsed |
| 0x379c | WIRE | parsed |
| 0x381c | FANOUT | parsed |
| 0x38bc | GLBSRC | parsed |
| 0x39cc | HCLK | parsed |
| 0x3a0c | DQS | missing |
| 0x3bec | DLLDLY | missing |
| 0x3c3c | DQCE | missing |
| 0x3c5c | DCS | missing |

The sub-models are not separate reads: `TmModel` is read verbatim and
`init_dlt` only scales each sub-model in place, so a field's file offset is the
sub-model offset above plus the field offset within the sub-model. (code)

Field names and offsets come from the getters. Each `STA::<X>TmModel::get<Name>(float*)`
copies four floats from `this + disp + 4 * k`, where `k` is added to the loop
index (sometimes as `sub $-k`). `tools/timing/tm_fields.py` lists these for every
sub-model. The offsets reproduce every group `tm_parser` already parsed, with
the same field order, and consecutive sub-models tile without gaps (for example
IREG/OREG at 0x306c ends at 0x3278). (code, data)

- IDDR/ODDR and IREG/OREG start at 0x2c. The first 0x2c bytes hold two quads and
  three zero floats (GW1N-9C: 0.355/0.426 and 0.851/1.021) that no getter reads.
  (data)
- IO (0x3278) has five fields (`Pad_PaddisV`, `Paddo_PadsV`, `Paddt_PadsV`,
  `Ioldo_PadsV`, `Iolto_PadsV`), each an array of ten 0x18-byte entries
  `{IoAttr flags (8 bytes), 4 floats}`, at 0x0, 0xf0, 0x1e0, 0x2d0 and 0x3c0. The
  getters read entry 0 only. `TmAnalyzer::createTmEdgesForIo` and `calcIoTiming`
  presumably choose an entry by IO attributes; not traced. On GW1N-9C only entry
  0 holds delays. (code, data)
- DQS, DLLDLY, DQCE and DCS have no getters, only `print*Delay`, and are not
  parsed.
- IODELAY (0x3728) holds `DI_DO` at 0x0, the delay step (`getStepDly`) as one
  float at 0x10, and the six other fields from 0x14. `tm_parser` called `DI_DO`
  `GI_DO` and read the later fields one float early until this was found. The
  SDF of an IODELAY with `C_STATIC_DLY=8` on GW1N-9C gives SETN→DF 0.316/0.275,
  the first and last values of `SETN_DF`, and DI→DO typical 0.810 =
  `DI_DO` 0.57 + 8 × step 0.030. (code, data)

### DSP (0xc8c)

`DSPTmModel::get<X>TmModel()` gives the sub-model offsets within the DSP block:
MULT 0x0, MULT36X36 0x410, MAC 0x5b0, MULTADD 0x850, MULTADDSUM 0xc90, PADD
0x14a0, ALU54 0x1700. The getters are `get<Name>(int i)`, reading float `i` of a
quad at `this + 4 * K`, and `get<Name>(int j, int i)`, reading float `i` of quad
`j` from `this + 4 * (K + 4 * j)`. The number of quads per two-index field is the
distance to the next field. Every sub-model tiles to the next, except a 16-byte
hole after MULTADD's last field and one after ALU54's `Alusel_Cout`. MULTADDSUM
has no getters. `tm_parser` stores two-index fields as `<name>_<j>`. (code)

Checked against the IDE's SDF on GW1N-9C C6/I5 (data):

| Primitive | Sub-model | Example |
|---|---|---|
| MULT9X9, MULT18X18 | MULT | A/B/ASIGN/BSIGN/ASEL/BSEL→DOUT 0.555/0.506/0.493/0.534/0.510/0.501 = `mdia_mout`, `mdib_mout`, `asign_mout`, `bsign_mout`, `asel_mout`, `bsel_mout` |
| MULT36X36 | MULT36X36 | same values as MULT |
| MULTALU18X18, MULTALU36X18, MULTADDALU18X18 | MULTADD | A0/A1→DOUT 0.269/0.273 = `mdia0_mout`, `mdia1_mout`; B 0.282 = `mdib0_mout`; C and ACCLOAD 0.271 = `addsub_mout` |
| ALU54D | ALU54 | A/B/ASIGN/BSIGN→DOUT 0.271/0.291/0.414/0.292 = `ina_dout`, `inb_dout`, `asign_dout`, `bsign_dout` |
| PADD18 | PADD | A→DOUT 0.451 = `pdia_pout`, ASEL→DOUT 0.562 = `asel_pout` |

- The second index selects by register use. With OUT_REG=1, CLK→DOUT is
  `clk_mout_1` (0.278). `clk_mout_0` (2.318) is CLK→DOUT through the multiplier
  from an earlier register. Input setup is `clk_mdias_1` with AREG=1 and
  `clk_mdias_0` with AREG=0. Some MAC and MULTADD fields have three quads; their
  third case is not identified.
- Setup times in the SDF are element 2 of the quad (`clk_mdias_1` is
  0.045/0.042/0.045/0.052 and the SDF gives 0.045; CE and RESET agree), not the
  maximum. IOPATH delays are the maximum of elements 2 and 3, as elsewhere.
- SDF hold times for registered inputs are negative (A hold -0.069 with AREG=1)
  and do not equal any `*h` field. Not resolved.
- The combinational multiplier delays are much smaller than CLK→DOUT through the
  multiplier (0.555 vs 2.318). That is what the IDE reports.

Checked against the IDE's SDF (GW1N-9C, C6/I5, `ide_io` design in "Method"):

| Arc | SDF max | Field |
|---|---|---|
| IDDR CLK→Q0, Q1 | 0.635, 0.540 | `iddroddr.iclk_q0`, `iclk_q1` |
| IDDR D setup, hold | 0.045, 0.015 | `iddroddr.iclk_dis_p`, `iclk_dih_p` (same for N) |
| ODDR CLK→Q0/Q1 rise, fall | 1.289, 1.273 | `iddroddr.oclk_q_p`, `oclk_q_n` |
| ODDR D0/D1 setup, hold | 0.045, 0.015 | `iddroddr.clk_oposs`, `clk_oposh` |
| DL G→Q, D setup | 0.458, 0.400 | `dl.clk_qpos`, `dl.di_clksetpos` |

- Flip-flops and the latch packed into IO registers (`-ireg_in_iob`,
  `-oreg_in_iob`) are timed with the DFF values (CLK→Q 0.458, setup 0.400, pulse
  width 1.25), not with IREG/OREG (`iclk_q` 0.635). On GW1N-9C the DL fields equal
  the DFF fields, so this design does not tell them apart either. IREG/OREG
  meaning is therefore from names only. (data)
- The SDF gives rPLL CLKIN→CLKOUT/P/D/D3 as 0, and no path in that design used a
  PLL clock, so the PLL, DLL and CLKDIV fields are from names only. (data)

GW5A: the new block has a DL class (`getDlVarName`: DI_M 0-3, DI_FS 4-7, DI_OFX
8-11, CE 12-15, LSR_SYN 16-19, CLK_QPos 20, CLK_QNeg 21, D_M/FS/OFX_to_Q 22-24,
LSR_Q 25, LSR_ASYN 26-29), which `tm_parser` maps like DFF (D from DI_FS). It has
no IOLOGIC, PLL, DLL or CLKDIV class, so those groups are left out for GW5A
rather than taken from the GW2A placeholder record. (code, data)

### Record index (`getTimingDataIndexByReportOpt`, 0x2c17cea)

The record index is computed from the speed number, the automotive flag (0x2cc)
and the typical-corner flag (0x2d0). `setDlyModel` (0x2c129a4) names the corner
"Typical ...V 25C" when 0x2d0 is set, and "Slow"/"Fast" otherwise. (code)

For GW2A, `index = 2 * slot + typical`, with speed 8, 7, 6, 9 giving slot 0, 1,
2, 3. `tm_parser`'s GW2A labels are right apart from `_LV`. (code)

For GW1N-class devices, non-automotive:

| Speed | Slow corner | Typical corner | tm_parser label of slow index |
|---|---|---|---|
| 5 | 0 | 1 | C5/I4 |
| 6 | 2 | 3 | C6/I5 |
| 7, devices with no C7 record | 6 | 7 | A4 (wrong) |
| 7, GW1N-9C/GW1NR-9C/GW1NS-4/GW1NZ-2 and others | 12 | 13 | C7/I6 |
| 4 | 9 | 5 | 9 |
| 3 | 8 | 11 | 8 |
| 2 | – | 10 | 10 |
| "5H" or "6H" on GW1N-4/9/9C | 6 | 7 | A4 (wrong) |

Automotive grades take other indices. In the data, the odd records have LUT and
wire delays about 15% below the even ones. CLK→Q is slightly higher in the odd
records, so the data only partly confirm the typical-corner reading. (data)

## Old model: routing delay (GW1N, GW2A)

Read from `STA::TmModel::getWiresDlyNew` (0x2d73de4) and
`FanoutTmModel::addWiresFanoutDly` (0x2d5f9d6). (code)

A connection's delay is the sum over every routing node from the sink back to
the net root (`TmAnalyzer::getSinkDlyOfOneNetNew`, 0x2c308b6). Each node
contributes `base(type) + n * Fan(type) / FanNum(type)`. Here `n` is the number
of used outgoing edges, excluding edges to the node's own X1_1, X2_1, X2_2,
X8_1 and X8_2 continuations. Node types are named by `getNodeType(NODE_TYPE)`
(0x1b765fc).

| Node | Wires | Base | Fanout |
|---|---|---|---|
| LUTOUT | F | – | FFan |
| REGOUT | Q | – | QFan |
| OF | OF | – | OFFan |
| X0 | X01–X08 | X0 | X0Fan |
| X1_0 | E100, SN10, ... | FX1 | X1Fan |
| X1_1 | E101, ... | – | X1Fan |
| X2_0 | E200, ... | X2 | X2Fan |
| X2_1, X2_2 | E201, E202, ... | – | X2Fan |
| X8_0 | E800, ... | X8 | – |
| X8_1, X8_2 | E804, E808, ... | – | X8Fan |
| LUTIN | A–D | ISB (0 on the devices checked) | – |
| CK, SR, CE, SEL | – | 0 | 0 |
| PCLK_BRANCH | – | CENT_SPINE + SPINE_TAP + TAP_BRANCH + BRANCH (PCLK) | – |

Further rules:

- Nodes in row 0, the last row, column 0 and the last column contribute 0.
- Corner HCLK nodes use `getHclkDly`.
- `SX1Fan`, `X0CTL`, `X0CLK` and `X0ME` are never read by this code.
- The connection value is `max(Σq[2], Σq[3])`; this matches the SDF max column.
- When a DFF's D is reached through a LUT input, the delay of that LUT input to
  F is added (`TmAnalyzer::addLutBufDelay`, 0x2c211d2, called from
  `calcNetTmEdgeDlyNew`, 0x2c29f62).

Checked against data. `tools/timing/routes.py` implements this formula on routes
decoded from the IDE bitstream. It reproduces the IDE's SDF interconnect delays
to a median of 0.3 ps on GW1N-9C (897 connections) and 0.4 ps on GW2A-18C (735
connections). The largest residuals are 22 ps and 46 ps; the cause is not known.

### Differences in nextpnr's pip model (data)

nextpnr charges per pip:
`int_delay(class of src) + drive_res(src) * Σ in_cap(bound pips from src)`.
`drive_res` is the `out_res = 1e6/FanNum` of the upstream pip's class.
Compared with the vendor formula:

- The source node (F, Q, OF) has no upstream pip, so its fanout term is never
  charged: 10–30 ps per connection.
- The divisor is the upstream class's FanNum, not the node's own.
- X8_0 gets a fanout term where the vendor has none.
- Edge rows and columns are charged where the vendor charges nothing. This only
  affects IO.

On GW1N-9C these errors roughly cancel (+2%). On GW2A-18C they leave routing
about 4% optimistic.

## Old model: cells

`TmModel::getLutPinToPinDly` (Pin, Pin) treats LUT5–LUT8 as single arcs (code):

| Primitive | Arc |
|---|---|
| LUT5 | x_OFX + FX_OFX1 |
| LUT6 | x_OFX + 2 × FX_OFX1 |
| LUT7 | x_OFX + 3 × FX_OFX1 |
| M0/M1 inputs | M0_OFX0 or M1_OFX1 plus the remaining FX_OFX1 |

Inputs are first remapped for pin swaps (`getSwapedPinIndexForLut4/8`).
nextpnr chains LUT4 and MUX2 arcs instead. On the critical paths compared, the
cell delays in both tools agreed: LUT 0.626, ALU first stage 0.96, carry 0.057
per stage, clk-to-q 0.458, setup 0.4. (data)

## New model (GW5A)

`apycula/tm_parser.py` (`parse_new_block`) parses the block and documents the
format. `tools/timing/tm_new.py` dumps it with variable names.

Classes:

| Class | Variables |
|---|---|
| LUT | A_F/B_F/C_F/D_F, the `_67` variants for LUT6/7, x_OFX0, M0/M1_OFX, FXA_FX1 |
| ALU | 20 variables |
| DFF | separate D setup for D from M (routing), FS (same-slice F) and OFX |
| DL | latch arcs |
| SSRAM | RAM16SDP4 arcs |
| XWIRE | X0/X1/X2/X8; VBUF crossing BSRAM/DSP columns; HBUF crossing VIQ/RPT/SPINE; HOS/VOS; *_LOAD_DERATE |
| FANOUT | FAN_RATIO per wire class and fanout range |
| GLBSRC | 73 clock-tree variables |
| IBUF/OBUF | per IO standard |
| BSRAM | 50 variables |

Each value has 12 floats: three groups of four, one per core type. Group 0 is
`[min, min, max, max]`, group 1 is max-only and group 2 is min-only. The core
type defaults to 1 and is set from the SDC report options. (code; meaning of
the core-type enum not confirmed)

`getTmModelDelayMultByDevice` (0x2c1b0f2) returns 1.25 for every GW5A device.
It is applied to group 1 only when the record index is 0, which is C1/I0. The
multiplier is otherwise 1.0. (code; data: GW5A C1 report values are the table
values × 1.25)

The data after the block (from byte 62,057 in `GW5A-25A.tm`) is `PrimTmEdge`
arcs, read only when the design contains BSRAM, DSP or similar. Not decoded.

### New model: routing (GW5A)

Read from `TmModelNew::getWiresDlyNew` (0x2d9d84a), `getWireFanout`
(0x2da5a1e) and `addMultArcDelayByFanout`. (code)

- An X0, X1, X2 or X8 wire is charged once, at its root node:
  `XWIRE[class] + n * FAN_RATIO_<class>_range_<r>`. Here `n` counts the used
  pips on all segments of the wire, and is capped by a per-variable table.
  The range variable is `_1_5` for n ≤ 4, `_5_9` for n ≤ 8 and `_9_13` above.
  Middle and end segments contribute nothing.
- F, Q and OF nodes contribute `n * FAN_RATIO_F/Q/OFX_range_<r>`.
- LUT inputs and CK/SR/CE/SEL contribute nothing. There is no ISB term.
- Each wire node carries a flag (`NETLIST::node::getXwireDelayValueFlag`).
  When it is set, the base and fanout variables are replaced by the
  `X*_VBUF_EBR/DSP`, `X*_HBUF_VIQ/RPT/SPINE` variants, plus `X*_VOS_*`/`X*_HOS_*`
  and a `*_LOAD_DERATE` correction (`subRowDistLoadRatio`). Where the flag comes
  from has not been traced.

Checked against data on GW5A-25A, 1305 connections. The formula without the
buffer variants reproduces the SDF for 285 connections and 81% of the total.
Most of the remaining connections are short by 0.32–0.38 ns, which matches the
X8 VBUF/HBUF values times 1.25. A smaller group is short by about 5 ps, which
looks like a fanout count off by one; the cause is not known.

Because of this, Apicula keeps the placeholder `wire` and `fanout` groups for
GW5A. The plain X-wire values make nextpnr's routing delays 17% low on
IDE-routed GW5A-25A designs, against 2% low with the placeholder values.

### What Apicula uses for GW5A

`tm_parser.read_tm_gw5a` builds the speed grades C1/I0, A0 and ES with ×1.25,
and C2/I1 with ×1.0. Each starts from a placeholder record. The `lut`, `alu`,
`dff`, `sram` and `bram` keys are then replaced with group-1 values from the
new block. DFF D setup and hold use the DI_FS arcs, because nextpnr always
feeds D from the slot's own LUT. That is the case
`STA::TmModelNew::getDffPinToPinDly` (0x2d98efa) maps to DI_FS.

Checked against the IDE's SDF for GW5A-25A C1/I0, which covers 366 ALUs,
1731 LUTs and 575 DFFs. Every ALU arc, the LUT A–D→F arcs (0.526, 0.516,
0.461, 0.262), CLK→Q (0.382) and D setup (0.064) match. For CE and LSR setup,
the SDF's posedge value equals the rising entry; Apicula keeps the larger of
the two edges.

### MUX2 arcs (all families)

On GW1N-9C and GW5A-25A the IDE times MUX2 cells as follows (data; GW1N values
from the timing report, GW5A from the SDF):

| Arc | IDE | nextpnr |
|---|---|---|
| MUX2_LUT5 I0/I1→O | x_OFX − x_F (GW1N 0.149, GW5A 0.196) | m0_ofx0 / m1_ofx1 |
| MUX2_LUT6/7/8 I0/I1→O | FX_OFX1 (GW1N 0.163, GW5A 0.101) | m0_ofx0 / m1_ofx1 |
| S0→O | M0_OFX0 / M1_OFX1 (GW1N 0.502, GW5A 0.252) | fx_ofx1 |

So nextpnr swaps the data and select arcs.

### GW5A cell delays (data, max over the slow pair)

| Arc | IDE C1/I0 | IDE C2/I1 | Apicula C1/I0, placeholder |
|---|---|---|---|
| LUT A→F | 0.526 | 0.421 | 0.549 |
| LUT D→F | 0.262 | 0.210 | 0.371 |
| ALU A→F | 0.731 | 0.585 | 0.549 |
| ALU A0→FCO | 0.556 | 0.445 | 0.549 |
| ALU FCI→FCO | 0.050 | 0.040 | 0.035 |
| ALU FCI→F0 | 0.244 | 0.195 | 0.470 |
| DFF CLK→Q | 0.382 | 0.306 | 0.232 |
| DFF D setup (from routing) | 0.291 | 0.233 | 0.035 |
| wire X2 | 0.188 | 0.150 | 0.237 |
| wire X8 | 0.269 | 0.215 | 0.266 |

The IDE's GW5A-25A critical path uses these values: CLK→Q 0.382, ALU I0→COUT
0.556, carry 0.050 per stage, MUX8 0.086.

## Method and tools

All scripts are in `tools/timing/`. They are research aids and their output is
not committed.

For cell arcs alone no route rebuilding is needed: compare the SDF IOPATH and
SETUPHOLD values with `read_tm` for the device's speed grade. The `ide_io`
design used for the IOLOGIC check is plain Verilog run through the IDE's own
synthesis (`add_file top.v`, `run all`, `-ireg_in_iob 1 -oreg_in_iob 1`): one
IDDR, one ODDR, one DL, an rPLL clocking a flip-flop, and flip-flops between
pads.

1. Prepare one netlist for both tools. Synthesize with yosys and write both
   `write_json` and `write_verilog -noattr -defparam`. The vendor netlist
   parser rejects `#()` parameters, `1'hx` and multi-bit constants inside
   concatenations, so run `setundef -zero; splitnets; opt_clean -purge`. For
   GW5A, expand multi-bit constants on port lines and map
   DFF/DFFE/DFFR/DFFS to DFFRE/DFFSE.
2. Run the IDE with `gw_sh`. If it fails with an `FT_Done_MM_Var` lookup error,
   run it as `LD_PRELOAD=/usr/lib/libfreetype.so.6 gw_sh`. Use
   `-gen_text_timing_rpt 1 -gen_sdf 1`, and put
   `report_timing -setup -max_paths 3000 -max_common_paths 20` in the SDC.
   The report supplies instance locations; `-gen_posp` wrote only a header.
3. `vendor_pips.py DEVICE impl/pnr/syn.fs vpips.json` decodes the fused pips.
   Fuse-less default pips are kept separately.
4. `routes.py DEVICE SPEED impl/pnr vpips.json routes.json` traces each SDF
   connection whose endpoints appear in the report and evaluates the old
   formula.
5. `ROUTES_DIR=... nextpnr-himbaechel ... --pre-pack tools/timing/npnr_eval.py`
   computes nextpnr's delays for the same routes.
6. `compare.py ROUTES_DIR` prints the comparison.

Limitations:

- Only connections on reported paths are covered, about 10% of all
  connections, biased towards critical ones.
- Sinks reached only through fuse-less pips are skipped.
- Clock, IO, long-wire and BSRAM nets are not covered.
- Fmax comparisons use each tool's own placement, so they measure placer
  quality as well as the timing model.
