# EMCU

The GW1NSR (used on the Tang Nano 4k) contains a ARM Cortex-M3 SoC, connected
to the FPGA fabric. It's based on the [ARM CoreLink SSE-050
Subsystem](https://developer.arm.com/documentation/100918/0001).

## Master memory ports

For the master ports, gowin has exposed:

- The AHB TARGETEXP0 port (called the Radio interface by ARM), starting at
  0xA000_0000, with a depth of 0x10000
- The APB APBTARGEXP2 port, starting at 0x4000_2000, with a depth of 0x1000
- The dedicated SRAM0 ports for sram read/write access
- The dedicated read-only TARGFLASH0 port for flash read-access, where RDATA is
  connected to the flash in hardware

## Reset

The emcu reset is wired up in hardware, presumably connected to the GSR.
