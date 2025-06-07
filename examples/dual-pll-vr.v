`default_nettype none
`include "pll/pllvr.v"
// Two PLLs, one dynamic - frequencies are switched by pressing key2
//                           / press key2
// led[0] - pin 34 - 58.5MHz / 90MHz 
// led[1] - pin 35 - LOCK PLL_0
// led[2] - pin 29 - 464KHz  / 714KHz
//
// led[3] - pin 30 - 90MHz
// led[4] - pin 31 - LOCK PLL_1
// led[5] - pin 32 - 714KHz
module top(input wire clk, output wire [5:0]led, input wire key_i);
	wire gnd;
	assign gnd = 1'b0;
	wire dummy;
	reg [5:0] fdiv;
	reg [5:0] idiv;
	reg [5:0] odiv;
    Gowin_PLLVR rpll_0(
        .clkout(led[0]),
        .clkin(clk),
		.lock_o(led[1]),
		.reset(gnd),
		.reset_p(gnd),
		.clkfb(gnd),
		.clkoutd_o(led[2]),
		.fdiv(fdiv),
		.idiv(idiv),
		.odiv(6'b111100) // 8
        );

    Gowin_PLLVR rpll_1(
        .clkout(led[3]),
        .clkin(clk),
		.lock_o(led[4]),
		.reset(gnd),
		.reset_p(gnd),
		.clkfb(gnd),
		.clkoutd_o(led[5]),
		.fdiv(~6'd9),
		.idiv(~6'd2),
		.odiv(6'b111100) // 8
        );

	// dynamic
	always @ (posedge clk) begin
		if (key_i) begin
			fdiv <= ~6'd12;
			idiv <= ~6'd5;
			odiv <= 6'b111000; // 16
		end else begin
			fdiv <= ~6'd9;
			idiv <= ~6'd2;
			odiv <= ~6'b111100; // 8
		end
	end
endmodule
