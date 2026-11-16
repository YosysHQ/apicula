# Vendor sweep: every primitive in primitive.xml

`tools/vendor_sweep.py` puts each primitive of a family's `primitive.xml` into a
design of its own, with one all-defaults case and three random cases from
`tools/primitive_strategies.py`, and runs the vendor alone. Nothing is placed and
Apicula is not run. When a design with several cases fails, each case is rerun
alone. IDE **1.9.10.03**, `-n 4`, devices GW1N-9C (GW1NR-9C), GW2A-18C and
GW5A-25A.

Wiring is as in the tiled fuzzer (see [tiled-fuzzer.md](tiled-fuzzer.md)):
- 1-bit inputs are undriven, bus inputs are tied to GND, and outputs go to
  dummy wires;
- ports with CLK in the name share one clock input;
- inout ports, and the pad side of I/O buffers, are top-level ports.

Many failures below come from this harness, not from parameter values.

| Device | Primitives | All cases accepted | Some | None |
|---|---|---|---|---|
| GW1N-9C | 183 | 96 | 11 | 76 |
| GW2A-18C | 183 | 94 | 13 | 76 |
| GW5A-25A | 157 | 50 | 14 | 93 |

## Parameter rules the XML does not have (checked by running the vendor)

- **Dual-port BSRAM write mode.** `DP`, `DPB`, `DPX9`, `DPX9B` reject
  `WRITE_MODE0/1 = 2'b10` (read-before-write): "PA2122: Not support ...
  please change write mode to 2'b00 or 2'b01". Seen on all three devices. The
  XML lists 2'b10. `primitive_strategies.RULES` filters it out.
- **XML defaults the vendor cannot parse.** The default INIT of `LUT6`, `LUT7`
  and `LUT8` is written with underscores (`64'h0000_0000_...`), and the netlist
  reader rejects it with PA2000. Only the all-defaults cases failed.
- **Bit-vector radix.** The vendor rejects a sized literal unless it uses the
  radix of the XML default (PA1002): LUT3 INIT `8'b10010101` and DFF INIT `1'h1`
  are rejected. Found with the tiled fuzzer.
- **GW1N/GW2A rPLL:** VCO 400–1200 MHz on GW1NR-9C (PA2078). The tiled fuzzer
  draws dividers within it.
- **GW5A `PLLA`:**
  - VCO 800–1600 MHz, and a PFD range (PA2078);
  - channel n must be disabled when `CLKn_OUT_SEL=1'b1` (PA2115);
  - `CLKOUTn_PE_COARSE <= ODIVn_SEL` (PA2096);
  - `CLKn_IN_SEL=1'b1` with `CLKn_OUT_SEL=1'b0` is only allowed under some
    `DYN_DPA_EN` setting (PA2093, message truncated);
  - `FCLKIN` "3" and "10" gave PA1002, while the default "100.0" passed. Whether
    the value or the missing decimal point is the problem has not been checked.
- **GW5A `ADC`:** `BUF_BK0_VREF_EN`, `BUF_BK6_VREF_EN` and `BUF_EN[0..2]` cannot be
  1 at the same time (PA2114).
- **GW5A `CSHIFT`:** "PA2067: Not defined parameter 'INIT = CE0'", and
  "PA2050: Module 'CSHIFT' is instantiated but not defined". The XML entry does
  not match what the vendor accepts.

## Not in the device (PA2085)

"No '<primitive>' resource in current device".

- **GW1N-9C:** BANDGAP CLKDIVG DCCG DQS ELVDS_IBUF_R ELVDS_IOBUF_R EMCU FLASH128K
  FLASH256K FLASH64K FLASH64KZ FLASH96K FLASH96KA I3C IBUF_R IDDR_MEM IDES4_MEM
  IDES8_MEM IEM IOBUF_R IODELAYB MCU MIPI_DPHY_RX ODDR_MEM OSCH OSCO OSCW OSCZ
  OSER4_MEM OSER8_MEM OTP PLLO PLLVR PWRGRD SAMB SPMI SPMI_DEBUG_GOWIN TLVDS_IOBUF
  TLVDS_OEN_BK USB20_PHY
