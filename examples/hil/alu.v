`default_nettype none

// Carry chains (ALU primitives, from +, - and <) against bit-serial adders.
// The expected sums are built one bit per cycle in flip-flops: a combinational
// gate-level adder gets proven equal to the ALUs by synthesis and the checks
// fold away. The old alu-simple example added a constant with its low bit
// set: add8c1 is that case (a constant carry in).
//
// 8-bit operands sweep all 65536 pairs; the 32-bit operands come from two
// LFSRs. Each pair is held for STEP cycles while the serial adders run, and
// compared in the last one.
//
// pass[0] a + b (9-bit sum), [1] a - b (9-bit, bit 8 the borrow), [2] a + b + 1
// (constant carry in), [3] a < b, [4] 32-bit a + b (33-bit), [5] 32-bit a - b,
// [6] the 8-bit sweep finished.

// x + y + cin over 33 bits, one bit per cycle with en after load
module alu_serial_add (
	input wire clk,
	input wire load,
	input wire en,
	input wire [32:0] x,
	input wire [32:0] y,
	input wire cin,
	output reg [32:0] sum
);
	reg [32:0] sx, sy;
	reg c;
	wire s = sx[0] ^ sy[0] ^ c;
	always @(posedge clk)
		if (load) begin
			sx <= x;
			sy <= y;
			c <= cin;
		end else if (en) begin
			sx <= sx >> 1;
			sy <= sy >> 1;
			c <= (sx[0] & sy[0]) | (c & (sx[0] ^ sy[0]));
			sum <= {s, sum[32:1]};
		end
endmodule

module alu_test (
	input wire clk,
	input wire rst,
	output wire [6:0] pass
);
	localparam STEP = 40;  // load, 33 serial steps, margin

	reg [5:0] ph;
	reg [15:0] ab;
	reg [31:0] la, lb;
	reg swept;
	always @(posedge clk)
		if (rst) begin
			ph <= 0;
			ab <= 0;
			la <= 32'h12345678;
			lb <= 32'hfedcba98;
			swept <= 0;
		end else begin
			ph <= ph == STEP - 1 ? 6'd0 : ph + 1'b1;
			if (ph == STEP - 1) begin
				ab <= ab + 1'b1;
				if (&ab) swept <= 1;
				// Galois LFSRs, x^32 + x^22 + x^2 + x + 1
				la <= {1'b0, la[31:1]} ^ (la[0] ? 32'h80200003 : 32'h0);
				lb <= {1'b0, lb[31:1]} ^ (lb[0] ? 32'h80200003 : 32'h0);
			end
		end

	wire [7:0] a = ab[15:8], b = ab[7:0];

	// Under test: Yosys maps these to ALUs
	wire [8:0] add8 = a + b;
	wire [8:0] sub8 = {1'b0, a} - {1'b0, b};
	wire [8:0] add8c1 = a + b + 9'd1;
	wire lt8 = a < b;
	wire [32:0] add32 = la + lb;
	wire [32:0] sub32 = {1'b0, la} - {1'b0, lb};

	// Expected: subtraction as x + ~y + 1
	wire load = ph == 0;
	wire en = ph >= 1 && ph <= 33;
	wire [32:0] e_add8, e_sub8, e_add8c1, e_add32, e_sub32;
	alu_serial_add s0(.clk(clk), .load(load), .en(en), .x({25'b0, a}), .y({25'b0, b}), .cin(1'b0), .sum(e_add8));
	alu_serial_add s1(.clk(clk), .load(load), .en(en), .x({25'b0, a}), .y(~{25'b0, b}), .cin(1'b1), .sum(e_sub8));
	alu_serial_add s2(.clk(clk), .load(load), .en(en), .x({25'b0, a}), .y({25'b0, b}), .cin(1'b1), .sum(e_add8c1));
	alu_serial_add s3(.clk(clk), .load(load), .en(en), .x({1'b0, la}), .y({1'b0, lb}), .cin(1'b0), .sum(e_add32));
	alu_serial_add s4(.clk(clk), .load(load), .en(en), .x({1'b0, la}), .y(~{1'b0, lb}), .cin(1'b1), .sum(e_sub32));

	reg [5:0] fail;
	reg seen;
	always @(posedge clk)
		if (rst) begin
			fail <= 0;
			seen <= 0;
		end else if (ph == STEP - 1) begin
			seen <= 1;
			if (add8 != e_add8[8:0]) fail[0] <= 1;
			if (sub8 != e_sub8[8:0]) fail[1] <= 1;
			if (add8c1 != e_add8c1[8:0]) fail[2] <= 1;
			if (lt8 != e_sub8[8]) fail[3] <= 1;
			if (add32 != e_add32) fail[4] <= 1;
			if (sub32 != e_sub32) fail[5] <= 1;
		end

	assign pass = {swept, {6{seen}} & ~fail};
endmodule
