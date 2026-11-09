# Agent notes

How to work on Apicula, and how to reverse engineer the Gowin IDE without
rederiving it each session. Findings about the vendor code and data files live in
[`doc/agent/`](doc/agent/README.md). Add to them when you learn something new.

## Project Overview

Apicula (package name: Apycula) is an open-source toolkit for reverse-engineering and generating bitstreams for Gowin FPGA devices. It provides Python tools that convert hardware designs from Yosys/Nextpnr to binary FPGA configurations.

The workflow is: Verilog → Yosys (synthesis) → Nextpnr (place & route) → gowin_pack (bitstream) → openFPGALoader (program FPGA)

## Build Commands

**Install for development:**
```bash
pip install -e .
```

**Build chip databases (requires Gowin EDA Tools v1.9.10.03):**
```bash
export GOWINHOME=/path/to/gowin
make
```

**Build examples:**
```bash
cd examples
make -j$(nproc) all
```

**Build a single example:**
```bash
cd examples
make blinky-tangnano9k.fs
```

## Console Entry Points

- `gowin_pack` - Convert Nextpnr JSON to bitstream (.fs file)
- `gowin_unpack` - Reverse bitstream to Verilog for verification
- `gowin_pll` - PLL configuration calculator

## Architecture

### Main Components (`apycula/`)

- **gowin_pack.py** - Main bitstream packer. Reads Nextpnr JSON, configures fuses for routing/LUTs/IOBs, outputs binary bitstream
- **gowin_unpack.py** - Reverse operation for verification
- **chipdb.py** - Device database structures (Device, Tile, BEL, PIP, etc.) and utilities
- **chipdb_builder.py** - Builds chip database from Gowin vendor files (parsing + SDRAM pin discovery)
- **bslib.py** - Bitstream I/O and CRC operations
- **wirenames.py** - Wire ID to name mappings (0-31: LUT inputs, 32-39: LUT outputs, etc.)
- **attrids.py** - Attribute ID and value mappings
- **fse_parser.py** - Parses Gowin `.fse` files (fuse configuration)
- **dat_parser.py** - Parses Gowin `.dat` files
- **tm_parser.py** - Parses Gowin `.tm` timing files

### Chip Databases

The `apycula/*.msgpack.xz` files are compressed device databases built by `chipdb_builder.py`. Each contains the complete FPGA architecture: tile grid, wire routing, fuse mappings, pin definitions, timing info.

### Wire Naming Convention

Wire IDs follow a pattern: `{direction}{length}{number}{segment}`
- Direction: N/S/E/W
- Length: 1 (one-hop), 2 (two-hop), 8 (eight-hop)
- Example: W270 = west two-hop wire 7

### Bitstream Structure

Bitstreams are organized as frames (one row of bits across tile grid), padded to bytes, with CRC-16 checksums. Each tile is roughly 60x24 bits with LUTs in bottom 4 rows and routing multiplexers in top 20 rows.

## Device Support

- GW1N family: GW1N-1, GW1N-4, GW1N-9, GW1N-9C, GW1NZ-1
- GW1NS family: GW1NS-2, GW1NS-4
- GW2A family: GW2A-18, GW2A-18C
- GW5A family: GW5A-25A
- GW5AST family: GW5AST-138C

**Note:** For "C" variant devices, pass the family (e.g., `GW1N-9C`) to both nextpnr's `--vopt family` and gowin_pack's `-d` flag, not the full device ID.

## Documentation

The `doc/` folder contains technical documentation about FPGA architecture, vendor file formats, and bitstream structure. Key files:
- `architecture.md` - Tile layout, LUT/DFF structure, clock routing
- `filestructure.md` - Vendor file format (.dat, .fse, .tm)
- `commandstructure.md` - Bitstream command/frame structure
- `longwires.md` - Long wire spine and tap routing

## Environment

- The supported IDE version is the one in the `GWVERSION` file, currently
  **1.9.10.03**. Only analyse that version. Enums, table types and layouts change
  between releases, and other releases are not supported.
- Set `GOWINHOME` to the install root, the directory containing `IDE/`.
- Use `.venv` for builds: `PATH=$PWD/.venv/bin:$PATH make -j4`. The chipdb build
  fails on a Python without `msgspec`.

## Checking a chipdb change

Back up `apycula/*.msgpack.xz`, rebuild, then compare by content:

    PYTHONPATH=. python3 tools/chipdb_compare.py BACKUP_DIR apycula

Rebuilt files never match byte for byte, because sets serialize in a different
order on each run. A raw msgpack comparison shows thousands of false differences.

## Reverse engineering the IDE

`IDE/lib/libgowin.so` holds place and route and bitstream generation. It is
**not stripped** and is built at **-O0**, so symbol names and very regular code
are available.

Pick the cheapest tool that answers the question:

1. `nm -DC` for names. Most of what you want is named; start with `fusegenMem::`.
2. `objdump -d -C --start-address --stop-address` for single functions.
   `nm -S` gives the address and size. -O0 disassembly is easy to follow.
3. Python over `objdump` output for anything repeated. Jump tables are
   `cmp; ja; lea table(%rip); movslq; add; jmp *%rax`, with 32-bit offsets
   relative to the table.
4. `tools/gowin_decompile.py` for real decompilation. It needs no full analysis
   and takes seconds. REA's full analysis of this library takes hours, treats
   `__dynamic_cast` as noreturn and truncates functions such as `setClsRegAttr`.

Prefer static analysis over running vendor binaries. Do not modify the IDE or
work around its licensing.

`apycula/fse_formats.py` is committed, so extraction only needs re-running for a
new IDE version. Vendor enums are not committed; generate them when updating
`apycula/attrids.py`:

| Tool | Purpose |
|---|---|
| `tools/gowin_extract.py extract` | Generates `apycula/fse_formats.py` and writes vendor enums to a local `enums.json` |
| `tools/gowin_extract.py check-attrids` | Compares `apycula/attrids.py` with vendor names |
| `tools/gowin_attr_sites.py` | Lists attribute assignments with approximate guards; research aid, output not committed |
| `tools/gowin_decompile.py` | Decompiles named functions with Ghidra, applying Gowin enums, parameter structs and signatures; no full analysis needed |
| `tools/chipdb_compare.py` | Content comparison of chipdb directories |

Do not edit `apycula/fse_formats.py` by hand.

## Separating evidence from inference

When writing findings, say what was read from code, what was checked against
data, and what is inferred. Name the IDE version for any address. Name the
primitives or tables you actually traced, rather than generalising from one.
