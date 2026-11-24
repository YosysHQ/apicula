`default_nettype none
// GW5A MULT12X12 (DOUT = A * B, signed, UG305 4.1.1). Rows:
//   0  0x345 * 0x0fd, A/B registered (CLK0)
//   1  -3 * 0x7ff, A/B and output registered on CLK1/RESET1
//   2  -0x800 * -0x800 = 0x400000, every register on (A, B, pipeline, output)
//   3  product 0 [11:0] * [23:12] through the fabric: 0xb31 (-1231) * 0x033
//   4  0x7ff * 0x7ff, no register
// DOUT is 24 bits, shown zero-extended.
module dsp_mult12x12(input wire clk, input wire reset,
	output wire [63:0] product,
	output wire [63:0] product1,
	output wire [63:0] product2,
	output wire [63:0] product3,
	output wire [63:0] product4);

	wire [23:0] d0, d1, d2, d3, d4;
	assign product = {40'b0, d0};
	assign product1 = {40'b0, d1};
	assign product2 = {40'b0, d2};
	assign product3 = {40'b0, d3};
	assign product4 = {40'b0, d4};

	MULT12X12 #(.AREG_CLK("CLK0"), .BREG_CLK("CLK0"), .PREG_CLK("BYPASS"), .OREG_CLK("BYPASS"),
		.MULT_RESET_MODE("ASYNC"))
	m0(.A(12'h345), .B(12'h0fd), .CLK({1'b0, clk}), .CE(2'b11), .RESET({1'b0, reset}), .DOUT(d0));

	MULT12X12 #(.AREG_CLK("CLK1"), .AREG_RESET("RESET1"), .BREG_CLK("CLK1"), .BREG_RESET("RESET1"),
		.PREG_CLK("BYPASS"), .OREG_CLK("CLK1"), .OREG_CE("CE1"), .OREG_RESET("RESET1"),
		.MULT_RESET_MODE("ASYNC"))
	m1(.A(12'hffd), .B(12'h7ff), .CLK({clk, 1'b0}), .CE(2'b11), .RESET({reset, 1'b0}), .DOUT(d1));

	MULT12X12 #(.AREG_CLK("CLK0"), .BREG_CLK("CLK0"), .PREG_CLK("CLK0"), .OREG_CLK("CLK0"),
		.MULT_RESET_MODE("ASYNC"))
	m2(.A(12'h800), .B(12'h800), .CLK({1'b0, clk}), .CE(2'b11), .RESET({1'b0, reset}), .DOUT(d2));

	MULT12X12 #(.AREG_CLK("CLK0"), .BREG_CLK("CLK0"), .PREG_CLK("BYPASS"), .OREG_CLK("BYPASS"),
		.MULT_RESET_MODE("ASYNC"))
	m3(.A(d0[11:0]), .B(d0[23:12]), .CLK({1'b0, clk}), .CE(2'b11), .RESET({1'b0, reset}), .DOUT(d3));

	MULT12X12 #(.AREG_CLK("BYPASS"), .BREG_CLK("BYPASS"), .PREG_CLK("BYPASS"), .OREG_CLK("BYPASS"),
		.MULT_RESET_MODE("ASYNC"))
	m4(.A(12'h7ff), .B(12'h7ff), .CLK({1'b0, clk}), .CE(2'b11), .RESET({1'b0, reset}), .DOUT(d4));
endmodule
