module top (
	input clk,
	input rst_i,
	output [`LEDS_NR-1:0] led
);

wire rst = rst_i ^ `INV_BTN;
wire rst_s;
wire tick_hz;

localparam HZ_PRESC = 12_000_000,
		HZ_SIZE = $clog2(HZ_PRESC);

reg [HZ_SIZE-1:0]  hertz_cpt;
wire [HZ_SIZE-1:0]  hertz_cpt_d = hertz_cpt - 1'b1;

always @(posedge clk) begin
	/* 1Hz clk */
	if (tick_hz) begin
		hertz_cpt <= HZ_PRESC;
	end else begin
		hertz_cpt <= hertz_cpt_d;
	end
end


reg [`LEDS_NR-1:0] ctr_q;
wire [`LEDS_NR-1:0] ctr_d;

// Sequential code (flip-flop)
always @(posedge clk or posedge rst_s) begin
	if (rst_s) begin
		ctr_q <= 'd1;
	end else if (tick_hz) begin
		ctr_q <= ctr_d;
	end
end

// Combinational code (boolean logic)
assign ctr_d = {ctr_q[0], ctr_q[`LEDS_NR-1:1]};
assign led = ctr_q;
assign tick_hz = (hertz_cpt == 0);
assign rst_s = !rst;

endmodule
