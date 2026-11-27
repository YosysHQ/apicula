# Round-trip equivalence test

Design for a property test that needs no IDE and no board: random RTL goes
through Yosys `synth_gowin` → nextpnr → `gowin_pack` → `gowin_unpack`, and the
unpacked netlist is proven equivalent to the synthesised one. Status:
implemented in `tools/roundtrip.py` and `tests/test_roundtrip.py`. Measurements
below were made on Yosys 0.71+130, nextpnr b4faf934 and Apicula e6dc4a6.

The tiled fuzzer ([tiled-fuzzer.md](tiled-fuzzer.md)) compares against the
vendor, but only for primitives it instantiates and pins by hand. It never sees
what Yosys infers or what nextpnr rewrites (constant ALUs, IOB register packing).
The round trip covers that, with the synthesised netlist as the specification.
Until now the only round-trip check was the "Sanity check" step in
`toolchain.yml`, which asserts that a DFF and a BUF exist.

Prior art: mfatgg's out-of-tree harness (github.com/mfatgg/fpga-bitstream-check,
MIT), which pairs FFs and ALUs through `NEXTPNR_BEL` and runs `equiv_simple`. It
found the #541 carry head and the #514 residual. #594 and #595 were its unpack
fixes; #585 lists the remaining gaps.

## Generator

`tools/roundtrip.py`, with Hypothesis strategies (drawn like `ps.draw` in
`tools/primitive_strategies.py`) that build a small RTL AST and write it as
Verilog. Four groups, each one test id:

- `logic`: LUT/MUX trees, wide functions, constants.
- `alu`: `+`, `-`, compares, counters, constant operands. This exercises
  nextpnr's constant-ALU rewrite, where #514 and #541 lived.
- `ff`: every DFF kind Yosys infers (edge, CE, sync/async set/reset), and INIT.
- `ioreg`: registers next to IBUF, OBUF and IOBUF.

Each design also draws the nextpnr seed, its pins (from `tiled_fuzzer`'s
`package_pins`) and one of `ireg_in_iob`, `oreg_in_iob`, `ioreg_in_iob`. All
three are needed: nextpnr packs `ireg` only into IBUFs, `oreg` only into OBUFs
and `ioreg` only into IOBUFs (read from nextpnr `pack_io.cc`, lines 593–655 at
b4faf934). Synthesis runs with `-nodsp -nobram -nolutram`; BSRAM, LUTRAM and
DSP need memory models on both sides and come later, if ever.

Rejected: Yosys-side random cells (`test_cell`). They give one cell per module
and no composition.

## Equivalence

Register correspondence plus one SAT miter per design:

1. Pair flip-flops through `NEXTPNR_BEL` in the pnr JSON.
2. Cut both netlists at the flip-flops, in Yosys JSON rather than by regex on
   Verilog: Q becomes a primary input; D, CE, CLK and SR become outputs. A pin
   one side lacks becomes its neutral constant.
3. Map the unpacked pads to design ports through the IOB bels.
4. Elaborate each side with Yosys' `cells_sim.v`, and `cells_xtra_*.v` as
   blackboxes. No Apicula-side models, so a port mismatch like #288 shows.
5. `setundef -undriven -anyseq` on each side. An undriven net is then free, so it
   can never be "equal undef" on both sides. Without it, an unpack gap gives a
   vacuous proof.
6. `miter -equiv` and `sat -prove`.

