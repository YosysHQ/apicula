# Agent-written documentation

Findings about the Gowin IDE's code and data files, written by coding agents during
reverse engineering. All of it refers to IDE **1.9.10.03** unless stated otherwise.

Treat these notes as working documents. Claims are marked as read from code,
checked against data, or inferred. Correct them when they turn out to be wrong.

- [primitive-to-fuse.md](primitive-to-fuse.md): how the vendor turns primitives
  into fuses, and how that compares with Apicula's structures.
- [fse-format.md](fse-format.md): `.fse` table types, per-device layouts and open
  questions.
- [pll.md](pll.md): how the vendor configures PLLs, compared with `gowin_pack`.
- [gw5-devices.md](gw5-devices.md): where GW5AT-60B and GW5AST-138C differ.
- [bsram.md](bsram.md): BSRAM handlers compared with `gowin_pack`.
- [timing.md](timing.md): how the IDE computes delays, the `.tm` formats, and how
  Apicula's and nextpnr's timing compare with it.
- [hand-written-tables.md](hand-written-tables.md): which Apicula tables have a
  vendor source, and what each `logicinfo` table is for.

Process notes and tooling are in [`AGENTS.md`](../../AGENTS.md).
