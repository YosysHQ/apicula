# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

See @AGENTS.md for the build environment and how to reverse engineer the Gowin IDE, and `doc/agent/` for what has been learned so far.

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
