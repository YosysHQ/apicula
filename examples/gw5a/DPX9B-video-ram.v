`default_nettype none
module video_ram(
	input wire clk,
	input wire reset,
	input wire write_clk,
	input wire write_reset,
	input wire write_ce,
	input wire read_wre,
	input wire [10:0] write_ad,
	input wire [8:0]  write_data,
	input wire   [10:0] read_ad,
	output wire [8:0] read_data
);

	wire gnd, vcc;
	assign gnd = 1'b0;
	assign vcc = 1'b1;

	wire [8:0] dummy;

	DPX9B mem(
		.DOB({dummy, read_data}),
		.DIA({{9{gnd}},write_data}),
		.DIB({18{gnd}}),
		.ADA({write_ad, gnd, gnd, gnd}),
		.ADB({ read_ad, gnd, gnd, gnd}),
		.CLKA(write_clk),
		.CLKB(clk),
		.OCEA(vcc),
		.OCEB(vcc),
		.CEA(write_ce),
		.CEB(vcc),
		.WREA(vcc),
		.WREB(read_wre),
		.BLKSELA(3'b000),
		.BLKSELB(3'b000),
		.RESETA(write_reset),
		.RESETB(reset)
	);
	defparam mem.READ_MODE0 = 1'b1;
	defparam mem.READ_MODE1 = 1'b1;
	defparam mem.WRITE_MODE0 = 2'b01;
	defparam mem.WRITE_MODE1 = 2'b01;
	defparam mem.BIT_WIDTH_0 = 9;
	defparam mem.BIT_WIDTH_1 = 9;
	defparam mem.BLK_SEL_0 = 3'b000;
	defparam mem.BLK_SEL_1 = 3'b000;
	defparam mem.RESET_MODE = "SYNC";
`include "img-video-ram1.vh"
endmodule

