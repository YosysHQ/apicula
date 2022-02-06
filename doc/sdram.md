# SDRAM

Gowin devices with the R suffic such as the GW1NR-9 have built-in SDRAM.
This SDRAM is a System-in-Package wirdebonded of the shelf SDRAM module.
So there isn't so much to fuzz, you just have to know the pinout and the model.

Gowin has been so kind as to provide LiteX with [the details](https://github.com/litex-hub/litex-boards/blob/8a33c2aa312dddc66297f7cd6e39107fda5a2efb/litex_boards/targets/trenz_tec0117.py#L92-L118) of the model and pinout. That is... the magic wire names that result in the vendor placing the IOB in the correct place.

For the open source tools, you can't use the magic wire names. But what you can do is feed the magic wire names to the vendor and look at the generated placement.
This is what has been done in `/legacy/sdram`, which is a standalone script not tied into the rest of Apicula.

The result for GW1NR-9 is as below. A daring adventurer could use these to develop their own SDRAM controller or try to add support for LiteX on open source Gowin tools.

```
IO_sdram_dq(0) -> R29C26_IOA
IO_sdram_dq(1) -> R29C27_IOA
IO_sdram_dq(2) -> R29C35_IOA
IO_sdram_dq(3) -> R29C36_IOA
IO_sdram_dq(4) -> R29C37_IOA
IO_sdram_dq(5) -> R29C38_IOA
IO_sdram_dq(6) -> R29C39_IOA
IO_sdram_dq(7) -> R29C40_IOA
IO_sdram_dq(8) -> R29C16_IOB
IO_sdram_dq(9) -> R29C17_IOB
IO_sdram_dq(10) -> R29C18_IOA
IO_sdram_dq(11) -> R29C18_IOB
IO_sdram_dq(12) -> R29C19_IOB
IO_sdram_dq(13) -> R29C20_IOB
IO_sdram_dq(14) -> R29C21_IOB
IO_sdram_dq(15) -> R29C22_IOB
O_sdram_clk -> R1C4_IOB
O_sdram_cke -> R1C9_IOA
O_sdram_cs_n -> R1C35_IOB
O_sdram_cas_n -> R1C40_IOB
O_sdram_ras_n -> R1C40_IOA
O_sdram_wen_n -> R1C44_IOA
O_sdram_addr(0) -> R1C31_IOA
O_sdram_addr(1) -> R1C28_IOA
O_sdram_addr(2) -> R1C27_IOA
O_sdram_addr(3) -> R1C26_IOA
O_sdram_addr(4) -> R1C22_IOB
O_sdram_addr(5) -> R1C21_IOB
O_sdram_addr(6) -> R1C18_IOB
O_sdram_addr(7) -> R1C18_IOA
O_sdram_addr(8) -> R1C14_IOB
O_sdram_addr(9) -> R1C14_IOA
O_sdram_addr(10) -> R1C31_IOB
O_sdram_addr(11) -> R1C9_IOB
O_sdram_dqm(0) -> R1C44_IOB
O_sdram_dqm(1) -> R1C4_IOA
O_sdram_ba(0) -> R1C35_IOA
O_sdram_ba(1) -> R1C32_IOA
```