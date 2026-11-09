# PLL configuration

Findings from the annotated decompile (`tools/gowin_decompile.py`) of
`fusegenMem::setPllAttrInPll`, IDE 1.9.10.03.

## Parameters

PLL parameters are strings in an object returned by `Pll::getPllInitValue()`
(`Pll + 0x898`). A parameter of `ALL_INIT_TYPE` type `t` is at offset
`(t - 0xb5) * 8` in that object, and `getDefInitTypeString` names each type.

## Handlers

| Function | Used for |
|---|---|
| `setPllAttrInPll(pllGrid*)` | Dispatches by device; the rPLL/PLLVR logic |
| `setPllAttrInPll_1N2` | GW1N-2 family |
| `setPllAttrInPll_GW5AT` | Wrapper; GW5 logic is in `setPllAttrInPll(pll*)` and `setPllAttrInPllgrid`, near duplicates |
| `initPllAttr` | Defaults, overridden by the handlers |
| `getGW1NPllAdvInfo`, `getGW2APllAdvInfo` | Charge pump and filter |

The family for each handler is inferred from its device checks and attribute names.

## rPLL compared with `get_pll_attrvals`

Read from the code. Agreeing: dividers and defaults, duty and phase, delay steps,
bypass and clock selects, fixed attributes, and the GW1N pump structure.

Vendor behaviour Apicula does not have:

- `GMCVREF=2` on `GW1NZ-1` for one core voltage. `gowin_pack` does not know the
  core voltage, so this cannot be expressed yet.
- `DYN_IN_SEL` sets `SELIN=DYN`, and `CLKFB_SEL` selects `FBSEL`.
- Overrides from `GMC_PROG`, `GMC_REF`, `GMC_SEL`, `KVCO`, `PLL_R`, `PLL_C`,
  `VCOBIAS_EN_*` and `SFTDLY`.

Checked against a vendor bitstream: `SFTDLY=1` is set for a static `ODIV_SEL` of 32
and not for 64 (GW1N-9C).

`INSEL` differs between the vendor (`CLKIN0`) and Apicula (`CLKIN1`) in that test,
but the tools placed the PLL on opposite sides. Whether it matters is not known.

## Decoder limits

`gowin_unpack.parse_attrvals` can report the wrong value when several rows of a table
overlap: it reported `SDIV` as 26 and 104 where the fuses match 2 exactly. Compare
fuses exactly before treating a difference as real.
