`default_nettype none
module image_rom(
	input wire clk,
	input wire reset,
	input wire [10:0] ad,
	output wire [15:0] data
);

	wire gnd, vcc;
	assign gnd = 1'b0;
	assign vcc = 1'b1;

	wire [15:0] dummy [1:0];
	wire [15:0] data_mux [1:0];
	assign data = data_mux[ad[10]];

	pROM rom(
		.AD({ad[9:0], gnd, gnd, gnd, gnd}),
		.DO({dummy[0], data_mux[0]}),
		.CLK(clk),
		.OCE(vcc),
		.CE(vcc),
		.RESET(reset)
	);
	defparam rom.READ_MODE = 1'b1;
	defparam rom.BIT_WIDTH = 16;
	defparam rom.RESET_MODE = "SYNC";
`include "img-rom.vh"

	pROM rom1(
		.AD({ad[9:0], gnd, gnd, gnd, gnd}),
		.DO({dummy[1], data_mux[1]}),
		.CLK(clk),
		.OCE(vcc),
		.CE(vcc),
		.RESET(reset)
	);
	defparam rom1.READ_MODE = 1'b1;
	defparam rom1.BIT_WIDTH = 16;
	defparam rom1.RESET_MODE = "SYNC";
`include "img-rom1.vh"

endmodule

