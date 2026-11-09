# Agent notes

How to work on Apicula, and how to reverse engineer the Gowin IDE without
rederiving it each session. Findings about the vendor code and data files live in
[`doc/agent/`](doc/agent/README.md). Add to them when you learn something new.

## Environment

- The supported IDE version is the one in the `GWVERSION` file, currently
  **1.9.10.03**. Only analyse that version. Enums, table types and layouts change
  between releases, and other releases are not supported.
- Set `GOWINHOME` to the install root, the directory containing `IDE/`.
- Use `.venv` for builds: `PATH=$PWD/.venv/bin:$PATH make -j4`. The chipdb build
  fails on a Python without `msgspec`.

## Checking a chipdb change

Back up `apycula/*.msgpack.xz`, rebuild, then compare by content:

    PYTHONPATH=. python3 tools/chipdb_compare.py BACKUP_DIR apycula

Rebuilt files never match byte for byte, because sets serialize in a different
order on each run. A raw msgpack comparison shows thousands of false differences.

## Reverse engineering the IDE

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
4. Ghidra or REA for real decompilation. `open_binary` is instant, but the first
   query starts a full analysis of this 78 MB library, which had not finished
   after about an hour. Do not make that a blocking step.

Prefer static analysis over running vendor binaries. Do not modify the IDE or
work around its licensing.

Generated data is committed, so extraction only needs re-running for a new IDE
version:

| Tool | Purpose |
|---|---|
| `tools/gowin_extract.py extract` | Enums, table types, device layouts into `tools/gowin_extract_out/` |
| `tools/gowin_extract.py gen-formats` | Generates `apycula/fse_formats.py` from those outputs |
| `tools/gowin_extract.py check-attrids` | Compares `apycula/attrids.py` with vendor names |
| `tools/gowin_attr_sites.py` | Lists attribute assignments with approximate guards; research aid, output not committed |
| `tools/chipdb_compare.py` | Content comparison of chipdb directories |

Do not edit `apycula/fse_formats.py` by hand.

## Separating evidence from inference

When writing findings, say what was read from code, what was checked against
data, and what is inferred. Name the IDE version for any address. Name the
primitives or tables you actually traced, rather than generalising from one.
