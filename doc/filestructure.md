# File structure

Three important types of vendor files are parsed, `.dat`, `.fse`, and `.tm`. A parser exists for the `.ini` files as well, other files are not currently parsed.

# Wire names

The vendor files use wire IDs that map to the following names. A full mapping is found in `wirenames.py`

* 0-31 LUT inputs
* 32-39 LUT outputs
* 40-47 DFF outputs
* 48-55 unknown, maybe MUX outputs
* 56-63 X0 tile-local wires
* 64-75 X1 one-hop wires, origin segments
* 76-107 X2 two-hop wires, origin segments
* 108-123 X8 eight-hop wires, origin segments
* 124-126 DFF clock wires
* 127-129 DFF reset wires
* 130-132 DFF clock-enable wires
* 133-140 MUX selection wires
* 141-148 X1 one-hop wires, destination segments
* 149-212 X2 two-hop wires, destination segments
* 213-244 X8 eight-hop wires, destination segments
* 245-260 X1 one-hop alias wires to SN/EW wires, going both ways
* 261-268 long wires (branches)
* 269-276 global wires (branches)
* 277-278 high and low constant wires
* 279-290 long wires (taps ans spines)
* 291-294 global wires (taps)
* 295-302 DRAM input wires
* 303-308 ALU carry-in
* 309-314 ALU carry-out

The format for inter-tile wires is {direction}{length}{number}{segment}. So W270 is a westward two-hop wire, number 7, segment 0 (the root). W272 (segment 2) would be the same wire, two tiles to the west.

# Data file

The `.dat` file seems to contain a lot of information related to PnR. It appears to be a C struct directly written to file, so not much structure is present. The parser for this is located in `dat19.py`. This format is not stable across IDE versions.

Some unknown areas remain in this file, a large part of which is expected to be related to chip packages.

The first thing of interest is the tile grid, which is stored in a 150x200 array, prefixed by the size of the actual FPGA, and the location of the center tile (suspected root of the clock tree). There is a 32-bit tile type (overkill much?) and a 8-bit "used" value. Gowin employs binning, so some devices have half of their tiles "disabled" here. Of note is that this tile grid contains an extra ring of tiles between the IOB and CFU that is not present in the bitstream.

Then follow discriptions of some primitives and their inputs. The format for a thing Foo is that there is `NumFoos` describing how many Foos there are, `NumFooIns` describing the number of Foo inputs, followed by the list of `Foos` and the list of `FooIns`. These numbers are wires IDs that can be mapped to names with `wirenames.py`.

Then follow description of various things about pins and banks that are not fully understood.

Then follows *another* tiled grid, this time in ASCII and without the extra padding ring. It's not clear what the use is of each of these.

Then follows a quite interesting section, relating to hard IP blocks. Each tile has roughly the same set of muxes, but for these special tile types they map to different names. For example, what would be F6 in a normal tile is the IOB A output in IOB tiles.

Then follows a huge set of tables that mostly reproduce the inputs and outputs within a tile. It is not known how these tables are used compared to the ones at the start of the file. There seem to be small differences between them.

Finally, there are some more hard IP inputs and outputs listed.

# Fuse file

The `.fse` file seems to contain information related to bitstream generation, but can also be used for PnR because the information in this file seems to be more detailed than the `.dat` file. This file is a more structured archive with various "files" containing data tables.

Ther is a 4 byte preamble at the top of the file, followed by a number of files, terminated by a stop byte. Each file consists of a 4 byte tile type, a 4 byte width and height of the tile, and a 4 byte number of tables. Each table has a 4 byte type and length, with some having a width as well. Tables are either 2 byte or 4 byte numbers.

The first file is the header, it has a zero width and height with `grid`, `fuse`, and `logicinfo` tables.

The `grid` table is another tile grid, where the tile types map to other files in the archive. It is used to find the actual connections, wires, and bits for a particular tile. It's recommended to use this grid over the less precise one in the `.dat` file.

The `fuse` table is an important one. Many other tables contain indices into this table. The primary index is the fuse number, the secondary index is the tile type. The value in the table is 10000 or a decimal number in the form of `YYXX` representing the bit location within a tile corresponding to this fuse. Yea, you read that correctly, they stuff the bit location into a single number using decimal digits.

