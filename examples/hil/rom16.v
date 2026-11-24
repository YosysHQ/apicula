`default_nettype none

// ROM16 (16x1 LUT ROM) as the old lutram example used it: eight of them
// with that example's contents, read at every address in turn. The expected
// bit comes from a 16-bit register per ROM, loaded with INIT_0 and rotated in
// step with the address.
//
// pass[i]: ROM i matched at every address of at least one full sweep.

module rom16_test (
	input wire clk,
	input wire rst,
	output wire [7:0] pass
);
	localparam [8*16-1:0] INIT = {
		16'b0000110000010000, 16'b0001100000101000,
		16'b0011000001000100, 16'b0110000010010010,
		16'b1100000110010010, 16'b1000001101000100,
		16'b0000001000101000, 16'b0000010000010000};

	reg [3:0] ad;
	reg [8*16-1:0] r;
	reg wrapped;
	reg [7:0] fail;
	wire [7:0] dout;

	genvar i;
	generate
		for (i = 0; i < 8; i = i + 1) begin : g
			ROM16 #(.INIT_0(INIT[16 * i +: 16])) rom(.AD(ad), .DO(dout[i]));
			always @(posedge clk)
				if (rst) begin
					r[16 * i +: 16] <= INIT[16 * i +: 16];
					fail[i] <= 0;
				end else begin
					r[16 * i +: 16] <= {r[16 * i], r[16 * i + 1 +: 15]};
					if (dout[i] != r[16 * i]) fail[i] <= 1;
				end
		end
	endgenerate

	always @(posedge clk)
		if (rst) begin
			ad <= 0;
			wrapped <= 0;
		end else begin
			ad <= ad + 1'b1;
			if (&ad) wrapped <= 1;
		end

	assign pass = {8{wrapped}} & ~fail;
endmodule
