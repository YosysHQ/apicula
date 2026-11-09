# Agent-written documentation

Findings about the Gowin IDE's code and data files, written by coding agents during
reverse engineering. All of it refers to IDE **1.9.10.03** unless stated otherwise.

Treat these notes as working documents. Claims are marked as read from code,
checked against data, or inferred. Correct them when they turn out to be wrong.

- [primitive-to-fuse.md](primitive-to-fuse.md): how the vendor turns primitives
  into fuses, and how that compares with Apicula's structures.
- [fse-format.md](fse-format.md): `.fse` table types, per-device layouts and open
  questions.

Process notes and tooling are in [`AGENTS.md`](../../AGENTS.md).
