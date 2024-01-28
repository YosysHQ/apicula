# SDRAM

Gowin devices with the R suffic such as the GW1NR-9 have built-in SDRAM.
This SDRAM is a System-in-Package wirdebonded of the shelf SDRAM module.
So there isn't so much to fuzz, you just have to know the pinout and the model.

Gowin has been so kind as to provide LiteX with [the details](https://github.com/litex-hub/litex-boards/blob/8a33c2aa312dddc66297f7cd6e39107fda5a2efb/litex_boards/targets/trenz_tec0117.py#L92-L118) of the model and pinout. That is... the magic wire names that result in the vendor placing the IOB in the correct place.

For the open source tools, you can't use the magic wire names. But what you can do is feed the magic wire names to the vendor and look at the generated placement.
This is what has been done in `/legacy/sdram`, which is a standalone script not tied into the rest of Apicula.

The result for GW1NR-9 is as below. A daring adventurer could use these to develop their own SDRAM controller or try to add support for LiteX on open source Gowin tools.

| SIGNAL NAME      | PIN LOCATION |
| ---------------- | ------------ |
| IO_sdram_dq(0)   | R29C26_IOA   |
| IO_sdram_dq(1)   | R29C27_IOA   |
| IO_sdram_dq(2)   | R29C35_IOA   |
| IO_sdram_dq(3)   | R29C36_IOA   |
| IO_sdram_dq(4)   | R29C37_IOA   |
| IO_sdram_dq(5)   | R29C38_IOA   |
| IO_sdram_dq(6)   | R29C39_IOA   |
| IO_sdram_dq(7)   | R29C40_IOA   |
| IO_sdram_dq(8)   | R29C16_IOB   |
| IO_sdram_dq(9)   | R29C17_IOB   |
| IO_sdram_dq(10)  | R29C18_IOA   |
| IO_sdram_dq(11)  | R29C18_IOB   |
| IO_sdram_dq(12)  | R29C19_IOB   |
| IO_sdram_dq(13)  | R29C20_IOB   |
| IO_sdram_dq(14)  | R29C21_IOB   |
| IO_sdram_dq(15)  | R29C22_IOB   |
| O_sdram_clk      | R1C4_IOB     |
| O_sdram_cke      | R1C9_IOA     |
| O_sdram_cs_n     | R1C35_IOB    |
| O_sdram_cas_n    | R1C40_IOB    |
| O_sdram_ras_n    | R1C40_IOA    |
| O_sdram_wen_n    | R1C44_IOA    |
| O_sdram_addr(0)  | R1C31_IOA    |
| O_sdram_addr(1)  | R1C28_IOA    |
| O_sdram_addr(2)  | R1C27_IOA    |
| O_sdram_addr(3)  | R1C26_IOA    |
| O_sdram_addr(4)  | R1C22_IOB    |
| O_sdram_addr(5)  | R1C21_IOB    |
| O_sdram_addr(6)  | R1C18_IOB    |
| O_sdram_addr(7)  | R1C18_IOA    |
| O_sdram_addr(8)  | R1C14_IOB    |
| O_sdram_addr(9)  | R1C14_IOA    |
| O_sdram_addr(10) | R1C31_IOB    |
| O_sdram_addr(11) | R1C9_IOB     |
| O_sdram_dqm(0)   | R1C44_IOB    |
| O_sdram_dqm(1)   | R1C4_IOA     |
| O_sdram_ba(0)    | R1C35_IOA    |
| O_sdram_ba(1)    | R1C32_IOA    |


Similarly, the results for the GW2AR-18 are below. When the SDRAM is used, the Bank Voltage for banks 2 and 7 must be set to 3.3V. The ID jump from ```21``` to ```24``` is due to two address wires that are not used on the GW2AR-18. 

| ID | SIGNAL NAME      | IO     | IO STANDARD | ASSOCIATED_PRIMITIVE |
| -- | ---------------- | ------ | ----------- | -------------------- |
| 1  | O_sdram_clk      | IOR11B | LVCMOS33    | OBUF                 |
| 2  | O_sdram_cke      | IOL13A | LVCMOS33    | OBUF                 |
| 3  | O_sdram_cs_n     | IOL14B | LVCMOS33    | OBUF                 |
| 4  | O_sdram_cas_n    | IOL14A | LVCMOS33    | OBUF                 |
| 5  | O_sdram_ras_n    | IOL13B | LVCMOS33    | OBUF                 |
| 6  | O_sdram_wen_n    | IOL12B | LVCMOS33    | OBUF                 |
| 7  | O_sdram_dqm[0]   | IOL12A | LVCMOS33    | OBUF                 |
| 8  | O_sdram_dqm[1]   | IOR11A | LVCMOS33    | OBUF                 |
| 9  | O_sdram_dqm[2]   | IOL18A | LVCMOS33    | OBUF                 |
| 10 | O_sdram_dqm[3]   | IOR15B | LVCMOS33    | OBUF                 |
| 11 | O_sdram_addr[0]  | IOR14A | LVCMOS33    | OBUF                 |
| 12 | O_sdram_addr[1]  | IOR13B | LVCMOS33    | OBUF                 |
| 13 | O_sdram_addr[2]  | IOR14B | LVCMOS33    | OBUF                 |
| 14 | O_sdram_addr[3]  | IOR15A | LVCMOS33    | OBUF                 |
| 15 | O_sdram_addr[4]  | IOL16B | LVCMOS33    | OBUF                 |
| 16 | O_sdram_addr[5]  | IOL17B | LVCMOS33    | OBUF                 |
| 17 | O_sdram_addr[6]  | IOL16A | LVCMOS33    | OBUF                 |
| 18 | O_sdram_addr[7]  | IOL17A | LVCMOS33    | OBUF                 |
| 19 | O_sdram_addr[8]  | IOL15B | LVCMOS33    | OBUF                 |
| 20 | O_sdram_addr[9]  | IOL15A | LVCMOS33    | OBUF                 |
| 21 | O_sdram_addr[10] | IOR12B | LVCMOS33    | OBUF                 |
| 24 | O_sdram_ba[0]    | IOR13A | LVCMOS33    | OBUF                 |
| 25 | O_sdram_ba[1]    | IOR12A | LVCMOS33    | OBUF                 |
| 26 | IO_sdram_dq[0]   | IOL3A  | LVCMOS33    | IOBUF                |
| 27 | IO_sdram_dq[1]   | IOL3B  | LVCMOS33    | IOBUF                |
| 28 | IO_sdram_dq[2]   | IOL8A  | LVCMOS33    | IOBUF                |
| 29 | IO_sdram_dq[3]   | IOL8B  | LVCMOS33    | IOBUF                |
| 30 | IO_sdram_dq[4]   | IOL9A  | LVCMOS33    | IOBUF                |
| 31 | IO_sdram_dq[5]   | IOL9B  | LVCMOS33    | IOBUF                |
| 32 | IO_sdram_dq[6]   | IOL11A | LVCMOS33    | IOBUF                |
| 33 | IO_sdram_dq[7]   | IOL11B | LVCMOS33    | IOBUF                |
| 34 | IO_sdram_dq[8]   | IOR9B  | LVCMOS33    | IOBUF                |
| 35 | IO_sdram_dq[9]   | IOR9A  | LVCMOS33    | IOBUF                |
| 36 | IO_sdram_dq[10]  | IOR5B  | LVCMOS33    | IOBUF                |
| 37 | IO_sdram_dq[11]  | IOR6A  | LVCMOS33    | IOBUF                |
| 38 | IO_sdram_dq[12]  | IOR5A  | LVCMOS33    | IOBUF                |
| 39 | IO_sdram_dq[13]  | IOR4B  | LVCMOS33    | IOBUF                |
| 40 | IO_sdram_dq[14]  | IOR3B  | LVCMOS33    | IOBUF                |
| 41 | IO_sdram_dq[15]  | IOR3A  | LVCMOS33    | IOBUF                |
| 42 | IO_sdram_dq[16]  | IOL39B | LVCMOS33    | IOBUF                |
| 43 | IO_sdram_dq[17]  | IOL39A | LVCMOS33    | IOBUF                |
| 44 | IO_sdram_dq[18]  | IOL35B | LVCMOS33    | IOBUF                |
| 45 | IO_sdram_dq[19]  | IOL35A | LVCMOS33    | IOBUF                |
| 46 | IO_sdram_dq[20]  | IOL30B | LVCMOS33    | IOBUF                |
| 47 | IO_sdram_dq[21]  | IOL30A | LVCMOS33    | IOBUF                |
| 48 | IO_sdram_dq[22]  | IOL20A | LVCMOS33    | IOBUF                |
| 49 | IO_sdram_dq[23]  | IOL18B | LVCMOS33    | IOBUF                |
| 50 | IO_sdram_dq[24]  | IOR17A | LVCMOS33    | IOBUF                |
| 51 | IO_sdram_dq[25]  | IOR16A | LVCMOS33    | IOBUF                |
| 52 | IO_sdram_dq[26]  | IOR16B | LVCMOS33    | IOBUF                |
| 53 | IO_sdram_dq[27]  | IOR17B | LVCMOS33    | IOBUF                |
| 54 | IO_sdram_dq[28]  | IOR18A | LVCMOS33    | IOBUF                |
| 55 | IO_sdram_dq[29]  | IOR18B | LVCMOS33    | IOBUF                |
| 56 | IO_sdram_dq[30]  | IOR44A | LVCMOS33    | IOBUF                |
| 57 | IO_sdram_dq[31]  | IOR44B | LVCMOS33    | IOBUF                |