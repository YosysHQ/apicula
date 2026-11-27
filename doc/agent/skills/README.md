# Agent skills

A snapshot of the skills our coding agents use for Apicula work, taken on
2026-11-27. They are [Hermes Agent](https://hermes-agent.nousresearch.com/) skills:
a `SKILL.md` with the procedure, plus references, templates and scripts it points
at. They are copied verbatim, so paths such as `~/code/apicula-wt/` are local to
the maintainer's machine, and the snapshot is not kept in sync.

- [apicula-fuzzer-burndown](apicula-fuzzer-burndown/SKILL.md): triaging fuzzer
  xfails, and the kanban flow of design, implement and review cards. The stage
  instructions the workers read are in its `templates/`.
- [fpga-hardware-in-the-loop](fpga-hardware-in-the-loop/SKILL.md): running and
  writing hardware-in-the-loop tests on the board rig.
- [nextpnr-qor-benchmarking](nextpnr-qor-benchmarking/SKILL.md): measuring
  nextpnr place-and-route quality on Gowin parts.

See [AI_POLICY.md](../../../AI_POLICY.md) for how they fit together.
