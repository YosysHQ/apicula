`default_nettype none

// A long shift register, as the old big-shift and 60k-shift examples ran
// across many LEDs: an LFSR feeds LEN flip-flops in a chain, and a second,
// identical LFSR that starts LEN cycles later predicts the bit at the end.
// The chain has no logic between its flip-flops.
//
// GW5AT_60B (tangconsole60k, build-only): the chain starts with 15 flip-flops
// pinned with BEL across the clock spine regions of the GW5AT-60B, at the
// sites of the old 60k-shift example (see its diagram in git history).
//
// pass[0]: the end of the chain matched for at least one full LFSR period
// (2^16 - 1 cycles) after it filled.

module big_shift_test #(
	parameter LEN = 1024
) (
	input wire clk,
	input wire rst,
	output wire [0:0] pass
);
	function [15:0] step(input [15:0] s);
		// Fibonacci LFSR x^16 + x^14 + x^13 + x^11 + 1, maximal length
		step = {s[14:0], s[15] ^ s[13] ^ s[12] ^ s[10]};
	endfunction

	reg [15:0] src, pred;
	reg [LEN-1:0] chain;
`ifdef GW5AT_60B
	localparam PIN = 15;
	wire [PIN:0] tap;
	assign tap[0] = src[15];
	(* BEL="X1Y71/DFF0" *)   DFFSE p0(.D(tap[0]), .Q(tap[1]), .CE(1'b1), .SET(rst), .CLK(clk));
	(* BEL="X72Y71/DFF0" *)  DFFRE p1(.D(tap[1]), .Q(tap[2]), .CE(1'b1), .RESET(rst), .CLK(clk));
	(* BEL="X2Y48/DFF1" *)   DFFRE p2(.D(tap[2]), .Q(tap[3]), .CE(1'b1), .RESET(rst), .CLK(clk));
	(* BEL="X72Y48/DFF2" *)  DFFRE p3(.D(tap[3]), .Q(tap[4]), .CE(1'b1), .RESET(rst), .CLK(clk));
	(* BEL="X74Y71/DFF3" *)  DFFRE p4(.D(tap[4]), .Q(tap[5]), .CE(1'b1), .RESET(rst), .CLK(clk));
	(* BEL="X145Y71/DFF4" *) DFFRE p5(.D(tap[5]), .Q(tap[6]), .CE(1'b1), .RESET(rst), .CLK(clk));
	(* BEL="X74Y40/DFF5" *)  DFFRE p6(.D(tap[6]), .Q(tap[7]), .CE(1'b1), .RESET(rst), .CLK(clk));
	(* BEL="X145Y40/DFF0" *) DFFRE p7(.D(tap[7]), .Q(tap[8]), .CE(1'b1), .RESET(rst), .CLK(clk));
	(* BEL="X3Y36/DFF7" *)   DFFRE p8(.D(tap[8]), .Q(tap[9]), .CE(1'b1), .RESET(rst), .CLK(clk));
	(* BEL="X72Y36/DFF2" *)  DFFRE p9(.D(tap[9]), .Q(tap[10]), .CE(1'b1), .RESET(rst), .CLK(clk));
	(* BEL="X74Y11/DFF3" *)  DFFRE p10(.D(tap[10]), .Q(tap[11]), .CE(1'b1), .RESET(rst), .CLK(clk));
	(* BEL="X95Y17/DFF4" *)  DFFRE p11(.D(tap[11]), .Q(tap[12]), .CE(1'b1), .RESET(rst), .CLK(clk));
	(* BEL="X74Y21/DFF5" *)  DFFRE p12(.D(tap[12]), .Q(tap[13]), .CE(1'b1), .RESET(rst), .CLK(clk));
	(* BEL="X130Y26/DFF6" *) DFFRE p13(.D(tap[13]), .Q(tap[14]), .CE(1'b1), .RESET(rst), .CLK(clk));
	(* BEL="X74Y30/DFF7" *)  DFFRE p14(.D(tap[14]), .Q(tap[15]), .CE(1'b1), .RESET(rst), .CLK(clk));
	wire chain_in = tap[PIN];
`else
	localparam PIN = 0;
	wire chain_in = src[15];
`endif
	reg [10:0] fill;   // cycles until the chain is full
	reg [16:0] checked;
	reg fail;

	always @(posedge clk)
		if (rst) begin
			src <= 16'hace1;
			pred <= 16'hace1;
			fill <= 0;
			checked <= 0;
			fail <= 0;
		end else begin
			src <= step(src);
			chain <= {chain[LEN-2:0], chain_in};
			if (fill != LEN + PIN)
				fill <= fill + 1'b1;
			else begin
				// chain[LEN-1] is src[15] of LEN + PIN cycles ago
				pred <= step(pred);
				if (chain[LEN-1] != pred[15]) fail <= 1;
				if (!checked[16]) checked <= checked + 1'b1;
			end
		end

	assign pass[0] = checked[16] && !fail;
endmodule
