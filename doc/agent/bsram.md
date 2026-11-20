# BSRAM

IDE 1.9.10.03. Handlers are `setBsramSPAttr`, `setBsramSDPAttr`, `setBsramDPAttr`,
`setBsramROMAttr` and `setBsramSpecialSPAttr`.

## GW1NZ-1 attributes 86 to 92

Read from code: on device types 10 (GW1NZ-1) and 34 (GW1NZ-1C), the SP and SDP
handlers set attributes 86 to 92 to value 16. DP and ROM do not. The IDs are past
the end of the `BSRAM_ATTR` enum, and what they do is unknown.

Checked against data: the rows exist only in the GW1NZ-1 `BSRAM_SP` and `BSRAM_SDP`
tables. Single-key rows in vendor and Apicula bitstreams agree for SP and SDP
designs once these are set.

## Differences left in place

Read from code. When a clock or control pin is driven through an inverter, the
vendor absorbs it into a BSRAM mux (`CLKMUX INV` and similar). `gowin_pack` leaves
the inverter in the fabric, which is logically equivalent. `checkBsramOutReg`
merging is not modelled.

## Hardware tests

`examples/hil/bsram.v` runs every primitive in several configurations on the
boards; the configurations are listed in `examples/hil.v` (`bsram-*` tests). The
`bsram-*-bugs` tests hold the configurations that fail and are in no batch; their
references are the masks a correct toolchain gives.

Measured on a Tang Nano 20K (GW2A-18C), Apicula and nextpnr of November 2026. The
causes are not traced; nothing here was compared with IDE bitstreams yet.

- Widths below 16 do not hold their output while CE (or OCE, READ_MODE 0) is low:
  the output shows the neighbouring word (word address bit 0 flipped) of the
  latched one. Seen on pROM/pROMX9 (READ_MODE 0 and 1, widths 1, 8, 9), SDPB/SDPX9B
  (both modes, widths 2, 8, 9) and SP READ_MODE 0 (width 8). SP READ_MODE 1 and DP
  pass: there nextpnr's `NEED_BSRAM_OUTREG_FIX` / `NEED_BSRAM_DP_CE_FIX` replace the
  output register, which suggests the vendor works around the same thing.
  Widths 16 to 36 pass.
- pROM/pROMX9 with BIT_WIDTH 32/36: part of word 0 (the upper half, all or some
  bits) can read wrong, in every pass over the memory; all other words are right.
  It depends on the design loaded before: after `hil-bsram-sp-bugs` the next load
  of `hil-bsram-rom-bugs` failed (twice), loading it again passed; most loads pass.
  With AD[3:0] high instead of low, word 0 read 0 in every build tried.
- SP BIT_WIDTH 32, WRITE_MODE 2 (read-before-write): during a write the upper 16
  bits show the previously read word, as with WRITE_MODE 0.
- SP and SDPB BIT_WIDTH 32 with byte enables from the fabric: writes with one
  byte enabled change bits of other lanes (SP: bit 17 written with lane 3).
- DPB/DPX9B below 16 bits with READ_MODE 1 on both ports and both outputs used:
  nextpnr fails its netlist check after packing (`bsram_fix_outreg` names the
  DFFs of both ports `<cell>_cache_dff$<bit>`).
