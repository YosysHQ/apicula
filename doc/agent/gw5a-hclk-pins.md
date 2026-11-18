# GW5A-25A: clock pins that feed HCLK through a pair IOB

On GW5A-25A some `GCLKT_nB` pins reach an HCLK block without general routing.
The vendor enables the clock input of the pin's pair IOB (`GCLKT_nA`) with
`INCKSELMUX=INCK_II`, and the clock enters the HCLK's `HCLK_GCLK` wire. This
note records the four bottom/right pins Apicula describes, where the data comes
from, and what is still missing. IDE 1.9.10.03 throughout.

## The pins

Checked against vendor bitstreams: a `CLKDIV` and a `CLKDIV2` fed straight from
the pin, HCLK pips decoded from the vendor output.

| pin (IOB, function) | MG121N / UG324 / PG256C / LQ144 | HCLK | `HCLK_GCLK` (raw) | path into the HCLK mux | pair IOB |
|---|---|---|---|---|---|
| X11Y36 `GCLKT_10B` | E2 / R5 / C6 / 6 | 1 | `HCLK_GCLK11` (311) | → ε10, fuse (30,75) | X30Y36 `GCLKT_10A` |
| X25Y36 `GCLKT_9B` | F2 / M10 / B3 / – | 1 | `HCLK_GCLK14` (314) | → ε14 and → ε17, **no fuse** | X32Y36 `GCLKT_9A` |
| X53Y36 `GCLKT_11B` | D5 / T14 / G2 / 23 | 1 | `HCLK_GCLK15` (315) | → ε14 fuse (31,23); → ε17 fuse (31,102) | X28Y36 `GCLKT_11A` |
| X74Y36 `GCLKT_6B` | – / N15 / L2 / 34 | 3 | `HCLK_GCLK35` (689) | → ε34 fuse (8,124); → ε37 fuse (9,133) | X90Y36 `GCLKT_6A` |

- The HCLK1 mux is at (36,27), HCLK3 at (35,91). In Apicula the pin's IOB wire
  `F5` joins the `HCLK_GCLK` wire (`chipdb.gw5_make_pin_to_hclk`); the pairs are
  `GW5A_25A.hclk_io_pairs` in `gowin_pack.py`.
- F2's path has no fuse: F2 and D5 bitstreams differ at (36,27) only in
  (31,23), and fse table 48 has no `HCLK_GCLKx0`/`x4` rows.

## Where the vendor defines them (read from code)

- `NETLIST::Hclk_5AT::buildGclkIO_5A25 @0x1a82dba` adds, per HCLK, eight edges
  `setDibNodeEdge(row, col, wire, node)` into the HCLK nodes `0x7b..0x82`
  (1-based row/col). For HCLK1 (bottom, row 37):

  | node | 0x7b | 0x7c | 0x7d | 0x7e | 0x7f | 0x80 | 0x81 | 0x82 |
  |---|---|---|---|---|---|---|---|---|
  | source | C35 F5 | C31 F5 | C36 Q6 | C32 Q6 | C33 F5 | C29 F5 | C34 Q6 | C30 Q6 |

  HCLK3 (right): 0x7b R31C92 F5, 0x7d R32C92 Q6, 0x7f R33C92 F5, 0x81 R34C92 Q6,
  0x7c R37C89 F5, 0x7e R37C90 Q6, 0x80 R37C91 F5, 0x82 R37C92 Q6. HCLK0 (top)
  and HCLK2 (left) have their own eight edges.
- Node `0x7b + k` of HCLK `h` is Apicula's raw HCLK wire `123 + k + 187·h`
  (`HCLK_GCLK{h}{k}`). Checked against data: the four measured wires above are
  exactly the nodes whose `F5` source is the pair IOB's cell (X30→0x7c→311,
  X32→0x7f→314, X28→0x80→315, X90 on HCLK3→0x80→689). So `HCLK_GCLK14` is the
  vendor's node 0x7f of HCLK1, not an inferred name.
- The vendor graph starts these edges at the **pair** cell's `F5`; Apicula
  starts them at the pin's `F5`, which is what nextpnr needs to route from the
  pin. Same fuses either way.
- `PLACEROUTE::Route::configIoAttrFor25 @0x2531c1c`: for a routed net whose
  source is a GCLK IO buffer and whose used edge enters a GCLK IO node owned by
  a *different* buffer, it sets `INCKSELMUX=INCK_II` on that other buffer (the
  pair) and `INCKSELMUX=DISELMUX` on the source (unless the source's logic
  instance type is 0x79, 0x7c, 0x7d or 0x81). It sets nothing else on the
  pair, and does not look at whether the pair is used.
  `setGclkAAtrrOfSameNumberGclkForGW5A @0x319049d` sets the same
  `INCK_II` through the B→A map of `setSameNumberGclkMapForGW5A25K @0x2017c39`.
- Not derivable from the `.dat`/`.fse` files: the table lives in code. Apicula
  keeps a hand-written table of the measured rows.

## The pair IOB

Checked against data: an unused pair IOB is the unused-IOB configuration plus
`IOB_UNKNOWN67=INCK_II` (Apicula's name for `INCKSELMUX`), nothing else. Three
bottom pairs on MG121N (unbonded) and UG324 (bonded) differ from their unused
state in (31,78)/(31,79) only. Before the fix that accompanies this note,
Apicula packed the pair as a used input carrying the clock cell's attributes,
which set extra fuses (E2's pair at
(36,30): (30,50), (30,68), (30,77)).

Unmeasured: a pair IOB that the design also uses as an I/O. The code reading
above suggests it keeps its own attributes and gains `INCK_II`; Apicula leaves a
used pair as it is, without `INCK_II`.

## Not covered

- The other `buildGclkIO_5A25` sources (X34 `F5`, the `Q6` edges, HCLK0 and
  HCLK2) have no pin or pair in `hclk_io_pairs`; not measured.
- GW5AT-60B and GW5AST-138C have no pin rows and no pairs
  (`buildGclkIO_5AT60` exists; nothing for 138C was traced). `hclknames_60b`
  carries the same EPSILON index typo that `hclknames_5a25a` had.
