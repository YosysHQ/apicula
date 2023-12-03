`default_nettype none
module video_ram(
	input wire clk,
	input wire reset,
	input wire wre,
	input wire [7:0]  write_data,
	input wire [10:0] ad,
	output wire [7:0] read_data
);

	wire gnd, vcc;
	assign gnd = 1'b0;
	assign vcc = 1'b1;

	wire [23:0] dummy;

	SP mem(
		.DO({dummy, read_data}),
		.DI({{24{gnd}}, write_data}),
		.AD({ad, gnd, gnd, gnd}),
		.CLK(clk),
		.CE(vcc),
		.WRE(wre),
		.OCE(vcc),
		.BLKSEL(3'b000),
		.RESET(reset)
	);
	defparam mem.READ_MODE = 1'b1;
	defparam mem.WRITE_MODE = 2'b01;
	defparam mem.BIT_WIDTH = 8;
	defparam mem.BLK_SEL = 3'b000;
	defparam mem.RESET_MODE = "SYNC";
`include "img-video-ram.vh"
endmodule

