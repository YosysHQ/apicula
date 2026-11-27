# Gowin logic tile: LUT / FF / MUX / SEL connectivity

Read this when reasoning about packing or placement constraints, or when drawing the tile.
The source of truth is the generator (`create_logic_tiletype` and the node builders in
`himbaechel/uarch/gowin/gowin_arch_gen.py`) plus the apicula chipdb pip lists
(`chipdb.load_chipdb(...).tiles[db.grid[r][c]].pips[dst]`). Check claims there before you
state or draw them; counts below are GW2A-18C, and GW1N-9C/GW5A-25A matched.

## Per slice i (LUT i + DFF i)

- LUT4 i: inputs A_i..D_i, each fed by its own 28:1 routing mux (3 X0 sources, the rest X1/X2
  taps and a few F/Q of the same tile). Output F_i.
- DFF i: D pin is the wire XD_i. The only fabric pip into XD_i is F_i (dedicated, ~0 ps).
  So an FF whose D is not its own LUT's output needs that LUT: after placement,
  `create_passthrough_luts` (in `postPlace`) puts a pass-through LUT4 into an empty LUT slot.
  6 FFs per tile on GW1N/GW2A, 8 when the chip has `HAS_DFF67` (GW5A).
- CLK/CE/LSR are shared per FF pair (CLK0..2, CE0..2, LSR0..2), so adjacent FFs need
  matching control sets.
- ALU i (i < 6) shares the LUT site and drives F_i; CIN/COUT chain between tiles.

## SEL wires and the wide-LUT mux tree

- SEL_i is a 9:1 routing mux: 4 X0 + 4 X2 taps + VCC (SEL3/SEL7 differ slightly). It is the
  select input of MUX i.
- Mux tree: MUX0/2/4/6 = MUX2_LUT5 (data: F pairs), MUX1/5 = MUX2_LUT6 (OF0+OF2, OF4+OF6),
  MUX3 = MUX2_LUT7 (OF1+OF5), MUX7 = MUX2_LUT8 (OF3 + OF30). OF30 is a node to OF3 of the
  tile to the east (x+1).
- A 2:1 sits in front of each DFF: D = F_i by default, D = SEL_i when fuse `REGi_SD` is set
  (gowin_unpack decodes `REG{idx%2}_SD` as "D from SEL{idx}"; not vendor-verified). The 9:1
  SEL mux exists either way; the fuse only switches the DFF's 2:1. nextpnr's wire XD_i is that
  2:1's output. With SEL->XD the FF can share a slice with an unrelated LUT, but only while
  MUX i is unused. The routing cost is SEL *access* (9 sources, X2 taps from one axis only),
  not X0 overload: total X0 pips went down while pips into SEL doubled. ECP5's equivalent
  (M -> DI) has a full input mux, so the same packing freedom is cheap there.
- The timing model gives LUT_IN, SEL and DI pips 0 ps, so the router sees SEL as free.

## Drawing it

For the repo, write **Mermaid in a `doc/agent/*.md` page** (GitHub renders it; verify the
rendered page in a browser before reporting) and link it from `doc/agent/README.md`; that
is where he wants hardware diagrams, not PNGs in `doc/fig`. Draw every selector mux as
its own node labelled with just the fuse name (`REGi_SD`), not a sentence; define
non-obvious nextpnr wire names (XD_i) in the text; label optional paths on the edge
instead of encoding meaning only in dash style or colour. A per-index source table
(SEL0..7) beats a single "9 sources" claim when indices differ.

For a quick look in chat, use Graphviz (`dot`). Write `.dot` with `rankdir=LR`, clusters for "general routing" and
"slice i", trapezium nodes for the routing muxes labelled with their source counts, and the
optional/experimental path dashed and coloured. Render with `dot -Tpng -Gdpi=110 x.dot -o x.png`
(plus `-Tsvg`), look at the PNG for overlapping labels (use `xlabel` on edges that cross a
cluster border), and deliver via `MEDIA:` with the `.dot` kept next to it.
