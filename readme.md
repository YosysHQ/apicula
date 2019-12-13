# Project Apicula

Documentation of the Gowin FPGA bitstream format.

Project Apicula uses a combination of fuzzing and parsing of the vendor data files to find the meaning of all the bits in the bitstream.

##  Dependencies

Version 1.9 of the Gowin vendor tools, and a copy of the Excel pinout files downloaded in `~/Documents/gowinsemi`

The latest Yosys and Nextpnr, installed with the generic backend.

Python:
* Numpy
* Pandas
* Pillow
* crcmod
* xlrd

## Getting Started

For GW1NR-9
TODO: update

```bash
virtualenv env
source env/bin/activate
export GOWINHOME=/gowin/installation
export DEVICE="GW1NR-9"
pip install numpy pandas pillow crcmod xlrd ipython
python dat19_h4x.py
# look at dat.json
cd legacy/empty
/gowin/installation/IDE/bin/gw_sh run.tcl
cp impl/pnr/empty.fs ../../
cd ../../generic
bash simple.sh blinky.v
# or
bash simple.sh attosoc/*.v
# open blinky.vm and blinky.posp in Gowin Floorplanner
# look at blinky.il and blinky.png
cd ..
python gowin_pack.py /gowin/installation/IDE/share/device/GW1NR-9/GW1NR-9.fse generic/pnrblinky.json
# look at pack.png and pack.fs
python gowin_unpack.py /gowin/installation/IDE/share/device/GW1NR-9/GW1NR-9.fse pack.fs
yosys -p "read_verilog -lib +/gowin/cells_sim.v; clean -purge; show" unpack.v
/gowin/installation/Programmer/bin/programmer_cli --device GW1NR-9 --run 2 --fsFile /path/to/pack.fs
```

For GW1N-1
TODO: add instructions

Other devices are currently not supported. Read on to learn how to contribute other devices.

## Status

This project is in its very early stages, and not ready for general use.
It only supports very rudimentary FPGA features, and has only been tested with the Trenz TEC0117 board with a GW1NR-9 FPGA.

For users, there is a very basic and slow Nextpnr script based on the generic target. It can be modified to synthesize simple designs. These can be packed into a bitstream using `gowin_pack`. This exprimental flow only uses basic IOB, and 3/4 of the available DFF and LUT. No other resources are supported yet. Global routing is not supported, so you might have setup and hold time violations.

For developers, there are two fuzzers, parsers for vendor data files, and a `gowin_unpack` script to inspect bitstreams. One fuzzer efficiently fuzzes the whole FPGA without any assumptions, while the other fuzzer uses vendor data files to inspect specific tiles. The vendor data parsers are fairly complete in the sense that there are few unparsed sections left, but understanding of the parsed data leaves a lot to be desired. The bitstream packer and unpacker take a few shortcuts when it comes to commands, but completely parse and emit correct data frames.

## What remains to be done / how can I help?

There is a lot of work left to do before this is a mature and complete FPGA flow.
The upside is that there is something for people from all skill levels and backgrounds.

### Fuzzing

This project partially relies on the data files provided by the vendor to work.
However, the exact meaning of these files is often not completely understood.
Fuzzing can be used to discover the meaning of the vendor files.

`tiled_fuzzer.py` is a fuzzer that uses vendor files to find bits in a specific tile type. Adding code for a new primitive or tile type is relatively easy. All that is neede is a function that uses `codegen.py` to generate the primitive of interest, which has to be added to the `fuzzers` list. Then the output at the bottom of the script can be adjusted to your needs.

There is a `gowin_unpack.parse_tile` function which uses our understanding of the vendor files to look for matching items. On the other hand `gowin_unpack.scan_fuses` will just give you a list of fuses that were set in the tile, and `gowin_unpack.scan_tables` will go through *all* vendor data tables and spit out even a partial match. The latter will give false positives, but is helpful when discovering new tables.

`fuzzer.py` is a bit more complex to write new fuzzers for, but could be usefull in some cases. It is for example much more efficient in fuzzing array parameters such as LUT bits, BRAM contents, and PLL settings. Have a look at `Lut4BitsFuzzer` for ideas about how to fuzz BRAM and DRAM for example.

Things that could be fuzzed:

