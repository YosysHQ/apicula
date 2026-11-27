# Sipeed onboard debugger (bridge MCU) firmware

The JTAG + UART path on Sipeed Tang boards is an MCU that emulates a programmer. Its
firmware, not the FPGA, is the usual reliability problem for HIL.

| Board | Bridge MCU | Firmware in use | USB identity |
|---|---|---|---|
| tangnano20k | BL616 | user's `~/code/bl616_dirtyjtag` (DirtyJTAG + CDC-ACM, baud hardcoded) | `1209:c0ca`, UART on `/dev/serial/by-id/usb-DirtyJTAG_DirtyJTAG_<serial>-if01` (ttyACM) |
| tangnano9k (and nano 1k/4k, primer20k) | BL702 | stock: emulates FT2232D; the 9K in apicula's HIL runs the same repo's BL702 target (full `hil-tangnano9k` 10/10, 20/20 load+capture soak); it replaced the tec0117 (dead FTDI) as the GW1N-9 HIL board, YosysHQ/apicula#609 | stock: `0403:6010` "SIPEED JTAG Debugger", JTAG = if00, UART = `…FactoryAIOT_Pro-if01-port0` (ttyUSB); DirtyJTAG: `1209:c0ca` like the 20K |

**USB serial = the chip's factory MAC** (`bflb_efuse_get_chipid()`, 12 hex chars, same code
on BL616 and BL702), so every board gets its own by-id path with no per-board build
option. Leading zeros are real MAC bytes (the 9K reads `000054f5634c` from efuse 0x14),
not a truncation — check the efuse dump before "fixing" the formatting. Older images report `0200`; the HIL Makefile's hardcoded
`usb-DirtyJTAG_DirtyJTAG_0200-if01` path must be updated whenever a board is reflashed —
read the real path from `ls /dev/serial/by-id/` after the replug.

## Getting custom firmware onto the chip

- **BL616:** the boot ROM only runs encrypted, Sipeed-signed firmware at flash 0x0. Custom
  firmware loads through a Sipeed-made signed bootloader that jumps to 0x20000; it is
  board/crystal specific, so each board type needs its own from Sipeed (the "BL616
  reliability" email thread, Proton index search `sipeed`).
- **BL702 (verified on a 9K: ISP entry, fuse read, unsigned custom firmware at 0x0 boots
  and enumerates):** no signing wall — efuse config word 0 reads `0` (no AES/signature boot) and the
  key area is empty. The boot strap (GPIO28, QFN32 pin 31, 10 kΩ pull-down) is **active-high**: download
  mode needs it pulled to 3.3 V at power-up; grounding it does nothing. The two tiny
  round pads directly above the BL702's top-left corner (the smaller QFN right of the
  USB-C) are a pair: one is 3V3, the other is the boot strap (~0 V). Bridge them directly
  while plugging in. If the user sees only one pad, it is usually the 3V3 one — have them
  measure (3.3 V = supply pad, ~0 V = boot pad) before advising a wire. Board revisions
  differ (silkscreen 3672 vs 3674; both schematics on dl.sipeed.com under
  `TANG/Nano 9K/2_Schematic/`) and some lack the second pad: then bridge the 3V3 pad to
  the non-ground end of R34 (the strap's 10 kΩ pull-down; the far end reads ~10 kΩ to
  GND) or to BL702 pin 31. Photos:
  `https://wiki.sipeed.com/hardware/zh/tang/common-doc/assets/hardware/nano9k_update.jpg`
  and the close-up `https://raw.githubusercontent.com/koshkin-sergey/Debugger_for_TANG_NANO-9K/master/res/BL702.png`;
  schematic: Sipeed download station `Tang_Nano_9k_3672_Schematic.pdf`, BL702 sheet. The
  ROM ISP enumerates as `ffff:ffff` "BLIOT CDC Virtual ComPort" on `ttyACM*` (instead of
  the two `ttyUSB`); flash with `bflb_mcu_tool --chipname=bl702 --xtal=32M`. First check:
  enter ISP, back up the flash, read the efuse, before planning a port — see *Reading a
  BL702 in ISP* below.
  `sipeed/RV-Debugger-BL702` is the open-source stock-style firmware. **Its 9K pin map
  (TMS 14, TCK 23, TDI 17, TDO 15) is wrong for the board we have:** the stock flash dump
  (reverse-engineered: app at flash 0x4000 → XIP 0x23000000, JTAG loop in TCM) bit-bangs
  **TDI = GPIO0, TDO = GPIO1, TMS = GPIO2, TCK = GPIO15** (OUT 0x188 masks 0x1/0x4/0x8000,
  IN 0x180 mask 0x2) — i.e. the repo's "4K" map. Stock pinmux: GPIO14 UART0 TX (log),
  GPIO23 UART0 RX, GPIO26/27 UART1 TX/RX, LEDs GPIO9/17, GPIO7/8 USB analog. Wrong pins
  give `TDO is stuck at 0`. Trust the binary over the repo's io_cfg.h. A DirtyJTAG port reuses the BL616 firmware's design and swaps GPIO registers,
  clocks and the USB driver (`bouffalo_sdk` covers both chips; BL702 USB device driver is
  `drivers/lhal/src/bflb_usb_v1.c`, board `bl702dk`).

