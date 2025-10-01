`default_nettype none
module clock_pll(input wire clk, input wire rst, output wire write_clk, output wire pixel_clk);
	wire gnd;
	assign gnd = 1'b0;

	rPLL pll(
	    .CLKOUT(pixel_clk),  // 9MHz
		.CLKOUTD(write_clk),
		.CLKIN(clk),
		.CLKFB(gnd),
		.RESET(!rst),
		.RESET_P(!rst),
		.FBDSEL({gnd, gnd, gnd, gnd, gnd, gnd}),
		.IDSEL({gnd, gnd, gnd, gnd, gnd, gnd}),
		.ODSEL({gnd, gnd, gnd, gnd, gnd, gnd}),
		.DUTYDA({gnd, gnd, gnd, gnd}),
		.PSDA({gnd, gnd, gnd, gnd}),
		.FDLY({gnd, gnd, gnd, gnd})
	);
	defparam pll.DEVICE = `PLL_DEVICE;
	defparam pll.FCLKIN = `PLL_FCLKIN;
	defparam pll.FBDIV_SEL = `PLL_FBDIV_SEL_LCD;
	defparam pll.IDIV_SEL =  `PLL_IDIV_SEL_LCD;
	defparam pll.ODIV_SEL = `PLL_ODIV_SEL;
	defparam pll.CLKFB_SEL="internal";
	defparam pll.CLKOUTD3_SRC="CLKOUT";
	defparam pll.CLKOUTD_BYPASS="false";
	defparam pll.CLKOUTD_SRC="CLKOUT";
	defparam pll.CLKOUTP_BYPASS="false";
	defparam pll.CLKOUTP_DLY_STEP=0;
	defparam pll.CLKOUTP_FT_DIR=1'b1;
	defparam pll.CLKOUT_BYPASS="false";
	defparam pll.CLKOUT_DLY_STEP=0;
	defparam pll.CLKOUT_FT_DIR=1'b1;
	defparam pll.DUTYDA_SEL="1000";
	defparam pll.DYN_DA_EN="false";
	defparam pll.DYN_FBDIV_SEL="false";
	defparam pll.DYN_IDIV_SEL="false";
	defparam pll.DYN_ODIV_SEL="false";
	defparam pll.DYN_SDIV_SEL=128;
	defparam pll.PSDA_SEL="0000";
endmodule
// vim: set et sw=4 ts=4:
