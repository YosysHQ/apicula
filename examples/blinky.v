module top (
	input clk,
	output reg [7:0] led
);

reg [25:0] ctr_q;
wire [25:0] ctr_d;

// Sequential code (flip-flop)
always @(posedge clk)
	ctr_q <= ctr_d;

// Combinational code (boolean logic)
assign ctr_d = ctr_q + 1'b1;
assign led = ctr_q[25:18];

endmodule
