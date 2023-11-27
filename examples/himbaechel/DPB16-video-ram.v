`default_nettype none
module video_ram(
	input wire clk,
	input wire reset,
	input wire write_clk,
	input wire write_reset,
	input wire write_ce,
	input wire read_wre,
	input wire [9:0] write_ad,
	input wire [15:0]  write_data,
	input wire   [9:0] read_ad,
	output wire [15:0] read_data
);

	wire gnd, vcc;
	assign gnd = 1'b0;
	assign vcc = 1'b1;

	wire [15:0] dummy;

	DPB mem(
		.DOB({read_data}),
		.DIA({write_data}),
		.DIB({16{gnd}}),
		.ADA({write_ad, gnd, gnd, vcc, vcc}),
		.ADB({ read_ad, gnd, gnd, vcc, vcc}),
		.CLKA(write_clk),
		.CLKB(clk),
		.OCEA(gnd),
		.OCEB(gnd),
		.CEA(write_ce),
		.CEB(vcc),
		.WREA(vcc),
		.WREB(read_wre),
		.BLKSELA(3'b000),
		.BLKSELB(3'b000),
		.RESETA(write_reset),
		.RESETB(reset)
	);
	defparam mem.READ_MODE0 = 1'b0;
	defparam mem.READ_MODE1 = 1'b0;
	defparam mem.WRITE_MODE0 = 2'b01;
	defparam mem.WRITE_MODE1 = 2'b01;
	defparam mem.BIT_WIDTH_0 = 16;
	defparam mem.BIT_WIDTH_1 = 16;
	defparam mem.BLK_SEL_0 = 3'b000;
	defparam mem.BLK_SEL_1 = 3'b000;
	defparam mem.RESET_MODE = "SYNC";
`include "img-video-ram.vh"
endmodule

