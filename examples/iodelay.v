/* */
module top (
    input clk,
	input key_i,
	input rst_i,
	input data_i,
	input fclk_i,
	input LCD_CLK,
	input LCD_SYNC,
	output [5:0] led
);


IODELAY id0(
	.DO(led[0]),
	.DI(rst_i),
	.DF(led[1]),
	.SDTAP(data_i),
	.SETN(fclk_i),
	.VALUE(key_i)
);
defparam id0.C_STATIC_DLY='d96;

IODELAY od1(
	.DO(led[2]),
	.DI(LCD_CLK),
	.DF(led[3]),
	.SDTAP(data_i),
	.SETN(fclk_i),
	.VALUE(key_i)
);
defparam od1.C_STATIC_DLY='d63;

endmodule

