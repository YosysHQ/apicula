# PR coordination: stacks, merge order, rebases

Read this when stacking chains, reporting what's open, or getting PRs ready to merge.

## Stacking
- **Follow-ups that touch the same code as a running chain are stacked on it.**
  - Branch the worktree from `origin/master`, and give the implement card two parents: its design and the parent chain's review card.
  - The stage file's "Stacked chains" section tells the implementer to rebase on the parent branch (or on master once merged), and the reviewer to review only the branch's own commits.
  - Design cards run right away.
- **Stacked PRs target their parent's branch** (`gh pr create --base fix/fuzz-<parent>`; retarget existing ones with `gh pr edit <n> --base ...`), so GitHub shows only their own commits. A dependent PR found based on master with its parent's commits inside: `gh stack link <parent#> <child#>` retargets the base and creates the native stack in one step (AGENTS.md requires real stacks). CI still runs, because `chipdb.yml` triggers on any `pull_request`. Native stacks retarget the child to master when its parent merges (see Landing, steps 2–3).
- **Native GitHub stacks are linear chains, and a PR belongs to one stack only.** Retargeting bases is not enough for the stack UI: link each chain with `gh stack link --base master <bottom> ... <top>` (extension `github/gh-stack`, PR numbers bottom→top; it refuses an update that would drop a PR already in the stack, so list them all). A parent with several stacked children can only stack one of them down to master, so the UI offers a stack that stops short. Fix it by linearising the siblings into one chain:
  - check each pair first with `git merge-tree --write-tree origin/<a> origin/<b>`;
  - the coordinator does clean rebases itself (rebase-train recipe, `--onto` the new parent), then retargets the base;
  - a sibling that conflicts gets a restack card that resolves the conflict, measures any behaviour the resolution adds, and hands back the force-push, followed by a short re-review. Put the conflicting one on top.
- When two chains change the same function (e.g. the input side and the output side of one rule), stack one on the other. Give each card an ownership comment saying which half is its own, so the rebase stays clean.
- **On REQUEST_CHANGES to a parent:**
  - park any stacked implement card (`hermes kanban assign <id> none`);
  - link the parent's next review round as an extra parent;
  - reassign it.
  - A stacked card that's already running can't be parked (`assign` refuses a claimed card). Comment on it to rebase onto the reworked parent before pushing. If it publishes first anyway, add a rebase card gated on the parent's re-review, and put the child's review behind it.

## Merge-order report
- **"Look at the status of all PRs" / "recall what they were about":** list them with `gh pr list` (checks grouped by conclusion), check master's own failing jobs first so shared reds aren't blamed on PRs, then fan out one read-only `delegate_task` child per PR with `option="review"` (worktree path, AGENTS.md test rule, no pushes or HIL). Condense their reports to one line of status + one next action per PR, grouped merged / holds up / needs fixing.
- **When he asks what's open,** list the PRs in tiers:
  1. CI changes first, since the others' CI depends on them;
  2. approved independent roots;
  3. the stacked ones, each with its parent and any nextpnr PR it waits on;
  4. work still on the board.
