# I/O loopback: board pins, banks, LVDS rules (Tang Nano 9K / 20K)

For HIL phase 2 (I/O self-tests over wires on the headers). Full write-up was a scratch report;
these are the durable facts.

## Read pin data from the chipdb, not from memory
- `chipdb.load_chipdb('apycula/<DEV>.msgpack.xz')` needs `msgspec` (use `~/code/apicula/apicula/.venv/bin/python`).
- `db.pinout[variant][package]` -> `{pin: (IOname, cfgs)}`; 9K = `['GW1NR-9C']['QFN88P']`, 20K = `['GW2AR-18C']['QFN88']`
  (nextpnr device GW2AR-LV18QN88C8/I7 maps to QFN88, see `db.packages`).
- `db.pin_bank[IOname]`; the IOB bel `db[row,col].bels['IOBA'|'IOBB']` has `is_diff`, `is_true_lvds`, `is_diff_p`
  (IOT n -> row 0, col n-1; IOB -> row rows-1; IOL -> col 0, row n-1; IOR -> col cols-1).
- GW2A-18C has no OSER16/IDES16 bels; GW1N-9C has them on top/bottom IO only.

## Board facts (schematics: 9K 3672 rev 6202, 20K 3921 rev 1.22)
- 9K: VCCO0/1/2 = 3.3 V, **bank 3 = 1.8 V** (pins 3-16, 79-88). Never wire bank-3 pins to 3.3 V pins.
  QN88P bonds no bank-0 pin, so no on-chip 100 ohm LVDS termination (UG289 3.3.2: GW1NR-9 bank 0 only).
  Free plain pins: J5-5..10 = 25,26,27,28,29,30 (bank 2, three adjacent true-LVDS pairs). Pins 68-75 carry
  HDMI with 49.9 ohm pull-ups to 3V3; 53-57 are SSPI (need --sspi_as_gpio).
- 20K: all VCCO 3.3 V (VCCO4/5 from own ME6211C33 LDOs). On-chip 100 ohm only banks 0/1, whose header pins
  go to BL616 HSPI or the SD slot. Pin 25 = HDMI CEC (27k pull-up), 26 = HPD (5.1k to GND).
  Pins 27-31, 41, 42, 77 only touch the empty LCD FPC.
- DS226 (2025 rev) gives TLVDS output VCCIO 2.5 V only; the 20K runs it at 3.3 V (works for HDMI, out of spec).
  DS117: GW1NR-9 TLVDS out at 2.5/3.3 V is fine; MIPI input only in bank 0 (unbonded on QN88P).

## Loop design rules
- OSER8/10/16, IDES8/10/16, OVIDEO and IVIDEO take both IOLOGICs of a pair (nextpnr `check_iologic_placement`):
  wire single-ended loops A-pin to A-pin of different pairs, and keep both B pins idle.
- A 100 ohm resistor across a diff RX pair forbids driving its two wires as independent single-ended signals.
- Proposed wiring per board: diff pair -> pair + 100 ohm, SE A->A loop, SE loop into a GCLK pin
  (9K: 25/26->27/28, 29<->33, 41<->35; 20K: 27/28->29/30, 31<->41, 15<->77).
- Unverified: whether IOBUF.O reads the pad while OEN=0 (would allow no-wire tests). Test this first.
