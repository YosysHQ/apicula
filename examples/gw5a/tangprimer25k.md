# Tang Primer 25K (GW5A-LV25MG121NC1/I0) - OSS Toolchain Guide

## Important Discovery

**The Tang Primer 25K has TWO package variants:**

| Variant | Package | Pins | Constraint File |
|---------|---------|------|-----------------|
| **MG121** | MBGA121N | 121 | `tangprimer25k-mg121.cst` |
| **UG324** | UBGA324 | 324 | `tangprimer25k-ug324.cst` |

Check your chip marking:
- `GW5A-LV25MG121NC1/I0` → **MG121 package** (use `tangprimer25k-mg121.cst`)
- `GW5A-LV25UG324C1/I0` → **UG324 package** (use `tangprimer25k-ug324.cst`)

## IO_TYPE Correction

**CRITICAL:** GW5A family uses **LVCMOS18**, not LVCMOS33!

The existing `primer25k.cst` in this repo uses `LVCMOS33` which is **incorrect** for GW5A.
All constraint files in this PR use `LVCMOS18`.

## Quick Start

### 1. Install OSS Toolchain

```bash
# Install Yosys, nextpnr, openFPGALoader
# On Ubuntu/Debian:
sudo apt install yosys nextpnr-gowin openFPGALoader

# Or use OSS CAD Suite:
# https://github.com/YosysHQ/oss-cad-suite-build
```

### 2. Install Apicula (chipdb)

```bash
pip install apycula

# Or build from source for latest GW5A-25A support:
git clone https://github.com/YosysHQ/apicula
cd apicula
GOWINHOME=/path/to/Gowin_IDE_1.9.10 python -m apycula.chipdb_builder GW5A-25A
```

### 3. Build a Blinky

```bash
# Create blinky.v
cat > blinky.v << 'EOF'
module blinky(
    input clk,
    input rst_n,
    output led
);
    reg [23:0] counter;
    
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n)
            counter <= 0;
        else
            counter <= counter + 1;
    end
    
    assign led = counter[23];
endmodule
EOF

# Synthesize
yosys -p "read_verilog blinky.v; synth_gowin -top blinky -json blinky.json"

# Place & Route (MG121 variant)
nextpnr-gowin --json blinky.json --write blinky_pnr.json \
    --device GW5A-LV25MG121NC1/I0 \
    --vopt cst=tangprimer25k-mg121.cst \
    --vopt sspi_as_gpio

# Pack to bitstream
gowin_pack -d GW5A-25A blinky_pnr.json blinky.fs \
    --sspi_as_gpio --cst tangprimer25k-mg121.cst

# Program
openFPGALoader -b tangprimer25k blinky.fs
```

## Device String

| Package | Device String |
|---------|---------------|
| MG121 | `GW5A-LV25MG121NC1/I0` |
| UG324 | `GW5A-LV25UG324C1/I0` |

**Important:** The `/I0` suffix is required for nextpnr!

## Pin Reference

### MG121 Package (Your Board)

| Function | Pin | Notes |
|----------|-----|-------|
| Clock (27MHz) | E2 | GCLKT_10B |
| Reset (button) | H10 | GCLKC_16, active-low |
| LED | A11 | IOL14A |
| UART RX | B3 | IOB56A |
| UART TX | C3 | IOB56B |

### UG324 Package (Alternative)

| Function | Pin | Notes |
|----------|-----|-------|
| Clock (27MHz) | A9 | GCLKC_1 |
| Reset (button) | A2 | IOT31B |
| LED | A11 | IOL14A |

## Troubleshooting

### "No pin found for X"

Check your package variant. MG121 and UG324 have different pinouts.

### Bitstream doesn't load

1. Ensure `--sspi_as_gpio` flag is used in both nextpnr and gowin_pack
2. Check Gowin IDE version: **v1.9.10** is required (v1.9.11 has FSE format issues)
3. Verify chipdb was built with correct GOWINHOME

### LVCMOS33 vs LVCMOS18

GW5A family operates at 1.8V IO. Using LVCMOS33 may cause:
- Timing violations
- Unreliable IO
- Potential damage at high drive strength

Always use `IO_TYPE=LVCMOS18` for GW5A.

## Files in This PR

| File | Description |
|------|-------------|
| `tangprimer25k-mg121.cst` | Minimal MG121 constraint file |
| `tangprimer25k-full-mg121.cst` | Complete MG121 pinout (86 pins) |
| `tangprimer25k-ug324.cst` | Minimal UG324 constraint file |
| `tangprimer25k-full-ug324.cst` | Complete UG324 pinout |
| `tangprimer25k.md` | This guide |

## Gowin IDE Version

**Required:** Gowin IDE v1.9.10.03

Do NOT use v1.9.11.x — it has FSE format incompatibility with Apicula.

Download: https://www.gowinsemi.com/en/support/download/ (requires login)