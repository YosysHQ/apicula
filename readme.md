# Project Apicula

<img src="apicula.svg" width="250" />

Open source tools and [Documentation](https://github.com/YosysHQ/apicula/wiki) for the Gowin FPGA bitstream format.

Project Apicula uses a combination of fuzzing and parsing of the vendor data files to provide Python tools for generating bitstreams.

## Getting Started

Install the latest git [yosys](https://github.com/yosyshq/yosys#setup), [nextpnr-himbaechel](https://github.com/YosysHQ/nextpnr#gowin), [openFPGALoader](https://github.com/trabucayre/openFPGALoader), and Python 3.8 or higher. [Yowasp](http://yowasp.org/) versions of Yosys and Nextpnr are also supported.

Currently supported boards are
 * Trenz TEC0117: GW1NR-UV9QN881C6/I5
 * Sipeed Tang Nano: GW1N-LV1QN48C6/I5
 * Sipeed Tang Nano 1K: GW1NZ-LV1QN48C6/I5
 * Sipeed Tang Nano 4K: GW1NSR-LV4CQN48PC7/I6
 * Sipeed Tang Nano 9K: GW1NR-LV9QN88PC6/I5 [^1]
 * Sipeed Tang Nano 20K: GW2AR-LV18QN88C8/I7 [^1]
 * Sipeed Tang Primer 20K: GW2A-LV18PG256C8/I7 [^1]
 * Seeed RUNBER: GW1N-UV4LQ144C6/I5
 * szfpga: GW1NR-LV9LQ144PC6/I5

[^1]: `C` devices require passing the `--vopt family` flag as well as `--device` to Nextpnr, and stating the family in place of device when passing `-d` to `gowin_pack` because the C isn't part of the device ID but only present in the date code. Check `examples/Makefile` for the correct command.

Install the tools with pip.

```bash
pip install apycula
```

Note that on some systems the installed binaries might not be on the path. Either add the binaries to the path, or use the path of the _installed binary_ directly. (running the source files will lead to import errors)

```bash
which gowin_pack # check if binaries are on the path
python -m site --user-base # find the site packages base directory
ls $HOME/.local/bin # confirm the binaries are installed in this folder
export PATH="$HOME/.local/bin:$PATH" # add binaries to the path
```

From there, compile a blinky.

The example below is for the Trenz TEC0117. For other devices, use the model numbers listed above for `--device`, and replace `tec0117` with `runber`, `tangnano`, `tangnano4k` or `tangnano9k` accordingly. Also note the number of LEDs on your board: 8 for tec0117 and runber, 3 for honeycomb and tangnano. 
You can also use the Makefile in the examples folder to build the examples.

```bash
cd examples
yosys -D LEDS_NR=8 -p "read_verilog blinky.v; synth_gowin -json blinky.json"
DEVICE='GW1NR-UV9QN881C6/I5'  # change to your device
BOARD='tec0117' # change to your board
nextpnr-himbaechel --json blinky.json \
                   --write pnrblinky.json \
                   --device $DEVICE \
                   --vopt cst=$BOARD.cst
gowin_pack -d $DEVICE -o pack.fs pnrblinky.json # chango to your device
# gowin_unpack -d $DEVICE -o unpack.v pack.fs
# yosys -p "read_verilog -lib +/gowin/cells_sim.v; clean -purge; show" unpack.v
openFPGALoader -b $BOARD pack.fs
```

For the Tangnano9k board, you need to call nextpnr and gowin_pack with the chip family as follows:
```
nextpnr-himbaechel --json blinky.json \
                   --write pnrblinky.json \
                   --device $DEVICE \
                   --vopt family=GW1N-9C \
                   --vopt cst=$BOARD.cst
gowin_pack -d GW1N-9C -o pack.fs pnrblinky.json
```

For the Tangnano20k (TangPrimer20k) board, you need to call yosys with the chip family as follows:
```
yosys -D LEDS_NR=8 -p "read_verilog blinky.v; synth_gowin -json blinky.json -family gw2a"
```

## Getting started for contributors

In addition to the above, to run the fuzzers and build the ChipDB, the following additional dependencies are needed.

Version 1.9.10.03 of the Gowin vendor tools. Newer versions may work, but have not been tested.

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

### Funding

This project was funded through the <a href="https://nlnet.nl/PET">NGI0 PET</a> and [NGI Zero Entrust](https://nlnet.nl/entrust) Fund, a fund established by <a href="https://nlnet.nl">NLnet</a> with financial support from the European Commission's <a href="https://ngi.eu">Next Generation Internet</a> programme, under the aegis of DG Communications Networks, Content and Technology under grant agreement N<sup>o</sup> 825310 and 101069594.
