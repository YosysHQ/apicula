# From primitive to fuse

All of this is in `libgowin.so`, class `fusegenMem`.

## The vendor flow

1. **Expand the primitive (code).** `set*Attr` functions translate a primitive and
   its parameters into attribute/value pairs, stored on netlist objects with
   setters such as `NETLIST::cls::setClsAttr(CLS_ATTR, CLS_VALUE)`.
2. **Flag the table (code).** `get*Fuse` calls `fseLogicInfoTable::reload()`, then
   `setOneLineFlag(attr, value)` for each attribute. That flags the matching
   `logicinfo` rows.
3. **Collect the fuses (data driven).** `fseSInfoValueTable::getFuseByInfo` walks
   the rows of a `shortval` table.

`getFuseByInfo` semantics (read from code):

- Each key is a `logicinfo` line number: 0 is ignored, positive means the line must
  be set, negative means it must not be set.
- The keys of a row are ANDed.
- The fuses of every matching row are unioned, up to 12 per row, stopping at the
  first negative fuse.

`get_table_fuses` in `apycula/chipdb.py` implements the same matching. Only the
`getClsFuse` path has been read in full. It passes stored values to
`setOneLineFlag` unchanged.

## The missing link is step 1

A parameter does not map to a single fuse because step 1 is hand-written C++.
Of 5,057 setter call sites, 4,597 pass constants, 263 are under an `INS_TYPE`
switch and 634 have no branch guard. The rest depend on string compares of
parameters, `atoi` on values, pin source checks and device type checks.

Numbers from `tools/gowin_attr_sites.py`. Its guard descriptions are approximate.

## Example: flip-flops

`fusegenMem::setClsRegAttr` switches on `INS_TYPE` (names from
`getInstSubTypeName`). Falling-edge variants (`DFFN*`) add `CLKMUX.CLK=INV`.

| Primitive | Attributes set here |
|---|---|
| DFF, DFFE | `REGMODE=FF` |
| DFFC, DFFCE | `REGMODE=FF`, `SRMODE=ASYNC`, `LSRONMUX=LSRMUX`, `REGn.REGSET=RESET` |
| DFFP, DFFPE | `REGMODE=FF`, `SRMODE=ASYNC`, `LSRONMUX=LSRMUX`, `REGn.REGSET=SET` |
| DFFR, DFFRE | `REGMODE=FF`, `LSRONMUX=LSRMUX`, `REGn.REGSET=RESET` |
| DFFS, DFFSE | `REGMODE=FF`, `LSRONMUX=LSRMUX`, `REGn.REGSET=SET` |

`n` is picked by a branch, inferred to be the bel index. Clock enable is not set in
this function. `gowin_pack` also sets `REGn_REGSET=RESET` on plain DFF and DFFE,
which this function does not. Whether that matters has not been checked.

## Vendor enums

`enumToStr(*_ATTR)`, `enumToStr(*_VALUE)` and `getInstSubTypeName` give vendor
names, which `tools/gowin_extract.py extract` dumps to `enums.json`. The numbers match
`apycula/attrids.py` in the tables compared, so those are the vendor's own enums.
`check-attrids` lists name differences. Most are naming choices. Some are likely
corrections, for example IOB values 247 (`SSTL135D_I`) and 254 (`SSTL135_I`), PLL
value 44 (`VCO`) and DSP attribute 88 (`CLKMUX.HSINSL`). The vendor has typos of
its own, such as `DELAYCHAIIN`.

## Vendor compared with Apicula

| Layer | Vendor | Apicula |
|---|---|---|
| Fuse to bit position | `.fse` `fuse` table | Resolved to `(row, col)` per tile type at build time |
| Valid attribute/value pairs | `logicinfo` | `Device.logicinfo` |
| Conditions to fuses | `shortval`, `longval`, `longfuse` | Same rows in `Device` |
| Attribute names | C++ enums | Hand-written `attrids.py` |
| Primitive to attributes | `set*Attr` code | `gowin_pack.py` handlers |
| Device differences | `getDevType` checks and `_5A25`-style variants | Per-device overrides |
| Per-bel flags and modes | None found | `Bel.flags`, `Bel.modes`, built in `chipdb.py` |

`Bel.flags` and `Bel.modes` are an Apicula-only layer of precomputed bit sets,
used by `gowin_unpack`. Vendor rules would map onto the `gowin_pack` handlers,
not onto this layer.

## Where to look next

- PLL: `initPllAttr`, `setPllAttrInPll`, `setPllAttrByPllReg`, `get*PllAdvInfo`.
- I/O: `setPioPadAttr`, `setIolAttrInIologic`.
- Table meanings: the `get*TableFuse` functions.
- Possible text dumps: `fusegenMem::testFseToTxt`, `fseFileData::outputToTxt`.
