# Command structure

## Config Frames

`0x3B` looks like the “load config” command (similar to `LSC_PROG_INCR_RTI` for ECP5)
`0x80` flags/config?
`0x02` number of frames MSB
`0xC8` number of frames LSB

Followed by configuration frames (`0x2C8`=712) of them in this case, gw1nr9)

Each frame seems to be:
    1. Frame data, with 1s appended at the start to make it an multiple of 8 bits (guess, similar to ECP5)
    2. CRC-16 that matches “CRC-16/ARC” algorithm at https://crccalc.com/ but endian swapped
    3. 6x `0xFF` bytes

At end of bitstream 18 more `0xFF` bytes followed by 2 bytes `0x34` `0x73` which are the CRC as above of the last 24 `0xFF` bytes

First CRC is special, like ECP5, as it also covers the commands after the preamble except the flash address.

## Preamble

20 `0xFF` bytes, followed by two bytes “file checksum”, followed by `0xFF` `0xFF` `0xA5` `0xC3`
For comparison ECP5 preamble is `0xFF` `0xFF` `0xBD` `0xB3`
“File checksum” matches value displayed in programmer, unlikely actually used by hardware

## Other commands

Command always followed by 3 “option” bytes, usually `0x00` except for “load config”, like ECP5 commands

`0x06` IDCODE check (similar to ECP5 `VERIFY_ID`)
Followed by 3x `0x00` bytes

Then the JTAG IDCODE
For GW1N-1: IDCODE `0x0900281B`; bytes here `0x09` `0x00` `0x28` `0x1B`
For GW1NR-9: IDCODE `0x1100581B`; bytes here `0x11` `0x00` `0x58` `0x1B`
For GW2AR-18: IDCODE `0x0000081B`; bytes here `0x00` `0x00` `0x08` `0x1B`


`0x10` some kind of config register like ECP5 `LSC_PROG_CNTRL0`
Followed by 3x `0x00` bytes
Then 4 config bytes

GWN1R-9 JTAG: `0x00000000`
GWN1R-9 JTAG AUTO BOOT: `0x00000000`
GWN1R-9 JTAG DUAL BOOT: `0x00780000`
Sets configuration speed, again similar to ECP5 (need to check exact options)

`0x51` Unknown
Followed by `0x00` then 6x `0xFF` bytes (seems to be same for all devices and configs)

`0x0B` Unknown 
Followed by 3x `0x00` bytes
Fairly near start, maybe some kind of init/setup or equivalent to `LSC_RESET_CRC`?

`0xD2` Set SPI flash address
Followed by `0x00` `0xFF` `0xFF`
Then 4-byte SPI flash address (or `0xFFFFFFFF` if N/A)

`0x12` Unknown
Followed by 3x `0x00` bytes
Last command before `0x3B` config frame load command, probably equiv to `LSC_INIT_ADDRESS`

`0x0A` set USERCODE (similar to `ISC_PROGRAM_USERCODE`)
Followed by 3x `0x00` bytes
Then the 4-byte USERCODE

`0x08` final command in bitstream, probably equivalent to ECP5 `ISC_PROGRAM_DONE`
Followed by 3x `0x00` bytes

`0xFF` NOP/padding


