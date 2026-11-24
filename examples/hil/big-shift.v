`default_nettype none

// A long shift register, as the old big-shift and 60k-shift examples ran
// across many LEDs: an LFSR feeds LEN flip-flops in a chain, and a second,
// identical LFSR that starts LEN cycles later predicts the bit at the end.
// The chain has no logic between its flip-flops; the GW5A examples also
// pinned one of them with INS_LOC, which is a board constraint, not tested
// here.
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
			chain <= {chain[LEN-2:0], src[15]};
			if (fill != LEN)
				fill <= fill + 1'b1;
			else begin
				// chain[LEN-1] is src[15] of LEN cycles ago
				pred <= step(pred);
				if (chain[LEN-1] != pred[15]) fail <= 1;
				if (!checked[16]) checked <= checked + 1'b1;
			end
		end

	assign pass[0] = checked[16] && !fail;
endmodule
