# Reverse engineering the IDE: tools

How to get answers out of the IDE cheaply. The rules (supported version, static
analysis first, no modifying the IDE) are in [`AGENTS.md`](../../AGENTS.md).

## `libgowin.so`

`IDE/lib/libgowin.so` holds place and route and bitstream generation. It is
**not stripped** and is built at **-O0**, so symbol names and very regular code
are available.

Pick the cheapest tool that answers the question:

1. `nm -DC` for names. Most of what you want is named; start with `fusegenMem::`.
2. `objdump -d -C --start-address --stop-address` for single functions.
   `nm -S` gives the address and size. -O0 disassembly is easy to follow.
3. Python over `objdump` output for anything repeated. Jump tables are
   `cmp; ja; lea table(%rip); movslq; add; jmp *%rax`, with 32-bit offsets
   relative to the table.
4. `tools/gowin_decompile.py` for real decompilation. It needs no full analysis
   and takes seconds. REA's full analysis of this library takes hours, treats
   `__dynamic_cast` as noreturn and truncates functions such as `setClsRegAttr`.

## Generated files

`apycula/fse_formats.py` is committed, so extraction only needs re-running for a
new IDE version. Do not edit it by hand. Vendor enums are not committed; generate
them when updating `apycula/attrids.py`.

## Tools in `tools/`

| Tool | Purpose |
|---|---|
| `gowin_extract.py extract` | Generates `apycula/fse_formats.py` and writes vendor enums to a local `enums.json` |
| `gowin_extract.py check-attrids` | Compares `apycula/attrids.py` with vendor names |
| `gowin_attr_sites.py` | Lists attribute assignments with approximate guards; research aid, output not committed |
| `gowin_decompile.py` | Decompiles named functions with Ghidra, applying Gowin enums, parameter structs and signatures; no full analysis needed |
| `chipdb_compare.py` | Content comparison of chipdb directories |
| `timing/` | Timing research: list old `.tm` record fields from the getters, parse the GW5A `.tm` block, rebuild IDE routes from its bitstream, compare IDE, reimplemented vendor and nextpnr delays. See [timing.md](timing.md) |
