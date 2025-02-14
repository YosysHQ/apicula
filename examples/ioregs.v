module top (
	input clk,
	input key_i,
	input rst_i,
	output [`LEDS_NR-1:0] led
);

wire key = key_i ^ `INV_BTN;
wire reset = rst_i ^ `INV_BTN;

reg [25:0] ctr_q;
wire [25:0] ctr_d;

always @(posedge clk) begin
	if (reset) begin
		ctr_q <= ctr_d;
	end
end

reg [`LEDS_NR - 2:0] led_r;
assign led = {ctr_q[25:25], led_r};
assign ctr_d = ctr_q + 1'b1;

always @(posedge clk) begin
	if (!key) begin
		led_r <= ctr_q[25:25-(`LEDS_NR - 2)];
	end
end

endmodule