The `logicinfo` table describes the valid values of the parameters of the primitives (bels). Each row is a pair (parameter_id, value). This table can be used to generate fuses that program the specified parameter value. The point is that the first two fields of the `shortval` and `longval` tables are the row numbers of this logicinfo table, meaning that the fuses listed in the row of the `shortval` table, for example, must be set to specify the values of this parameter pair.

The other files all correspond to a specific tile type, and have a width and height. Note that IOB, DSP and BRAM tiles are slightly bigger than CFU tiles. Some important tables in thes tile files follow.

The `wire` tables contain the pips of a tile. it is of the format `[src, dest, *fuses]`, where an unused fuse is `-1`. The wire IDs can be mapped to names with `wirenames.py`. Some rows have a negative source wire, which seems to indicate that this fuse should be set to zero. These negative fuses contain the "default" state of a pip. Some rows also have wire IDs that fall outside the valid wire range, it is expected this is some sort of flag, but the meaning is not known. Table 2 contains the main routing, the use of other wire tables is not known.

`shortval` and `longval` describe bel features that can be configured. A short value has 2 "features" and a long value has 16 "features". Unused features are zero. Some known tables:

* 5: LUT bits, [LUT, bit, fuse]
* 23-24: IOB configuration, meaning unknown, fuzzer output used
* 25-27: DFF bits, meaning unknown, fuzzer output used
* 37: Bank enable, meaning unknown, maybe logic levels

The `const` table just contains some fuses that are always set, their meaning is unknown.
The meaning of `wiresearch` and `alonenode` tables is not known.

# Timing file

The `.tm` file contains timing info for the FPGA. This format is again more or less a C struct mapped to a file, however, the format is rather simple.

The file is split in several timing classes. Within a timing class there are several large subsections for things like LUTs, DFF, or routing. Within these sections are list of items, like the delay between two ports or some setup/hold time. Each item is expressed as 4 floating point numbers.

The reason there are 4 numbers is because NMOS transistors are more effective than PMOS transistors of the same size. An NMOS can pull down a wire faster than a PMOS can pull it up. So if there is an input and an output, that means 4 possible transitions.

Since we can assume the falling edge is faster, looking at items like the following, it can be seen that for the LUT the first and third item are lower and identical. For the DFF on the other hand, the first two items are lower than the second two items.

Since the first item relates to "data-in setuptime", and there is no combinational path through a DFF, it follows that these numbers can only relate to the input rising/falling edge. For the LUT clearly the output matters a great deal, and by elimination it *only* seems to take output times in to account.

```
'di_clksetpos': [0.36000001430511475, 0.36000001430511475, 0.5759999752044678, 0.5759999752044678]
'a_f': [1.2081600427627563, 1.2542400360107422, 1.2081600427627563, 1.2542400360107422]
```

So this means that the numbers represent

1. input falling, output falling
2. input falling, output rising
3. input rising, output falling
4. input rising, output rising

# IO Initialization File (.ini)

The .ini file contains IO configuration information. It reads like a table and contains information similar to what is found in the vendor provided IO CSV files (`input.csv`, `bidir.csv` and `output.csv`).

## Header
The header of the `.ini` files roughly corresponds to configurable **Features** (PullMode, Mode, etc) available for a device under consideration. The order of these features is predetermined. 

## Sections
The `.ini` file has 4 ordered sections -- `input`, `output`, `bidirectional` and `i3cBank`(optional). The i3cBank section seems to describe what IO banks on the device are capable of i3c; the `input` , `output` and `bidirectional` sections contain the information that their names imply. The number of rows corresponding to each section is predetermined but seems to always be the same as the number of rows in corresponding csv files like `{GOWINHOME}/IDE/data/iotable/input.csv`.


## Rows

The cells in a row map to cofiguration options for specific IO Features (defined by the header). The first cell is a 4-byte value that represents the IO Type and the last cell is a 4-byte value that represents IO Mode. The cells between the first and last cells contain configuration options for each IO **Feature**. These cells are prefixed by a 2-byte `count` that determines the number of options available, followed by `count` 4-byte words that correspond to individual configuration options.

