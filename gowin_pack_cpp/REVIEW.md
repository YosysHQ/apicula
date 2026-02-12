# C++ Packer Review: Comparison with Python Reference

This review compares the C++ packer (`gowin_pack_cpp/`) against the Python reference
(`apycula/gowin_pack.py`) to identify differences, missing functionality, duplicated
code, and "bug-compatible" behavior that could be improved.

---

## 1. Missing Functionality

### 1.1 DLLDLY (Delay Line DLL) — **Not Implemented**

The Python packer has a complete DLLDLY handler (`gowin_pack.py:2717-2744`, dispatched
at line 3494), but the C++ packer only recognizes `DLLDLY` in the BEL regex
(`place.cpp:111`) without any dispatch entry in `place_cells()`. Any design using
DLLDLY primitives will silently produce an incomplete bitstream.

**Python implementation:**
- `set_dlldly_attrs()` processes `DLL_INSEL`, `DLY_SIGN`, `DLY_ADJ` parameters
- Expands 32-bit `DLY_ADJ` into individual `ADJ0`–`ADJ31` fuses
- Writes fuses to all tiles listed in `db.extra_func[row, col]['dlldly_fusebels']`
- Uses `get_long_fuses()` with table name `DLLDEL{num}`

**C++ status:**
- `attrids.hpp:1202-1226` already defines `dlldly_attrids` and `dlldly_attrvals`
- Just needs the handler function and dispatch entry

### 1.2 BSRAM Init with `write_bitstream_with_bsram_init` — **Not Wired Up**

The Python `main()` has three write paths (`gowin_pack.py:4321-4355`):
1. GW5A with BSRAM → `write_bitstream()` with init map + bsram positions
2. Non-GW5A with BSRAM → `write_bitstream_with_bsram_init()` (init map appended inline)
3. No BSRAM → plain `write_bitstream()`

The C++ `main.cpp:103-109` only has two paths:
1. GW5A with BSRAM → `write_bitstream_gw5a()`
2. Everything else → `write_bitstream()`

The non-GW5A BSRAM init path (case 2 above) appears to be missing — when a non-GW5A
device uses BSRAM with initialization data, the init values may not be written to the
bitstream. Needs verification in `bitstream.cpp` to confirm whether `write_bitstream()`
handles the inline BSRAM init case.

### 1.3 CST File Output — **Not Implemented**

Python writes constraint output when `--cst` is specified (`gowin_pack.py:4357-4359`).
The C++ `main.cpp:37` accepts `--cst` via CLI but never uses `cst_file`. No constraint
tracking or output is implemented.

### 1.4 PNG Bitmap Visualization — **Not Implemented**

Python optionally generates a PNG visualization of the fuse bitmap
(`gowin_pack.py:4313-4314`). The C++ version has no equivalent, though this is low
priority since it's a debugging feature.

---

## 2. Bug-Compatible Behavior (Candidates for Improvement)

### 2.1 PLL DYN_*_SEL / CLKOUT*_BYPASS Dead Code

**Location:** `place.cpp:1712-1740`

The Python packer calls `attrs_upper()` to uppercase all attribute values before the
parameter loop, then compares against lowercase `"true"`. Since `"TRUE" != "true"`, the
`DYN_IDIV_SEL`, `DYN_FBDIV_SEL`, `DYN_ODIV_SEL`, `CLKOUT_BYPASS`, `CLKOUTP_BYPASS`,
and `CLKOUTD_BYPASS` branches are **never reached** in Python.

The C++ code faithfully replicates this bug:
```cpp
// line 1717-1719
if (ua == "DYN_IDIV_SEL") {
    if (uv == "true") pll_str_attrs["IDIVSEL"] = "DYN";  // never triggers
    continue;
}
```

**Improvement:** Compare against `"TRUE"` instead of `"true"` to actually enable
dynamic divider selection when requested.

### 2.2 PLL DYN_DA_EN Dead Code

**Location:** `place.cpp:1759-1788`

Same bug: `DYN_DA_EN == "true"` never matches after uppercasing. The C++ code uses
`if (false && uv == "TRUE")` to make this explicit, which is good documentation but
the branch is unreachable.

**Improvement:** Fix the comparison and enable dynamic duty/phase adjustment.

### 2.3 `_banks[bank].bels` Never Populated

**Location:** `place.cpp:1220-1223` (documented in comment)

In Python, the `_banks[bank].bels.add()` line that tracks which IOB pins are "used" is
commented out. This means the "unused IOB" loop that writes default IO_TYPE fuses
processes **all** pins including used ones, overwriting their fuses with defaults.

