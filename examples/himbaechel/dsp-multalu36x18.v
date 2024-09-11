`default_nettype none
module idsp(input wire clk, input wire reset, 
	output wire [63:0] product, 
	output wire [63:0] product1, 
	output wire [63:0] product2, 
	output wire [63:0] product3, 
	output wire [63:0] product4);

	wire [54:0] soa;
	wire [54:0] sob;
	wire [54:0] soa0;
	wire [54:0] soa1;
	wire [54:0] soa2;
	wire [54:0] soa3;
	wire [54:0] soa4;
	wire [54:0] sob2;
	wire gnd = 1'b0;

	MULTALU36X18 multalu_0(
		.A(18'h00002),
		.B(36'h5f76fe56f),
		.C(54'h10000),
		.CASI({55{gnd}}),
		.ASIGN(gnd),
		.BSIGN(gnd),
		.ACCLOAD(gnd),
		.CE(1'b1),
		.CLK(clk),
		.RESET(reset),
		.CASO(soa),
		.DOUT(product)
	);
	defparam multalu_0.AREG=1'b0;
	defparam multalu_0.BREG=1'b0;
	defparam multalu_0.CREG=1'b0;
	defparam multalu_0.ASIGN_REG=1'b0;
	defparam multalu_0.BSIGN_REG=1'b0;
	defparam multalu_0.ACCLOAD_REG0=1'b0;
	defparam multalu_0.ACCLOAD_REG1=1'b0;
	defparam multalu_0.OUT_REG=1'b1;
	defparam multalu_0.PIPE_REG=1'b0;
	defparam multalu_0.C_ADD_SUB=1'b1;
	defparam multalu_0.MULT_RESET_MODE="SYNC";
	defparam multalu_0.MULTALU36X18_MODE=0;

	MULTALU36X18 multalu_1(
		.A(18'h3ffff),
		.B(36'hbee000000),
		.C(52'h0),
		.CASI(soa),
		.ASIGN(1'b1),
		.BSIGN(gnd),
		.ACCLOAD(gnd),
		.CE(1'b1),
		.CLK(clk),
		.RESET(reset),
		.CASO(),
		.DOUT(product1)
	);
	defparam multalu_1.AREG=1'b0;
	defparam multalu_1.BREG=1'b0;
	defparam multalu_1.CREG=1'b0;
	defparam multalu_1.ASIGN_REG=1'b0;
	defparam multalu_1.BSIGN_REG=1'b0;
	defparam multalu_1.ACCLOAD_REG0=1'b0;
	defparam multalu_1.ACCLOAD_REG1=1'b0;
	defparam multalu_1.OUT_REG=1'b0;
	defparam multalu_1.PIPE_REG=1'b0;
	defparam multalu_1.C_ADD_SUB=1'b0;
	defparam multalu_1.MULT_RESET_MODE="SYNC";
	defparam multalu_1.MULTALU36X18_MODE=2;

	MULTALU36X18 multalu_2(
		.A(18'h01000),
		.B(36'h00002),
		.C(54'h0),
		.CASI({55{gnd}}),
		.ASIGN(gnd),
		.BSIGN(gnd),
		.ACCLOAD(1'b1),
		.CE(1'b1),
		.CLK(clk),
		.RESET(reset),
		.CASO(soa2),
		.DOUT(product2)
	);
	defparam multalu_2.AREG=1'b0;
	defparam multalu_2.BREG=1'b0;
	defparam multalu_2.CREG=1'b0;
	defparam multalu_2.ASIGN_REG=1'b0;
	defparam multalu_2.BSIGN_REG=1'b0;
	defparam multalu_2.ACCLOAD_REG0=1'b0;
	defparam multalu_2.ACCLOAD_REG1=1'b0;
	defparam multalu_2.OUT_REG=1'b1;
	defparam multalu_2.PIPE_REG=1'b0;
	defparam multalu_2.C_ADD_SUB=1'b0;
	defparam multalu_2.MULT_RESET_MODE="SYNC";
	defparam multalu_2.MULTALU36X18_MODE=1;

	MULTALU36X18 multalu_3(
		.A(18'h3fffe),
		.B(36'hffffffffd),
		.C(54'h0),
		.CASI(soa2),
		.ASIGN(1'b1),
		.BSIGN(1'b1),
		.ACCLOAD(gnd),
		.CE(1'b1),
		.CLK(clk),
		.RESET(reset),
		.CASO(soa4),
		.DOUT(product3)
	);
	defparam multalu_3.AREG=1'b0;
	defparam multalu_3.BREG=1'b0;
	defparam multalu_3.CREG=1'b0;
	defparam multalu_3.ASIGN_REG=1'b0;
	defparam multalu_3.BSIGN_REG=1'b1;
	defparam multalu_3.ACCLOAD_REG0=1'b0;
	defparam multalu_3.ACCLOAD_REG1=1'b0;
	defparam multalu_3.OUT_REG=1'b1;
	defparam multalu_3.PIPE_REG=1'b0;
	defparam multalu_3.C_ADD_SUB=1'b0;
	defparam multalu_3.MULT_RESET_MODE="SYNC";
	defparam multalu_3.MULTALU36X18_MODE=2;

	MULTALU36X18 multalu_4(
		.A(18'h01600),
		.B(36'h00010),
		.C(52'h6532),
		.CASI({55{gnd}}),
		.ASIGN(gnd),
		.BSIGN(gnd),
		.ACCLOAD(gnd),
		.CE(1'b1),
		.CLK(clk),
		.RESET(reset),
		.CASO(),
		.DOUT(product4)
	);
	defparam multalu_4.AREG=1'b0;
	defparam multalu_4.BREG=1'b0;
	defparam multalu_4.CREG=1'b0;
	defparam multalu_4.ASIGN_REG=1'b0;
	defparam multalu_4.BSIGN_REG=1'b0;
	defparam multalu_4.ACCLOAD_REG0=1'b0;
	defparam multalu_4.ACCLOAD_REG1=1'b0;
	defparam multalu_4.OUT_REG=1'b0;
	defparam multalu_4.PIPE_REG=1'b0;
	defparam multalu_4.C_ADD_SUB=1'b1;
	defparam multalu_4.MULT_RESET_MODE="SYNC";
	defparam multalu_4.MULTALU36X18_MODE=0;
endmodule

`define FIRMWARE "riscv-firmware/multalu36x18.hex"
`include "dsp-riscv.v"

