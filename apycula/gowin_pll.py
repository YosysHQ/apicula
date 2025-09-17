# pll tool to find best match for the target frequency
# calculations based on: https://github.com/juj/gowin_fpga_code_generators/blob/main/pll_calculator.html
# limits from:
# - http://cdn.gowinsemi.com.cn/DS117E.pdf,
# - http://cdn.gowinsemi.com.cn/DS861E.pdf,
# - https://cdn.gowinsemi.com.cn/DS226E.pdf

import argparse
import re
import sys


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-i", "--input-freq-mhz", help="PLL Input Frequency", type=float, default=27
    )
    parser.add_argument(
        "-o", "--output-freq-mhz", help="PLL Output Frequency", type=float, default=108
    )
    parser.add_argument(
        "-d", "--device", help="Device", type=str, default="GW1NR-9 C6/I5"
    )
    parser.add_argument(
        "-f",
        "--filename",
        help="Save PLL configuration as Verilog to file",
        type=str,
        default=None,
    )
    parser.add_argument(
        "-m",
        "--module-name",
        help="Specify different Verilog module name than the default 'pll'",
        type=str,
        default="pll",
    )
    parser.add_argument("-l", "--list-devices", help="list device", action="store_true")

    args = parser.parse_args()

    device_name = args.device
    match = re.search(
        r"(GW[125][A-Z]{1,3})-[A-Z]{0,2}([0-9]{1,2})[A-Z]{1,3}[0-9]{1,3}P*N*(C[0-9]/I[0-9]|ES)",
        device_name,
    )
    if match:
        device_name = f"{match.group(1)}-{match.group(2)} {match.group(3)}"
    else:
        print(f'Warning: cannot decipher the name of the device {device_name}.')

    device_limits = {
        "GW1N-1 C6/I5": {
            "comment": "Untested",
            "pll_name": "rPLL",
            "pfd_min": 3,
            "pfd_max": 400,
            "vco_min": 400,
            "vco_max": 900,
            "clkout_min": 3.125,
            "clkout_max": 450,
        },
        "GW1N-1 C5/I4": {
            "comment": "Untested",
            "pll_name": "rPLL",
            "pfd_min": 3,
            "pfd_max": 320,
            "vco_min": 320,
            "vco_max": 720,
            "clkout_min": 2.5,
            "clkout_max": 360,
        },
        "GW1NR-2 C7/I6": {
            "comment": "Untested",
            "pll_name": "PLLVR",
            "pfd_min": 3,
            "pfd_max": 400,
            "vco_min": 400,
            "vco_max": 800,
            "clkout_min": 3.125,
            "clkout_max": 750,
        },
        "GW1NR-2 C6/I5": {
            "comment": "Untested",
            "pll_name": "PLLVR",
            "pfd_min": 3,
            "pfd_max": 400,
            "vco_min": 400,
            "vco_max": 800,
            "clkout_min": 3.125,
            "clkout_max": 750,
        },
        "GW1NR-2 C5/I4": {
            "comment": "Untested",
            "pll_name": "PLLVR",
            "pfd_min": 3,
            "pfd_max": 320,
            "vco_min": 320,
            "vco_max": 640,
            "clkout_min": 2.5,
            "clkout_max": 640,
        },
        "GW1NR-4 C6/I5": {
            "comment": "Untested",
            "pll_name": "PLLVR",
            "pfd_min": 3,
            "pfd_max": 400,
            "vco_min": 400,
            "vco_max": 1000,
            "clkout_min": 3.125,
            "clkout_max": 500,
        },
        "GW1NR-4 C5/I4": {
            "comment": "Untested",
            "pll_name": "PLLVR",
            "pfd_min": 3,
            "pfd_max": 320,
            "vco_min": 320,
            "vco_max": 800,
            "clkout_min": 2.5,
            "clkout_max": 400,
        },
        "GW1NSR-4 C7/I6": {
            "comment": "Untested",
            "pll_name": "PLLVR",
            "pfd_min": 3,
            "pfd_max": 400,
            "vco_min": 400,
            "vco_max": 1200,
            "clkout_min": 3.125,
            "clkout_max": 600,
        },
        "GW1NSR-4 C6/I5": {
            "comment": "Untested",
            "pll_name": "PLLVR",
            "pfd_min": 3,
            "pfd_max": 400,
            "vco_min": 400,
            "vco_max": 1200,
            "clkout_min": 3.125,
            "clkout_max": 600,
        },
        "GW1NSR-4 C5/I4": {
            "comment": "Untested",
            "pll_name": "PLLVR",
            "pfd_min": 3,
            "pfd_max": 320,
            "vco_min": 320,
            "vco_max": 960,
            "clkout_min": 2.5,
            "clkout_max": 480,
        },
        "GW1NSR-4C C7/I6": {
            "comment": "Untested",
            "pll_name": "PLLVR",
            "pfd_min": 3,
            "pfd_max": 400,
            "vco_min": 400,
            "vco_max": 1200,
            "clkout_min": 3.125,
            "clkout_max": 600,
        },
        "GW1NSR-4C C6/I5": {
            "comment": "Untested",
            "pll_name": "PLLVR",
            "pfd_min": 3,
            "pfd_max": 400,
            "vco_min": 400,
            "vco_max": 1200,
            "clkout_min": 3.125,
            "clkout_max": 600,
        },
        "GW1NSR-4C C5/I4": {
            "comment": "Untested",
            "pll_name": "PLLVR",
            "pfd_min": 3,
            "pfd_max": 320,
            "vco_min": 320,
            "vco_max": 960,
            "clkout_min": 2.5,
            "clkout_max": 480,
        },
        "GW1NR-9 C7/I6": {
            "comment": "Untested",
            "pll_name": "rPLL",
            "pfd_min": 3,
            "pfd_max": 400,
            "vco_min": 400,
            "vco_max": 1200,
            "clkout_min": 3.125,
            "clkout_max": 600,
        },
        "GW1NR-9 C6/I5": {
            "comment": "tested on TangNano9K Board",
            "pll_name": "rPLL",
            "pfd_min": 3,
            "pfd_max": 400,
            "vco_min": 400,
            "vco_max": 1200,
            "clkout_min": 3.125,
            "clkout_max": 600,
        },
        "GW1NR-9 C6/I4": {
            "comment": "Untested",
            "pll_name": "rPLL",
            "pfd_min": 3,
            "pfd_max": 320,
            "vco_min": 3200,
            "vco_max": 960,
            "clkout_min": 2.5,
            "clkout_max": 480,
        },
        "GW1NZ-1 C6/I5": {
            "comment": "untested",
            "pll_name": "rPLL",
            "pfd_min": 3,
            "pfd_max": 400,
            "vco_min": 400,
            "vco_max": 800,
            "clkout_min": 3.125,
            "clkout_max": 400,
        },
        "GW2A-18 C8/I7": {
            "comment": "untested",
            "pll_name": "rPLL",
            "pfd_min": 3,
            "pfd_max": 500,
            "vco_min": 500,
            "vco_max": 1250,
            "clkout_min": 3.90625,
            "clkout_max": 625,
        },
        "GW2AR-18 C8/I7": {
            "comment": "untested",
            "pll_name": "rPLL",
            "pfd_min": 3,
            "pfd_max": 500,
            "vco_min": 500,
            "vco_max": 1250,
            "clkout_min": 3.90625,
            "clkout_max": 625,
        },
        "GW5A-25 ES": {
            "comment": "untested",
            "pll_name": "rPLL",
            "pfd_min": 19,
            "pfd_max": 800,
            "vco_min": 800,
            "vco_max": 1600,
            # The previous four parameters are taken from the datasheet (as in
            # this case from https://cdn.gowinsemi.com.cn/DS1103E.pdf), but I
            # don't know where these two come from:(
            "clkout_min": 6.25,
            "clkout_max": 1600,
        },
    }

    if args.list_devices:
        for device in device_limits:
            print(f"{device} - {device_limits[device]['comment']}")
        sys.exit(0)

    if device_name not in device_limits:
        print(f"ERROR: device '{device_name}' not found")
        sys.exit(1)

    limits = device_limits[device_name]
    setup = {}

    FCLKIN = args.input_freq_mhz
    min_diff = FCLKIN

    for IDIV_SEL in range(64):
        for FBDIV_SEL in range(64):
            for ODIV_SEL in [2, 4, 8, 16, 32, 48, 64, 80, 96, 112, 128]:
                PFD = FCLKIN / (IDIV_SEL + 1)
                if not (limits["pfd_min"] <= PFD <= limits["pfd_max"]):
                    continue
                CLKOUT = FCLKIN * (FBDIV_SEL + 1) / (IDIV_SEL + 1)
                if not (limits["clkout_min"] < CLKOUT < limits["clkout_max"]):
                    continue
                VCO = (FCLKIN * (FBDIV_SEL + 1) * ODIV_SEL) / (IDIV_SEL + 1)
                if not (limits["vco_min"] < VCO < limits["vco_max"]):
                    continue
                diff = abs(args.output_freq_mhz - CLKOUT)
                if diff < min_diff:
                    min_diff = diff
                    setup = {
                        "IDIV_SEL": IDIV_SEL,
                        "FBDIV_SEL": FBDIV_SEL,
                        "ODIV_SEL": ODIV_SEL,
                        "PFD": PFD,
                        "CLKOUT": CLKOUT,
                        "VCO": VCO,
                        "ERROR": diff,
                    }

    if setup:

        extra_options = ""
        if limits["pll_name"] == "PLLVR":
            extra_options = ".VREN(1'b1),"

        pll_v = f"""/**
 * PLL configuration
 *
 * This Verilog module was generated automatically
 * using the gowin-pll tool.
 * Use at your own risk.
 *
 * Target-Device:                {device_name}
 * Given input frequency:        {args.input_freq_mhz:0.3f} MHz
 * Requested output frequency:   {args.output_freq_mhz:0.3f} MHz
 * Achieved output frequency:    {setup['CLKOUT']:0.3f} MHz
 */

module {args.module_name}(
        input  clock_in,
        output clock_out,
        output locked
    );

    {limits['pll_name']} #(
        .FCLKIN("{args.input_freq_mhz}"),
        .IDIV_SEL({setup['IDIV_SEL']}), // -> PFD = {setup['PFD']} MHz (range: {limits['pfd_min']}-{limits['pfd_max']} MHz)
        .FBDIV_SEL({setup['FBDIV_SEL']}), // -> CLKOUT = {setup['CLKOUT']} MHz (range: {limits['clkout_min']}-{limits['clkout_max']} MHz)
        .ODIV_SEL({setup['ODIV_SEL']}) // -> VCO = {setup['VCO']} MHz (range: {limits['vco_min']}-{limits['vco_max']} MHz)
    ) pll (.CLKOUTP(), .CLKOUTD(), .CLKOUTD3(), .RESET(1'b0), .RESET_P(1'b0), .CLKFB(1'b0), .FBDSEL(6'b0), .IDSEL(6'b0), .ODSEL(6'b0), .PSDA(4'b0), .DUTYDA(4'b0), .FDLY(4'b0), {extra_options}
        .CLKIN(clock_in), // {args.input_freq_mhz} MHz
        .CLKOUT(clock_out), // {setup['CLKOUT']} MHz
        .LOCK(locked)
    );

endmodule
"""
        if args.filename:
            open(args.filename, "w").write(pll_v)
        else:
            print(pll_v)


if __name__ == "__main__":
    main()
