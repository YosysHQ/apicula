# Apicula timing data: stage instructions

**Read your card's comment thread before starting (`kanban_show`).** Coordinator comments carry Pepijn's later decisions and override the card body and this file. Say in your completion summary which ones you applied.

Each item is a chain of three kanban cards sharing one worktree: design → implement → review. The card body names the worktree, the branch and the gap. The goal of the whole batch: Apicula exports the timing data that nextpnr needs to close nextpnr#1906 (DSP timing) and nextpnr#1907 (GW5A routing delays), then a release ships it.

## Environment and rules

`~/code/apicula-wt/BURNDOWN-STAGES.md` applies, with these exceptions:
- **Sections that apply as they stand:** "Environment", "Stacked chains", stage 1's "Deliverable, then halt", and stage 3's "How". Leave out the fuzzer and `BROKEN` items: timing data isn't fuzzed.
- **Vendor code:** read `doc/agent/timing.md` first. It holds what is already known about `STA::TmModel`, `STA::TmModelNew` and the X-wire crossings, with addresses (IDE 1.9.10.03). Extend it rather than starting a new file. Ghidra project: `~/code/apicula-wt/ghidra-libgowin`.
- **Evidence is the IDE's own SDF:** build a design with the IDE, then compare per connection with `tools/timing/` (`routes.py`, `npnr_eval.py`, `compare.py`; see `timing.md`). Report total and median ratio, before and after. Keep vendor runs to one at a time per card: other cards run them too.
- **Mark every claim** as code (read from the vendor), data (checked against the SDF or `.tm`) or inferred.
- **nextpnr:** cards never commit to nextpnr. If checking the data needs a nextpnr change, prototype it uncommitted in the card's own `~/code/apicula-wt/nextpnr-<slug>` worktree and list the hunk in the completion summary. The coordinator carries it into the nextpnr PR.
- **Apicula release:** don't bump versions or tag. The coordinator does the release after the batch merges.

# Stage 1: design
Answer the card's questions with code addresses. Then post one package comment:
- findings, each marked code, data or inferred;
- the recommended design: what changes in `tm_parser` / `chipdb_builder`, and the shape of the exported group, so the nextpnr side can read it;
- one alternative;
- the test plan: which IDE designs, which comparison, and what number counts as done;
- the size, trivial or substantial.

Block once with `needs_input`, as in BURNDOWN-STAGES.

# Stage 2: implement
Implement the approved design, then:
1. **Regression test:** a unit test in `tests/` that loads the built chipdb and checks values you read by hand from the `.tm`/`.dat` or found in the IDE's SDF, so a parser offset error fails it. It must fail on master. Never pin the chipdb's own current output (a change-detector test, AGENTS.md Testing rule 1). If nothing has a vendor reference, write no test and say so in the PR.
2. **SDF comparison** on each device the card names, with real output.
3. **Unchanged output elsewhere:** `tools/chipdb_compare.py` (or a `cmp` of the msgpacks) for GW1N-9C and GW2A-18C shows no change, unless the design says otherwise.
4. `python -m unittest discover tests` passes.
5. Commit with a Collaborative Work Statement, push the branch to `origin` and open a **draft** PR. The body states what was run and which nextpnr issue the data is for, as `YosysHQ/nextpnr#1906` or `#1907`.
6. `kanban_complete` with the PR URL, the head SHA and the nextpnr prototype hunk, if any.

# Stage 3: review
As in BURNDOWN-STAGES stage 3, with these acceptance criteria:
- the parser reads the vendor format as `timing.md` documents it, with addresses cited;
- the regression test would catch an offset error;
- the SDF comparison numbers in the PR body reproduce on one device;
- GW1N/GW2A chipdbs are unchanged, unless the design said otherwise;
- the change is minimal, and the code is simple.
