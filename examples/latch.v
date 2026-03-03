module top (
	input clk,
	input key_i,
	output [`LEDS_NR-1:0] led
);

wire key = key_i ^ `INV_BTN;

reg [25:0] ctr_q;
reg [`LEDS_NR-1:0] latch_q;

// Free-running counter
always @(posedge clk) begin
	ctr_q <= ctr_q + 1'b1;
end

// Latch: update LEDs while key is held, hold value on release
always @*
	if (!key) latch_q <= ctr_q[25:25-(`LEDS_NR - 2)];

assign led = latch_q;

endmodule
