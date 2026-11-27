`default_nettype none

// An input register in a pad's I/O logic (YosysHQ/apicula#668). The test
// drives a free, harmless pad through an IOBUF and reads it back through the
// same pad's input buffer into a flip-flop that IOBFF makes nextpnr pack into
// the pad's IOLOGIC (the per-cell form of --vopt ioreg_in_iob). The register
// must follow the driven value.
//
// The pad changes every 8 clocks and is checked only in the last two of them,
// so that the delay through the pad does not count: the test is about the
// register. Checks start 1024 clocks after reset: on the Primer 25K the pad
// read 1 for about the first 40 clocks, whatever was driven.
//
// pass[0] the register never disagreed with the driven value, [1] it read a 1,
// [2] it read a 0. #668 shows as 0x4: stuck at 0.
module iob_ireg_test (
	input wire clk,
	input wire rst,
	inout wire pad,
	output wire [2:0] pass
);
	reg [10:0] cnt;
	always @(posedge clk)
		cnt <= rst ? 11'd0 : cnt + 1'b1;
	wire drv = cnt[3];

	wire in;
	(* IOBFF *)
	IOBUF iob (.I(drv), .OEN(1'b0), .O(in), .IO(pad));

	reg q;  // packed into the IOLOGIC
	always @(posedge clk)
		q <= rst ? 1'b0 : in;

	reg warm, bad, one, zero;
	always @(posedge clk)
		if (rst) begin
			warm <= 0;
			bad <= 0;
			one <= 0;
			zero <= 0;
		end else begin
			if (cnt[10]) warm <= 1;
			if (warm && cnt[2:1] == 2'b11) begin
				if (q != drv) bad <= 1;
				if (q) one <= 1;
				else zero <= 1;
			end
		end
	assign pass = {zero, one, !bad};
endmodule
