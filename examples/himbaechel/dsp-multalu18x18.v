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

	MULTALU18X18 multalu_0(
		.A(18'h00005),
		.B(18'h00002),
		.C(54'd9),
		.D(54'd0),
		.CASI({55{gnd}}),
		.ASIGN(gnd),
		.BSIGN(gnd),
		.DSIGN(gnd),
		.ACCLOAD(1'b1),
		.CE(1'b1),
		.CLK(clk),
		.RESET(reset),
		.CASO(soa),
		.DOUT(product)
	);
	defparam multalu_0.AREG=1'b0;
	defparam multalu_0.BREG=1'b0;
	defparam multalu_0.CREG=1'b0;
	defparam multalu_0.DREG=1'b0;
	defparam multalu_0.ASIGN_REG=1'b0;
	defparam multalu_0.BSIGN_REG=1'b0;
	defparam multalu_0.DSIGN_REG=1'b0;
	defparam multalu_0.ACCLOAD_REG0=1'b0;
	defparam multalu_0.ACCLOAD_REG1=1'b0;
	defparam multalu_0.OUT_REG=1'b1;
	defparam multalu_0.PIPE_REG=1'b0;
	defparam multalu_0.B_ADD_SUB=1'b0;
	defparam multalu_0.C_ADD_SUB=1'b1;
	defparam multalu_0.MULT_RESET_MODE="SYNC";
	defparam multalu_0.MULTALU18X18_MODE=0;

	MULTALU18X18 multalu_1(
		.A(18'h0000f),
		.B(18'h0000e),
		.C(52'h0),
		.D(52'hd),
		.CASI(soa),
		.ASIGN(gnd),
		.BSIGN(gnd),
		.DSIGN(gnd),
		.ACCLOAD(1'b0),
		.CE(1'b1),
		.CLK(clk),
		.RESET(reset),
		.CASO(soa0),
		.DOUT(product1)
	);
	defparam multalu_1.AREG=1'b0;
	defparam multalu_1.BREG=1'b0;
	defparam multalu_1.CREG=1'b0;
	defparam multalu_1.DREG=1'b0;
	defparam multalu_1.ASIGN_REG=1'b0;
	defparam multalu_1.BSIGN_REG=1'b0;
	defparam multalu_1.DSIGN_REG=1'b0;
	defparam multalu_1.ACCLOAD_REG0=1'b0;
	defparam multalu_1.ACCLOAD_REG1=1'b0;
	defparam multalu_1.OUT_REG=1'b0;
	defparam multalu_1.PIPE_REG=1'b0;
	defparam multalu_1.B_ADD_SUB=1'b1;
	defparam multalu_1.C_ADD_SUB=1'b0;
	defparam multalu_1.MULT_RESET_MODE="SYNC";
	defparam multalu_1.MULTALU18X18_MODE=2;

	MULTALU18X18 multalu_2(
		.A(18'h10000),
		.B(18'h00003),
		.C(54'h0),
		.D(54'h0),
		.CASI(soa0),
		.ASIGN(gnd),
		.BSIGN(gnd),
		.DSIGN(gnd),
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
	defparam multalu_2.DREG=1'b0;
	defparam multalu_2.ASIGN_REG=1'b0;
	defparam multalu_2.BSIGN_REG=1'b0;
	defparam multalu_2.DSIGN_REG=1'b0;
	defparam multalu_2.ACCLOAD_REG0=1'b0;
	defparam multalu_2.ACCLOAD_REG1=1'b0;
	defparam multalu_2.OUT_REG=1'b1;
	defparam multalu_2.PIPE_REG=1'b0;
	defparam multalu_2.B_ADD_SUB=1'b0;
	defparam multalu_2.C_ADD_SUB=1'b0;
	defparam multalu_2.MULT_RESET_MODE="SYNC";
	defparam multalu_2.MULTALU18X18_MODE=1;

	MULTALU18X18 multalu_3(
		.A(18'h10000),
		.B(18'h00002),
		.C(54'h0),
		.D(54'h0),
		.CASI(soa2),
		.ASIGN(gnd),
		.BSIGN(gnd),
		.DSIGN(gnd),
		.ACCLOAD(1'b1),
		.CE(1'b1),
		.CLK(clk),
		.RESET(reset),
		.CASO(soa4),
		.DOUT(product3)
	);
	defparam multalu_3.AREG=1'b0;
	defparam multalu_3.BREG=1'b0;
	defparam multalu_3.CREG=1'b0;
	defparam multalu_3.DREG=1'b0;
	defparam multalu_3.ASIGN_REG=1'b0;
	defparam multalu_3.BSIGN_REG=1'b0;
	defparam multalu_3.DSIGN_REG=1'b0;
	defparam multalu_3.ACCLOAD_REG0=1'b0;
	defparam multalu_3.ACCLOAD_REG1=1'b0;
	defparam multalu_3.OUT_REG=1'b1;
	defparam multalu_3.PIPE_REG=1'b0;
	defparam multalu_3.B_ADD_SUB=1'b1;
	defparam multalu_3.C_ADD_SUB=1'b0;
	defparam multalu_3.MULT_RESET_MODE="SYNC";
	defparam multalu_3.MULTALU18X18_MODE=1;

	MULTALU18X18 multalu_4(
		.A(18'h2a000),
		.B(18'h00010),
		.C(52'h0),
		.D(52'h0),
		.CASI(soa4),
		.ASIGN(1'b1),
		.BSIGN(gnd),
		.DSIGN(gnd),
		.ACCLOAD(1'b0),
		.CE(1'b1),
		.CLK(clk),
		.RESET(reset),
		.CASO(),
		.DOUT(product4)
	);
	defparam multalu_4.AREG=1'b0;
	defparam multalu_4.BREG=1'b0;
	defparam multalu_4.CREG=1'b0;
	defparam multalu_4.DREG=1'b0;
	defparam multalu_4.ASIGN_REG=1'b0;
	defparam multalu_4.BSIGN_REG=1'b0;
	defparam multalu_4.DSIGN_REG=1'b0;
	defparam multalu_4.ACCLOAD_REG0=1'b0;
	defparam multalu_4.ACCLOAD_REG1=1'b0;
	defparam multalu_4.OUT_REG=1'b0;
	defparam multalu_4.PIPE_REG=1'b0;
	defparam multalu_4.B_ADD_SUB=1'b0;
	defparam multalu_4.C_ADD_SUB=1'b0;
	defparam multalu_4.MULT_RESET_MODE="SYNC";
	defparam multalu_4.MULTALU18X18_MODE=2;
endmodule

`define FIRMWARE "riscv-firmware/multalu18x18.hex"
`include "dsp-riscv.v"

