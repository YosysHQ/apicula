`default_nettype none
module image_rom(
	input wire clk,
	input wire reset,
	input wire [11:0] ad,
	output wire [7:0] data
);

	wire gnd, vcc;
	assign gnd = 1'b0;
	assign vcc = 1'b1;

	wire [23:0] dummy_w [1:0];
	wire [7:0] data_w [1:0];
	assign data = data_w[ad[11]];

	pROM rom(
		.AD({ad[10:0], gnd, gnd, gnd}),
		.DO({dummy_w[0], data_w[0]}),
		.CLK(clk),
		.OCE(vcc),
		.CE(vcc),
		.RESET(reset)
	);
	defparam rom.READ_MODE = 1'b1;
	defparam rom.BIT_WIDTH = 8;
	defparam rom.RESET_MODE = "SYNC";
`include "img-rom.vh"

	pROM rom1(
		.AD({ad[10:0], gnd, gnd, gnd}),
		.DO({dummy_w[1], data_w[1]}),
		.CLK(clk),
		.OCE(vcc),
		.CE(vcc),
		.RESET(reset)
	);
	defparam rom1.READ_MODE = 1'b1;
	defparam rom1.BIT_WIDTH = 8;
	defparam rom1.RESET_MODE = "SYNC";
`include "img-rom1.vh"

endmodule

