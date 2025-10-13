`default_nettype none
module video_ram(
	input wire clk,
	input wire reset,
	input wire write_clk,
	input wire write_reset,
	input wire write_ce,
	input wire [10:0] write_ad,
	input wire [7:0]  write_data,
	input wire [10:0] read_ad,
	output wire [7:0] read_data
);

	wire gnd, vcc;
	assign gnd = 1'b0;
	assign vcc = 1'b1;

	wire [31:0] dummy_w;
	assign read_data = (read_ad[1:0] == 2'b00 ?   dummy_w[7:0] : 8'd0) |
		               (read_ad[1:0] == 2'b01 ?  dummy_w[15:8] : 8'd0) |
					   (read_ad[1:0] == 2'b10 ? dummy_w[23:16] : 8'd0) |
					   (read_ad[1:0] == 2'b11 ? dummy_w[31:24] : 8'd0);

	SDPB mem(
		.DO(dummy_w),
		.DI({{24{gnd}}, write_data}),
		.ADA({write_ad[10:2], gnd, write_ad[1:0] == 2'b11, write_ad[1:0] == 2'b10, write_ad[1:0] == 2'b01, write_ad[1:0] == 2'b00}),
		.ADB({ read_ad[10:2], gnd, gnd, gnd, gnd, gnd}),
		.CLKA(write_clk),
		.CLKB(clk),
		.OCE(vcc),
		.CEA(1'b0/*write_ce*/),
		.CEB(vcc),
		.BLKSELA(3'b000),
		.BLKSELB(3'b000),
		.RESET(reset)
	);
	defparam mem.READ_MODE = 1'b0;
	defparam mem.BIT_WIDTH_0 = 32;
	defparam mem.BIT_WIDTH_1 = 32;
	defparam mem.BLK_SEL_0 = 3'b000;
	defparam mem.BLK_SEL_1 = 3'b000;
	defparam mem.RESET_MODE = "SYNC";
`include "img-video-ram.vh"
endmodule

