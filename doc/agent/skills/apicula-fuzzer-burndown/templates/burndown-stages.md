# Apicula fuzzer burn-down: stage instructions

**Read your card's comment thread before starting (`kanban_show`).** Coordinator comments carry Pepijn's later decisions and override the card body and this file. Say in your completion summary which ones you applied.

Each fix is a chain of three kanban cards sharing one worktree: design → implement → review.
The card body names the worktree, the branch and the failure; this file says how each stage works.

## Environment (already set up — do not reinstall)
- Worktree: `<the worktree named in the card body>` on branch `<the branch named in the card body>`, cut from `origin/master` (8c2a5cd). This card's workspace; never create another worktree, never switch the main checkout `~/code/apicula/apicula`.
- Read `AGENTS.md`, `doc/agent/tiled-fuzzer.md` and `doc/agent/testing.md` first; AGENTS.md governs.
- `export GOWINHOME=~/bin/Gowin_V1.9.10.03_linux PATH=~/code/apicula/apicula/.venv/bin:$PATH YOSYS=/usr/local/bin/yosys NEXTPNR=/home/pepijn/code/apicula-wt/nextpnr-main/build/nextpnr-himbaechel`. The venv has msgspec, pytest and the Hypothesis version CI pins.
- **Base-class changes in `gowin_pack.py` reach the whole GW5A family.** GW5AT-60B and GW5AST-138C inherit the `Device` handlers; only GW5A-25A overrides some of them. A fix proven on GW1N/GW2A must be scoped to GW1N/GW2A explicitly, with the file's existing family mechanism. Check `examples/gw5a` output is unchanged. Never claim "GW5A unchanged" without checking which class each changed method reaches.
- **Force-push needs the coordinator.** Unattended workers can't force-push (the harness blocks it). After a rebase, verify locally, then block once with the exact `git push --force-with-lease=<branch>:<old-sha> origin <branch>` command, plus any `gh pr edit` body file. The coordinator runs it and unblocks you to complete.
- **No guessing in shipped code.** If a rule rests on untried combinations, measure the whole (small) space with vendor runs before publishing. Never ship a comment or PR line that says "guess" or "extrapolated" about the code's behaviour. Inference is fine in follow-up notes and `BROKEN` reasons; the code itself must implement a measured rule.
- **Stacked PRs target their parent branch** (`gh pr create --base fix/<parent>`), so GitHub shows only their own commits. CI still runs, because `chipdb.yml` triggers on any `pull_request`. After the parent merges, the coordinator retargets the child to master and rebases it.
- **Check the logic against the vendor code.** For every rule a fix encodes (a default, a condition, a width set), find the vendor function that sets that attribute (`libgowin.so`, typically `fusegenMem::set*`/`init*Attr`; tools per `doc/agent/reverse-engineering.md`, Ghidra is installed). Cite it as `Class::func @0xaddr (IDE 1.9.10.03)` in the PR. Bitstream measurements confirm the reading; they don't replace it. If the function can't be found within reasonable effort, say so explicitly, and the measured table is then the evidence.
- **No yowasp for development.** Use the local Yosys, and the nextpnr baseline build above (origin/main, Release, read-only: never edit or rebuild it). The pinned yowasp in `.github/workflows/fuzzer.yml` belongs to CI; leave it alone.
- **Yosys and nextpnr are external projects under the [interim YosysHQ LLM policy](https://blog.yosyshq.com/p/interim-yosyshq-llm-policy/) (no LLM-generated code in PRs; AI-assisted code only from a human who can defend every choice in it); we follow our own AI policy as an outside contributor there.** Never commit, push or open a PR or issue on them. A small fix: prepare it in a nextpnr worktree under `~/code/apicula-wt/`, build and test it, and hand Pepijn the diff with evidence; he submits it. A complex one: write an issue draft (problem, reproducer, proposed approach) for him to post. Either way, card it as a follow-up; don't do it inside an Apicula card.
- Chipdbs: `make apycula/GW1N-9C.msgpack.xz apycula/GW2A-18C.msgpack.xz` (seconds; not committed). Rebuild after touching chipdb code.
- Fuzzer, targeted: `python3 tools/tiled_fuzzer.py -d GW1N-9C -n 20 --seed 1 --prims <PRIMS> -j 4 -o $TMPDIR/<name>`; replay a saved case with `--replay`. Full suite per device: `pytest tests/test_fuzz.py --device GW1N-9C --fuzz-jobs 4 -rxX` (10–20 min). Never more than `-j 4` (follow-up cards: `-j 2`): other cards run vendor jobs on this box too.
- Quick hardware sanity check (optional; Tang Nano 9K = GW1N-9C, Tang Nano 20K = GW2A-18C): `~/.hermes/skills/software-development/fpga-hardware-in-the-loop/scripts/hil-run.sh <tangnano9k|tangnano20k> <bitstream.fs> [settle_ticks] [reference.txt]`. It loads the board on the CI runner and prints the UART tick block. It does not replace the PR's `hil` CI job.
- Comments on this card cite pull requests as `#N`, never as a URL or markdown link (a PR URL in a card comment freezes the card for 24 h). URLs go in the completion summary/metadata only.

## Stacked chains
A card body may say the chain is **stacked on** another chain's branch, because it touches the same code. Then the implement stage starts only after that chain's review. If the parent PR is merged, rebase onto `origin/master`. Otherwise rebase onto the parent branch and open the draft PR against `master` with "Stacked on #N" in the body. The design stage reads the parent branch (`git diff origin/master...<parent branch>`) so it designs against the code as it will be.

## PRs that depend on a nextpnr change
If a primitive passes only with a pending nextpnr change, make the test green in the same PR anyway: take the primitive out of `BROKEN`, or narrow its reason to what still fails *with* the change. Verify with a local nextpnr build that includes the change, and report baseline vs fixed.
- The PR body names the nextpnr PR and says it stays a draft until that PR is merged into nextpnr main. CI's dev nextpnr then carries it.
- **Ignore yowasp entirely.** Never bump or mention the yowasp pin.

# Stage 1: design
No implementation in this stage.

## Establish before designing
- Reproduce with the targeted fuzzer on the affected devices; record command, seed and status totals.
- Find the cause in Apicula (`apycula/gowin_pack.py`, `gowin_unpack.py`, chipdb tables) and, where the intent is unclear, in the vendor (`IDE/lib/libgowin.so`, cheapest tool first per `doc/agent/reverse-engineering.md`). Separate what was read from code, what was checked against bitstreams, and what is inferred; name the IDE version for any address.
- Decide whether the primitive(s) can come out of `BROKEN` on every device or only some. `BROKEN` is keyed per primitive across all devices; if a primitive still differs elsewhere (GW5A), the change splits that entry per device. Say which.
(plus the card-specific questions in the card body)

## Deliverable, then halt
1. Post the design package as ONE card comment: the questions with your recommendation and what would flip it, then the recommended design as one paragraph (what changes, where, why), one or two alternatives in a sentence, the test plan (which fuzzer runs and `BROKEN` edits prove it; the `BROKEN` xfail is the regression test, no extra unit test needed unless a pure-Python helper warrants one), and a size verdict: **trivial** or **substantial**.
2. `kanban_block(kind="needs_input", reason=<one line: "design ready for review: <recommendation>">)` and stop. Do not commit, do not complete before the answer. Block exactly once.
3. When resumed (the thread has Pepijn's answer via the coordinator): apply it.
   - **substantial**: commit the design to `doc/agent/` (extend the relevant existing file, e.g. `tiled-fuzzer.md`, or a new file linked from `doc/agent/README.md`) on this branch, with a Collaborative Work Statement in the commit body. Do not push, no PR.
   - **trivial**: commit nothing; the plan travels in your completion summary.
4. `kanban_complete` with a summary that is the full implementation brief for stage 2 (files, functions, fuse rows, devices, `BROKEN` edits, verification commands), and metadata `{"size": "trivial|substantial", "design_commit": <sha or null>}`.

# Stage 1 for nextpnr/Yosys items (design only)
Same as Stage 1, in a nextpnr worktree on `origin/main`. **Never commit, push, open PRs or file issues on nextpnr or Yosys.** Add these to the package:
- the size of the change in lines and files, and whether it's in the style of existing code;
- whether the fuzzer, run with a local build of the change, would prove it;
- a recommendation: **PR** (simple; Pepijn commits and pushes it) or **issue** (complex or design-level; Pepijn posts it).

Prototyping in the worktree is allowed: build per the skill's flags, inside a `systemd-run` memory scope with `-j6`. Leave it uncommitted. Block once with the package, as in Stage 1. When resumed with the decision:
- **PR**: finish the change, build and verify it, and complete with the diff, the before/after fuzzer totals and a suggested commit message, all uncommitted.
- **issue**: complete with an issue draft (problem, reproducer, proposed approach; deeper analysis in a collapsed block) for Pepijn to post.

# Stage 2: implement
Stage 2 of 3: implement the approved design from stage 1 (read the parent handoff with `kanban_show`; if the design was substantial it is committed under `doc/agent/` on this branch). Stay inside that design; anything beyond it is a follow-up, listed in the PR body, not done here. If the design turns out wrong, `kanban_block(needs_input)` with the one question instead of improvising.


## Done means (AGENTS.md Testing; report real output for each)
1. The fixed primitives are removed from `BROKEN` in `tests/test_fuzz.py` (split per device where the design says so; update the reason strings and `doc/agent/tiled-fuzzer.md`'s known-differences list). That xfail→pass is the regression test: show it xfails on master and passes here. Any extra unit test checks a vendor reference (bitstream, SDF, hand-read vendor file), never the code's own current output.
2. Targeted fuzzer runs on every affected device, `-n 20 --seed 1`: command and status totals. Then the full `pytest tests/test_fuzz.py --device <dev> --fuzz-jobs 4 -rxX` on each affected device: no new failures, no XPASS left unhandled.
3. `python -m unittest discover tests` still passes.
4. Unchanged output: pack the same nextpnr JSONs for a few `examples/` designs that do not use the feature with master's and this branch's `gowin_pack`, `cmp` the bitstreams, explain every difference.
5. Commit (never amend; commit messages per AGENTS.md with a Collaborative Work Statement: origin = Pepijn's fuzzer burn-down, design approved by Pepijn in stage 1, evidence, testing). Publish before polish: push `<the branch named in the card body>` to `origin` (YosysHQ/apicula) and open a **draft** PR against `master` with `gh pr create --draft`, body stating what was run.
6. `kanban_complete` with the PR URL and the head SHA in the summary and metadata `{"pr": <url>, "head_sha": <sha>, "tests_run": [...]}`. Do not merge, do not mark ready.

# Stage 3: review
Stage 3 of 3: independent review of the draft PR produced by the parent card (its URL and head SHA are in the parent handoff via `kanban_show`). Review the artifact, not the author's reasoning: read the PR diff, the PR body and the acceptance criteria below; do not read the parent cards' comment threads.

Worktree `<the worktree named in the card body>`, branch `<the branch named in the card body>`; check out nothing else. Pin the review to the head SHA from the handoff.

## Acceptance criteria
- The change fixes the problem described in this card's body and does nothing else (minimal; unrelated refactors are a finding).
- The primitives removed from `BROKEN` really pass: rerun the targeted fuzzer (`python3 tools/tiled_fuzzer.py -d <dev> -n 20 --seed 2 --prims <PRIMS> -j 4 -o $TMPDIR/review`, a different seed than the author) on each affected device and report totals. Env: as in the Environment section above; `make apycula/<dev>.msgpack.xz` first.
- Primitives still in `BROKEN` have accurate reasons; per-device splits are correct.
- AGENTS.md: commit message carries a Collaborative Work Statement; evidence vs inference kept apart; the PR body says what was run, including the unchanged-output `cmp`.
- Code is simple; edge cases fall out naturally rather than being special-cased.

## How
Obtain the verdict through `delegate_task` with `option="review"` (give it the diff, the PR body and these criteria — not the design argument), and run the fuzzer check yourself. Record the model the review route actually served (`cache/delegation/live/<id>/manifest.json`); if the route fails, retry once, then report it rather than substituting your own verdict. Do not push, merge, mark ready or comment on GitHub. Card comments cite PRs as `#N`, never a URL.

`kanban_complete(summary=<APPROVE or REQUEST_CHANGES, one line why>, metadata={"verdict":..., "reviewer_model":..., "head_sha":..., "blocking":[...], "non_blocking":[...], "fuzzer":{...}})`.