### BL702 port: layout and pitfalls

- **Chosen layout: the app alone at 0x0**, flashed via ROM ISP. Routes back into download
  mode without the strap, as tested:
  - Erasing the app's boot header (sector 0) from firmware and resetting does **not** work:
    the ROM does not fall back to USB ISP, the board stops enumerating entirely until the
    strap is bridged. Don't retry it.
  - The SDK's `examples/boot2_isp` at 0x0 (app writes `"USB"` to `HBN_RSV0` and resets;
    boot2 runs the eflash loader over USB) is the remaining route, but with
    `HAL_BOOT2_SUPPORT_USB_IAP` set to 1 (`port/bl702/bflb_port_boot2.h`) it fails to link
    (`xip memory overflowed`): the boot2 region must be enlarged or features dropped first.
    That is bootloader work, not part of a port.
- **Call `GLB_Select_Internal_Flash()` first in `main`, before `board_init()`.** GPIO23–28
  (UART1 on 26/27) are the SF2 flash pads; until `GLB_GPIO_USE_PSRAM__IO` (0x40000088)
  bits 0–5 are set they stay routed to the flash interface (UART1 26/27 needs this). This
  alone did NOT fix `TDO is stuck at 0` — that was the wrong JTAG pin map above. It must precede `board_init()` because
  `bflb_flash_init()` re-claims the pads when it sees those bits clear. Sipeed's stock
  firmware (`RV-Debugger-BL702` usb2uartjtag `main.c`) does the same. The current SDK's
  LHAL `bflb_gpio_init()` already applies the +9 config remap for these pins once the bits
  are set, so plain LHAL GPIO calls are fine after that.
- When the port misbehaves, diff its init against the **stock binary** (see *Reverse-engineering
  the stock image* below), not against `RV-Debugger-BL702`'s source: the source is a hint,
  the dump is what actually works on this board revision.
- Fast bit-bang uses the single GPIO output/input registers (0x40000188 / 0x40000180,
  verify against `glb_reg.h`), not the BL616's per-pin registers.

## Reverse-engineering the stock image

Do this before the first reflash of a port, and whenever a port fails on hardware: an
answer from the dump costs no bench step, a guessed fix costs a strap-bridged reboot.
Hand it to a subagent (context-heavy), with the dump path and the question.

- **Find the code.** On the 9K dump: partition table at flash 0x1000/0x2000 (`FW` entry
  at 0x3000), app boot header at 0x3000, code at flash 0x4000 = XIP `0x23000000`. Confirm
  the base by resolving a known string (`Copyright (c) 2021 Sipeed team`).
- **Tools:** Ghidra headless (`ghidra-analyzeHeadless`, RV32 language) for decompiled C;
  the SDK's `riscv64-unknown-elf-objdump -b binary -m riscv` for raw listings. Name ROM
  calls via the ROM API table at `0x21018800` (`bl702_romdriver.h` gives the indices).
  crt0 copies TCM code/data out of flash; map those copies too, the hot JTAG loop lives
  in TCM.
