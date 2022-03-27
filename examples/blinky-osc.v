module top (
	output [`LEDS_NR-1:0] led
);

wire clk;

`ifdef OSC_TYPE_OSC
OSC osc(
	.OSCOUT(clk)
);
`elsif OSC_TYPE_OSCZ
OSCZ osc(
	.OSCEN(1'b1),
	.OSCOUT(clk)
);
`elsif OSC_TYPE_OSCF
OSCF osc(
	.OSCEN(1'b1),
	.OSCOUT(clk),
	.OSCOUT30M()
);
`elsif OSC_TYPE_OSCH
OSCH osc(
	.OSCOUT(clk)
);
`endif
defparam osc.FREQ_DIV=128;

reg [25:0] ctr_q;
wire [25:0] ctr_d;

// Sequential code (flip-flop)
always @(posedge clk)
	ctr_q <= ctr_d;

// Combinational code (boolean logic)
assign ctr_d = ctr_q + 1'b1;
assign led = ctr_q[25:25-(`LEDS_NR - 1)];

endmodule