- Remind him that all of them are drafts. Check each nextpnr PR's state (`gh pr view <n> -R YosysHQ/nextpnr --json state`) before calling anything "waiting on nextpnr".
- **"Ready to merge"** means reviewed, rebased onto current master, and CI green. After a CI-layout PR merges, PRs opened before it carry stale CI evidence and need the rebase train before they count as ready.
- **"Merge if no conflicts"** covers the conflicts a squash-merged stack creates by itself (see Landing step 3); stop only on a conflict where both sides changed the same lines.
- **"Merge once it passes"**: start one background watcher (`terminal(background=True, notify=True)`) that waits ~60 s for the checks to exist, runs `gh pr checks <n> --watch`, then merges only if every failing check is on an explicit known-red list (master's own reds, e.g. the stable 60K example) **and** the HIL job of each board the PR touches passed. Otherwise it prints the failures and stops. A red outside the list never gets merged over silently: triage it (`fpga-hardware-in-the-loop`, step 1) and report before merging.
- Report readiness to him once, as one merge-order list, when the whole set is there.
- **While converging, report a "path to merge" table**: one row per stack (PRs as linked titles), and in the
  second column the concrete steps still left ("claims rework finishing, then review", "body fix + re-review",
  "approved; merge last"). Under it, the single open question that blocks a merge, and a line listing what's parked.

## Rebase train (coordinator only; workers can't force-push)
Rebase every open stack in one go, after a CI-layout merge or before the merge report. All cards on those branches must be idle.
1. Make a detached scratch worktree: `git worktree add --detach $TMPDIR/rebase-train origin/master`. The real branches are checked out in card worktrees, so `--update-refs` can't move them.
2. Create a `tmp-<slug>` branch at each `origin/fix/fuzz-<slug>`.
3. Rebase each linear chain with `git rebase --update-refs origin/master tmp-<tip>`, which carries the intermediate tmp branches along. For siblings stacked on a rebased parent, use `git rebase --onto tmp-<parent> <old parent sha> tmp-<child>`.
4. Check each tip:
   - `git rev-list --count origin/master..tmp-<slug>` gives the expected own-commit count;
   - `git range-diff` shows only master's new commits;
   - the unit tests pass.
5. Push once, atomically: `git push --atomic origin --force-with-lease=fix/fuzz-<slug>:<old sha> tmp-<slug>:refs/heads/fix/fuzz-<slug> ...`.
6. `git -C <card worktree> reset --hard origin/<branch>` in each clean card worktree. Then remove the scratch worktree and the tmp branches.
7. Expect a long queue. Each PR's CI is about 30 jobs, and the org's concurrency cap queues the rest, so ten PRs take hours. Cancel runs on superseded heads after any later push (`gh run list -b <branch> -s queued` → `gh run cancel`). If he wants merges sooner, offer to cancel the stacked children's runs, since they rerun after their parent merges anyway.
8. Start one background watcher (`terminal(background=True, notify=True)`) that loops over `gh pr checks <n>` until nothing is pending, then prints the non-passing checks per PR. Don't poll by hand.
9. **Triage red checks before the merge report.** For each failing job, ask two questions. Does master fail the same job (`gh run list -b master`)? Then it's not the PR's. Is it an example job that died in routing? Read the log.
   - `gh run view --log-failed` often dies with a stream error. Fetch the job log instead: `gh api --allow-escape-sequences repos/YosysHQ/apicula/actions/jobs/<job-id>/logs > f`, strip escape codes with `sed 's/\x1b\[[0-9;]*m//g'`, then grep `ERROR:|make: \*\*\*`.
   - "Routing design failed" on a `dsp-*` example in a PR that doesn't touch DSP is the Makefile's `-r` random-seed flake. Rerun only the failed jobs (`gh run rerun <run> --failed`). Report it as "rerun pending" until the rerun is green, and track the flake in the backlog.
   - A fuzz job that fails only on reds another open PR fixes clears with the rebase after that PR merges. Say so; don't call the PR red.

**Rebasing one PR while its review card runs:** do it in a scratch worktree (`git worktree add $TMPDIR/<x> -b tmp/<x> origin/<branch>`), not in the card's worktree, so the reviewer's builds and bench runs aren't pulled from under it. Push with `--force-with-lease=<branch>:<old sha>`, remove the scratch tree, and comment on the review card: new head, what changed ("only the test-file merge"), and `git fetch && git reset --hard origin/<branch>` before it checks the final head.

**Two chains that each create the same new file** (e.g. `tests/test_dsp.py`) conflict as add/add when the first merges. Resolve as a union: one import block, both test classes, then run that test file. Spot it when cutting parallel chains from the same master, and tell him which one will conflict.

**An upstream dependency that lands as different commits** (he retypes a nextpnr PR by hand; GitHub then shows it closed, not merged): confirm on `origin/main` with `git log origin/main -S'<distinctive line>' -- <file>`. Rebase each local branch stacked on it and `git rebase --skip` the superseded commit when it conflicts. Update the branch line in its `-PR.md` draft ("on main", not "stacked on #N") and in `BACKLOG.md`. Rerun the full CI of Apicula PRs that waited on it with `gh run rerun <id>` (all jobs, so the dev toolchain rebuilds from the new main; `--failed` alone reuses the old tools artifact).

A single PR rebased by a worker: the worker verifies locally and blocks with the exact `git push --force-with-lease=<branch>:<old-sha> origin <branch>` command, plus any body file. The coordinator checks `git log`, runs the command, comments the new head, and unblocks the card.

## Landing (when he says "land everything")
He marks the PRs ready and wants the coordinator to sit through the conflicts. Merge first, measure once at the end: don't compute a per-PR suite summary beforehand, it's double work.
1. **Re-read the state each step.** `git fetch` and `git log origin/master` before every merge: he may have merged some stacks himself, and GitHub's "Rebase stack" may have moved heads. Squash is the repo's method.
2. **Merge native-stack members with `gh stack merge <stack#> --yes --squash`,** or one PR at a time with `gh api -X PUT repos/YosysHQ/apicula/pulls/<n>/merge-async -f merge_method=squash -H "X-GitHub-Api-Version: 2026-03-10"`, polling `gh pr view <n> --json state` until MERGED. `gh pr merge` and the plain REST `PUT pulls/<n>/merge` refuse a PR in a stack ("must be merged using the asynchronous merge"). A standalone PR still uses `gh pr merge <n> --squash`. Merge a stack as a whole when a lower PR alone regresses something an upper one restores. GitHub retargets the next PR to master after each merge and rebases linear branches itself; check that each one's diff against master equals its old diff against its old base before merging it.
3. **Rebase each stack onto the new master in a detached scratch worktree** with `land-<slug>` branches (rebase-train recipe). **Before rebasing, check that each child contains its parent's current head** (`git merge-base --is-ancestor origin/<parent> origin/<child>`). A child that was branched before the parent got a late fix commit drops that commit silently under `--update-refs`. Rebuild such a top by cherry-picking the parent's own commits (`git cherry-pick origin/<grandparent>..origin/<parent>`), then the child's own commits.
   **A branch that contains a merge commit** shows CONFLICTING once its parent is squashed, and a rebase replays that merge's already-resolved conflicts. Merge `origin/master` into it instead. For each conflicted file, `git diff --quiet <old parent head> origin/master -- <file>`: unchanged on master since the parent means `git checkout --ours`. Then confirm the PR's diff against master has the same `--stat` as before and push normally (a fast-forward).
4. **Resolve `BROKEN` and doc conflicts by intent, not by side.** Master's reasons are the newer truth for primitives other PRs fixed. Keep only the PR's own additions (new entries, its narrowing), and drop entries master already removed. Later commits in the same rebase may edit the same lines, so after the rebase, grep the tip for conflict markers and diff `tests/test_fuzz.py` against master to read the final reasons whole. Pure list or doc conflicts (two bullet sets) are usually a union.
5. **Verify locally, then push and merge without waiting for the full CI queue:** unittest plus a targeted fuzzer run of the primitives whose entries changed, on each touched device. A fresh scratch worktree has no chipdb: symlink `~/code/apicula/apicula/apycula/*.msgpack.xz` into it (fine for unchanged chipdb code), or `make apycula/<dev>.msgpack.xz`. Push all branches of the stack in one `git push --atomic --force-with-lease=...`.
6. **The draw-changing PRs go last, and the last one waits for its CI.** Its `BROKEN` triage predates the other merges, and its CI fuzz on all three devices is also the "after" measurement.
   - Before waiting, cancel every queued run on branches that already merged (`gh run list -L 40 --json databaseId,headBranch,status` → `gh run cancel`). Each rebase push started a full run, and they starve the one run that matters.
   - The watcher must wait for the fuzz jobs to **exist** before testing "none pending": right after a push only `build` is listed, so a naive "no pending fuzz job" loop exits at once. Loop until `gh pr checks` lists all three `dev / fuzz` jobs and none is pending, or `build`/`build-tools` failed.
   - A "fixed by <other PR>" claim in its body is unproven until that PR has merged and this CI ran on top. Read every red in the job log; a new failure gets a `BROKEN` entry stating what the diff shows (marked inferred where it is), as a coordinator commit with a Collaborative Work Statement. A `BROKEN`-only change doesn't alter the draws, so merge it without another full run.
   - It may have drifted back to draft: `gh pr ready <n>` before `gh pr merge`.
7. **Then report the movement once**, from the CI fuzz-job summary lines (`N passed, M skipped, K xfailed` per device), against the baseline from the last master run before landing.
8. **Scratch worktrees and the shell's cwd:** removing a worktree the terminal session sits in makes every later command fail before it runs. Pass `workdir=` on terminal calls into scratch trees, and remove a tree only from outside it.
