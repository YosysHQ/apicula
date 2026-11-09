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
