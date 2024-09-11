`default_nettype none
module idsp(input wire clk, input wire reset, 
	output wire [63:0] product, 
	output wire [63:0] product1, 
	output wire [63:0] product2, 
	output wire [63:0] product3, 
	output wire [63:0] product4);

	wire [17:0] soa;
	wire [17:0] sob;
	wire [17:0] soa0;
	wire [17:0] sob0;
	wire [17:0] soa1;
	wire [17:0] sob1;
	wire [17:0] soa2;
	wire [17:0] sob2;
	wire [54:0] caso;
	wire gnd = 1'b0;

	MULTADDALU18X18 multaddalu_0(
		.A0({18'h5}),
		.B0({18'hfd}),
		.A1({18'h25}),
		.B1({18'haa}),
		.C({54'h1}),
		.SIA({18{gnd}}),
		.SIB({18{gnd}}),
		.CASI({55{gnd}}),
		.ASIGN({gnd, gnd}),
		.BSIGN({gnd, gnd}),
		.ASEL({1'b1, gnd}),
		.BSEL({gnd, gnd}),
		.ACCLOAD(gnd),
		.CE(1'b1),
		.CLK(clk),
		.RESET(gnd),
		.SOA(soa),
		.SOB(sob),
		.CASO(),
		.DOUT(product)
	);
	defparam multaddalu_0.A0REG=1'b0;
	defparam multaddalu_0.A1REG=1'b0;
	defparam multaddalu_0.B0REG=1'b0;
	defparam multaddalu_0.B1REG=1'b0;
	defparam multaddalu_0.CREG=1'b0;
	defparam multaddalu_0.PIPE0_REG=1'b0;
	defparam multaddalu_0.PIPE1_REG=1'b0;
	defparam multaddalu_0.OUT_REG=1'b1;
	defparam multaddalu_0.ASIGN0_REG=1'b0;
	defparam multaddalu_0.ASIGN1_REG=1'b0;
	defparam multaddalu_0.BSIGN0_REG=1'b0;
	defparam multaddalu_0.BSIGN1_REG=1'b0;
	defparam multaddalu_0.ACCLOAD_REG0=1'b0;
	defparam multaddalu_0.ACCLOAD_REG1=1'b0;
	defparam multaddalu_0.SOA_REG=1'b1;
	defparam multaddalu_0.B_ADD_SUB=1'b0;
	defparam multaddalu_0.C_ADD_SUB=1'b0;
	defparam multaddalu_0.MULT_RESET_MODE="SYNC";
	defparam multaddalu_0.MULTADDALU18X18_MODE=0;

	MULTADDALU18X18 multaddalu_1(
		.A0({18'h12}),
		.B0({18'hfd}),
		.A1({18'h32}),
		.B1({18'h3fffe}),
		.C({54{gnd}}),
		.SIA(soa),
		.SIB(sob),
		.CASI({55{gnd}}),
		.ASIGN({gnd, gnd}),
		.BSIGN({1'b1, gnd}),
		.ASEL({1'b1, 1'b1}),
		.BSEL({gnd, gnd}),
		.ACCLOAD(1'b1),
		.CE(1'b1),
		.CLK(clk),
		.RESET(gnd),
		.SOA(soa0),
		.SOB(),
		.CASO(),
		.DOUT(product1)
	);
	defparam multaddalu_1.A0REG=1'b0;
	defparam multaddalu_1.A1REG=1'b0;
	defparam multaddalu_1.B0REG=1'b0;
	defparam multaddalu_1.B1REG=1'b0;
	defparam multaddalu_1.CREG=1'b0;
	defparam multaddalu_1.PIPE0_REG=1'b0;
	defparam multaddalu_1.PIPE1_REG=1'b0;
	defparam multaddalu_1.OUT_REG=1'b1;
	defparam multaddalu_1.ASIGN0_REG=1'b0;
	defparam multaddalu_1.ASIGN1_REG=1'b0;
	defparam multaddalu_1.BSIGN0_REG=1'b0;
	defparam multaddalu_1.BSIGN1_REG=1'b0;
	defparam multaddalu_1.ACCLOAD_REG0=1'b0;
	defparam multaddalu_1.ACCLOAD_REG1=1'b0;
	defparam multaddalu_1.SOA_REG=1'b1;
	defparam multaddalu_1.B_ADD_SUB=1'b0;
	defparam multaddalu_1.C_ADD_SUB=1'b0;
	defparam multaddalu_1.MULT_RESET_MODE="SYNC";
	defparam multaddalu_1.MULTADDALU18X18_MODE=1;

	MULTADDALU18X18 multaddalu_2(
		.A0({18'h123}),
		.B0({18'h30000}),
		.A1({18'h1000}),
		.B1({18'h10}),
		.C({54{gnd}}),
		.SIA(soa0),
		.SIB({18{gnd}}),
		.CASI({55{gnd}}),
		.ASIGN({gnd, gnd}),
		.BSIGN({gnd, gnd}),
		.ASEL({gnd, 1'b1}),
		.BSEL({gnd, gnd}),
		.ACCLOAD(gnd),
		.CE(1'b1),
		.CLK(clk),
		.RESET(gnd),
		.SOA(),
		.SOB(),
		.CASO(caso),
		.DOUT(product2)
	);
	defparam multaddalu_2.A0REG=1'b0;
	defparam multaddalu_2.A1REG=1'b0;
	defparam multaddalu_2.B0REG=1'b0;
	defparam multaddalu_2.B1REG=1'b0;
	defparam multaddalu_2.CREG=1'b0;
	defparam multaddalu_2.PIPE0_REG=1'b0;
	defparam multaddalu_2.PIPE1_REG=1'b0;
	defparam multaddalu_2.OUT_REG=1'b1;
	defparam multaddalu_2.ASIGN0_REG=1'b0;
	defparam multaddalu_2.ASIGN1_REG=1'b0;
	defparam multaddalu_2.BSIGN0_REG=1'b0;
	defparam multaddalu_2.BSIGN1_REG=1'b0;
	defparam multaddalu_2.ACCLOAD_REG0=1'b0;
	defparam multaddalu_2.ACCLOAD_REG1=1'b0;
	defparam multaddalu_2.SOA_REG=1'b1;
	defparam multaddalu_2.B_ADD_SUB=1'b0;
	defparam multaddalu_2.C_ADD_SUB=1'b0;
	defparam multaddalu_2.MULT_RESET_MODE="SYNC";
	defparam multaddalu_2.MULTADDALU18X18_MODE=2;

	MULTADDALU18X18 multaddalu_3(
		.A0({18'h3fffd}),
		.B0({18'h3fffe}),
		.A1({18'h0}),
		.B1({18'h0}),
		.C({54{gnd}}),
		.SIA({18{gnd}}),
		.SIB({18{gnd}}),
		.CASI(caso),
		.ASIGN({gnd, 1'b1}),
		.BSIGN({gnd, 1'b1}),
		.ASEL({gnd, gnd}),
		.BSEL({gnd, gnd}),
		.ACCLOAD(1'b1),
		.CE(1'b1),
		.CLK(clk),
		.RESET(gnd),
		.SOA(),
		.SOB(),
		.CASO(),
		.DOUT(product3)
	);
	defparam multaddalu_3.A0REG=1'b1;
	defparam multaddalu_3.A1REG=1'b1;
	defparam multaddalu_3.B0REG=1'b1;
	defparam multaddalu_3.B1REG=1'b1;
	defparam multaddalu_3.CREG=1'b1;
	defparam multaddalu_3.PIPE0_REG=1'b1;
	defparam multaddalu_3.PIPE1_REG=1'b1;
	defparam multaddalu_3.OUT_REG=1'b1;
	defparam multaddalu_3.ASIGN0_REG=1'b1;
	defparam multaddalu_3.ASIGN1_REG=1'b1;
	defparam multaddalu_3.BSIGN0_REG=1'b1;
	defparam multaddalu_3.BSIGN1_REG=1'b1;
	defparam multaddalu_3.ACCLOAD_REG0=1'b0;
	defparam multaddalu_3.ACCLOAD_REG1=1'b0;
	defparam multaddalu_3.SOA_REG=1'b1;
	defparam multaddalu_3.B_ADD_SUB=1'b0;
	defparam multaddalu_3.C_ADD_SUB=1'b0;
	defparam multaddalu_3.MULT_RESET_MODE="SYNC";
	defparam multaddalu_3.MULTADDALU18X18_MODE=2;
endmodule

`define FIRMWARE "riscv-firmware/multaddalu18x18.hex"
`include "dsp-riscv.v"

