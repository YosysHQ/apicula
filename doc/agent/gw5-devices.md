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

Read from symbol names; bodies not traced. The 138 has its own
`setGW5AT138IolAttrInIologic`, `setGW5AT138IolIDDR`, `setGW5AT138IolODDR`,
`setGW5AT138IDelay`, `setGW5AT138ODelay` and `setGw5at138PioPadAttr`. Checked
against data: `IOB` logicinfo has 199 rows on 60B and 285 on 138C, `IOLOGIC` 659
and 648.

The name `isDeviceBeforeGW5AT138` is misleading: 25A, 60B, 75 and 15A return false
along with the 138 parts, so it separates GW5 from earlier families.

## Open

- The vendor bitstream omits `ODIV1_SEL` and `ODIV6_SEL` when the channel is
  disabled, although the handler sets them unconditionally. The cause is unknown.
  `gowin_pack` still writes them.
- `A_CLKIN_SEL` differed in every GW5A-25A comparison (vendor 21, ours 18). It
  probably depends on placement; not confirmed.
