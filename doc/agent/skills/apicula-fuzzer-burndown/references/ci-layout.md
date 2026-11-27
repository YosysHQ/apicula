# Apicula CI layout and how to change it

## What each job needs

| Workflow / job | Needs the IDE? | Needs Yosys/nextpnr? | Produces |
|---|---|---|---|
| `chipdb.yml` build | the device data only, inside `docker run pepijndevos/apicula:<GWVERSION> make` | no | `python-dist` wheel with the chipdbs; PyPI; oss-cad-suite data |
| `toolchain.yml` build-tools (dev, stable) | no | builds them; nextpnr's chipdb comes from the wheel | `tools-<name>` |
| example (dev, stable × boards) | no | `tools-*` + wheel | bitstreams |
| hil | no | no (self-hosted runner, bitstreams only) | board UART diffs |
| fuzz (dev only) | runs `gw_sh`; reads `IDE/bin/primitive.xml` and `prim_syns/gw5a/primitive.xml` at runtime | `tools-dev` + wheel | fuzz reports |
| `docker-build.yml` | builds the image (downloads the IDE) | no | the apicula image |

The fuzz job is the only one that needs vendor execution together with our tools. Its chipdb
comes from the wheel; rebuilding it with the IDE is unnecessary.

## Pepijn's rules for this layout

- **One build environment for every job that needs the tools.** `build-tools`, `example` and
  `fuzz` run with `container: pepijndevos/apicula:<GWVERSION>` (Debian `python:3` base), with
  build deps apt-installed there. Tools built on `ubuntu-latest` don't run inside the image
  (newer glibc and Boost), so mixing host-built tools with the image breaks.
- **Never copy the IDE out of the image** to run it on the host, and don't wrap vendor calls in a
  `docker run` shim when a `container:` job can hold everything.
- **The `LD_PRELOAD` of the IDE's `libfontconfig` in `codegen.Pnr.run_pnr` stays for now.** It is a
  CI fix from upstream history, not a one-machine hack. The IDE's bundled `IDE/lib/libfreetype.so.6`
  is older than the image's Debian `libfontconfig` (`undefined symbol: FT_Done_MM_Var`), so `gw_sh`
  needs it inside the image too, including the chipdb build's SDRAM pin discovery. Removing it
  takes a Dockerfile change first, renaming the bundled freetype. That has to be a separate PR
  merged before the preload goes, because `docker-build.yml` only pushes the image on master, so a
  PR can't test against a rebuilt image. Check `git log -S` for a workaround's origin before
  calling it machine-specific.
- Running example jobs inside the image changes their meaning: the image preinstalls numpy,
  fastcrc and msgspec, so the `pure: true` job has to uninstall them, or it tests nothing.
- **No yowasp in the fuzzer path.** Dev nextpnr passing is the bar.
- A CI PR is verified by its own CI run: fuzz counts identical to master's on every device,
  examples and hil as green as master. A job that also fails on master is noted, not fixed.
- **`hil` needs the whole `example` matrix of its toolchain**, so one red example skips that
  toolchain's HIL on every board. The stable toolchain's 60K example fails on a missing chipdb, so
  `stable / hil` is skipped on every run, master included. He chose to leave stable CI alone: don't
  propose fixing it unasked; judge HIL by `dev / hil`, and say "stable skipped as on master".

## How to propose a CI change

Start with a job table like the one above (runs on, needs IDE, needs tools, produces), and point
out which job is the odd one out before proposing anything. He decides on the map, and asks why a
step needs what it needs; a proposal without the map gets questioned step by step.