The C++ code matches this behavior and documents it:
```cpp
// Note: in the Python packer, _banks[bank].bels is never populated
// (the .bels.add() line is commented out), so the unused IOB loop
// processes ALL pins including used ones, writing default attrs on top.
// We match this behavior by NOT skipping used pins.
```

**Improvement:** Once 100% match is confirmed, track used pins and skip them in the
default loop. This would avoid redundant fuse writes and potential subtle overwrites.

### 2.4 BSRAM BIT_WIDTH_0 Byte Enable Dead Code

**Location:** `place.cpp:2256-2257` (documented in comment)

In Python, the byte-enable logic for `BIT_WIDTH_0` with `val == 16/18` is dead code
because it's nested inside the `else` branch for `val == 32/36`. The C++ code matches
this and documents it:
```cpp
// Note: In Python, byte_enable dispatch for BIT_WIDTH_0 with val=16/18
// is dead code (nested inside else for 32/36). Only SDP with 32/36 is live.
```

**Improvement:** Move the `val == 16/18` byte-enable logic outside the `val == 32/36`
branch so it actually executes.

### 2.5 BSRAM BIT_WIDTH_1 Byte Enable Dead Code

**Location:** `place.cpp:2297-2298` (documented in comment)

Same issue: byte-enable dispatch for `BIT_WIDTH_1` is entirely dead code in Python.

```cpp
// Note: In Python, byte_enable dispatch for BIT_WIDTH_1 is all
// dead code (nested inside else for 32/36). No byte_enable set here.
```

---

## 3. Code Duplication

### 3.1 DSP Attribute Handlers (`bels/dsp.cpp`)

The `dsp.cpp` file (971 lines) has significant duplication across its six type-specific
handlers:

- **Register configuration pattern** (AREG, BREG, CREG, etc.): The same
  check-parameter → set-bypass-or-enable → configure-CE/CLK/RST sequence repeats in
  `set_multalu18x18_attrs()`, `set_multaddalu18x18_attrs()`, and `set_mult9x9_attrs()`.

- **CE/CLK/RST mux setting:** The pattern
  `da["CE" + h + "MUX_REG..."] = ce_val` appears ~200+ times across handlers.

- **MULT_RESET_MODE check:** `if (params["MULT_RESET_MODE"] == "SYNC")` appears ~25
  times.

**Suggestion:** Extract a `configure_dsp_register()` helper that takes register name,
CE/CLK/RST values, and sync reset flag.

### 3.2 IOB Fuse Application

The IOB placement code in `place_iob()` (`place.cpp:661-1391`) and
`set_adc_iobuf_fuses()` (`place.cpp:3520-3619`) both build IOB attribute sets and
call `get_longval_fuses()` / `set_fuses_in_tile()`. The ADC IOB fuse builder has 12
identical `add_attr_val()` calls repeated for IOBA and IOBB (with minor differences
for bus type).

**Suggestion:** Extract a helper like `build_adc_iob_base_attrs()` that returns the
common attribute set.

### 3.3 Bank Fuse Handling

Bank fuse generation at `place.cpp:1173-1259` has two near-identical blocks: one for
used banks (lines 1180-1206) and one for unused banks (lines 1235-1258). Both call
`get_bank_fuses()` + `get_longval_fuses("IOBA"/"IOBB")` + `set_fuses_in_tile()`.

**Suggestion:** Extract a `set_bank_fuses()` helper parameterized by the attribute set.

### 3.4 Bounds Checking Boilerplate

Nearly every `place_*` function starts with:
```cpp
int64_t row = bel.row - 1;
int64_t col = bel.col - 1;
if (row < 0 || row >= db.rows() || col < 0 || col >= db.cols()) return;
```

This appears 12+ times. Could be a one-line helper or validated at BEL extraction time.

---

## 4. Structural Differences from Python

### 4.1 BEL Extraction Architecture

**Python:** Uses generator functions with `yield from` for composability:
- `get_bels()` yields main BELs
- `extra_pll_bels()`, `extra_clkdiv_bels()`, `extra_mipi_bels()`, `extra_bsram_bels()`,
  `extra_dsp_bels()` yield auxiliary BELs
- `_pip_bels` global list accumulates pass-through LUTs from routing

**C++:** `get_bels()` returns a flat vector. Auxiliary BELs (RPLLB, CLKDIV_AUX,
MIPI_IBUF_AUX, BSRAM_AUX) are handled inline in `place_cells()` rather than being
generated as separate BELs. This works but makes the dispatch logic harder to follow.

