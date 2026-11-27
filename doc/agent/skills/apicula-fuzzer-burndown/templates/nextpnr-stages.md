# nextpnr Gowin work: stage instructions

**Read your card's comment thread before starting (`kanban_show`).** Coordinator comments carry Pepijn's later decisions and override the card body and this file. Say in your completion summary which ones you applied.

Each item is a chain of three kanban cards sharing one nextpnr worktree: design → implement → review. The card body names the worktree, the branch, the issue and Pepijn's decisions. Goal: a nextpnr branch that **fully closes** its issue, committed locally, which Pepijn reviews, tweaks and submits himself.

## nextpnr policy (gatecat) — hard rules
- LLM-assisted patches are accepted only if Pepijn has gone through them and understands everything, and **comments are human-written**: LLM-written comments are against nextpnr codebase policy.
- So: **every code comment you write starts with `TODO: rewrite:`** (`// TODO: rewrite: <what and why>`). Pepijn rephrases each one in his own words before submitting, and drops the marker. Write them wherever a comment is needed, concise and factual (vendor function + address where it applies). Mark or remove any unmarked agent-written comment already on the branch. No separate `file:line` list is needed.
- **Never push, never open PRs or issues, never comment on GitHub** in YosysHQ/nextpnr. Commit locally only, author Pepijn (the repo's git config), trailer `Co-Authored-By: Claude <model> <noreply@anthropic.com>`. Commit messages and the PR body are drafts he edits; keep them plain, every number measured.
- Simple code in the style of the surrounding gowin uarch code; minimal diff; no refactors beyond the issue.

## Environment
- Load skills: `apicula-fuzzer-burndown` (nextpnr build flags, vendor runs), `nextpnr-qor-benchmarking` (Fmax/rip-up bench at `~/code/apicula-wt/qor-bench`), `memory-safe-builds` (build inside `systemd-run --user --scope -p MemoryMax=12G`, `-j6` max).
- First rebase the branch onto current `origin/main` (or the parent branch named in the card); local rebase only. Ignore `git stash` entries; they belong to other branches.
- Apicula data: `~/code/apicula-wt/apicula-master` (detached at the released master, chipdbs built). Read-only for cards. Always run the chipdb generator and Apicula tools with `PYTHONPATH=~/code/apicula-wt/apicula-master`, and configure nextpnr with `-DPython3_EXECUTABLE=~/code/apicula/apicula/.venv/bin/python3` under that PYTHONPATH (the venv's site-packages apycula is stale).
- The branch must also work with apycula releases that lack new groups (`.get(...)`, skip when absent), so nextpnr CI never breaks.
- Vendor: `GOWINHOME=~/bin/Gowin_V1.9.10.03_linux`; vendor knowledge in `doc/agent/timing.md` of apicula-master; Ghidra project `~/code/apicula-wt/ghidra-libgowin`. One vendor run at a time per card.
- Mark every claim as code (read from the vendor), data (checked against SDF/.tm/bitstream) or inferred.
- Card comments cite PRs/issues as `#N`, never a URL.

# Bug-fix chains (crashes, wrong placement) — overrides for stages 1–3
Cards whose body says **bug-fix chain** use these instead of the timing evidence:
- **Reproducer:** build it against `origin/main` (or the branch's base) and show the crash/wrong result; with the fix it builds. Use your own Apicula worktree for HIL designs (`git -C ~/code/apicula/apicula worktree add --detach ~/code/apicula-wt/<card-slug>-apicula <branch>`, copy the gitignored chipdb data in). Never build in someone else's worktree.
- **Root cause first** (systematic-debugging): name the exact function and why it fails. If the cause is in Apicula (`gowin_pack`), say so and `kanban_block(needs_input)` once: the fix moves to an Apicula PR.
- **Vendor check** where behaviour is in question: the IDE's bitstream for the same design (`gowin_unpack`) or `libgowin.so` code.
- **Hardware:** if the fix changes a bitstream, run the affected HIL test/batch on the rig with `fpga-hardware-in-the-loop`'s `scripts/hil-run.sh` (locked). Don't touch a desk board another card owns.
- **Unchanged elsewhere:** a few `examples/` designs not using the feature give identical bitstreams with and without the fix (`cmp`), GW1N-9C and GW2A-18C (GW5A-25A where the path reaches).
- Stage 2's SDF/QoR items don't apply; the rest of stage 2 and stage 3 do.

# Stage 1: design
Read the branch (`git log origin/main..`), the issue, the vendor notes and Pepijn's decisions in the card body. Post ONE comment: findings (code/data/inferred), the design as one paragraph, the test plan with the number that counts as done, and the list of human comments needed. **Do not block** unless the vendor code contradicts one of Pepijn's decisions or a new decision appears that changes the implementation: then `kanban_block(kind="needs_input")` once with the one question. Otherwise `kanban_complete` with the full implementation brief as summary.

# Stage 2: implement
Implement the brief; anything beyond it is a follow-up (list it).
- **Long work: post a progress comment before you run low on iterations** (what is built, the first open bug, where the harness lives, what's left), so a respawn continues instead of restarting.
- **Apicula data gap** (a field the vendor rule reads that Apicula doesn't export): read it with `.get` when present, leave the arc out with a warning otherwise, and list the exact field/offset as an Apicula follow-up. Don't block on it.

Done means, with real output:
1. Builds for every device the card names.
2. Timing chains: **SDF comparison** against the IDE's own routes/SDF (`tools/timing/`), before (origin/main) and after: total %, p10/median/p90 per device.
3. Timing chains: **QoR** on the qor-bench designs, before/after: post-route Fmax and router rip-ups/runtime, ≥3 seeds.
4. Unchanged where it must be: devices/arcs outside the issue get identical chipdb timing (diff the `.bba` timing sections, or explain each difference).
5. Commit locally (no push). Write `~/code/apicula-wt/<worktree-name>-PR.md`: draft PR title, body (problem, change, evidence tables, what was not done + follow-up issue drafts).
6. `kanban_complete` with head SHA, the PR-draft path, and metadata `{"head_sha":..., "tests_run":[...], "followups":[...]}`.

# Stage 3: review
Independent review of the committed branch at the handoff's head SHA. Review the artifact (diff + PR draft + acceptance criteria), not the author's reasoning.
- Verdict via `delegate_task` with `option="review"` (diff, PR draft, criteria). Record the model served (`~/.hermes/cache/delegation/live/<id>/manifest.json`); if the route fails, retry once, then block rather than substituting your own verdict.
- Yourself: reproduce one evidence number from the PR draft; check there are **zero** agent-written code comments; check the old-apycula fallback.
- Check where each new early-return or rewrite branch sits relative to the function's existing guards (null-net / missing-pin / constant-net checks). A branch placed above them acts on cells the guards were meant to skip (e.g. disconnecting a user's OCE when CE has no net, which the vendor never does). Moving it below the guards is usually the whole fix and keeps the diff the same size: list it as blocking unless the vendor does act in that case.
- `kanban_complete(summary="APPROVE|REQUEST_CHANGES: <why>", metadata={"verdict","reviewer_model","head_sha","blocking":[],"non_blocking":[]})`. Never push or comment on GitHub.
