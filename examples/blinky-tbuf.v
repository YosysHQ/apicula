module top (
	input clk,
	input key_i,
	output [`LEDS_NR-1:0] led
);

wire key = key_i ^ `INV_BTN;

reg [25:0] ctr_q;
wire [25:0] ctr_d;

// Sequential code (flip-flop)
always @(posedge clk) begin
	ctr_q <= ctr_d;
end

// Combinational code (boolean logic)
assign ctr_d = ctr_q + 1'b1;
assign led[`LEDS_NR - 1:1] = ctr_q[25:25-(`LEDS_NR - 2)];

TBUF tbuf(
	.I(ctr_q[25 - (`LEDS_NR - 1)]),
	.O(led[0]),
	.OEN(~key)
);

endmodule