### 4.2 Global State

**Python** uses module-level globals: `_gnd_net`, `_vcc_net`, `_pip_bels`, `_banks`,
`bsram_init_map`, `adc_iolocs`, `device`, `pnr`.

**C++** uses file-scope statics in `place.cpp`: `gnd_net_bits`, `vcc_net_bits`,
`slice_attrvals`, `adc_iolocs`. The main data (`bsram_init_map`, `gw5a_bsrams`,
`extra_slots`) is passed by pointer through function parameters, which is cleaner.

### 4.3 Stub BEL Files

7 of 8 files in `bels/` are empty stubs (lut.cpp, dff.cpp, alu.cpp, iob.cpp, pll.cpp,
bsram.cpp, iologic.cpp). Only `bels/dsp.cpp` has a real implementation. All actual
placement logic lives in `place.cpp`. The stubs serve no purpose and could be removed
to reduce confusion.

### 4.4 Python `extra_*_bels()` vs C++ Inline Handling

Python generates auxiliary BELs as separate entries that flow through the same dispatch:
```python
def extra_pll_bels(cell, row, col, num, cellname):
    yield ("RPLLB", col + 1, row, ..., "RPLLB")
```

C++ handles RPLLB inline in `place_pll()` (lines 1946-1968) by directly writing fuses
to adjacent tiles. This is equivalent but means the auxiliary tile logic is embedded
in the main handler rather than being independently testable.

---

## 5. Potential Correctness Issues

### 5.1 GW5AST-138C Support

Python checks `device in {'GW5A-25A', 'GW5AST-138C'}` in several places
(`gowin_pack.py:4316-4317, 4321`). The C++ code sometimes checks only for
`device == "GW5A-25A"` (e.g., `place.cpp:2006`, `bitstream.cpp` transpose logic).
Verify that GW5AST-138C is handled everywhere the Python checks for both devices.

### 5.2 MIPI_IBUF_AUX Handling

Python generates a `MIPI_IBUF_AUX` BEL at `col+1` via `extra_mipi_bels()` which then
gets processed in `place()` with specific fuse attributes (`gowin_pack.py:3226-3232`).

C++ handles this inline in `place_cells()` at lines 296-309, setting MIPI AUX fuses
directly. Verify that the attribute sets match exactly.

### 5.3 ADC Attribute Merge Bug

In `place.cpp:3328-3338`, the ADC attribute merge loop runs twice:
```cpp
// First pass (line 3328-3333): conditional merge
for (const auto& [k, v] : parms) {
    std::string key = to_upper(k);
    if (adc_inattrs.count(key) || default_adc_attrs.count(key) == 0) {
        adc_inattrs[key] = v;
    }
}
// Second pass (line 3335-3338): unconditional override
for (const auto& [k, v] : parms) {
    std::string key = to_upper(k);
    adc_inattrs[key] = v;
}
```

The first pass is entirely redundant since the second pass unconditionally overwrites.
This isn't a bug (the result is correct), but the first loop is dead code that should
be removed.

### 5.4 PINCFG Validation Missing

Python's `place()` function validates PINCFG cells against GPIO flags
(`gowin_pack.py:3208-3213`), printing warnings when a dual-mode pin is used without
the corresponding `--*_as_gpio` flag. The C++ `place_cells()` treats PINCFG as a
no-op (line 288) without validation.

---

## 6. Summary

| Category | Item | Severity |
|----------|------|----------|
| **Missing** | DLLDLY handler | High — silent failure |
| **Missing** | Non-GW5A BSRAM init write path | Medium — needs verification |
| **Missing** | CST file output | Low |
| **Missing** | PNG visualization | Low |
| **Bug-compat** | PLL DYN_*_SEL / BYPASS dead code | Medium — features don't work |
| **Bug-compat** | PLL DYN_DA_EN dead code | Medium |
| **Bug-compat** | `_banks.bels` not tracked | Low — extra fuse writes |
| **Bug-compat** | BSRAM BIT_WIDTH_0/1 byte-enable dead code | Low |
| **Duplication** | DSP register configuration (~200 lines) | Medium |
| **Duplication** | ADC IOB fuse builder | Low |
| **Duplication** | Bank fuse handling | Low |
| **Duplication** | Bounds-check boilerplate (12+ sites) | Low |
| **Correctness** | GW5AST-138C checks | Medium — may break device |
| **Correctness** | ADC double-merge dead code | Low |
| **Correctness** | PINCFG validation missing | Low |
| **Cleanup** | 7 empty stub BEL files | Low |