A gold register with no counterpart in the bitstream fails on its own (#668).

Rejected: `equiv_make`/`equiv_simple` as the main check. It scales better but
gives no input vector and is incomplete on deep carry chains: on #514's
crtb_9699690 (1060 FFs, 3259 ALUs) it left 316 of 3336 points unproven; those
checked one by one with SAT so far all prove. It is the route for kit-sized
designs, as a follow-up. A whole-design `sat -tempinduct` cannot reach deep
states.

### Report and xfail signatures

A failure reports, for each differing point: the gold register or port with its
RTL `src`, the gate's tile, the input vector, and the undriven gate wires in its
cone. A point is classed `unpack-gap` only if its gate value depends on those
wires: two copies of the gate netlist, each with its own free values for them,
differ there (`dependent()`). An undriven wire in a cone that does not matter
explains nothing. An undriven carry-in (`R<r>C<c>_CIN<n>`) never counts: no
#585 gap leaves one undriven, and a chain head that reads it is a miscompute
(#541's `0x505a` head was one). Without this rule, a sabotaged carry-out in
unpack's RAW ALU decode was excused as a gap; with it, the `alu` group fails
on both devices. Classified points are dropped and the miter rerun, so a known
gap in one point cannot hide a miscompute in another. A miscompute in a point
that also depends on a gap stays hidden until that gap is fixed.

`tests/test_roundtrip.py` xfails a group only if every failure has a kind in
its `KNOWN` map:

| kind | signature | issue |
|---|---|---|
| `unpack-gap` | the point's gate value depends on undriven wires | #585 |
| `alu-i2` | an unpacked `ALU` has an `I2` port, which Yosys' `ALU` lacks | #288 |
| `lost-iob-reg` | a gold register nextpnr packed into I/O logic has no counterpart | #668 |

For #288 the checker drops `I2` and records the problem, so the rest of the
design is still checked rather than stopping at an elaboration error.

Anything else fails hard, even while those issues are open. Each group run also
inverts one LUT in the unpacked netlist of the first design that proves, and
expects an unexplained failure, which keeps the check from going vacuous.

A design that proves, and a control that fails as it should, keep only
`design.json`, `top.v` and `result.json` (`--keep` keeps everything). The
netlists are about 12 MB per design.

## CI

A new dev-only `roundtrip (<device>)` job in `toolchain.yml`, in
`container: pepijndevos/apicula` with `needs: build-tools` and the wheel's
chipdb, like `fuzz`:

| job | needs IDE | needs tools | produces |
|---|---|---|---|
| example | no | yes | bitstreams, sanity unpack |
| fuzz | yes | yes | fuzz reports |
| roundtrip | no | yes | counterexample reports |

`pytest tests/test_roundtrip.py --device <dev> --roundtrip-jobs $(nproc)`, 25
designs per group per device (fewer after duplicates are dropped). Measured
here with 4 jobs: 76 s on GW1N-9C, 123 s on GW2A-18C, for all four groups.
Per small design: synth 0.3 s, pnr 0.2 s (GW1N-9C) or 2.5 s (GW2A-18C), pack
0.4–1 s, unpack 1.1–3.4 s, check 1–2 s.

On master (e6dc4a6, nextpnr b4faf934, `--roundtrip-seed 0`) both devices give
the same counts: `logic` proves 23 of 23 and passes; `alu` proves 9 of 24 and
xfails with #288 and #585; `ff` proves 10 of 20 and xfails with #585; `ioreg`
proves 0 of 20 and xfails with #668 and #585. The mutation control fails as
it should in `logic`, `ff` and `alu`; `ioreg` has no design that proves to run
it on.

It does not replace the sanity check yet: that step unpacks the examples (PLL,
OSER, BSRAM), which the generator doesn't produce.

Devices: GW1N-9C and GW2A-18C. GW5A-25A proved 0 of 10 designs even with
mfatgg's unpack fixes (FFs without CE/LSR drivers, undriven edge wires), gaps
#585 doesn't cover. It joins once those have an issue.

## Findings at design time

20 random designs per device, prototype generator:

| device | master proves | all #585 gaps fixed | gaps needed (designs) |
|---|---|---|---|
| GW1N-9C | 5/20 | 20/20 | clock 14, long wires 3, empty tiles 1, alone-node 0 |
| GW2A-18C | 6/20 | 20/20 | clock 14, long wires 10, alone-node 1, empty tiles 0 |

"All gaps fixed" used mfatgg's `unpack_full.py`. Every master failure had an
undriven gate wire in the cone of each differing point; no miscompute was found.
On GW1N-9C, 9 of 20 designs did not elaborate because of #288; the counts above
strip `I2` to see past it.

- **#668** reproduces with nextpnr main: the issue's own design on GW2A-18C, and
  a one-register design on GW1N-9C with `ireg_in_iob`. The register has no
  counterpart in the bitstream. Output registers (`oreg_in_iob`) are lost as
  well: `get_IOLOGICO_EMPTY_fuses` writes no OREG attributes (read from code),
  and the I/O-cases fuzzer track vendor-checked it. On GW1N-9C, GW2A-18C and
  GW5A-25A, Apicula lacks the IOLOGIC rows the vendor sets (`CLKIMUX/CLKOMUX`,
  `SRMODE`, `CEIMUX_1/CEOMUX_1`, `OUTMODE=OREG`, `OREG_REGSET`,
  `*_INREGMODE/OUTREGMODE`) for DFF, DFFR, DFFRE, DFFNCE, DFFPE and DFFNS.
- **#541** does not reproduce. Its mechanism was a `0x505a` carry head without
  CIN. With nextpnr b4faf934, both of the reporter's seeds (12345, 4242) give
  heads C2L ×20, ONE2C ×42 and `0x000a` ×4, and no `0x505a`. The design uses 22
  BSRAMs, out of scope for the round trip, so it gets no dedicated test.
- **#514** does not reproduce at bitstream level. crtb_2310 seed 1 proves with
  the gaps fixed. crtb_9699690 seed 1: `equiv_simple` proved 3020 of 3336
  points, per-point SAT a further 224, no counterexample; the rest timed out.
  The residual's symptom (one bitstream passing on one load and failing on the
  next) is invisible to a round trip. The `alu` group covers the bug class.

## Blind spots

The round trip compares Apicula with itself through the bitstream. It cannot
see:

- a wrong belief shared by the chipdb and unpack, as in #607: pack writes the
  wrong fuse, and unpack reads it back as the intended function;
- a wrong `cells_sim.v` model, since both sides use it;
- timing and analog effects, such as the #514 residual;
- anything nextpnr records wrongly in `NEXTPNR_BEL`, since the register pairing
  trusts it.

The vendor comparison (tiled fuzzer) and HIL tests cover those.

## Follow-ups

- Unpack-only fixes for the four #585 gaps (clock aliases, long wires, empty
  tiles, alone-node fuses), one PR each, each flipping its xfail. No pack or
  chipdb changes (yrabbit's condition in #585).
- #288: unpack's `ALU` port list vs Yosys' `cells_sim.v`.
- #668: IOLOGIC register fuses in `gowin_pack`.
- GW5A-25A unpack gaps: file an issue, then add the device.
- `equiv_simple` plus per-point SAT for kit-sized designs.
- Run the checker on the examples and drop the sanity step.
