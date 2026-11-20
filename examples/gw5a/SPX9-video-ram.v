`default_nettype none
module video_ram(
	input wire clk,
	input wire reset,
	input wire wre,
	input wire [8:0]  write_data,
	input wire [10:0] ad,
	output wire [8:0] read_data
);

	wire gnd, vcc;
	assign gnd = 1'b0;
	assign vcc = 1'b1;

	wire [26:0] dummy;

	SPX9 mem(
		.DO({dummy, read_data}),
		.DI({{27{gnd}}, write_data}),
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
	defparam mem.BIT_WIDTH = 9;
	defparam mem.BLK_SEL = 3'b000;
	defparam mem.RESET_MODE = "SYNC";
`include "img-video-ram1.vh"
endmodule

