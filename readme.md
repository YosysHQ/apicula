# Project Apicula

Documentation and open source tools for the Gowin FPGA bitstream format.

Project Apicula uses a combination of fuzzing and parsing of the vendor data files to provide Python tools for generating bitstreams.

This project is supported by our generous sponsors. Have a look at our [contributors](https://github.com/YosysHQ/apicula/graphs/contributors) and sponsor them with via the various platforms linked on our [github](https://github.com/YosysHQ/apicula).

## Getting Started

Install the latest git [yosys](https://github.com/yosyshq/yosys#setup), [nextpnr-gowin](https://github.com/YosysHQ/nextpnr#nextpnr-gowin), [openFPGALoader](https://github.com/trabucayre/openFPGALoader), and Python 3.6 or higher. [Yowasp](http://yowasp.org/) versions of Yosys and Nextpnr are also supported.

Currently supported boards are
 * Trenz TEC0117: GW1NR-UV9QN881C6/I5
 * Sipeed Tang Nano: GW1N-LV1QN48C6/I5
 * Sipeed Tang Nano 1K: GW1NZ-LV1QN48C6/I5
 * Sipeed Tang Nano 4K: GW1NSR-LV4CQN48PC7/I6
 * Sipeed Tang Nano 9K: GW1NR-LV9QN88PC6/I5 [^1]
 * Seeed RUNBER: GW1N-UV4LQ144C6/I5
 * @Disasm honeycomb: GW1NS-UX2CQN48C5/I4

[^1]: `C` devices require passing the `--family` flag as well as `--device` to Nextpnr, and stating the family in place of device when passing `-d` to `gowin_pack` because the C isn't part of the device ID but only present in the date code. Check `examples/Makefile` for the correct command.

Install the tools with pip.

```bash
pip install apycula
```

Note that on some systems the installed binaries might not be on the path. Either add the binaries to the path, or use the path of the _installed binary_ directly. (running the source files will lead to import errors)

```bash
which gowin_bba # check if binaries are on the path
python -m site --user-base # find the site packages base directory
ls $HOME/.local/bin # confirm the binaries are installed in this folder
export PATH="$HOME/.local/bin:$PATH" # add binaries to the path
```

From there, compile a blinky.

The example below is for the Trenz TEC0117. For other devices, use the model numbers listed above for `--device`, and replace `tec0117` with `runber`, `tangnano`, `tangnano4k` or `honeycomb` accordingly. Also note the number of LEDs on your board: 8 for tec0117 and runber, 3 for honeycomb and tangnano. 
You can also use the Makefile in the examples folder to build the examples.

```bash
cd examples
yosys -D LEDS_NR=8 -p "read_verilog blinky.v; synth_gowin -json blinky.json"
DEVICE='GW1NR-UV9QN881C6/I5'  # change to your device
BOARD='tec0117' # change to your board
nextpnr-gowin --json blinky.json \
              --write pnrblinky.json \
              --device $DEVICE \
              --cst $BOARD.cst
gowin_pack -d $DEVICE -o pack.fs pnrblinky.json # chango to your device
# gowin_unpack -d $DEVICE -o unpack.v pack.fs
# yosys -p "read_verilog -lib +/gowin/cells_sim.v; clean -purge; show" unpack.v
openFPGALoader -b $BOARD pack.fs
```

## Getting started for contributors

In addition to the above, to run the fuzzers and build the ChipDB, the following additional dependencies are needed.

Version 1.9.8 of the Gowin vendor tools. Newer versions may work, but have not been tested.

Alternatively, you can use the `Dockerfile` to run the fuzzers in a container.

To run the fuzzers, do the following in a checkout of this repo

```bash
pip install -e .
export GOWINHOME=/gowin/installation
make
```

## Resources

Check out the `doc` folder for documentation about the FPGA architecture, vendor file structure, and bitstream structure.

My internship report about this project [can be downloaded here](https://github.com/pepijndevos/internshipreport).

My presentations at [FPT2020](https://www.youtube.com/watch?v=kyQLtBh6h0U) and [RC3](https://media.ccc.de/v/rc3-739325-how_to_fuzz_an_fpga_my_experience_documenting_gowin_fpgas).

I did a few [livestreams on twitch](https://www.twitch.tv/pepijnthefox) working on this project, which are collected [on this playlist](https://www.youtube.com/playlist?list=PLIYslVBAlKZad3tjr5Y4gqBV3QKQ5_tPw) I've also started to write Jupyter notebooks of my explorations that are more condensed than a video.

You can also come chat on [Matrix](https://matrix.to/#/#apicula:matrix.org) or [IRC](https://web.libera.chat/#yosys-apicula)

## What remains to be done / how can I help?

There is a lot of work left to do before this is a mature and complete FPGA flow.
The upside is that there is something for people from all skill levels and backgrounds.

### Fuzzing

This project partially relies on the data files provided by the vendor to work.
However, the exact meaning of these files is often not completely understood.
Fuzzing can be used to discover the meaning of the vendor files.

`tiled_fuzzer.py` is a fuzzer that uses vendor files to find bits in a specific tile type. Adding code for a new primitive or tile type is relatively easy. All that is neede is a function that uses `codegen.py` to generate the primitive of interest, which has to be added to the `fuzzers` list. Then the output at the bottom of the script can be adjusted to your needs.

There is a `fuse_h4x.parse_tile` function which uses our understanding of the vendor files to look for matching items. On the other hand `fuse_h4x.scan_fuses` will just give you a list of fuses that were set in the tile, and `fuse_h4x.scan_tables` will go through *all* vendor data tables and spit out even a partial match. The latter will give false positives, but is helpful when discovering new tables.

`fuzzer.py` is a bit more complex to write new fuzzers for, but could be usefull in some cases. It is for example much more efficient in fuzzing array parameters such as LUT bits, BRAM contents, and PLL settings. Have a look at `Lut4BitsFuzzer` for ideas about how to fuzz BRAM and DRAM for example.

Things that could be fuzzed:

* DRAM modes and bits
* BRAM modes and bits
* IO logic (LVDS etc.), expected to be complex.
* PLL settings

### Parsing

For each FPGA, the vendor provides `.dat`, `.fse`, `.ini`, `.pwr`, and `.tm` files. Of these, only parsers for `.dat`, `.fse` and `.tm` have been written.

The format of these other files is unknown, you're on your own here. I could only offer you some vague pointers based on experience from the other two files.

For a description of the known file formats, [see the documentation](doc/filestructure.md).

The parser for the `.fse` format is fairly robust and complete, but vendor software updates sometimes add new file and table types.
The main thing lacking here is a better understanding of the meaning of all these tables. Part of this can be done with [fuzzing](#fuzzing), but another large part is just looking at the data for patterns and correlations. For example, some numbers might be indices into other tables, wire IDs, fuse IDs, or encoded X/Y positions.

The parser for the `.dat` file is more fragile and incomplete. This is mainly because it just appears to be a fixed format struct with array fields. New vendor software versions sometimes add new fields, breaking the parser. Here there are actually a few gaps in the data that have not been decoded and named. It is suspected that at least some of these gaps are related to pinouts and packaging.

The format of the '.tm' appears to be just a big collection of floats. Not all of them have a meaning that is well understood, but the parser itself is fairly complete.

### Refactoring

There are quite a few sketchy places in the code that could use some tender loving care, without taking a deep dive into FPGA documenting.

The `.dat` parser was sort of patched to output a JSON file, but it would be a lot nicer if one could just import it as a library and get Python datastructures back directly. Both parsers could optionally be extended to map known IDs to more human readable values (`wirenames.py` for example), provide a more convenient structure, and chomp of padding values.

The fuzzers should be extended so that they run against all FPGA types. This is important to detect differences between FPGAs and generate ChipDBs for all of them. This does not require much in-depth knowledge. Just adding parameters for all FPGA types. A bit more involved is extending the fuzzer to fuzz global settings and constraints, these would need to be assigned config bits and toggle them accordingly.

This project was funded through the <a href="/PET">NGI0 PET</a> Fund, a fund established by <a href="https://nlnet.nl">NLnet</a> with financial support from the European Commission's <a href="https://ngi.eu">Next Generation Internet</a> programme, under the aegis of DG Communications Networks, Content and Technology under grant agreement N<sup>o</sup> 825310.
