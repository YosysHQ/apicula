#!/usr/bin/python3
#
# pll tool to find best match for the target frequency (GW1NR-9C C6/I5 (Tang Nano 9K proto dev board))


import argparse


parser = argparse.ArgumentParser()
parser.add_argument(
    "-i", "--input-freq-mhz", help="PLL Input Frequency", type=float, default=27
)
parser.add_argument(
    "-o", "--output-freq-mhz", help="PLL Output Frequency", type=float, default=108
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

args = parser.parse_args()

limits = {
    "pfd_min": 3,
    "pfd_max": 400,
    "vco_min": 400,
    "vco_max": 1200,
    "clkout_min": 3.125,
    "clkout_max": 600,
}
setup = {}

FCLKIN = args.input_freq_mhz
min_diff = FCLKIN

for IDIV_SEL in range(64):
    for FBDIV_SEL in range(64):
        for ODIV_SEL in [2, 4, 8, 16, 32, 48, 64, 80, 96, 112, 128]:
            PFD = FCLKIN / (IDIV_SEL + 1)
            if not (limits["pfd_min"] < PFD < limits["pfd_max"]):
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
                    "FBDIV_SEL": IDIV_SEL,
                    "ODIV_SEL": IDIV_SEL,
                    "PFD": PFD,
                    "CLKOUT": CLKOUT,
                    "VCO": VCO,
                    "ERROR": diff,
                }


if setup:
    pll_v = f"""
module {args.module_name}(
        input  clock_in,
        output clock_out,
        output locked
    );

    rPLL #(
        .FCLKIN("{args.input_freq_mhz}"),
        .IDIV_SEL({setup['IDIV_SEL']}), // -> PFD = {setup['PFD']} MHz (range: {limits['pfd_min']}-{limits['pfd_max']} MHz)
        .FBDIV_SEL({setup['FBDIV_SEL']}), // -> CLKOUT = {setup['CLKOUT']} MHz (range: {limits['vco_min']}-{limits['clkout_max']} MHz)
        .ODIV_SEL({setup['ODIV_SEL']}) // -> VCO = {setup['VCO']} MHz (range: {limits['clkout_max']}-{limits['vco_max']} MHz)
    ) pll (.CLKOUTP(), .CLKOUTD(), .CLKOUTD3(), .RESET(1'b0), .RESET_P(1'b0), .CLKFB(1'b0), .FBDSEL(6'b0), .IDSEL(6'b0), .ODSEL(6'b0), .PSDA(4'b0), .DUTYDA(4'b0), .FDLY(4'b0),
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
