/*
* led[0] is connected directly, led[1] --- via ODDR. This primitive needs 4 clock cycles to start working, so be patient:)
*/
module top (
	input clk,
	input key_i,
	input rst_i,
	output [`LEDS_NR-1:0] led
);

wire key = key_i ^ `INV_BTN;
wire rst = rst_i ^ `INV_BTN;

reg [24:0] ctr_q;
wire [24:0] ctr_d;

// Sequential code (flip-flop)
always @(posedge clk) begin
	if (rst) begin
		ctr_q <= ctr_d;
	end
end

// Combinational code (boolean logic)
assign ctr_d = ctr_q + 1'b1;
assign led[`LEDS_NR-1:2] = {(`LEDS_NR - 2){1'b1}};
assign led[0] = ctr_q[24:24];

wire aux_wire;

IODELAY delay0(
	.DI(aux_wire),
	.DO(led[1]),
	.SDTAP(1'b0),
	.SETN(1'b1),
	.VALUE(1'b0),
	.DF()
);
defparam delay0.C_STATIC_DLY=100;

ODDRC oddr_0(
	.D0(1'b0),
	.D1(1'b1),
	.CLK(ctr_q[24:24]),
	.Q0(aux_wire),
	.Q1(),
	.TX(1'b1),
	.CLEAR(!key)
);

endmodule
