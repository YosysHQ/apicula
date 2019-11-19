# Architecture

Gowin FPGAs have a LUT4 architecture common to many smaller FPGA architectures. The FPGA consist of a grid of tiles with I/O buffers around the edges, rows of special-function blocks such as BRAM, and a large grid configurable logic units.

![tile layout](fig/fuse.png)

Each Configurable logic unit consists of 8 LUT4s grouped in 4 slices, of which 3 have data flip-flops. Each slice shares certain resources such as clock inputs and reset lines.

Each LUT4 has 4 inputs and one output that is directly connected to the data flip-flop input. The LUT output can be used independently, but the flip-flop is always used through the LUT. Each pair of flip flops has data in and out, clock, clock enable, and set/reset. Each pair of flip-flops can be configured for rising edge or falling edge sensitivity, and asynchronous or synchronous set or clear.

These tiles are connected with various multiplexers to adjacent tiles as well as global clock lines. Each tile has 8 tile-local wires, 4 one-hop wires of which 2 are shared between north/south and east/west, 8 two-hop wires with one-hop taps, and 4 eight-hop wires with four-hop taps. An overview of all wires can be seen below.

![tile wires](fig/clu.png)

The bitstream consist of frames. Frames describe one row of bits on the FPGA tile grid. Frames are padded to full bytes, and verified with a CRC-16 checksum. These rows are stacked on top of each other to describe a bitmap that is overlaid on the FPGA tile grid.

The number of tiles on the grid depend on the specific FPGA model. A tile is roughly 60x24 bits, with I/O buffers and some special tiles being a few rows or columns larger. A common logic tile has the LUTs and flip-flops in the bottom 4 rows, with the top 20 rows being filled with multiplexers. An overview of the bitstream layout of LUTs, flip-flops, and multiplexers in a logic tile can be seen below.

![tile fuses](fig/tile.png)
