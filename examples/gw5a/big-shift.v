`default_nettype none
`define LEDS_NR 24

module top(input wire clk, input wire reset, output wire [23:0]led);
wire tick_hz;

localparam HZ_PRESC = 6_000_000,
		HZ_SIZE = $clog2(HZ_PRESC);

reg [HZ_SIZE-1:0]  hertz_cpt;
wire [HZ_SIZE-1:0]  hertz_cpt_d = hertz_cpt - 1'b1;

always @(posedge clk) begin
	if (tick_hz) begin
		hertz_cpt <= HZ_PRESC;
	end else begin
		hertz_cpt <= hertz_cpt_d;
	end
end


reg [`LEDS_NR-1:0] ctr_q;
wire [`LEDS_NR-1:0] ctr_d;

always @(posedge clk) begin
	if (reset) begin
		ctr_q <= 'd1;
	end else if (tick_hz) begin
		ctr_q <= ctr_d;
	end
end

assign ctr_d = {ctr_q[0], ctr_q[`LEDS_NR-1:1]};
assign led = ~ctr_q;
assign tick_hz = (hertz_cpt == 0);
endmodule