* ALU modes, look at `CIN` and `COUT` wires.
* DRAM modes and bits
* IOB logic levels and drive stengths, may require some refactoring to fuzz constraints.
* BRAM modes and bits
* IO logic (LVDS etc.), expected to be complex.
* Global routing, have a look at `Cmux` tables in `.dat` files and `GB` wires, compare with [Project Trellis Global Routing](https://symbiflow.readthedocs.io/en/latest/prjtrellis/docs/architecture/global_routing.html)
* PLL settings

### Parsing

For each FPGA, the vendor provides `.dat`, `.fse`, `.ini`, `.pwr`, and `.tm` files. Of these, only parsers for `.dat` and `.fse` have been written. It is expected that the `.pwr`, and `.tm` files contain respectively power and timing data, which will be of crucial importance when writing a full-fledged Nextpnr flow.

The format of these other files is unknown, you're on your own here. I could only offer you some vague pointers based on experience from the other two files.

For a description of the known file format, [see the documentation](doc/filestructure.md).

The parser for the `.fse` format is fairly robust and complete, but vendor software updates sometimes add new file and table types.
The main thing lacking here is a better understanding of the meaning of all these tables. Part of this can be done with [fuzzing](#fuzzing), but another large part is just looking at the data for patterns and correlations. For example, some numbers might be indices into other tables, wire IDs, fuse IDs, or encoded X/Y positions.


The parser for the `.dat` file is more fragile and incomplete. This is mainly because it just appears to be a fixed format struct with array fields. New vendor software versions sometimes add new fields, breaking the parser. Here there are actually a few gaps in the data that have not been decoded and named. It is suspected that at least some of these gaps are related to pinouts and packaging.

### Nextpnr

Currently, the Nextpnr flow is based on the [simple example](https://github.com/YosysHQ/nextpnr/tree/master/generic/examples) of the generic target. This script is very slow to load (over a dozen seconds) and cannot be easily extended to support more of the Gowin FPGA. So this script should very much be seen as a proof of concept that is not worth extending.

Eventually a proper Nextpnr target will need to be written. This is quite a large chunk of code that needs to be written, but the upside is that the ice40 target can serve as a basis. [Some documentation is available](https://github.com/YosysHQ/nextpnr/blob/master/docs/coding.md)

Part of this will be writing a [binary blob assembler](https://github.com/YosysHQ/nextpnr/tree/master/bba) script to encode the vendor data files into a format suitable for Nextpnr, or port the Python parsers for the vendor files to C++ and use the vendor files directly with Nextpnr.

### Refactoring

There are quite a few sketchy places in the code that could use some tender loving care, without taking a deep dive into FPGA documenting.

The `.dat` parser was sort of patched to output a JSON file, but it would be a lot nicer if one could just import it as a library and get Python datastructures back directly. Both parsers could optionally be extended to map known IDs to more human readable values (`wirenames.py` for example), provide a more convenient structure, and chomp of padding values.

The fuzzers should be extended so that they run against all FPGA types. This is important to detect differences between FPGAs and generate ChipDBs for all of them. This does not require much in-depth knowledge. Just adding parameters for all FPGA types. A bit more involved is extending the fuzzer to fuzz global settings and constraints, these would need to be assigned config bits and toggle them accordingly.

The user-facing tools such as `gowin_pack` and `gowin_unpack` could really use some proper command line arguments, and could also be packaged in a proper Python package so that they can be installed easily. They could also be ported to something other than Python for speed.

Currently the ChipDB is just using Pickle because it's easy. This is however not a good format going forward. Some research needs to be done into a suitable format. This might involve either a single database, or a "master" database in a human readable format, and derived databases for PnR and bitgen.

Eventually it'd be really sweet if there were some tests and continuous integration.


### JTAG programmer

Currently the vendor programming tool is used. For a truly end-to-end open source flow, a JTAG programmer would have to be written, or at least adapted for use with Gowin FPGAs.

In some toolchains the IDE can generate a SVF file for use with other JTAG programmers. This could for example be used with OpenOCD. However, Gowin is not one of those toolchains.

So what needs to be done is to extract the JTAG commands used by the vendor tools by either capturing USB packets, or using a logic analyser to decode the JTAG commands at the FPGA inputs. With these commands, a script can be written that converts a bitstream to an SVF file that could be used with OpenOCD.

## Files overview

* `bslib.py` utilities for parsing `.fs` bitstream files in ascii format.
* `chipdb.py` a library for combining vendor and fuzzing data into a single chipDB
* `codegen.py` utilities for generating Verilog netlist files.
* `dat19_h4x.py` a parser for vendor `.dat` files used in PnR.
* `doc` documentation.
* `example` a simple test program.
* `fuse_h4x.py` a parser for vendor `.fse` files used in bitgen.
* `fuzzer.py` a fuzzer for finding bit locations of various things, not based on vendor files.
* `generic` Python files for the Nextpnr generic target
  * `bitstream.py` writes `.fasm`(unused) and `.vm`/`.posp` (for vendor floorplanner).
  * `blinky.v` example program
  * `simple.py` main Python script that generates all the bels and pips.
  * `simple.sh` script to synth and PnR Verilog files.
  * `simple_timing.py` generates the pip and port delays.
  * `synth` Yosys synthesis scripts and libs.
    * `cells_map.v` techmap file.
    * `prims.v` simulation primitives.
    * `synth_generic.tcl` Yosys synthesis script.
* `gowin_pack.py` the bitstream packer, turns Nextpnr JSON into Gowin `.fs`.
* `gowin_unpack.py` the bitstream unpacker, tursn Gowin `.fs` into Verilog.
* `legacy` old bash fuzzers, sometimes useful for a quick test.
* `pindef.py` extract pinout information form vendor spreadsheets.
* `tiled_fuzzer.py` a simplified fuzzer that uses vendor data files to fuzz a specific tile type.
* `wirenames.py` mapping between vendor wire IDs and names.