- **Find the pins** by searching for the GPIO register constants: the bit-bang loop loads
  `0x40000180` (IN) and writes `0x40000188` (OUT); its masks are the pin numbers. The init
  path shows the pinmux (`GLB_GPIO_Init` calls, UART_SIG_SEL at `0x400000c0`).

## Reading a BL702 in ISP (read-only)

- Tooling: `uv venv --python 3.12 $TMPDIR/bflb-venv` then `uv pip install bflb-mcu-tool`
  (it imports `telnetlib`, which Python 3.13+ removed). `bflb-mcu-tool` itself only
  writes; reads go through its bundled eflash loader. From the package dir
  (`…/site-packages/bflb_mcu_tool`):
  `python -c "import sys; sys.argv=['eflash']+sys.argv[1:]; from libs import bflb_eflash_loader as e; e.run()" --chipname=bl702 --port=/dev/ttyACM<n> --baudrate=115200 --xtal=32M --config=chips/bl702/eflash_loader/eflash_loader_cfg.conf`
  plus `--flash --read --start=0x0 --end=0x7ffff --file=flash.bin` (512 KiB backup) or
  `--efuse --read --start=0x0 --end=0x7f --file=efuse.bin`.
- **Reuse the resident helper instead of re-entering ISP.** The first invocation loads a
  helper into RAM; a second one fails with `eflash loader present` / `BFLB LOAD HELP BIN
  FAIL` at any baud. Copy the config with `load_function = 0` and `do_reset = false`
  (`sed` on `eflash_loader_cfg.conf` into e.g. `noload.conf`) and pass that `--config`:
  it talks to the helper already running, at 115200. This works for every later read and
  write as long as the board stays powered — check `lsusb` for `ffff:ffff` before asking
  the user to bridge the strap again.
- Efuse word 0 = `0` means encryption and signature checks are off: unsigned firmware at
  0x0 boots.

## Flashing the BL702 port

1. **Use the stock flash settings in the boot header.** The SDK's `bl702dk` header carries a
   generic flash config that differs from the one the stock image uses for this board's
   flash. Copy the stock FCFG block into the build output: bytes `0x08–0x63` (magic `FCFG`,
   config, its own CRC32 at `0x60`) from `flash_stock.bin`, then recompute the header CRC32
   over bytes `0x00–0xAB` into `0xAC` (`zlib.crc32`, little-endian). Check the layout first
   by confirming both CRCs on the stock image; only the FCFG block may differ.
2. **Write it.** Freshly strap-bridged ISP (helper not yet loaded): use the stock
   `eflash_loader_cfg.conf`, which loads the helper first; the explicit `--addr`/`--file`
   override the config's default boot2/partition file list. Helper already resident from
   an earlier read: use `noload.conf` above. Either way:
   `--flash --write --addr=0x0 --file=<patched>.bin`. The write is verified when the log
   says `sha256 caled by dev: …` / `verification succeeded` and that hash equals
   `sha256sum` of the file. The helper stops answering after a write, so a read-back fails
   with `EFLASH LOADER HANDSHAKE FAIL`; the device-side hash is the verification.
3. **Replug without the strap** so the new image boots, then check `lsusb` for
   `1209:c0ca` and `openFPGALoader -c dirtyJtag --detect` before running the soak.
4. Every further reflash needs the strap bridged again (no software route back into ISP
   yet), so batch fixes: build, review against the stock firmware's init, then ask for
   one bridged boot.

## Localizing a DirtyJTAG-port UART fault

The firmware appends `struct uart_debug_state` (natural alignment: `u32 rx_bytes` = bytes
submitted to CDC IN, `u32 tx_bytes`, `u8 cdc_configured`, `u8 cdc_tx_busy`, 2 pad, `u32
baudrate`) after the 10-byte `DJTAG2` string in the `CMD_INFO` reply. Read it with pyusb
(install into the 3.12 `bflb-venv`): write `[0x01, 0x00]` to EP `0x01`, read 64 bytes
from EP `0x82` (detach/claim interface 0 first). Keep a small probe script that prints
one line per second and run it while one long `cat` holds the CDC port open.

