`default_nettype none

// Wide LUTs built by hand: two 8-input functions, each from 16 LUT4s and
// the MUX2_LUT5 .. MUX2_LUT8 tree (O = S0 ? I1 : I0), as the old lut8 example
// did with buttons. A counter sweeps all 256 inputs; the expected bit comes
// from a 256-bit register loaded with the truth table and rotated in step
// with the counter, so the check uses flip-flops only, not LUTs.
//
// pass[i]: function i matched on every input of at least one full sweep.

module lut8_tree #(
	parameter [255:0] T = 0
) (
	input wire [7:0] x,
	output wire f
);
	wire [15:0] l4;
	wire [7:0] l5;
	wire [3:0] l6;
	wire [1:0] l7;

	genvar i;
	generate
		for (i = 0; i < 16; i = i + 1) begin : g4
			LUT4 #(.INIT(T[16 * i +: 16])) lut(.I0(x[0]), .I1(x[1]), .I2(x[2]), .I3(x[3]), .F(l4[i]));
		end
		for (i = 0; i < 8; i = i + 1) begin : g5
			MUX2_LUT5 mux(.I0(l4[2 * i]), .I1(l4[2 * i + 1]), .S0(x[4]), .O(l5[i]));
		end
		for (i = 0; i < 4; i = i + 1) begin : g6
			MUX2_LUT6 mux(.I0(l5[2 * i]), .I1(l5[2 * i + 1]), .S0(x[5]), .O(l6[i]));
		end
		for (i = 0; i < 2; i = i + 1) begin : g7
			MUX2_LUT7 mux(.I0(l6[2 * i]), .I1(l6[2 * i + 1]), .S0(x[6]), .O(l7[i]));
		end
	endgenerate
	MUX2_LUT8 mux8(.I0(l7[0]), .I1(l7[1]), .S0(x[7]), .O(f));
endmodule

module lut8_test (
	input wire clk,
	input wire rst,
	output wire [1:0] pass
);
	// Random tables (Python random.seed(5), getrandbits(256) twice)
	localparam [255:0] T0 = 256'hd76d4330f1446beab0c11fdecb91ce375bc8fbbcbde5c0994164d8399f767c45;
	localparam [255:0] T1 = 256'hc6a5387777330bdbd7210dff076ce2ef87b0b125ec1d7da0a6eb8c9ebd69fe29;

	reg [7:0] x;
	reg [255:0] r0, r1;  // r[0] = T[x]
	reg wrapped;
	always @(posedge clk)
		if (rst) begin
			x <= 0;
			r0 <= T0;
			r1 <= T1;
			wrapped <= 0;
		end else begin
			x <= x + 1'b1;
			r0 <= {r0[0], r0[255:1]};
			r1 <= {r1[0], r1[255:1]};
			if (&x) wrapped <= 1;
		end

	wire f0, f1;
	lut8_tree #(.T(T0)) t0(.x(x), .f(f0));
	lut8_tree #(.T(T1)) t1(.x(x), .f(f1));

	reg [1:0] fail;
	always @(posedge clk)
		if (rst)
			fail <= 0;
		else begin
			if (f0 != r0[0]) fail[0] <= 1;
			if (f1 != r1[0]) fail[1] <= 1;
		end

	assign pass = {2{wrapped}} & ~fail;
endmodule
