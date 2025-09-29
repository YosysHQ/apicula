# Command structure

## Config Frames

`0x3B` looks like the “load config” command (similar to `LSC_PROG_INCR_RTI` for ECP5)
`0x80` CRC enable
`0x02` number of frames MSB
`0xC8` number of frames LSB

Followed by configuration frames (including EBR) (`0x2C8`=712) of them in this case, gw1nr9)

Each frame seems to be:
    1. Frame data, with 1s appended at the start to make it an multiple of 8 bits (guess, similar to ECP5)
    2. CRC-16 that matches “CRC-16/ARC” algorithm at https://crccalc.com/ but endian swapped (optional)
    3. 6x `0xFF` bytes

At end of bitstream 18 more `0xFF` bytes followed by 2 bytes `0x34` `0x73` which are the CRC as above of the last 24 `0xFF` bytes

First CRC is special, like ECP5, as it also covers the commands after the preamble except the flash address.

## Preamble

20 `0xFF` bytes, followed by two bytes “file checksum” (for early Vendor tool release), followed by `0xFF` `0xFF` `0xA5` `0xC3`
For comparison ECP5 preamble is `0xFF` `0xFF` `0xBD` `0xB3`
“File checksum” matches value displayed in programmer, unlikely actually used by hardware

## Slots
Slots (the name was chosen for lack of a better term) are single cells located outside the main grid. They are designed to accommodate fuses for a single functional block, such as a PLL.

The slots have the same height of 8 rows and different widths. There is no geometric reference to the main grid or to each other, but there is a unique number that defines the function of the slot - for example, slot number 8 is intended for the lowest PLL.     

Slots that are not used in a particular design are simply not included in the output file.

Slot commands:

`0x6a` `0x00` `0x00` `0x00` `0x00` `0x00` `0x00` `slot_index` - beginning of the slot description with the `slot_index` index, a special case when `slot_index=0xff` is specified - this is the beginning of the slot block if the  slots were included in the design at all.

`0x6d` `0x00` `0x00` `0x00` + 16 bytes of `0xff` - unknown.

`0x6b` `0x80` `0x00` + `slot_size` - size in bytes, actually the width of the slot since the height is always equal to 8. This is followed by the slot content bytes, followed by two CRC bytes and 16 bytes of `0xff`.

`0x68` `0x00` `0x00` `0x00` `0x00` `0x00` `0x00` `0x00` - end of the slot block

## BSRAM init (GW5A)
The data for initialising BSRAM in chips up to the GW5A series is a single continuous array containing data for all BSRAM elements in the entire chip and located immediately after the description of the main grid fuse - in fact, it is simply a continuation of the main matrix, with no separator bytes.

It's a completely different story in the GW5A series, where initialisation data is only specified for elements that are actually used*. Therefore, we will need commands to specify where to place the initialisation data in the chip. These commands operate on vertical blocks 256 bits wide as units.

`0x12` (or `0x92` when `bit_crc_check` not set) `0x00` `0x00` `0x00` - start of description of one or more consecutive blocks.

`0x70` `0x00` `0x00` index_lsb index_msb 0*index - The index of the first block.

Blocks are numbered from zero, but you cannot take the first two because they simply do not exist. Here is a fragment of the beginning of the 10th row of the chip grid (rows with BSRAM). Before we get to the letter B, which symbolises BSRAM, we have cells with IO and cells with routing wires.

dat.grid.rows[10] = [1RRRRBbbBbbBb...

The tail contains a zero byte repeated index times. The theory is that the receiving mechanism in the chip is not that complex and it uses every zero byte to shift some internal position for recording further data.

`0x4e` `0x80` count_lsb count_msb - number of consecutive blocks.
Specifies data for how many 256-byte blocks follow next.

Next comes the actual data for the BSRAM blocks, with 256 lines per block. At the end of each line there are two CRC bytes and 6 bytes of `0xff`.

18 * `0xff` two bytes CRC - end of description of one sequence of blocks.

* This is true to a certain extent — if there is both used and unused BSRAM in a single block, the data for the entire block is still unloaded.

## Other commands

Command always followed by 3 “option” bytes, usually `0x00` except for “load config”, like ECP5 commands

`0x06` (or `0x86` when `bit_crc_check` not set) IDCODE check (similar to ECP5 `VERIFY_ID`)
Followed by 3x `0x00` bytes

Then the JTAG IDCODE
For GW1N-1: IDCODE `0x0900281B`; bytes here `0x09` `0x00` `0x28` `0x1B`
For GW1NR-9: IDCODE `0x1100581B`; bytes here `0x11` `0x00` `0x58` `0x1B`
For GW2AR-18: IDCODE `0x0000081B`; bytes here `0x00` `0x00` `0x08` `0x1B`


`0x10` (or `0x90` when `bit_crc_check` not set)
- [56:24]: unknown `0x00000000` (seems to be same for all devices and configs)
- [23:16]: value depending on `loading_rate` (value to determine) (or 0x00 when N/A)
- [15:14]: unknown `0x0`
- [13]   : `1` when `bit_compress` set
- [12]   : `1` when `program_done_bypass` set
- [11:0] : unknown `0x000`

`0x51` (or `0xD1` when `bit_crc_check` not set) Compress configuration
 - [56:24] : unknown `0x00FFFFFF` (seems to be same for all devices and configs)
 - [23:16] : `OxFF` for uncompressed bitstream or a value used to replace 8x `0x00` in compress mode
 - [15:8]  : `OxFF` for uncompressed bitstream or a value used to replace 4x `0x00` in compress mode
 - [7:0]   : `OxFF` for uncompressed bitstream or a value used to replace 2x `0x00` in compress mode

`0x0B` (or `0x8B` when `bit_crc_check` not set) only present when `bit_security` is set
Followed by 3x `0x00` bytes

`0xD2` Set SPI flash address (8 bytes)
 - [56:32]: unknown, always `0x00FFFF`
 - [31:0] : SPI flash address (or `0x00000000` if N/A)


Last command before `0x3B` (or `0xBB` when `bit_crc_check` not set) config frame load command, probably equiv to `LSC_INIT_ADDRESS`
- [23]   : `1` when `bit_crc_check` set
- [22:16]: unknown, always `0x00`
- [15:0] : number of lines in configuration data section

`0x0A` set USERCODE (similar to `ISC_PROGRAM_USERCODE`)
Followed by 3x `0x00` bytes
Then the 4-byte USERCODE

`0x08` final command in bitstream, probably equivalent to ECP5 `ISC_PROGRAM_DONE`
Followed by 3x `0x00` bytes

`0xFF` NOP/padding


