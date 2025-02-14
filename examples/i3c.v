/*
*  Nothing meaningful is tested here other than compilation - a real I3C
*  system requires either a large state machine or an intricate connection to
*  the processor.
*/
module top (
	input clk,
	input key_i,
	input rst_i,
	output [`LEDS_NR-1:0] led,
	inout i3c
);

	wire rst = rst_i ^ `INV_BTN;
	wire key = key_i ^ `INV_BTN;

	reg dat;
	always @(posedge clk) begin
		dat <= ~dat; 
	end

	I3C_IOBUF inst(
		.IO(i3c),
		.O(led[0]),
		.I(dat),
		.MODESEL(key)
	);

endmodule
