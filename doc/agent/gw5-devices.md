# GW5AT-60B and GW5AST-138C

IDE 1.9.10.03. The two devices share PLL logic but differ in the clock network, IO
and configuration.

## PLL: effectively the same

Read from code. `setPllAttrInPll_GW5AT` selects the handler by device type:

- `setPllAttrInPllgrid`: GW5AT-138, every 138B and 138C part, GW5AT-75B and 75C.
- `setPllAttrInPll(pll*)`: everything else, including 25A, 25B, 60B and 15A.

After normalising names, the two handlers make the same assignments under the same
conditions. The one difference is `VR_EN`: the 138 path tests for `1'b0` and the
other for `1'b1`, which only matters for a value that is neither.

Checked against data: the `PLL` logicinfo tables differ, with 2512 rows on 60B and
2531 on 138C. In Apicula's databases the PLL table for 60B is in slot 1024, while
138C has `PLL` tables on ordinary tile types. Only GW5A-25A has been compared with
a vendor bitstream.

## Clock network: separate code

Read from symbol names in `fusegenMem`; bodies not traced.

| Area | 138 | 60 |
|---|---|---|
| Central mux | `setCmux5AT138*`, `setCmuxBridge5AT138*`, top, bottom and bridge grids | `setCmuxMap_5AT60`, `setCmuxWireFuse_5AT60`, `setCenMuxFuse_5AT60` |
| HCLK | `set5AT138HclkWireFuse`, `setHclkMrccMap_5AT138` | `set5AT60HclkWireFuse`, `setHclkMrccMap_5AT60` |
| Clock enable tables | `5A_PCLK_ENABLE_*` | `5A_60_PCLK_ENABLE_*` |

`GW5AST_138C` in `gowin_pack` matches this shape, with its top, bottom and bridge
areas.

## IO

Read from symbol names; apart from the I/O logic rows below, bodies not traced. The 138 has its own
`setGW5AT138IolAttrInIologic`, `setGW5AT138IolIDDR`, `setGW5AT138IolODDR`,
`setGW5AT138IDelay`, `setGW5AT138ODelay` and `setGw5at138PioPadAttr`. Checked
against data: `IOB` logicinfo has 199 rows on 60B and 285 on 138C, `IOLOGIC` 659
and 648.

The name `isDeviceBeforeGW5AT138` is misleading: 25A, 60B, 75 and 15A return false
along with the 138 parts, so it separates GW5 from earlier families.

### I/O logic LSR, GSR and clock rows

This holds for the whole GW5 family, 25A included.

Read from code (IDE 1.9.10.03). `setIolAttrInIologic` @0x3083e12 sends GW5 parts
to `setGW5AIolAttrInIologic` @0x3084010 or `setGW5AT138IolAttrInIologic`
@0x3084522. Both run `initIolAttr` @0x308d1fe, `setIolLsrmux` @0x308e660,
`setGW5AT138IolIDDR` @0x30894d2 and `setGW5AT138IolODDR` @0x308a15a. They differ
only in the delay handler: `setGW5AIodelay` @0x308c44a against
`setGW5AT138IDelay` @0x308c80e, which writes `IDEL_*` rows. So 60B takes the same
LSR and GSR rule whichever branch it uses.

- `setIolLsrmux` takes the reset pin of the I/O register (or of the delay cell)
  and asks `getPinSrcType` @0x3098cec where it comes from. A `GND` instance
  leaves `LSRIMUX_0`/`LSROMUX_0` off. `VCC`, a signal or an inverted signal
  turn it on. A primitive without a reset port gets no assignment and keeps the
  `initIolAttr` default, which is off.
- Unlike `setIolIDDR` @0x308898e on GW1N/GW2A, the GW5 handlers never read
  `GSREN` or `LSREN`. The vendor rejects both parameters on GW5A
  (`PA2066 Invalid parameter name`, checked on 25A).

Checked against vendor bitstreams on GW5A-25A (4 cases per primitive, pin A and
B) and GW5AST-138C (2 cases), with the reset from a pin, from `GND` (both parts)
and from `VCC` (25A). Both parts give the same rows:

