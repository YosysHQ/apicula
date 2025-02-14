`default_nettype none
module image_rom(
	input wire clk,
	input wire reset,
	input wire [10:0] ad,
	output wire [17:0] data
);

	wire gnd, vcc;
	assign gnd = 1'b0;
	assign vcc = 1'b1;

	wire [17:0] dummy_w [1:0];
	wire [17:0] data_w [1:0];
	assign data = data_w[ad[10]];

	pROMX9 rom2(
		.AD({ad[9:0], gnd, gnd, gnd, gnd}),
		.DO({dummy_w[0], data_w[1]}),
		.CLK(clk),
		.OCE(vcc),
		.CE(vcc),
		.RESET(reset)
	);
	defparam rom2.READ_MODE = 1'b1;
	defparam rom2.BIT_WIDTH = 18;
	defparam rom2.RESET_MODE = "SYNC";
`include "img-rom2.vh"

	pROMX9 rom3(
		.AD({ad[9:0], gnd, gnd, gnd, gnd}),
		.DO({dummy_w[1], data_w[0]}),
		.CLK(clk),
		.OCE(vcc),
		.CE(vcc),
		.RESET(reset)
	);
	defparam rom3.READ_MODE = 1'b1;
	defparam rom3.BIT_WIDTH = 18;
	defparam rom3.RESET_MODE = "SYNC";
`include "img-rom3.vh"

endmodule

