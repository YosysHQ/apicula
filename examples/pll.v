`default_nettype none
module top(input wire clk, input wire key, output wire [`LEDS_NR-1:0]led);
	wire VCC;
	wire GND;
	assign VCC = 1'b1;
	assign GND = 1'b0;
	reg reset;
`ifdef PLL_DYN
	reg [5:0]fdiv;
	reg [5:0]idiv;
`else
	wire [5:0]fdiv;
	assign fdiv = 6'd0;
	wire [5:0]idiv;
	assign idiv = 6'd0;
`endif
	rPLL pll(
		.CLKOUT(led[0]),         // connect an oscilloscope here. main freq
		.CLKIN(clk),
		.CLKOUTD(led[2]),		 // freq / SDIV = freq / 124
		.LOCK(led[1]),           // this LED lights up when the PLL lock is triggered
		.CLKFB(GND),
		.FBDSEL(fdiv),
		.IDSEL(idiv),
		.ODSEL({GND,GND,GND,GND,GND,GND}),
		.DUTYDA({GND,GND,GND,GND}),
		.PSDA({GND,GND,GND,GND}),
		.FDLY({GND,GND,GND,GND}),
		.RESET(reset),
	);
	defparam pll.DEVICE = `PLL_DEVICE;
	defparam pll.FCLKIN = `PLL_FCLKIN;
	defparam pll.FBDIV_SEL = `PLL_FBDIV_SEL;
	defparam pll.IDIV_SEL =  `PLL_IDIV_SEL;
	defparam pll.ODIV_SEL =  `PLL_ODIV_SEL;
	defparam pll.CLKFB_SEL="internal";
	defparam pll.CLKOUTD3_SRC="CLKOUTP";
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
`ifdef PLL_DYN
	defparam pll.DYN_FBDIV_SEL="true";
	defparam pll.DYN_IDIV_SEL="true";
`else
	defparam pll.DYN_FBDIV_SEL="false";
	defparam pll.DYN_IDIV_SEL="false";
`endif
	defparam pll.DYN_ODIV_SEL="false";
	defparam pll.DYN_SDIV_SEL=124;
	defparam pll.PSDA_SEL="0000";

    // dynamic
`ifdef PLL_DYN
    always @ (posedge clk) begin
        if (key) begin
            fdiv <= ~`PLL_FBDIV_SEL;
            idiv <= ~`PLL_IDIV_SEL;
        end else begin
            fdiv <= ~`PLL_FBDIV_SEL_1;
            idiv <= ~`PLL_IDIV_SEL_1;
        end
    end
`else
	always @ (posedge clk) begin
		reset = ~key;
	end
`endif
endmodule

