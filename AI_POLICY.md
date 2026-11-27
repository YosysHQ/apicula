# AI Policy

LLMs are great fun and very powerful, and with great power comes great responsibility.
Unfortunately in an open source project, drive-by contributors get all the fun and maintainers all the responsibility.
This makes the value of most AI contributions negative: It saves minimal effort prompting an agent, and costs significant extra review effort.
With that in mind:

- If you're not a maintainer, please open an issue before opening a PR for anything more than a few lines
- Spend your tokens on issues with an agreed scoped and design
- Never submit code you don't understand
- Prefer human-authored communication for anything you care about

## As maintainers

Apicula predates LLMs, and we intend to maintain a carefully curated architecture.
But there is no doubt that LLMs can greatly expedite mechanical work which we will take full advantage of.

### Finding the gaps

Apicula is reverse engineered, so most of the work is finding where it disagrees
with the vendor. Two oracles keep that honest, for humans and agents alike:

- **Property testing.** `tools/tiled_fuzzer.py` draws random primitive
  configurations with Hypothesis, builds them with both Apicula and the Gowin IDE,
  and compares the fuses. Known mismatches are xfails in `tests/test_fuzz.py`, so a
  fix shows up as an xfail turning into a pass.
- **Hardware in the loop.** A rig of Gowin boards runs self-checking test designs
  (`examples/hil.v`) in CI. It catches what fuse equality can't: designs that
  match the vendor and still misbehave on silicon.

### Humans decide, agents execute

Agent work runs through a kanban board, with every fix a chain of cards:

1. **Triage and design.** An agent investigates (fuzzer diffs, the vendor code,
   hardware runs) and stops with a design package. A maintainer decides scope and
   approach; nothing is implemented before that.
2. **Implementation.** An agent implements the agreed design and opens a draft PR.
   Changes for Yosys and nextpnr, which do not accept LLM-generated code, end as a
   proposal instead: an issue draft, or a diff a maintainer rewrites and submits
   themselves.
3. **Review.** An independent agent reviews the PR against the testing rules in
   [AGENTS.md](AGENTS.md) and reruns the fuzzer, then a maintainer reviews and merges.

Commits record who decided what in a Collaborative Work Statement (see AGENTS.md).
The instructions the agents follow are in [doc/agent/skills/](doc/agent/skills/README.md),
for reuse and so you can see exactly how the sausage is made.
