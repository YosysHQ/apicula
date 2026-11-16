# Agent-written documentation

Findings about the Gowin IDE's code and data files, written by coding agents during
reverse engineering. All of it refers to IDE **1.9.10.03** unless stated otherwise.

Treat these notes as working documents. Claims are marked as read from code,
checked against data, or inferred. Correct them when they turn out to be wrong.

Working notes, referenced from `AGENTS.md`:

- [codebase.md](codebase.md): building, the modules, chipdbs, wire names and
  supported devices.
- [testing.md](testing.md): regression tests, vendor tests with the tiled
  fuzzer, hardware-in-the-loop tests, and comparisons with `master`.
- [reverse-engineering.md](reverse-engineering.md): tools for reading
  `libgowin.so` and the IDE's data, and the scripts in `tools/`.

Findings:

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

The rules are in [`AGENTS.md`](../../AGENTS.md).