- **GW2A-18C:** BANDGAP CLKDIVG DCC DCCG DHCENC EMCU FLASH128K FLASH256K FLASH608K
  FLASH64K FLASH64KZ FLASH96K FLASH96KA I3C I3C_IOBUF IDES16 IODELAYB IODELAYC MCU
  MIPI_DPHY_RX MIPI_IBUF MIPI_IBUF_HS MIPI_IBUF_LP MIPI_OBUF MIPI_OBUF_A OSCH OSCO
  OSCW OSCZ OSER16 OTP PLLO PLLVR PWRGRD SAMB SPMI SPMI_DEBUG_GOWIN TLVDS_OEN_BK
  USB20_PHY
- **GW5A-25A:** ADCA_DB ADCLRC ADCLRC_DB ADCULC ADCULC_DB ADC_SAR ADC_SAR_DB
  AE350_RAM AE350_SOC CMSER CMSERB **DFF DFFC DFFE DFFN DFFNC DFFNCE DFFNE DFFNP
  DFFNPE DFFNR DFFNRE DFFNS DFFNSE DFFP DFFR DFFS** **DL DLC DLCEA DLE DLN DLNC
  DLNCE DLNE DLNP DLNPE DLP DLPEA** JPEG_DB LICD MULTACC OSC OSCB PLL RAM16S1
  RAM16S2 RAM16S4 RAM16SDP1 RAM16SDP2 RAM16SDP4 SAMBA SDP136K SDP36KE

On GW5A-25A, `DFFRE` (and presumably `DFFSE`, `DFFPE`, `DFFCE`, which passed) is
accepted, but every other flip-flop and latch type is not. Neither are the
SSRAM primitives (`RAM16S*`, `RAM16SDP*`). The tiled fuzzer must not generate
those for GW5A.

## Harness limits (not parameter rules)

These failures come from how the sweep wires primitives. Fuzzing these
primitives needs per-family harness code:

- **I/O logic must connect to an I/O buffer** (PR0018): IDDR, ODDR, IDES*, OSER*,
  IODELAY*, IVIDEO, OVIDEO. The `_MEM` variants also need DQS (PR2060).
- **Clock buffers and dividers cannot have a dangling output** (PA2099):
  CLKDIV2, DCC, DHCEN, DHCENC. HCLK logic needs a constraint (PR2067, CLKDIV).
- **Wide LUT muxes need LUT or mux drivers**: `MUX2_LUT6` and up must be driven by
  `MUX2_LUT5` (PA2068), and `MUX2_LUT5` by LUTs (PR2075).
- **Other pin rules:**
  - DLLDLY and DQS need a DLL on `DLLSTEP` (PR2015, PR0015);
  - DQS needs a buffer on `DQSIN` (PR0014);
  - `MULTALU27X18` needs `SIA` connected to `SOA` (PR1145);
  - `OSIDES32`/`64` need differential clocks (PR1113);
  - `MIPI_OBUF_A` needs output I/O logic (PR1136/PR1138).
- **Placement or routing:** DLCEA and DLPEA could not be placed (PR0003), and
  `MULT36X36` left 80 nets unrouted (PR0004).
- `GW_JTAG` takes the JTAG pins, which the default configuration uses as I/O
  (PR1079).
- `VIRTUAL_BUF` is in the XML but not defined (PA2050).
- `ALU` passes with a warning: the head ALU's `CIN` has no source (CA2141).

## Caveats

- Outputs are unloaded. For LUTs and DFFs the vendor kept unloaded cells (see
  [tiled-fuzzer.md](tiled-fuzzer.md)), and it counted unloaded PLLs against the
  resource limit (PA2017). But checks late in the flow may be skipped for cells
  it removes.
- Several cases of one primitive per design can exceed the device's resources
  (PA2017: 3 PLLs, 2 available). Those cases are rerun alone.
