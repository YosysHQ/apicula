# HIL tests without loopback wiring: carry chains and pad readback

Design for two hardware-in-the-loop tests (see [testing.md](testing.md)) that
need no wires between header pins. Both check themselves: the reference is the
design's own specification, never a captured output. Toolchain for every
measurement below: nextpnr b4faf934, Yosys 0.70+ fbe6f4d66, Apicula e6dc4a6.
Each rig result is one load.

## `carry-crt`: carry chains checked by arithmetic

Hardware is the only oracle when the chipdb and the simulation are wrong in the
same way, as in #514 and #541.

**Design.** `examples/hil/carry-crt.v`, module `carry_crt_test`, report 3 bits,
reference `0x7`:

- **CRT** (#514's `rad_min.v` datapath): a counter sweeps 0..N-1 once,
  N = 2·3·5·7·11·13·17 = 510510. Its residues `cnt % p` are registered and
  rebuilt into `sum(r_p * E_p) mod N`, which the Chinese remainder theorem says
  is `cnt` again. `pass[0]`: never mismatched.
- **Chunked add** (#541): a 48-bit `A + B` of two LFSRs in 2-bit chunks, the carry between
  chunks through a flip-flop so nothing merges them into one chain. Each chunk
  starts with a carry-from-logic head. Checked against the same sum computed in
  one piece. `pass[1]`: never mismatched.
- `pass[2]`: the sweep finished.
- Every register is enabled once in 16 clocks (one sweep is 0.3 s at 27 MHz).
  The CRT paths miss 27 MHz by nextpnr's own timing (about 22 MHz), and a slow
  path must not pass for a wrong carry.

**Build.** `synth_gowin -nodsp` for this test only:
`hil-carry-crt-%-synth.json: YOSYS_FLAGS += -nodsp`. Measured: with DSP
products, shifted-add products, or unregistered residues, the design no longer
caught #514 (below). `-nodsp` must not reach the DSP tests, so `carry-crt` is a
batch of its own, listed directly in `HIL_BATCHES_*` for tangnano9k,
tangnano20k and primer25k. Size: 2888 LUT4 + 1952 ALU, 56 % of the GW1N-9C.

**Diversity.** One placement per run. The `-r` seed changes every CI run, which
over time covers placement-dependent bugs like #541; #514's class failed on
every seed.

**What it catches** (measured on the rig):

| build | 9K | 20K | 25K |
|---|---|---|---|
| nextpnr main | 0x7 | 0x7 | 0x7 |
| main with nextpnr #1736 (175787b2) reverted, the #514 bug | | 0x6 | |

- #514 is fixed on nextpnr main; the test is a regression guard. The issue's
  kit `rad_min_uart` agrees: main passes, the reverted build fails with the
  issue's 2/7 signature.
- #514's "residual" 8-port `crtb_9699690` passed seeds 1–6 on the 20K. nextpnr
  times it at 16.8–18.5 MHz against the 27 MHz clock. Inferred, not proven: the
  residual is a timing violation, not a carry bug.
- #541 is fixed by nextpnr 6030081a. Emulated pre-fix by setting
  `RAW_ALU_LUT` of every carry-from-logic head (`*_HEAD_ALULC`,
  `CIN_NETTYPE=LOGIC`) back from `0x000a` to `0x505a` in the routed JSON, which
  is that commit's diff. With 4-bit chunks this was caught in 1 of 4
  placements (`0x5`). Bisecting the heads: the leak comes from heads whose west
  ALU5 is empty; heads next to another chain's tail did not leak. Hence 2-bit
  chunks, for more heads.

**Gate on the #541 part** (decided by the coordinator): stage 2 measures the
emulated #541 detection with 2-bit chunks over 5 seeds on the 20K. If it is
caught in fewer than about half, drop the chunked add, and say so in the pull
request.

## `iob-ireg`: an input register in the pad's I/O logic

**Design.** `examples/hil/iob-ireg.v`, module `iob_ireg_test`, report 3 bits,
reference `0x7`. A counter bit drives a pad through an `(* IOBFF *) IOBUF`
(`OEN=0`), and the same pad's input buffer feeds a flip-flop that nextpnr packs
into the pad's IOLOGIC. The register must equal the driven value one clock
later. `pass[0]`: never disagreed; `pass[1]`: read a 1; `pass[2]`: read a 0.
#668 shows as `0x4`: the register stuck at 0.

**No `ioreg_in_iob` batch.** nextpnr packs per cell when the IOBUF has the
`IOBFF` attribute (read from `pack_io.cc`), so the test needs no
`--vopt ioreg_in_iob`, which would apply to the whole batch.

**Pad.** `hil.v` gets an `` `ifdef HIL_IOB_IREG `` `inout hil_pad` on `top`,
constrained in each board's CST:

| board | pad | why it is safe |
|---|---|---|
| tangnano9k | pin 10, LED0, IOL15A, LVCMOS18 (bank 3 is 1.8 V) | an LED is meant to be driven by the FPGA: a resistor to the rail, nothing else drives it |
| tangnano20k | pin 15, LED0, IOL47A, LVCMOS33 | as above |
| primer25k | G5, Dock PMOD | nothing is connected to any rig board (Pepijn) |

The SDRAM DQ0 that #668 used was rejected: its safety rests on CS_n. Header pins
were avoided because #651 will wire them.

**Measured:** 9K and 20K `0x4` with `IOBFF`, `0x7` without (register in the
fabric). The 25K builds with IOLOGICI packed but was not loaded.

**Batch.** `HIL_BROKEN_tangnano9k` and `HIL_BROKEN_tangnano20k`, comment `#668`.
For the 25K, stage 2 loads it once: `0x7` puts it in `gw5a-a`, anything else in
`HIL_BROKEN_primer25k` with `#668`. Once #668 is fixed, it moves into `gw1n9-a`
and `gw2a-a`; it is a few cells.

## #534 is not testable on the rig

The freeze was fixed by #535, confirmed by the reporter. What stays open needs
an HDMI sink or loopback wiring, or is a packing difference the vendor fuzzer
catches better. The Tang Nano 20K's bank-0 true-LVDS pairs (pins 83/84, 85/86,
from the chipdb) go to the BL616 or the SD slot.
