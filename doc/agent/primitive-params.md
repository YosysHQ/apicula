# Primitive parameters and their allowed values

Where to get each primitive's ports, parameters and legal parameter values, for
example to generate random but valid designs. IDE **1.9.10.03**.

## Sources compared

| Source | Ports | Defaults | Allowed values | Usable |
|---|---|---|---|---|
| `IDE/bin/primitive.xml` (GW1N, GW2A) | name, direction, width | yes | yes | yes |
| `IDE/bin/prim_syns/gw5a/primitive.xml` | name, direction, width | yes | yes | yes |
| Yosys `+/gowin/cells_sim.v`, `cells_xtra_<family>.v` | yes | yes | no | yes, with `read_verilog -lib`, then `blackbox =A:whitebox` before `write_json` |
| `IDE/bin/prim_syn.v` (GW1N, GW2A) | yes | no, all blank | no | parses, but adds nothing |
| `IDE/bin/prim_syns/gw5a/prim_syn.v` | | | | no, encrypted (`pragma protect`) |
| `IDE/simlib/*/prim_sim.v` | | | | no, uses Verilog UDPs, which Yosys rejects. Only a few `$display` checks, none for parameters |

`primitive.xml` is the only source that has allowed values. `tools/gowin_primitives.py dump`
turns it into JSON. Modules named `VLG_*` are the vendor's generic RTL operators
with `width="variable"` ports, not primitives, and are skipped.

## Domain encoding (checked against data)

A `PARAMETER` has a `type` (`number` or `string`), an `INIT_VAL` default and
optional `PARAM_VAL` entries:

- Three entries `min`, `max`, `normal` form an inclusive range with step 1, for
  example `rPLL.IDIV_SEL` 0..63. With `even` instead of `normal` the step is 2, for
  example `OSC.FREQ_DIV` 2..128. GW5A uses `even` only for the `FREQ_DIV` of
  `OSC`, `OSCA` and `OSCB`.
- Entries after the range tag are allowed too. GW5A `OSCA.FREQ_DIV` is 2..126
  `even` plus `3`.
- Any other list is an enumeration, for example `rPLL.ODIV_SEL` 2, 4, 8, ... 128.
- With no entries, the default is a sized literal such as `16'h0000`, meaning any
  value of that width. The exceptions are the real-valued `FCLKIN` of the PLLs and
  of `DCC`/`DCCG`.

Counts with `VLG_*` excluded: GW1N/GW2A has 185 primitives, with 1386 bit-vector
parameters, 224 enumerations, 28 ranges and 6 reals. GW5A has 860 bit-vector,
503 enumeration, 60 range and 2 real parameters. No parameter is left without a
domain.

## The vendor enforces these domains (checked by running it)

GW1NR-9C with a netlist given directly to `run pnr`:

- `OSC.FREQ_DIV` = 3 (odd) and 130 (above 128), and `rPLL.ODIV_SEL` = 6 (not
  enumerated), each give `WARN (PA1002) Invalid parameterized value`. Values in
  the domain give no warning. PA1002 is only a warning. What the IDE then uses
  has not been checked, so a generator should treat PA1002 as an invalid case.
- Rules across parameters are not in the XML. A PLL whose VCO frequency is
  outside 400–1200 MHz fails with `ERROR (PA2078)`. `apycula/gowin_pll.py`
  already has this calculation.

The netlist reader is stricter than Verilog:

- Every port of every instance must be connected. Otherwise you get
  `ERROR (PA2058) Error pin number`.
- A sized constant such as `6'b0` on a port is a syntax error (PA2000). Tie
  inputs to the output of a `GND` or `VCC` primitive, and write buses as
  concatenations of that net, which `codegen.Primitive` emits for list portmaps.

## Yosys compared with the XML

Things to know when synthesising against Yosys' library. None of these have been
fixed:

- Missing from Yosys for GW1N/GW2A: `rROM`, `rSDP`, `rSDPX9`, the `IODELAYA/B/C`
  primitives, `PLLO`, `DLL` and others.
- Different defaults:
  - `DLP`, `DLPE`, `DLNP` and `DLNPE` have `INIT` 1'b1 in the XML but 0 in Yosys.
  - `OSC.FREQ_DIV` defaults to 96 in the XML and 100 in Yosys.
  - In the GW1N `cells_xtra`, several `DQS` and `*_MEM` parameters are declared
    without a value.
- The `DL*` latches name their gate input `G` in the XML and `CLK` in Yosys.
- `ID` parameters, and the FLASH timing parameters `*_S1`..`*_S5`, `IDLE` and
  `RD_S*`, appear only in Yosys.

## More rules the XML does not have (checked by running the vendor)

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

Primitives a device lacks ("PA2085: No '<primitive>' resource in current
device") are listed in `primitive_strategies.UNAVAILABLE`. On GW5A-25A these
include every flip-flop and latch type except `DFFRE`, `DFFSE`, `DFFPE` and
`DFFCE`, and all SSRAM.