BL702 builds with the bounded-EP0-wait change (bl616_dirtyjtag PR #5) append `struct
usb_dc_debug` (six `u32`: ISR count, EP0 SETUP/OUT RDY-wait timeouts, bad SETUP length,
longest EP0 wait in µs, deferred bulk DONEs) at reply bytes 26..49; `debug_uart.py`
prints them. Non-zero timeouts after a concurrent-load soak confirm the EP0-wait wedge.

Reading the counters — `rx_bytes` frozen does **not** by itself mean UART1 receives
nothing:
- Also read the UART1 FIFO count (`0x4000A184` bits 15:8 on BL702; 128 = full) and the
  uart task's tick / loop counter / fill level / `eTaskGetState` (add them to a debug
  vendor command; the reply is built in ISR context, so use `xTaskGetTickCountFromISR`).
- FIFO full + task alive + `busy=1` = forwarding is stuck on the USB IN side, not RX.
  FIFO empty + task alive = nothing arrives on the pin.
- `busy=1, fill=512` while no process has the port open is expected: the host does not
  poll IN on a closed tty, and the first read after reopening returns stale bytes (the
  HIL's `dd` flush discards them). Never diagnose from several short `cat`s.
- Unexpected text on the UART (e.g. a LiteX BIOS banner) means the FPGA is running the
  design in its own flash: the SRAM load did not stick, or the FPGA rebooted. Check the
  load with `openFPGALoader -v` (`Done Final` in the status register) before blaming the
  bridge.
- On BL702 a remapped SF2 pad (GPIO23–28 after `GLB_Select_Internal_Flash`) reads back in
  the input register as GPIO n+9 (pad 27 → `0x40000184` bit 4), not at its own bit.

Anything beyond these counters needs an instrumented build: fold it into the next
strap-bridged reflash rather than spending a reboot on it alone.

## Fault signatures

- **BL616 stock firmware:** UART stops entirely after a baud-rate change (why the custom
  firmware hardcodes it).
- **BL702 stock firmware wedged:** `openFPGALoader` fails with `unable to open ftdi device:
  -6 (ftdi_usb_reset failed)` and the kernel log fills with `ftdi_sio ttyUSB1: failed to
  get modem status: -32` / `failed to set flow control: -32` — every control request
  STALLs. Only a replug recovers it. Read the kernel log with `journalctl -k --since …`
  (plain `dmesg` is not permitted for the user on the desktop). Rule out other openers
  first: `systemctl is-active ModemManager brltty`.
- **BL702 stock firmware UART lockup (measured on the 9K):** 20/20 clean load+capture
  rounds at a fixed 115200 (re-`stty` to the same rate is fine), but one 9600 → 115200
  switch (with the FPGA sending 115200 during the 9600 window) leaves the UART at 0 bytes
  while JTAG `--detect` still works, no kernel errors; survives FPGA reload, only a replug
  recovers. Same class as the BL616 stock lockup.
- **BL702 DirtyJTAG port, fixed (bl616_dirtyjtag de8719e):** after a bitstream load a
  following `cat` got 0 bytes, `stty` took ~11 s, and any write to the JTAG endpoint
  restarted the flow. Cause: the SDK's `bflb_usb_v1.c` ISR cleared all DONE bits on
  entry, then busy-waited for the OUT endpoint's RDY; an early DONE got counted for the
  next packet and the ISR spun on the idle EP1, starving everything. Fix: ack an
  endpoint's DONE only once its RDY has dropped (as bl_mcu_sdk does); the driver is
  built from the repo's `src/` for BL702 only. Signature to recognise a CPU stuck in an
  ISR: tick advances, task loop counter frozen, control requests time out.
- Garbled-but-flowing bytes are not a bridge fault until the TX-glitch check in SKILL.md
  step 3 is done.

## Measuring bridge reliability

Run `scripts/bridge-soak.sh` (load + `stty` + flush + capture, N iterations, stops at the
first failed step and says which). Report "k of N iterations" plus the failing step and the
kernel-log signature; a wedge on the first JTAG access counts as 0 of 1.
