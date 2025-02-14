module top (
	input clk,
	input key_i,
	input rst_i,
	output [`LEDS_NR-1:0] led,
	output [1:0] mipi_out
);

wire key = key_i ^ `INV_BTN;
wire reset = rst_i ^ `INV_BTN;

reg [25:0] ctr_q;
wire [25:0] ctr_d;

always @(posedge clk) begin
	ctr_q <= ctr_d;
end

assign ctr_d = ctr_q + 1'b1;

MIPI_OBUF mipio(
	.I(ctr_d[25]),
	.IB(ctr_d[24]),
	.O(mipi_out[0]),
	.OB(mipi_out[1]),
	.MODESEL(key)
);

endmodule
