# Project Apicula

Documentation of the Gowin FPGA bitstream format.

Project Apicula uses a combination of fuzzing and parsing of the vendor data files to find the meaning of all the bits in the bitstream.

# Files overview

* `bslib.py` utilities for parsing `.fs` bitstream files in ascii format.
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
  * `simple.sh` script to synth and PnR `blinky.v`.
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
