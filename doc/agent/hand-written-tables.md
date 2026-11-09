# Hand-written tables and their vendor sources

A survey of literal tables in `apycula/` against `libgowin.so`. The library has no
named data tables worth copying, so vendor knowledge is in code and in the data
files. Each table below was compared with that code unless marked otherwise.

| Apicula table | Vendor source | Status |
|---|---|---|
| `attrids.py` tables | `enumToStr` | Checked with `tools/gowin_extract.py check-attrids` |
| `fse_parser` type lists | `fseFileData::readOneTable` | Replaced by `apycula/fse_formats.py` |
| `_known_logic_tables` | `getTable(N)` in `get*Fuse` | Checked, see below |
| `ini_h4x.PIO_STR_MAPPINGS` | `getPioValueStr` | Could be replaced directly; not done |
| `_dff_types`, `dffmap`, DSP `*_defaults` | `setClsRegAttr`, `set*Attr` | Rules, not tables; need the rules walker |
| `gowin_pll.device_limits` | `chip::reBuildPllLimit`, `getPllFreRange` | Candidates from names; not read |
| `_known_tables` (`shortval`, `longval`) | `get*TableFuse` | Vendor selects these at runtime; not checked |
| `_pll_pads`, `_pll_loc`, `_hclk_to_fclk`, `_io_cfg` | Not found in code | Probably `.dat` data; not investigated |

## `logicinfo` table numbers

The table numbers requested through `fseFileData::getTable(FSD_TABLE)` show which
function uses each table. Every name in `_known_logic_tables` agrees with its
vendor caller. The names below are inferred from the caller, not from a vendor name
table.

| Table | Vendor caller |
|---|---|
| 7 | `getCiuFuse` |
| 16 | `getPLLTESTFuse` |
| 55 | `getDLLFuse`, `getCiuDDRDLLFuse`, `getCoreDDRDLLFuse`, `getIobDDRDLLFuse` |
| 57 | `getDqsFuse` |
| 65 | `getEflashFuse` |
| 70 | `getI3cFuse` |
| 72 | `getSpmiFuse` |
| 74 | `getVcpFuse` |
| 76 | `getBgFuse` |
| 78 | `getEmcuFuse` |
| 81 | `getPorTableFuse` |
| 83 | `getPwdTableFuse` |
| 85 | `getDphyTableFuse`, `generateMipiDphyFuseList` |
| 134 (`0x86`, signed) | `getAdclrcFuse` |
| 135 (`0x87`, signed) | `getAdculcFuse` |
| 154 | `generateMipiCphyFuseList` |
| 157 | `getMultaccTableFuse` |
| 159 | `getJpeg1ScramblerTableFuse` |
| 161 | `setIolSclkGenAttrFuse` |
| 167 | `setHclkMrccAttrFuse_3A20` |

`shortval` tables 156 (`setOsc1AttrFuse`, `setOscMap`), 162
(`setIolSclkGenAttrFuse`) and 168 (`setHclkMrccAttrFuse_3A20`) are requested the
same way.
