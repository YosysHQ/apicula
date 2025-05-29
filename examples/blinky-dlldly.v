module top (
	input clk,
	input key_i,
	output [2:0] led
);

wire key = key_i ^ `INV_BTN;

reg [25:0] ctr_q;
wire [25:0] ctr_d;

wire o_clk, flag;
DLLDLY dll0 (
    .CLKIN(clk),
    .DLLSTEP(8'b10101010),
    .DIR(1'b0),
    .LOADN(1'b0),
    .MOVE(1'b1),
    .CLKOUT(o_clk),
    .FLAG(flag)
);
defparam dll0.DLL_INSEL=1'b1;
defparam dll0.DLY_SIGN=1'b1;
defparam dll0.DLY_ADJ=8'd255;

assign led[2] = ~flag;
assign led[0] = clk;
assign led[1] = o_clk;

/*
// Sequential code (flip-flop)
always @(posedge o_clk) begin
	if (key) begin
		ctr_q <= ctr_d;
	end
end

// Combinational code (boolean logic)
assign ctr_d = ctr_q + 1'b1;
assign led[1:0] = ctr_q[25:25-(`LEDS_NR - 2)];
*/

endmodule
