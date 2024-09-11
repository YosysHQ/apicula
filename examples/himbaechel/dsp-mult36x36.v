`default_nettype none
module idsp(input wire clk, input wire reset, 
	output wire [63:0] product, 
	output wire [63:0] product1, 
	output wire [63:0] product2, 
	output wire [63:0] product3, 
	output wire [63:0] product4);

	wire gnd = 1'b0;

	// Simple multiplication of positive numbers without registers
	MULT36X36 mu_0(
		.A({36'h412345678}),
		.B({36'h187654321}),
		.ASIGN(gnd),
		.BSIGN(gnd),
		.CE(1'b1),
		.CLK(clk),
		.RESET(reset),
		.DOUT({product1[7:0], product})
	);
	defparam mu_0.AREG=1'b0;
	defparam mu_0.BREG=1'b0;
	defparam mu_0.OUT0_REG=1'b0;
	defparam mu_0.OUT1_REG=1'b0;
	defparam mu_0.PIPE_REG=1'b0;
	defparam mu_0.ASIGN_REG=1'b0;
	defparam mu_0.BSIGN_REG=1'b0;
	defparam mu_0.MULT_RESET_MODE="SYNC";

	// Multiplication of negative numbers with all registers
	MULT36X36 mu_1(
		.A({36'haebdccdbf}),  // -0x514233241 
		.B({36'hfffdcba99}),  // -0x234567 
		.ASIGN(1'b1),
		.BSIGN(1'b1),
		.CE(1'b1),
		.CLK(clk),
		.RESET(reset),
		.DOUT({product3[7:0], product2})
	);
	defparam mu_1.AREG=1'b1;
	defparam mu_1.BREG=1'b1;
	defparam mu_1.OUT0_REG=1'b1;
	defparam mu_1.OUT1_REG=1'b1;
	defparam mu_1.PIPE_REG=1'b1;
	defparam mu_1.ASIGN_REG=1'b1;
	defparam mu_1.BSIGN_REG=1'b1;
	defparam mu_1.MULT_RESET_MODE="SYNC";
endmodule

`define FIRMWARE "riscv-firmware/mult36x36.hex"
`include "dsp-riscv.v"

