/* Pressing the button stops the blinking of one or another group of LEDs */
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
wire key1 = rst_i ^ `INV_BTN;

DQCE dqce(
	.CLKIN(clk),
	.CE(key),
	.CLKOUT(clk1)
);

DQCE dqce2(
	.CLKIN(clk),
	.CE(key1),
	.CLKOUT(clk2)
);

always @(posedge clk1) begin
    if (counter < 31'd1350_0000)
        counter <= counter + 1;
    else begin
        counter <= 31'd0;
        led[1:0] <= {~led[0],led[1]};
    end
end

always @(posedge clk2) begin
    if (counter2 < 31'd1350_0000)
        counter2 <= counter2 + 1;
    else begin
        counter2 <= 31'd0;
        led[2] <= ~led[2];
    end
end

endmodule
