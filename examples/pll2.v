`default_nettype none
// Two PLLs, one dynamic - frequencies are switched by pressing key
//                           / key is pressed
// PLL_0_CLKOUT  - 58.5MHz / 90MHz 
// PLL_0_LOCK    - PLL_0_LOCK
// PLL_0_CLKUOTD - 464KHz  / 714KHz
// 
// PLL_1_CLKOUT  - 90MHz
// PLL_1_LOCK    - PLL_1_LOCK
// PLL_1_CLKOUTD - 714KHz
module top(input wire clk, 
	       output `PLL_0_CLKOUT, 
	       output `PLL_0_CLKOUTD, 
	       output `PLL_0_LOCK, 
	       output `PLL_1_CLKOUT, 
	       output `PLL_1_CLKOUTD, 
	       output `PLL_1_LOCK, 
		   input wire rst, input wire key);
	wire gnd;
	assign gnd = 1'b0;
	wire dummy;
	reg [5:0] fdiv;
	reg [5:0] idiv;
    Gowin_rPLL rpll_0(
        .clkout(`PLL_0_CLKOUT),
        .clkin(clk),
		.lock_o(`PLL_0_LOCK),
		.reset(gnd),
		.reset_p(gnd),
		.clkfb(gnd),
		.clkoutd_o(`PLL_0_CLKOUTD),
		.fdiv(fdiv),
		.idiv(idiv)
        );
	defparam rpll_0.DEVICE = `PLL_DEVICE;
	defparam rpll_0.FCLKIN = `PLL_FCLKIN;
	defparam rpll_0.ODIV_SEL =  `PLL_ODIV_SEL;
	defparam rpll_0.DYN_FBDIV_SEL = "true";
	defparam rpll_0.DYN_IDIV_SEL = "true";
	defparam rpll_0.DYN_ODIV_SEL = "false";
	defparam rpll_0.DYN_SDIV_SEL = 124;

    Gowin_rPLL rpll_1(
        .clkout(`PLL_1_CLKOUT),
        .clkin(clk),
		.lock_o(`PLL_1_LOCK),
		.reset(gnd),
		.reset_p(gnd),
		.clkfb(gnd),
		.clkoutd_o(`PLL_1_CLKOUTD),
		.fdiv(~6'd`PLL_FBDIV_SEL_1),
		.idiv(~6'd`PLL_IDIV_SEL_1)
        );
	defparam rpll_1.DEVICE = `PLL_DEVICE;
	defparam rpll_1.FCLKIN = `PLL_FCLKIN;
	defparam rpll_1.ODIV_SEL =  `PLL_ODIV_SEL;
	defparam rpll_1.DYN_FBDIV_SEL = "true";
	defparam rpll_1.DYN_IDIV_SEL = "true";
	defparam rpll_1.DYN_ODIV_SEL = "false";
	defparam rpll_1.DYN_SDIV_SEL = 124;

	// dynamic
	always @ (posedge clk) begin
		if (key) begin
			fdiv <= ~6'd`PLL_FBDIV_SEL;
			idiv <= ~6'd`PLL_IDIV_SEL;
		end else begin
			fdiv <= ~6'd`PLL_FBDIV_SEL_1;
			idiv <= ~6'd`PLL_IDIV_SEL_1;
		end
	end
endmodule
