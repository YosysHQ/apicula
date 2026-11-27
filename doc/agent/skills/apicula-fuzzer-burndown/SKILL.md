---
name: apicula-fuzzer-burndown
description: "Use when working apicula PRs, xfails, timing or HIL."
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [apicula, gowin, fpga, fuzzer, xfail, kanban, triage]
    related_skills: [fpga-hardware-in-the-loop, github, hermes-agent]
---

# Apicula tiled-fuzzer burn-down

`tests/test_fuzz.py` compares Apicula's bitstreams with the vendor IDE on random
primitive configurations (`tools/tiled_fuzzer.py`). Known-broken primitives are
listed in its `BROKEN` dict and are reported as xfail. The repo's AGENTS.md and
`doc/agent/tiled-fuzzer.md` cover the per-change gates and how the fuzzer works. This
skill covers the triage and project-management loop around them.

## When to Use

- Any Apicula PR work: status sweeps of the open PRs, reviews against AGENTS.md's test rules,
  stacking and landing (`references/pr-coordination.md`).
- Choosing which fuzzer xfails or mismatches to fix next, or acting as PM on a board
  of them.
- Reading a `Tiled fuzzer` CI failure.
- Writing the card for a fix to a single primitive. Use `fpga-hardware-in-the-loop` for
  the hardware test.