| Primitive | Sites with rows | LSRxMUX_0, reset from a pin or VCC | LSRxMUX_0, reset = GND | Clock row | GSR |
|---|---|---|---|---|---|
| IDES4/8/10, IVIDEO, IDDRC | the pin site | LSRIMUX_0 on | off | CLKIMUX=ENABLE | ENGSR |
| IDES16 | main only; the other site has no LSR or clock rows | LSRIMUX_0 on | off | CLKIMUX=ENABLE | ENGSR |
| IDDR (no reset port) | the pin site | off | n/a | CLKIMUX=ENABLE | ENGSR |
| OSER4, ODDRC | the pin site | LSROMUX_0 on | off | CLKOMUX=ENABLE | ENGSR |
| OSER8 | main only; **no helper cell** | LSROMUX_0 on | off | CLKOMUX=ENABLE | ENGSR |
| OSER10, OSER16 | both sites | LSROMUX_0 on, both | off, both | CLKOMUX=ENABLE, both | ENGSR |
| ODDR (no reset port) | the pin site | off | n/a | CLKOMUX=ENABLE | ENGSR |
| IODELAY (standalone) | the pin site | both off | n/a | none | ENGSR; INDEL=ENABLE |

- `GSR=DISGSR` never appears: GSR is always enabled.
- `CLKOMUX_1` has only the value `0` in the chipdb of all three GW5 parts, so it
  has no fuse.
- OVIDEO is not measured: the vendor wants an LVDS output buffer (`PR1016`) and
  the fuzzer harness gives it a plain one.

So on GW5 the LSR mux follows the reset net, where on GW1N/GW2A `LSREN` decides.
`Device.iologic_lsr(cell)` in `gowin_pack` writes `'0'` when the main cell has no
RESET/CLEAR connection or it is on the GND net, and `'1'` otherwise. GW5's
logicinfo only knows `LSRxMUX_0='0'`, so `'1'` leaves the `!LSRxMUX_0=0` row set.
Input `DDRENABLE` sites keep `'0'`, as the table has rows only at the pin site,
and the OSER8 aux cell is not written at all.

## PLL input select follows the clock pin

Read from code: `A_CLKIN_SEL` comes from the internal `IN_SEL` value, which the
placer sets from the input buffer's dedicated function (`placeOneFixIOBBufInst`,
`isCfgPllClkin*TypeForGW5A25`).

Checked against vendor bitstreams, GW5A-25A in MBGA121N with only the clock pin
changed:

| Clock pin | Function | `A_CLKIN_SEL` |
|---|---|---|
| A10, A1, B3 | none | 18 (`CLKIN0`) |
| C2 | `LPLL1_C_FB0` | 18 |
| C11 | `GCLKT_13`, `LPLL0_T_IN1` | 21 |
| A11 | `LPLL1_T_IN0` | 22 |
| E11 | `GCLKT_14`, `LPLL0_T_IN2` | 22 |
| C10 | `GCLKC_13`, `LPLL0_C_FB1` | 19 |
| E10 | `GCLKC_14`, `LPLL0_C_FB0` | 52 |
| E1 | `GCLKC_10B`, `LPLL1_C_IN1` | 53 |
| F1, F2 | `GCLK*_9B` | 52 |

`gowin_pack` always writes 18. With every pin matched to the vendor's on A10, all
56 attributes agree. The same holds for rPLL `INSEL` on GW1NR-9C: `CLKIN1` on plain
pins 3, 11 and 13, as `gowin_pack` writes, but `CLKIN0` on `LPLL_T_IN` and
`RPLL_T_IN`, and `CLKIN4` on `GCLKT_4`.

## Open

- GW5A-25A B-site I/O logic: `gowin_pack` writes the `IOLOGICB` cell into the
  main tile, whose `IOLOGICB` table has 2 rows. The real table, with 677 rows, is
  in the IOBB `fuse_cell_offset` tile. Checked against data: every B-site case in
  the fuzzer writes nothing there.
- 60B and 138C can't be fuzzed yet. nextpnr fails to route the clock to any I/O
  logic (`Failed to find a route for arc 0 of net clk`, or the router1.cc:347
  assert for ODDR). The harness picks 60B pins without an IOB bel and finds no
  `GCLK*` pin on 138C, whose clock pins are `MGCLKT`/`SGCLKT`. And `bslib` reads
  917 rows from 60B bitstreams where the chipdb has 918.
- The vendor bitstream omits `ODIV1_SEL` and `ODIV6_SEL` when the channel is
  disabled, although the handler sets them unconditionally. The cause is unknown.
  `gowin_pack` still writes them.
