/* Pressing the button stops the blinking because no clock source will be selected */
module top (
	input clk,
	input key_i,
	input rst_i,
	output [`LEDS_NR-1:0] led
);

reg [31:0] counter;
reg [31:0] counter2;
wire clk1, clk2;

wire key = key_i ^ `INV_BTN;

DCS dcs(
	.CLK0(1'b1),
	.CLK1(clk),
	.CLK2(1'b1),
	.CLK3(1'b1),
	.CLKSEL({1'b0, 1'b0, key, 1'b0}),
	.SELFORCE(1'b1),
	.CLKOUT(clk1)
);
defparam dcs.DCS_MODE="CLK1_GND";

always @(posedge clk1) begin
    if (counter < 31'd1350_0000)
        counter <= counter + 1;
    else begin
        counter <= 31'd0;
        led[1:0] <= {~led[0],led[1]};
    end
end

endmodule
