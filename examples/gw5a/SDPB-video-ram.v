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

	wire [23:0] dummy_w;

	SDPB mem(
		.DO({dummy_w, read_data}),
		.DI({{24{gnd}}, write_data}),
		.ADA({write_ad, gnd, gnd, gnd}),
		.ADB({ read_ad, gnd, gnd, gnd}),
		.CLKA(write_clk),
		.CLKB(clk),
		.OCE(vcc),
		.CEA(write_ce),
		.CEB(vcc),
		.BLKSELA(3'b000),
		.BLKSELB(3'b000),
		.RESET(reset)
	);
	defparam mem.READ_MODE = 1'b0;
	defparam mem.BIT_WIDTH_0 = 8;
	defparam mem.BIT_WIDTH_1 = 8;
	defparam mem.BLK_SEL_0 = 3'b000;
	defparam mem.BLK_SEL_1 = 3'b000;
	defparam mem.RESET_MODE = "SYNC";
`include "img-video-ram.vh"
endmodule

