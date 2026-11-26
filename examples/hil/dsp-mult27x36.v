`default_nettype none
// GW5A MULT27X36: DOUT = A*B or (A +- D)*B, signed (UG305 4.1.2). Rows (63
// bits, shown zero-extended):
//   0  (0xcafe + 0x10) * 2 (the old example), A/B/D and output registered
//   1  -2^26 * (2^35 - 1), no pre-adder
//   2  (5 - (-1)) * -3 = -18, pre-subtraction, every register on CLK1
//   3  (row 0 [26:0] + 0x10) * 2 through the fabric
module dsp_mult27x36(input wire clk, input wire reset,
	output wire [63:0] product,
	output wire [63:0] product1,
	output wire [63:0] product2,
	output wire [63:0] product3,
	output wire [63:0] product4);

	wire [62:0] d0, d1, d2, d3;
	assign product = {1'b0, d0};
	assign product1 = {1'b0, d1};
	assign product2 = {1'b0, d2};
	assign product3 = {1'b0, d3};
	assign product4 = 64'b0;

	MULT27X36 #(.AREG_CLK("CLK0"), .BREG_CLK("CLK0"), .DREG_CLK("CLK0"), .OREG_CLK("CLK0"),
		.MULT_RESET_MODE("ASYNC"), .DYN_P_SEL("FALSE"), .P_SEL(1'b1), .DYN_P_ADDSUB("FALSE"), .P_ADDSUB(1'b0))
	p0(.A(27'hcafe), .B(36'd2), .D(26'h10), .PSEL(1'b0), .PADDSUB(1'b0),
		.CLK({1'b0, clk}), .CE(2'b11), .RESET({1'b0, reset}), .DOUT(d0));

	MULT27X36 #(.AREG_CLK("CLK0"), .BREG_CLK("CLK0"), .OREG_CLK("CLK0"),
		.MULT_RESET_MODE("ASYNC"), .DYN_P_SEL("FALSE"), .P_SEL(1'b0), .DYN_P_ADDSUB("FALSE"), .P_ADDSUB(1'b0))
	p1(.A(27'h4000000), .B(36'h7ffffffff), .D(26'h0), .PSEL(1'b0), .PADDSUB(1'b0),
		.CLK({1'b0, clk}), .CE(2'b11), .RESET({1'b0, reset}), .DOUT(d1));

	MULT27X36 #(.AREG_CLK("CLK1"), .AREG_RESET("RESET1"), .BREG_CLK("CLK1"), .BREG_RESET("RESET1"),
		.DREG_CLK("CLK1"), .DREG_RESET("RESET1"), .PREG_CLK("CLK1"), .PREG_RESET("RESET1"),
		.OREG_CLK("CLK1"), .OREG_RESET("RESET1"),
		.MULT_RESET_MODE("ASYNC"), .DYN_P_SEL("FALSE"), .P_SEL(1'b1), .DYN_P_ADDSUB("FALSE"), .P_ADDSUB(1'b1))
	p2(.A(27'd5), .B(36'hffffffffd), .D(26'h3ffffff), .PSEL(1'b0), .PADDSUB(1'b0),
		.CLK({clk, 1'b0}), .CE(2'b11), .RESET({reset, 1'b0}), .DOUT(d2));

	MULT27X36 #(.AREG_CLK("CLK0"), .BREG_CLK("CLK0"), .DREG_CLK("CLK0"), .OREG_CLK("CLK0"),
		.MULT_RESET_MODE("ASYNC"), .DYN_P_SEL("FALSE"), .P_SEL(1'b1), .DYN_P_ADDSUB("FALSE"), .P_ADDSUB(1'b0))
	p3(.A(d0[26:0]), .B(36'd2), .D(26'h10), .PSEL(1'b0), .PADDSUB(1'b0),
		.CLK({1'b0, clk}), .CE(2'b11), .RESET({1'b0, reset}), .DOUT(d3));
endmodule
