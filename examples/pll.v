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
	Gowin_rPLL pll0(
		.clkout(led[0]),         // connect an oscilloscope here. main freq
		.clkfb(GND),
		.clkin(clk),
		.clkoutd_o(led[2]),		 // freq / SDIV = freq / 124
		.lock_o(led[1]),           // this LED lights up when the PLL lock is triggered
		.fdiv(fdiv),
		.idiv(idiv),
		.reset(reset),
		.reset_p(GND)
	);
	defparam pll0.DEVICE = `PLL_DEVICE;
	defparam pll0.FCLKIN = `PLL_FCLKIN;
	defparam pll0.FBDIV_SEL = `PLL_FBDIV_SEL;
	defparam pll0.IDIV_SEL =  `PLL_IDIV_SEL;
	defparam pll0.ODIV_SEL =  `PLL_ODIV_SEL;
`ifdef PLL_DYN
	defparam pll0.DYN_FBDIV_SEL="true";
	defparam pll0.DYN_IDIV_SEL="true";
`else
	defparam pll0.DYN_FBDIV_SEL="false";
	defparam pll0.DYN_IDIV_SEL="false";
`endif
	defparam pll0.DYN_ODIV_SEL="false";
	defparam pll0.DYN_SDIV_SEL=124;
	defparam pll0.PSDA_SEL="0000";

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

