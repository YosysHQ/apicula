module top(input wire clk, output wire [`LEDS_NR-1:0]led);
	wire VCC;
	wire GND;
	wire [2:0]dummy;
	assign VCC = 1'b1;
	assign GND = 1'b0;
	rPLL pll(
		.CLKOUT(led[0]),         // connect an oscilloscope here
		.CLKIN(clk),
		.CLKOUTP(dummy[0]),
		.CLKOUTD(dummy[1]),
		.CLKOUTD3(dummy[2]),
		.LOCK(led[1]),           // this LED lights up when the PLL lock is triggered
		.CLKFB(GND),
		.FBDSEL({GND,GND,GND,GND,GND,GND}),
		.IDSEL({GND,GND,GND,GND,GND,GND}),
		.ODSEL({VCC,GND,GND,GND,GND,GND}),
		.DUTYDA({GND,GND,GND,GND}),
		.PSDA({GND,GND,GND,GND}),
		.FDLY({GND,GND,GND,GND}),
		.RESET(GND),
		.RESET_P(GND) 
	);
	defparam pll.DEVICE = `PLL_DEVICE;
	defparam pll.FCLKIN = `PLL_FCLKIN;
	defparam pll.FBDIV_SEL = `PLL_FBDIV_SEL;
	defparam pll.IDIV_SEL =  `PLL_IDIV_SEL;
	defparam pll.ODIV_SEL =  `PLL_ODIV_SEL;
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
	defparam pll.DEVICE="GW1N-1";
	defparam pll.DUTYDA_SEL="1000";
	defparam pll.DYN_DA_EN="false";
	defparam pll.DYN_FBDIV_SEL="false";
	defparam pll.DYN_IDIV_SEL="false";
	defparam pll.DYN_ODIV_SEL="false";
	defparam pll.DYN_SDIV_SEL=2;
	defparam pll.PSDA_SEL="0000";
endmodule

