/*
* led[0] is connected directly, led[1] --- via ODDR. This primitive needs 4 clock cycles to start working, so be patient:)
*/
module top (
	input clk,
	output [`LEDS_NR-1:0] led
);

reg [24:0] ctr_q;
wire [24:0] ctr_d;

// Sequential code (flip-flop)
always @(posedge clk)
	ctr_q <= ctr_d;

// Combinational code (boolean logic)
assign ctr_d = ctr_q + 1'b1;
assign led[`LEDS_NR-1:2] = {(`LEDS_NR - 2){1'b1}};
assign led[0] = ctr_q[24:24];

ODDR oddr_0(
	.D0(1'b0),
	.D1(1'b1),
	.CLK(ctr_q[24:24]),
	.Q0(led[1]),
	.Q1(),
	.TX()
);

endmodule
