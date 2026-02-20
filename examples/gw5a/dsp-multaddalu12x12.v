`default_nettype none
module idsp(input wire clk, input wire reset, input wire key,
	output wire [63:0] product, 
	output wire [63:0] product1, 
	output wire [63:0] product2, 
	output wire [63:0] product3, 
	output wire [63:0] product4);

	wire gnd = 1'b0;

	wire [11:0] in_a0 = 12'h3;
	wire [11:0] in_b0 = 12'h4;
	wire [11:0] in_a1 = 12'h2;
	wire [11:0] in_b1 = 12'h5;
	wire [47:0] cas[4];

	MULTADDALU12X12 m0(
		.A0(in_a0),
		.B0(in_b0),
		.A1(in_a1),
		.B1(in_b1),
		.CASI(),
		.CASISEL(1'b0),
		.ADDSUB(2'b00),
		.ACCSEL(key),
		.CLK({clk, clk}),
		.CE(2'b11),
		.RESET({1'b0, reset}),
		.DOUT(product),
		.CASO(cas[0])
	);
	defparam m0.A0REG_CLK="CLK0";
	defparam m0.B0REG_CLK="CLK1";
	defparam m0.A1REG_CLK="CLK0";
	defparam m0.B1REG_CLK="CLK1";
	defparam m0.ADDSUB0_IREG_CLK="CLK0";
	defparam m0.ADDSUB1_PREG_CLK="CLK0";
	defparam m0.CASISEL_PREG_CLK="CLK1";
	defparam m0.PREG0_CLK="CLK0";
	defparam m0.FB_PREG_EN="TRUE";
	defparam m0.OREG_CLK="CLK1";
	defparam m0.OREG_CE="CE1";
	defparam m0.OREG_RESET="RESET1";
	defparam m0.MULT_RESET_MODE="ASYNC";
	defparam m0.DYN_ACC_SEL="TRUE";
    defparam m0.DYN_ACC_SEL="TRUE";
    defparam m0.DYN_ADD_SUB_0="TRUE";
    defparam m0.DYN_ADD_SUB_1="TRUE";	

	MULTADDALU12X12 m1(
		.A0(12'h1),
		.B0(12'h2),
		.A1(12'h3),
		.B1(12'h4),
		.CASI(cas[0]),
		.CASISEL(),
		.ADDSUB(2'b01),
		.ACCSEL(key),
		.CLK({clk, clk}),
		.CE(2'b11),
		.RESET({1'b0, reset}),
		.DOUT(product1),
		.CASO(cas[1])
	);
	defparam m1.A0REG_CLK="CLK0";
	defparam m1.B0REG_CLK="CLK1";
	defparam m1.A1REG_CLK="CLK0";
	defparam m1.B1REG_CLK="CLK1";
	defparam m1.ADDSUB0_IREG_CLK="CLK0";
	defparam m1.ADDSUB1_PREG_CLK="CLK0";
	defparam m1.CASISEL_PREG_CLK="CLK1";
	defparam m1.CASI_SEL=1'b1;
	defparam m1.DYN_CASI_SEL="FALSE";
	defparam m1.PREG0_CLK="CLK0";
	defparam m1.FB_PREG_EN="TRUE";
	defparam m1.OREG_CLK="CLK1";
	defparam m1.OREG_CE="CE1";
	defparam m1.OREG_RESET="RESET1";
	defparam m1.MULT_RESET_MODE="ASYNC";
	defparam m1.DYN_ACC_SEL="TRUE";
	defparam m1.PRE_LOAD=48'h00000000cafe;

	MULTADDALU12X12 m2(
		.A0(in_a0),
		.B0(in_b0),
		.A1(in_a1),
		.B1(in_b1),
		.CASI(cas[1]),
		.CASISEL(),
		.ADDSUB(2'b01),
		.ACCSEL(key),
		.CLK({clk, clk}),
		.CE(2'b11),
		.RESET({1'b0, reset}),
		.DOUT(product2),
		.CASO(cas[2])
	);
	defparam m2.A0REG_CLK="CLK0";
	defparam m2.B0REG_CLK="CLK1";
	defparam m2.A1REG_CLK="CLK0";
	defparam m2.B1REG_CLK="CLK1";
	defparam m2.ADDSUB0_IREG_CLK="CLK0";
	defparam m2.ADDSUB1_PREG_CLK="CLK0";
	defparam m2.CASISEL_PREG_CLK="CLK1";
	defparam m2.CASI_SEL=1'b1;
	defparam m2.DYN_CASI_SEL="FALSE";
	defparam m2.PREG0_CLK="CLK0";
	defparam m2.FB_PREG_EN="TRUE";
	defparam m2.OREG_CLK="CLK1";
	defparam m2.OREG_CE="CE1";
	defparam m2.OREG_RESET="RESET1";
	defparam m2.MULT_RESET_MODE="ASYNC";
	defparam m2.DYN_ACC_SEL="FALSE";
	defparam m2.ACC_SEL=1'b1;

	MULTADDALU12X12 m3(
		.A0(in_a0),
		.B0(in_b0),
		.A1(in_a1),
		.B1(in_b1),
		.CASI(cas[2]),
		.CASISEL(),
		.ADDSUB(2'b01),
		.ACCSEL(key),
		.CLK({clk, clk}),
		.CE(2'b11),
		.RESET({1'b0, reset}),
		.DOUT(product3),
		.CASO(cas[3])
	);
	defparam m3.A0REG_CLK="CLK0";
	defparam m3.B0REG_CLK="CLK1";
	defparam m3.A1REG_CLK="CLK0";
	defparam m3.B1REG_CLK="CLK1";
	defparam m3.ADDSUB0_IREG_CLK="CLK0";
	defparam m3.ADDSUB1_PREG_CLK="CLK0";
	defparam m3.CASISEL_PREG_CLK="CLK1";
	defparam m3.CASI_SEL=1'b1;
	defparam m3.DYN_CASI_SEL="FALSE";
	defparam m3.PREG0_CLK="CLK0";
	defparam m3.FB_PREG_EN="TRUE";
	defparam m3.OREG_CLK="CLK1";
	defparam m3.OREG_CE="CE1";
	defparam m3.OREG_RESET="RESET1";
	defparam m3.MULT_RESET_MODE="ASYNC";
	defparam m3.DYN_ACC_SEL="FALSE";
	defparam m3.ACC_SEL=1'b0;
	defparam m3.PRE_LOAD=48'h000000000002;

	MULTADDALU12X12 m4(
		.A0(in_a0),
		.B0(in_b0),
		.A1(in_a1),
		.B1(in_b1),
		.CASI(cas[3]),
		.CASISEL(1'b1),
		.ADDSUB(2'b01),
		.ACCSEL(key),
		.CLK({clk, clk}),
		.CE(2'b11),
		.RESET({1'b0, reset}),
		.DOUT(product4),
		.CASO()
	);
	defparam m4.A0REG_CLK="CLK0";
	defparam m4.B0REG_CLK="CLK1";
	defparam m4.A1REG_CLK="CLK0";
	defparam m4.B1REG_CLK="CLK1";
	defparam m4.ADDSUB0_IREG_CLK="CLK0";
	defparam m4.ADDSUB1_PREG_CLK="CLK0";
	defparam m4.CASISEL_PREG_CLK="CLK1";
	defparam m4.DYN_CASI_SEL="TRUE";
	defparam m4.PREG0_CLK="CLK0";
	defparam m4.FB_PREG_EN="TRUE";
	defparam m4.OREG_CLK="CLK1";
	defparam m4.OREG_CE="CE1";
	defparam m4.OREG_RESET="RESET1";
	defparam m4.MULT_RESET_MODE="ASYNC";
	defparam m4.DYN_ACC_SEL="FALSE";
	defparam m4.ACC_SEL=1'b0;
	defparam m4.PRE_LOAD=48'h000000000002;
endmodule

`define FIRMWARE "../riscv-firmware/multaddalu12x12.hex"
`include "dsp-riscv.v"

