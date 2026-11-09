# The `.fse` format

Complements [`doc/filestructure.md`](../filestructure.md). The vendor reader is
`fseFileData::readOneTable`, with `readFseData` methods per table class.

## Table types

`readOneTable` is a jump table from table type to reader class. It is extracted
into `TABLE_KINDS` in `apycula/fse_formats.py`.

| Vendor class | Apicula name | Row width (16-bit words) |
|---|---|---|
| `fseBfdArrayTable` (61) | `grid` | 32-bit entries, width in the file |
| `fseFuseTable` | `fuse` | Depends on device |
| `fseWireTable` | `wire` | Depends on device (8 or 9) |
| `fseWireSearchTable` | `wiresearch` | 3 |
| `fseConstTable` | `const` | 1 |
| `fseSInfoValueTable` | `shortval` | 14 |
| `fseAloneNodeTable` | `alonenode` | 15 |
| `fseLogicInfoTable` | `logicinfo` | 3 |
| `fseSignedLogicInfoTable` | `signedlogicinfo` | 3 |
| `fseLFuseValueTable` | `longfuse` | 17 |
| `fseLInfoValueTable` | `longval` | 28 |
| `fseDrpFuseTable` | `drpfuse` | 10 |

## Per-device layout

`fseFuseTable::readFseData(_IO_FILE*, DEV_TYPE)` and `fseWireTable::readFseData`
switch on `DEV_TYPE`. `devToFsePath` names each code. Fuse rows are 150, 169, 512 or
559 words. Results are in `DEVICE_FORMATS` in `apycula/fse_formats.py`.

Seven installed GW1N-family devices, such as `GW1N-9` and `GW1NS-4`, are not named
by the decoded `devToFsePath` cases. `fse_parser.device_format` gives them the
150/8 layout, which parses them correctly.

## Table 0x43

`readOneTable` picks the class by device. It is `fseSignedLogicInfoTable` on the
25A, 15A and 60B families, and `fseLogicInfoTable` otherwise. Apicula calls it the
`ADC` logic table, so `fse_fill_logic_tables` uses it from either kind.

## `logicinfo`

- Rows are read as whole 6-byte items. The third field is mostly 0, sometimes
  `0x7f00`. It is inferred to be the in-memory "set" flag, saved to the file.
  Apicula ignores it.
- No duplicate `(attr, value)` rows in the six devices checked (`GW1N-1`,
  `GW1N-9C`, `GW2A-18C`, `GW5A-25A`, `GW5AST-138C`, `GW5AT-138B`).
- `setOneLineFlag` starts scanning at line number `attr` and stops once the
  attribute is greater than the one wanted, which relies on rows being sorted.

## Open questions

- **`GW5AT-138`** does not parse. No part in `device_info.csv` uses it, and the
  vendor reader expects 512-word `fuse` rows for it, which misaligns. Walking the
  whole file at width 440 reaches the end marker with no bytes left, after 246
  files and 2,199 tables. It is inferred to be a leftover in an older layout.
- **Signed `logicinfo` types `0x86` and `0x87`** are parsed but not used by the
  builder. They are requested by `getAdclrcFuse` and `getAdculcFuse`, and the vendor
  has a `getFuseByInfo` overload for them. What the signed rows mean is not known.
