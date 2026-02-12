/* DLLDLY example: delay the input clock using the delay line module */
module top (
	input clk,
	input key_i,
	input rst_i,
	output [`LEDS_NR-1:0] led
);

wire delayed_clk;

wire key = key_i ^ `INV_BTN;

DLLDLY dlldly_inst (
	.CLKIN(clk),
	.CLKOUT(delayed_clk),
	.DLLSTEP(8'b0),
	.DIR(1'b0),
	.LOADN(1'b1),
	.MOVE(1'b0),
	.FLAG()
);
defparam dlldly_inst.DLL_INSEL = 1'b1;
defparam dlldly_inst.DLY_SIGN = 1'b0;
defparam dlldly_inst.DLY_ADJ = 8'd5;

reg [31:0] counter;

always @(posedge delayed_clk) begin
    if (counter < 31'd1350_0000)
        counter <= counter + 1;
    else begin
        counter <= 31'd0;
        led[1:0] <= {~led[0], led[1]};
    end
end

endmodule