- Running Apicula timing-data work (`tm_parser`/`chipdb_builder`, checked against the
  IDE's SDF) through the same design → implement → review card loop, with
  `templates/timing-stages.md` instead of the fuzzer stage file.

## Procedure

1. **Orient.** The checkout is `~/code/apicula/apicula`. The remotes are `origin` =
   YosysHQ, `fork` = pepijndevos and `yrabbit`. It is usually on a feature branch, so read
   master with `git show origin/master:<path>` and never switch branches. Check access
   with `gh repo view YosysHQ/apicula --json viewerPermission`. ADMIN means draft PRs on
   YosysHQ are fine.
2. **Get the failure data from CI, not a local run.** A full run takes 10–20 min per
   device. The fuzz jobs (`fuzz (<device>)`) live in the dev toolchain of the `Chipdb builder`
   workflow (`chipdb.yml` → `toolchain.yml`); older runs are in a separate `Tiled fuzzer`
   workflow (`fuzzer.yml`). Find the latest with `gh run list -R YosysHQ/apicula --workflow <file>`.
   A run still in progress has no log yet, so take the last completed one. Then run
   `gh run view <id> -R YosysHQ/apicula --log > $TMPDIR/fuzzlog.txt` and
   `python3 scripts/xfail_summary.py $TMPDIR/fuzzlog.txt`. The script prints one line
   per xfailed device-primitive: case count, number of differing fuse lines, distinct
   fuse rows and any exception text. To see one block in full:
   `--show GW1N-9C-OSER4 ...`.
3. **Sort the list into bins**, using the reason strings in `BROKEN`:
   - nextpnr or Yosys problems ('no cell or bel', 'no Yosys cell definition'). These
     belong to other repos. Park them.
   - a few fuses (1–3 distinct rows): the candidates;
   - many rows (DSP, PLL, GW5A I/O): epics, not first picks.
4. **Rank by easy × value.** Easy means few distinct fuse rows, or a crash with an
   obvious missing handler (an `AttributeError` on a `get_<PRIM>_fuses` method).
   Value means the primitive turns up in real designs: Yosys-inferred memories (the
   `RAM16SDP4` LUTRAM, the `SDPB` BSRAM), OSER10 for the HDMI examples, and input buffers
   on every pin. A fuse row that is shared by several primitives (for example the ECLK
   mux or GSR row across OSER and IDES, or input `CLAMP` across IBUF, IDDR and IDES) is
   worth more than a row in a single primitive.
5. **Present the whole picture, then the batch.** Give a short binned overview of
   everything that is xfailed, then 3–4 recommended cards with the differing fuse rows
   and who uses each primitive. Ask for go-ahead on the batch as a single question.
   - **Keep the pipeline fed, until he says converge.** "Nothing needs you" means it's time to
     propose the next batch from the remaining bins. When he says to hold, or to converge on validating
     and merging, freeze new work: unassign unstarted chains and follow-up designs (`hermes kanban
     assign <id> none`), file newly found gaps as issues or list them as parked rather than carding them,
     and spend every turn on reviews, reworks, rebases and the merge path. Re-propose only when he asks.
     Follow-up chains spawned from design packages are the usual way the WIP balloons; card them only
     when nothing is waiting on review or rework. A parked chain that only adds PRs **on top of** a stack
     doesn't hold up merges below it: when he asks what it takes to restart it, say so, reassign it, and
     gate its implement card behind the rework of the PR it stacks on, so the rework's force-push doesn't
     land underneath a running implementer.
   - **Follow-ups found by a design card** each get one of three homes; propose which per item:
     - a new chain, when it's a concrete fix with a test;
     - an issue on YosysHQ/apicula, when it's a bigger behaviour gap not tied to one test. As
       maintainer the coordinator files it directly, after a duplicate search: problem, reproducer,
       open questions, and evidence vs inference in a collapsed block. Then point the relevant card
       at the issue number.
     - a bullet in the PR body, when it'll be absorbed by bigger work later.
6. **Cards: a chain of three per fix, in one worktree the coordinator makes.**
   - Before the first chain, make sure the nextpnr baseline build exists (see Pitfalls: no yowasp).
     Building it takes a while, and every fuzzer check waits on it, so start it first.
   - Worktree: `git -C ~/code/apicula/apicula worktree add -b fix/fuzz-<slug> ../../apicula-wt/fuzz-<slug> origin/master`.
   - The shared stage instructions (env, design/implement/review procedure, halt rule) live in
     `~/code/apicula-wt/BURNDOWN-STAGES.md`. Card bodies point at it and carry only the worktree,
     the primitives and devices, the fuse diff, and the card-specific questions. After editing that
     file, copy it over `templates/burndown-stages.md`, so the template never goes stale. Running
     cards don't re-read it, so also steer them with a card comment.
   - Create the cards with the `kanban_create` tool, never `hermes kanban create`: only the tool subscribes this session, so CLI-made cards complete and block silently. For a batch from `execute_code`, either loop the tool, or subscribe afterwards: make a throwaway card with the tool, read its `local:<chat-id>` with `hermes kanban notify-list <id>`, run `hermes kanban notify-subscribe --platform local --chat-id <chat-id> --delivery-mode notify+wake <card>` for each card, then archive the throwaway. Cards: `assignee=default`,
     `workspace_kind=dir`, keys `apicula:fuzz-<slug>:design|impl|review`, each stage parented on the previous one.
     For a batch of similar cards (one rework plus review per stack), build the bodies in `execute_code` from a
     shared preamble and loop `hermes kanban create <title> --body-file <f> --assignee default
     --workspace dir:<path> --idempotency-key <k> [--parent <id>] --json`. Parse the id from the JSON to chain the next card, then subscribe every card as described above.
   - **1 design**: triage + design, posts the package as one comment, then blocks `needs_input` once.
     The coordinator presents it to Pepijn, comments his answer on the card and unblocks it. A
     substantial design is committed to `doc/agent/`; a trivial one travels in the completion summary,
     which becomes the implementer's brief.
   - **2 implement**: removes the primitives from `BROKEN`. That xfail→pass is the regression test,
     with no extra unit test. Runs the fuzzer and the unchanged-output `cmp`, then opens a draft PR.
     When a primitive shares another's handler (a narrower variant placed on the same bel), write
     a class-attribute alias with a one-line comment saying why, not a wrapper method that looks
     arbitrary. Check first that no subclass overrides the target, because the alias binds the base function.
     When the change alters every design's bitstream (an I/O default such as input `CLAMP`), the card
     also runs the latch example on both Tang Nanos with `fpga-hardware-in-the-loop`'s
     `scripts/hil-run.sh` and puts the PASS lines in the PR body.
   - **On REQUEST_CHANGES** add a rework card (key `…:rework1`, same worktree, the blocking finding
     as concrete instructions, code untouched if only wording is wrong) and a round-2 review card
     parented on it. Stacked children: see `references/pr-coordination.md`.
     A wrong line in a PR body (for example a rule the implementer missed) needs no rework card:
     fix it with `gh pr edit --body-file`. A wording-only miss in a `BROKEN` reason or the doc (say
     the cause was re-attributed after the card pushed) is a coordinator commit on the idle branch:
     new commit, Collaborative Work Statement, fast-forward push. A code change still gets a rework card.
     After every completion that had a correction comment pending, grep the pushed reason, doc and body
     for the corrected claim before reporting it done.
     A message-only blocker on a local nextpnr branch (a commit message contradicting the PR draft)
     is also the coordinator's:
     - back up the head with `git branch -f backup/<x> <head>`;
     - reword with `GIT_SEQUENCE_EDITOR="sed -i 's/^pick <sha>/edit <sha>/'" git rebase -i <parent>`,
       then `git commit --amend -F <msg>` and `git rebase --continue`;
     - check that `git diff --stat backup/<x> HEAD` is empty;
     - update the SHAs in the `-PR.md` draft and comment the new head on the review card.
     The same holds for a pushed Apicula PR whose review asks only for commit-message, PR-body or
     docstring fixes: amend in a scratch worktree, push with `--force-with-lease=<branch>:<old sha>`,
     `gh pr edit --body-file`, then `reset --hard` the card worktree to the new head.
     A conflict after a sibling PR merged (two PRs each adding the same new test file: keep both
     test classes, merge the imports) gets the same scratch-worktree rebase, even while a review card
     is running in the card worktree: don't touch that worktree under it; comment the new head and
     `git fetch && git reset --hard origin/<branch>` on the card instead.
     A small code tweak he asks for after approval (an edge case the review listed as non-blocking)
     is also the coordinator's, and it doesn't need another rig run if the hardware result can be
     carried over: rebuild nextpnr (memory scope), rebuild the designs whose bitstreams passed on the
     rig (the evidence dir's `build.sh`/`cmp.sh` and synth JSONs), and `cmp` them against the
     evidence's `final/*.fs`. All identical means the bench results still hold; say so with the
     count. Then amend, and fix the SHA in
     the `-PR.md` draft.
   - **Force-pushes are the coordinator's** (the harness blocks them for unattended workers): the
     worker blocks with the exact command; rebase recipes in `references/pr-coordination.md`.
   - **Never `git stash` in any apicula or nextpnr worktree.** `refs/stash` is shared by all worktrees of a
     repo and holds his old entries (both repos): a no-op `git stash` followed by `git stash pop` pops one of
     his. To move uncommitted changes onto a new base, `git diff > $TMPDIR/x.patch`, reset, `git apply`.
     To test old code,
     `git show <rev>:<path> > $TMPDIR/...` or `git archive <rev> | tar -x -C $TMPDIR/<rev>`.
   - **Cards working in the main checkout** (audits, reports) never switch, stash or reset it — it's
     his branch with uncommitted work. They pack in `git worktree add --detach $TMPDIR/<name> origin/<branch>`.
   - **3 review**: the verdict comes from `delegate_task(option="review")`, plus a fuzzer rerun on another seed.
     The body restates the problem so the reviewer never reads the author's thread. The `review`
     route runs on the main model (Claude is the only provider). If a review card blocks because
     the route is down, unassign every pending review card (`hermes kanban assign <id> none`) until
     it's fixed. Each one would otherwise start, block again and drift towards triage escalation.
     Reassign them afterwards, and unblock the one that already blocked.
7. **Run the design queue.** Assign all design cards at once. When several block, present
   one package at a time and list the rest as "queued" in a short outstanding list:
   - the findings as bullets;
   - what the card rejected;
   - one decision.

   Read the package with `hermes kanban show <id>`. A package that waited behind other
   decisions gets re-presented whole, starting with a one-line problem statement and which PR
   it follows from. "Design X is still open" alone gets "what design?".

   On his answer:
   - `kanban_comment` the answer, with any amendments as concrete code-level instructions;
   - `kanban_unblock`;
   - confirm the implement child moved to `running` about a minute later.

   A card blocked on his answer for long gets respawned, hits block-loop detection and lands in
   triage. The triage pass may rewrite the title **and the body**, and it can write in a design he
   rejected. Neither `unblock`, `block` nor `promote` takes a card out of triage, and
   `specify` re-runs the rewriter. Replace the card instead:
   - create a fresh card with the corrected body, pointing at the old card's comments;
   - `hermes kanban link <new> <child>`, then `unlink <old> <child>`;
   - archive the old card.

   A card already waiting on his pick re-enters triage with a rewritten title each time it is
   re-promoted; that notification carries no new information. Answer it in one line and repeat
   the open question, rather than re-presenting the package.

   Worse, triage can **auto-decompose** it: new `auto-decomposer` cards that redo finished
   investigations (even on the rig), linked as parents of the old card. Check `kanban_list`
   for `created_by: auto-decomposer` after any triage notification. Clean up with
   `hermes kanban complete --force <running>`, `unlink <dup> <card>`, `archive <dups>`.
   `complete --force` does **not** stop the worker process: find it by its environment
   (`HERMES_KANBAN_TASK=<id>` in `/proc/<pid>/environ` of `kanban_worker_client`) and kill it.
   To end the loop once the design package is posted: **complete the design card** (summary
   = findings + "decision pending"), and park the decision on the implement card instead:
   `unlink <design> <implement>`, then `kanban_block` it at once (unlinking promotes it to
   ready; block before it spawns). Relink or unblock when he picks.

   To pause a card for him, comment the pause and let the worker block on it. Don't call
   `kanban_block` yourself on top of the worker's own blocks: that pushes it over the loop limit.

   A plain agreement ("right") counts as approval. A follow-up question ("what's more
   correct?") is not: investigate it and re-ask.

   **Re-derive a card's question before relaying it; don't pass on the card's framing.** A worker's
   "option A or B" (say, two weightings of a fitted constant) hides what is actually being decided.
   Read the design brief and the card's numbers, then present:
   - the model limit that forces a choice (e.g. one linear slope where the vendor has a step function);
   - what each option gets right and wrong, and for which share of the data;
   - the simplest option, even if the card didn't offer it.
   When the winning fit collapses to a vendor constant after rounding, recommend the constant
   itself with one line of why. That leaves no derived weights to justify upstream. A terse A/B
   relay of a modelling question gets "that's more complicated than it seemed" and a pause.

   Read the package's numbers before presenting it. If a count moves the wrong way without an
   explanation (for example `unsupported` going up after a harness fix), point it out and make
   explaining it in the PR body part of the approval. Apicula rejecting more cases can be a
   combination limit becoming visible, which belongs on the record, not under the rug.

   When a later card (a review, or another design) finds something that bears on a sibling
   design still running, pass it on as a comment on that design card. Mark it inferred or
   traced, as the card that found it did.
8. **Answering "which layer is more correct".** Before you weigh options, check the history
   with `git log -S'<symbol>' -- <file>` and `git show <sha>`. A pack/unpack asymmetry is
   usually drift: one side moved to a new data source and the other never followed.
   Prefer the fix that leaves one source of truth that pack and unpack both read, and
   delete the dead code the drift left behind.

## Backlog

Deferred work lives in `~/code/apicula-wt/BACKLOG.md` (outside the repo, not committed): parked cards, filed issues, and follow-ups from PR bodies. Pepijn tracks burn-down follow-ups there, not as GitHub issues; add every new follow-up there as it appears, and remove items when they land. A Ghidra project with `libgowin.so` already analysed is at `~/code/apicula-wt/ghidra-libgowin` (IDE 1.9.10.03); reuse it rather than re-importing. For a quick decompile by `nm` address (`analyzeHeadless` is not on PATH: use `/opt/ghidra/support/analyzeHeadless`; Ghidra's image base is +0x100000, so a `func_0x011d6a48` call is the PLT stub at `0x10d6a48` in `objdump -d -C`, which names it): `analyzeHeadless ~/code/apicula-wt/ghidra-libgowin gowin -process libgowin.so -noanalysis -readOnly -scriptPath <ABSOLUTE dir> -postScript DecompAddrs.java <outdir> 0x<addr>...`. A relative `-scriptPath` fails with "class could not be found". A minimal DecompAddrs.java that loops over `getFunctionAt(imageBase+addr)` and calls `DecompInterface` is enough. To find callers, `objdump -d -C --no-show-raw-insn libgowin.so` once (9M lines, seconds) and grep `call .*<name(`; helpers in `~/code/apicula-wt/fix-dp16-site-evidence/decomp/`: `resolve.py` (rewrites Ghidra's `func_0x…` to names), `containing.py` (address → enclosing function), `strs.py` (`&UNK_…` → .rodata string). Before tracing a vendor workaround family, grep `nm -C` for siblings by topic (`isNeedRouted`, `analysis*Bsram`): the function a card names is often not the one that decides. `~/code/apicula-wt/nextpnr-main` is the local nextpnr build; rebuild it at the current origin/main before relying on its numbers. Place-and-route quality questions (rip-ups, route time, Fmax, delay-model or router tuning) are not fuzzer work: use `nextpnr-qor-benchmarking`.

## Pitfalls

- **No change-detector tests** (Pepijn, citing "Change-Detector Tests Considered Harmful"; AGENTS.md
  Testing rule 1 since #656). A committed test's expected values come from the vendor (bitstreams,
  SDF, hand-read `.tm`/`.dat`), never from the code's current output. A test that passes on master is
  a red flag. When presenting a package, say per test what its reference is. If there is none, drop
  the test and put the evidence in the PR body and the doc.
  - Two shapes slip past a quick read: pinning **every element of a quad** when the SDF gives only
    min:typ:max (the inner elements are current output — compare `min(e0,e1)`/`max(e2,e3)` to the
    SDF instead), and **comparing Apicula with itself** across devices or speed grades (a vendor fact
    like identical `.tm` bytes belongs in the doc, not in a self-comparison test).
- **Check the chipdb matches the branch before trusting a local test run.** Tests load the built
  `apycula/<dev>.msgpack.xz`, which can predate the branch's last commits: compare its mtime with
  `git log --format='%ci %h' --stat origin/master..HEAD`, and rebuild unless every later commit
  touches only comments, docs or tests (`.venv/bin/python -m pytest tests/<file>`).
- **No guessing in shipped code** (Pepijn's review: "no guessing"). A rule in code must be measured
  over its whole (small) input space with vendor runs, or cite the vendor function. Never ship a
  comment or PR line calling the code's behaviour a guess or an extrapolation. Inference is fine
  in `BROKEN` reasons and follow-up notes. When reviewing a package, grep the diff for "guess" or
  "extrapolat" before presenting it.
- **Check the logic against the vendor code, not only bitstreams** (Pepijn). Agents default to fuzzing. Every rule a fix encodes needs the vendor function that sets it (`libgowin.so`, `fusegenMem::set*`/`init*Attr`, Ghidra installed), cited as `func @0xaddr (IDE 1.9.10.03)`. Measurements confirm the reading; if the function isn't found, the PR says so. Make decompiling a required design-card step, not an optional one.
  When the fix drops or narrows something the vendor does *sometimes* (a fuse set only under a netlist condition), the PR body gets a "Why this is correct" section before the evidence: the vendor condition (function + address), a table of vendor runs showing when it fires and when it doesn't (fuse bits + decoded attributes per case), and why our flow never meets the condition (which tool would have to produce it, checked in its source). A bare "the vendor only sets it when X" reads as a conditional being ignored, and he asks for the explanation before it goes up. Also name what would have to change upstream for the condition to start mattering.
  When he asks why the removed workaround was there ("there must have been a reason"): `git log -S'<attr>' --format='%h %ad %an %s' origin/master -- <file>` and keep going past rewrite commits that only moved the line to the introducing commit; read its message, PR and the example committed with it; then bench that example's exact configuration (e.g. the pin tied to a constant) packed by master and by the branch from the same nextpnr JSON (`PYTHONPATH=<checkout> python -m apycula.gowin_pack ...`, `hil-run.sh`). Report the board result per pack and label any story about the original motive as unverified.
- **Test-coverage tracks** (making tests catch open bugs, not fixing a primitive) reuse `BURNDOWN-STAGES.md` with overrides in the card body: "done" means each listed bug fails or xfails with `#N` in its reason; workers don't comment on GitHub issues but return a `tracks` map and a `fixes` map (`trivial` + sketch, or `needs-design` + why) in their metadata. Design cards ask him only about building the test, never about fixing the bugs, and complete without blocking when they have no such question. Once the test is on master, a needs-design bug gets one issue comment ("now tracked as a failure by <test>"), and a trivial one gets a fix chain, after which the issue is closed. Before carding, close issues that master already fixes; reproduce on master and on the commit before the fix, and name the fixing PR. Skip bugs that already have an open yrabbit PR.
- **Claims audit before the merge report** (Pepijn: "review all PRs for unvalidated or incomplete claims"). Fan out report-only `delegate_task(option="review")` children, one per stack. Write the shared context file **before** dispatching (children read it first). They do no vendor or fuzzer runs (OOM), and output a table per claim: where, quote, problem (inferred/incomplete/stale/wrong), validating check. Then one rework card per stack, plus a review card, chained to limit parallel vendor runs. Gate stacked chains' implement cards behind the rework of the PR they stack on.
- **Sweep the board on every notification, not only the card it names.** Blocked cards and
  REQUEST_CHANGES verdicts slip when several notifications arrive while a decision is being
  discussed: a blocked rework sat for hours waiting on a force-push, and two review verdicts never
  got a rework card. After handling a notification, run `hermes kanban list | grep -v '✓'` and act on
  every `blocked` card (`hermes kanban show <id> | grep 'blocked {'`). For every review card completed
  since the last sweep, read its verdict and make sure a REQUEST_CHANGES has a rework card.
- **Implementers can miss coordinator comments posted while their card waited in `todo`**,
  because the body is what they plan from. Put rule changes in the stage file too, which tells
  workers to read the thread first and list the comments they applied. Before a review card
  starts, check the implementer's summary against the latest comments; on a miss, park the review
  (`assign none`), add a rework card, link the review behind it, and reassign.
- **A PR that depends on a nextpnr change flips the test itself and waits** (Pepijn's rule;
  gatecat merges quickly). It removes the primitive from `BROKEN`, or narrows the reason to
  what fails even with the fix, and is verified with a local build of the nextpnr change. It
  stays a draft until the nextpnr PR is merged into nextpnr main; CI's dev nextpnr passing is
  good enough. Name the nextpnr PR number in the Apicula card and PR body once he has
  submitted it (`gh pr list -R YosysHQ/nextpnr --author pepijndevos`). Track those PRs, and mark
  them ready when nextpnr merges.
- **A nextpnr issue that needs Apicula data closes in three steps:** Apicula data chains
  first, then an Apicula release, then a nextpnr PR that really closes the issue (no
  "Part of" PRs left dangling). Asked "what's needed to close it", list per issue:
  - each remaining item, tagged as Apicula data, nextpnr code, or a maintainer decision
    (e.g. a himbaechel core change);
  - which items close the issue and which to split into a follow-up issue.
  Check that the nextpnr branch tolerates the *released* Apycula lacking the new groups
  (`groups.get(...)` / `if group == ...`), so it can merge before the release without breaking
  CI. Keep the per-issue remaining items in `BACKLOG.md` with the branch names.
  A data gap a nextpnr implementer finds mid-chain loops back the same way: on his go, a small
  Apicula timing chain (`TIMING-STAGES.md`, design told not to block) exports the field, then
  another release; the nextpnr branch keeps its read-when-present fallback meanwhile.
- **A card blocked with "ran out of iterations" is transient,** not a design question: comment
  "continue from comment <N>" plus any decision it raised in passing, and unblock it. Raise only
  the real decisions it surfaced (e.g. a data gap) with him.
- **Stacks, the merge-order report, the rebase train and landing** are in `references/pr-coordination.md`.
  "Ready to merge" means reviewed, rebased onto current master and CI green; report it once, as one
  merge-order list, when the whole set is there. When he says "land everything", follow its Landing
  section: merge first, measure the suite once at the end.
- **A card that blocked with a question can complete without his answer**, after a block-loop
  respawn, by reading an earlier approval broadly. When that happens, tell him plainly which option
  the card took on its own, and offer the alternative as a rework card. Don't present it as his
  decision. The stage file now forbids this. Still check every completion of a card that had an
  open question.
- **Full nextpnr chains when he asks to have them written, reviewed and tested for his review**
  (closing a nextpnr issue, fixing a nextpnr crash): copy `templates/nextpnr-stages.md` to
  `~/code/apicula-wt/NEXTPNR-STAGES.md` and run design → implement → review in a nextpnr worktree.
  Settle the open design questions with him first, one at a time, and write his decisions into the
  design card body; the design card then doesn't halt unless the vendor contradicts a decision.
  Branches end as local commits plus a `<worktree>-PR.md` draft, never pushed.
  Before proposing to split one commit off such a branch as its own PR, check it builds on
  `origin/main` alone: it may call helpers only the branch defines, and the reduced version is a
  different change with unmeasured numbers.
  When a bug-fix design card finds the cause in Apicula (an issue's own hypothesis is often
  wrong: check which variable actually separates passing from failing seeds), present it and, on
  his go: complete the nextpnr design card with the resolution, complete its implement and review
  children as "Dropped", remove the empty nextpnr worktree and branch, and open an Apicula chain
  (`BURNDOWN-STAGES.md`, worktree from current `origin/master`) whose design body points at the
  old card's evidence directory and lists only the checks still missing (vendor function, other
  slots/devices, `BROKEN` entry), so nothing gets re-measured.
- **Otherwise nextpnr/Yosys items get a design-only card** ("Stage 1 for nextpnr/Yosys items" in the
  stage file), in a nextpnr worktree. The package ends in PR (Pepijn submits), issue (Pepijn
  posts) or drop. There are no implement or review children; after the decision, the same card
  finishes the uncommitted diff or the issue draft. A follow-up that spans both repos, such as
  RAM16SDP1 (nextpnr routing plus an Apicula handler), is one Apicula chain whose design covers both halves.
  When a decision he has to make hinges on a nextpnr crash ("keep it required or xfail?"), have
  the draft fix already made and building in `~/code/apicula-wt/nextpnr-<slug>` when you ask: his
  first question is whether a draft checkout exists. When presenting a nextpnr package for him to submit, show the actual diff hunks (`git diff` in the
  worktree), one short mechanism line per hunk (what failed before, what happens now), the effect on
  each device, the open behavioural questions (e.g. hard error vs fallback), and the suggested commit
  message. He reads the code before submitting; a summary of the package alone gets "explain the change".
  Asked to explain one ("what is this one about?"), go in this order: the background (what the
  surrounding code is for, in two or three lines), the bug's mechanism with the symptom per device,
  the diff, why designs without the trigger come out byte-identical, the evidence, and what it
  doesn't fix. Read the surrounding function first; explain from the code, not from the card summary.
  Asked "how critical is this bug?", answer from the code paths, not from the issue: which chips
  (the chip flag in Apicula's `set_chip_flags`), which designs reach it (read Yosys's
  `/usr/local/share/yosys/gowin/brams_map.v`/`brams.txt` to see which pins inference drives and at
  which widths, e.g. CE = read enable, OCE tied 1), what goes wrong and whether anything warns,
  when it actually bites in real designs, and what is still unknown. End with a send-it-soon / can-wait call.
  Asked "why an early return rather than …" about a fix, look for a step the special case shares
  with the main path: make the shared step unconditional and return after it, so the special case
  falls out and the duplicate goes. Say which edge-case behaviour moves (e.g. a guard that now also
  covers the other mode), then re-`cmp` the bench bitstreams before handing it back.
  Asked "why does it remove the assertion?": when a fix widens a failure condition ("missing"
  becomes "missing or occupied") and so replaces an invariant `NPNR_ASSERT` with a skip, recommend
  keeping the assert narrowed to the original impossible case (chipdb damage) and skipping only the
  new legitimate case, so a broken chipdb still fails loudly. Review cards check for this.
- **"The vendor bitstream fails too" / "bad silicon at this site" needs more before a decision.**
  A vendor run built from *our Yosys netlist* through the IDE's pnr is not the vendor flow; also
  run GowinSynthesis from RTL. "Unrouted" is not a known value: it reads the mux's zero-fuse
  source (for BSRAM pins, the block's own DO), so a vendor bitstream that "passes with the pin
  unrouted" may pass by luck of the test data. Pepijn wants such a result investigated before any
  fix is chosen, as three parallel investigation cards linked as parents of the design card
  (`kanban_link`, then comment + unblock it so it re-derives the cause when they finish):
  - hardware: failure *rate* per bitstream from a rerun loop, a clock sweep, write vs read,
    neighbouring sites (a varying first-bad-word between loads is not marginality by itself);
  - the vendor router's rule for pins it deliberately leaves unrouted (grep `nm -C` for
    `analysis*Bsram`/`NoNeedRoute`, not only the function the card first named);
  - what the unrouted inputs actually read.
  Before weighing fixes, measure the candidate constant at **every** site of the part, not only
  the failing one and a few neighbours: an all-sites bitstream (one DUT per site, `BEL`-pinned)
  per variant (current tie-off vs alternative, each primitive) answers "does the alternative cost
  anything anywhere" in one load. If the alternative passes everywhere and only the documented
  value fails somewhere, a constant on a don't-care pin is a cheap fix even if it departs from the
  vendor; say so rather than defending "match the vendor". Re-rank the options when the data
  moves; explain the pins first (a width → address-bit table) when he asks what they are.
  A fault on one site of the only board is still a die-vs-site question. His order: a one-off
  hand-runnable all-sites bitstream set (plain-text UART report + LED status, SRAM-only load,
  short `INSTRUCTIONS.md` and a zip) that he sends to a collaborator with a second board; only
  after their results, a normal **batched** HIL regression test for the bug (the all-sites test
  is too expensive for CI batching). Until then the fix decision waits on the implement card;
  the unrelated PR that exposed the fault waits too, unless he says otherwise.
- **Evidence technique lives in `references/fuzzer-evidence.md`:** reading diffs, ruling out
  harness/nextpnr/neighbour causes, the default-bug pair audit, draw-changing changes ship last,
  harness changes need full suites on every device, GW5A-family reach (the most frequent review
  blocker), comparing revisions, diagnosing a nextpnr unroutable arc (pre-route probe, router2
  `Failed to bind`), and proving a nextpnr change. Point design and review cards at it.
- **GW5A DSP `*_PAD=INV` means an absorbed inverter, nothing else** (`fusegenMem::setAlu48Attr`/`setAlu48PadAttr`, IDE 1.9.10.03: `hasInvertInPin`/`getPinSrcType==3`). Its fuse can share a row with the static value (CASISEL_PAD=INV and CASI_SEL=1 are both (12,37)), so `parse_attrvals` misdecodes it; read raw bits. Generator for dynamic-select vendor runs with optional `~pin`: `~/code/apicula-wt/fix-casisel-evidence/gen.py`.
- **Pinning DSP cells in vendor runs:** `INS_LOC "<inst>" R<row>C<col>[macro][A|B]` for 18-bit cells, `[A–D]` for PADD9/MULT9X9 (= Apicula idx 0–3). The fuzzer harness pins only the macro, so a residual diff with vendor-only pair-1 rows (`OR2CIB_EN1`, `OREG1`) is a slot choice, not a pack bug. Generators: `~/code/apicula-wt/fix-padd-match-evidence/gen_*.py`.
- **Gowin DSP timing: which arcs exist is a separate vendor function from their values.** Values come from `STA::*TmModel::get*PinToPinDly`; arc existence from `STA::TmAnalyzer::createTmEdgeFor<Prim>` (e.g. MultAddAlu 0x2c515f2), and the IDE's SDF still drops some edges the builder makes (MULTADDALU18X18 sign comb arcs, A0/B0 with only PIPE1_REG). Decompile both and check single-register configs against the SDF, not only all-or-nothing register sets. Unfilled vendor values show up as 0 checks without the hold adjustment.
  IDE DRCs for GW5A DSP test designs: DYN_ACC_SEL needs OREG (PA2113); DYN_C_SEL needs ADD_SUB static add (PA2114); DYN_CASI_SEL needs CASI fed by another DSP's CASO (PR1141); DYN_A_SEL needs SIA fed by SOA (PR1145); ALU54D ACCLOAD_REG alone is rejected (PA2079). Per-part limits: ≤12 MULTADDALU18X18 on GW2A-18C, ≤8 on GW1N-9C. Generators: `~/code/apicula-wt/nextpnr-gowin-dsp-timing-evidence/gen2.py`.
- **Vendor runs are local.** The IDE is at `GOWINHOME=~/bin/Gowin_V1.9.10.03_linux` and works
  natively. Its bundled `IDE/lib/libfreetype.so.6` is renamed to `.orig`: it was too old for the
  system fontconfig (`FT_Done_MM_Var`). The `LD_PRELOAD` in `codegen.run_pnr` stays: the
  `pepijndevos/apicula` image has the same mismatch (Debian fontconfig vs the bundled freetype).
  Redo the rename for a fresh IDE install. The main checkout's `.venv` has msgspec, pytest and the pinned Hypothesis.
  A worktree builds its chipdb in seconds with `make apycula/<dev>.msgpack.xz`. Cap fuzzer
  jobs at `-j 4` per card.
- **No yowasp, anywhere.** Pepijn's rule: it's bumped sporadically and often broken. Locally use
  the local Yosys and a local nextpnr build. CI's dev Yosys commit (in the CI log) is built from
  `~/code/apicula/yosys` with CMake (no Makefile any more: `cmake -B build-ci . -DCMAKE_BUILD_TYPE=Release
  && cmake --build build-ci -j6 && cmake --install build-ci --prefix ~/.local`, memory scope) into
  `~/.local/bin`, ahead of the root-owned older `/usr/local/bin/yosys` on PATH; he allows updating it.
  Match CI's commit when reproducing a CI placement; in CI the fuzzer uses the dev tools
  (see `references/ci-layout.md`). Once a nextpnr fix merges into nextpnr main, PRs waiting on it
  only need a fresh CI run (a rebase) to go green; they no longer wait on anything. The shared baseline is `~/code/apicula-wt/nextpnr-main` (detached
  origin/main, Release build in `build/`, read-only for cards). Rebuild it after his nextpnr PRs
  merge: a stale baseline reports a fixed primitive as `unsupported`. Rebuild with
  `git checkout --detach origin/main && cd build && cmake . && make -j4 nextpnr-himbaechel`. The
  `cmake .` refreshes the cached `git describe`; without it `--version` still shows the old SHA, and
  cards told to wait for the new version wait forever. Until then, verify with that
  fix's own worktree build. A nextpnr fix gets its own worktree
  and build under `~/code/apicula-wt/nextpnr-<slug>`. Never use `~/code/apicula/nextpnr`; that's his
  working branch. The cmake
  flags: `-DARCH=himbaechel -DHIMBAECHEL_UARCH=gowin -DHIMBAECHEL_GOWIN_DEVICES="GW1N-9C;GW2A-18C;GW5A-25A"
  -DCMAKE_BUILD_TYPE=Release -DBUILD_PYTHON=ON -DBUILD_GUI=OFF
  -DPython3_EXECUTABLE=~/code/apicula/apicula/.venv/bin/python3`. Build inside a `systemd-run`
  memory scope (`memory-safe-builds`). That venv has a stale non-editable apycula 0.32 in
  site-packages, so the chipdb generator imports it unless `PYTHONPATH` points at an Apicula
  checkout with built chipdbs (`~/code/apicula-wt/apicula-master`, detached at origin/master);
  set it for cmake and every generator run, or nextpnr silently gets old timing data.
- **Releases:** `gh release create <ver> -R YosysHQ/apicula --target <full sha> --generate-notes`
  (a short SHA gets HTTP 422). The tag's own `chipdb.yml` run tests before its PyPI step, so
  there is no need to wait for master CI first.
- **Yosys and nextpnr: we are outside contributors, under the [interim YosysHQ LLM policy](https://blog.yosyshq.com/p/interim-yosyshq-llm-policy/):** no LLM-generated
  code in PRs, issues with a minimal failing test case instead, and AI-assisted code only from a
  human who can defend every choice in it. Apply our own AI policy there too. Agents never open PRs or file issues in those repos, and by default
  don't commit or push either.
  - gatecat's terms (nextpnr#1881): LLM-assisted patches are fine if Pepijn has gone through
    them, understands everything, and has replaced comments with human-written ones; LLM-written
    comments are against nextpnr codebase policy, and he won't review code Pepijn hasn't. So:
    every agent-written comment in a nextpnr diff starts with `TODO: rewrite:`, and Pepijn
    rephrases each one in his own words before submitting. That's his choice over `file:line`
    lists, which made him key in line numbers. Reviews check that no agent comment is unmarked. Every nextpnr handoff is
    the full diff for his line-by-line review; nothing goes up before he has read it. PR bodies
    and commit messages are drafts he edits. An agent comment already in a PR he has submitted
    stays unless gatecat objects (his call): don't chase submitted PRs for rewrites.
  - **Hand-over format: uncommitted changes in the worktree.** He retypes and commits nextpnr
    changes himself; his retyped #1947 was merged at once, while AI-made PRs got no clear
    answer. When he asks for them:
    - check `git log -1 --format='%h %an %ar %s'` in each worktree first: he may already have
      committed one himself, so leave that worktree alone;
    - keep the agent commit as a backup branch (`git branch -f agent/<branch> HEAD`), then
      `git reset --mixed <merge-base with origin/main>`, moving onto current `origin/main` when the
      touched files are unchanged there (`git diff --quiet <base> origin/main -- <files>`);
    - give him one table: worktree path, diff size, and the `TODO: rewrite:` comments it carries.
    Asked which are "trivial vs behemoths", size them with `git diff --shortstat
    origin/main...HEAD` per worktree and recommend submitting the small self-contained ones first.
  - Exception, on his say-so: a nontrivial change (he said "the honest move" is to credit
    Claude) is committed by the coordinator in his name with `Co-Authored-By: Claude …`,
    pushed to a branch on `fork` (pepijndevos/nextpnr), and handed over as the
    `https://github.com/pepijndevos/nextpnr/pull/new/<branch>` link. He opens the PR and argues
    for the code himself. Pick a branch name that doesn't clash with his local branches in
    the shared repo (`git branch -a | grep <name>` first).
  - A simple fix: its own card prepares it uncommitted in a nextpnr worktree under
    `~/code/apicula-wt/`, builds it, and proves it with the fuzzer (baseline vs fix). It hands over
    the diff and a suggested commit message. Pepijn commits and pushes it himself.
  - A complex change: the card writes an issue draft (problem, reproducer, proposed approach) for
    Pepijn to post.
  - The Apicula chain only lists it as a follow-up.
  - Don't touch a code comment that is already correct just to add provenance ("measured
    against vendor bitstreams…"). The evidence belongs in the PR description, which the card
    drafts for him: what was measured, on which device and IDE version, and any dependency on an
    Apicula change, including whether the patch is harmless without it.
  - When a second reviewer (another session) raises gaps, check each against the card's actual
    evidence (which primitives and parameter combinations were replayed) before answering. Send
    real gaps back to the design card as concrete checks rather than asserting coverage.
  - Asked whether a sibling primitive needs the same packer fix ("doesn't DPB need it too?"),
    check every call site of the helper (`grep -n <helper> pack_*.cc`). Compare each pin
    argument against the primitive's port list **per family** in Yosys
    (`/usr/local/share/yosys/gowin/cells_xtra_gw1n.v`, `_gw2a.v`, `_gw5a.v`; SP/SPX9 are in
    `cells_sim.v`). Ports differ per family: SDPB has RESETA/RESETB on GW1N/GW2A and a single
    RESET on GW5A. Answer with the call site and the port list, then point to related open
    hardware faults (the apicula issue the HIL `*-bugs` tests name) as the possible next chain.
  - Keep an upstream patch in the file's existing pattern, even when a refactor looks nicer
    (for example folding a per-call-site condition into a helper). A one-liner that matches the
    neighbouring calls is easier for the maintainers to accept. Mention the refactor as something he
    could send separately. Before calling a condition foldable, check whether it differs per call site.

## Support files

- `scripts/xfail_summary.py`: turns a `gh run view --log` dump of the fuzzer workflow
  into a per-primitive summary, or prints full blocks with `--show`.
- `templates/burndown-stages.md`: the canonical shared stage instructions. Copy it to
  `~/code/apicula-wt/BURNDOWN-STAGES.md` when that file is missing or stale.
- `templates/nextpnr-stages.md`: stage instructions for full nextpnr chains (agent comments
  only with a `TODO: rewrite:` marker, local commits only, timing evidence or the
  bug-fix-chain overrides). Copy it to `~/code/apicula-wt/NEXTPNR-STAGES.md`.
- `templates/timing-stages.md`: stage instructions for timing-data chains (tm_parser /
  chipdb_builder work checked against the IDE's SDF with `tools/timing/`, no fuzzer or
  `BROKEN`). Copy it to `~/code/apicula-wt/TIMING-STAGES.md`.
- `references/ci-layout.md`: which CI job needs the IDE or the tools, where each runs, and
  Pepijn's rules for changing that layout. Read it before touching the workflows.
- `references/fuzzer-evidence.md`: root-causing a mismatch and proving a fix (defaults, draws,
  harness pins, GW5A-family reach, revision compares, nextpnr crashes on omitted parameters,
  nextpnr baseline vs fix, and checking the draws hit the trigger / writing a direct reproducer).
- `references/pr-coordination.md`: stacking, the merge-order report, the rebase train, and landing
  (`gh stack merge`, conflict resolution, stale-parent check).
