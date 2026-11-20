# Agent-written documentation

Findings about the Gowin IDE's code and data files, written by coding agents during
reverse engineering. All of it refers to IDE **1.9.10.03** unless stated otherwise.

Treat these notes as working documents. Claims are marked as read from code,
checked against data, or inferred. Correct them when they turn out to be wrong.

- [codebase.md](codebase.md), [testing.md](testing.md) and
  [reverse-engineering.md](reverse-engineering.md): details for `AGENTS.md`.
- [primitive-to-fuse.md](primitive-to-fuse.md): how the vendor turns primitives
  into fuses, and how that compares with Apicula's structures.
- [fse-format.md](fse-format.md): `.fse` table types, per-device layouts and open
  questions.
- [pll.md](pll.md): how the vendor configures PLLs, compared with `gowin_pack`.
- [gw5-devices.md](gw5-devices.md): where GW5AT-60B and GW5AST-138C differ, and the GW5 I/O logic LSR/GSR rule.
- [gw5a-hclk-pins.md](gw5a-hclk-pins.md): GW5A-25A clock pins that reach HCLK
  through a pair IOB, and the vendor tables behind them.
- [logic-tile.md](logic-tile.md): how LUTs, DFFs, the wide-LUT muxes and SEL connect
  inside a logic tile.
- [bsram.md](bsram.md): BSRAM handlers compared with `gowin_pack`.
- [timing.md](timing.md): how the IDE computes delays, the `.tm` formats, and how
  Apicula's and nextpnr's timing compare with it.
- [primitive-params.md](primitive-params.md): primitive ports, parameters and
  allowed values from the IDE's `primitive.xml`, compared with Yosys' cell library.
- [tiled-fuzzer.md](tiled-fuzzer.md): comparing Apicula with the vendor on random
  primitive configurations, and what the comparison has to allow for.
- [hand-written-tables.md](hand-written-tables.md): which Apicula tables have a
  vendor source, and what each `logicinfo` table is for.

Process notes and tooling are in [`AGENTS.md`](../../AGENTS.md).
