`default_nettype none
// In all primitives except the last one, B is set as SBI, the registers on
// B are turned on so that at the initial moment everywhere A is added to 0,
// and then 0xd propagates from the last PADD to the first. 
// I did not redo the byte output procedure so that 0x038000 has 18
// significant bits and if we consider it as a signed number it is -0x8000 ---
// what happens when A=0xf12 reaches the N2 primitive and 0x8f12 is subtracted
// from it.

module idsp(input wire clk, input wire reset, 
	output wire [63:0] product, 
	output wire [63:0] product1, 
	output wire [63:0] product2, 
	output wire [63:0] product3, 
	output wire [63:0] product4);

	wire [8:0] sob;
	wire [8:0] sob0;
	wire [8:0] sob1;
	wire [8:0] sob2;
	wire gnd = 1'b0;

	PADD9 padd_0(
		.A({9'h1}),
		.B({9'h6}),
		.SI({9{gnd}}),
		.SBI(sob),
		.ASEL(gnd),
		.CE(1'b1),
		.CLK(clk),
		.RESET(reset),
		.SO(),
		.SBO(),
		.DOUT(product[8:0])
	);
	defparam padd_0.AREG=1'b0;
	defparam padd_0.BREG=1'b1;
	defparam padd_0.ADD_SUB=1'b0;
	defparam padd_0.BSEL_MODE=1'b1;
	defparam padd_0.SOREG=1'b0;
	defparam padd_0.PADD_RESET_MODE="SYNC";

	PADD9 padd_1(
		.A({9'h2}),
		.B({9'h5}),
		.SI({9{gnd}}),
		.SBI(sob0),
		.ASEL(gnd),
		.CE(1'b1),
		.CLK(clk),
		.RESET(reset),
		.SO(),
		.SBO(sob),
		.DOUT(product1[8:0])
	);
	defparam padd_1.AREG=1'b0;
	defparam padd_1.BREG=1'b1;
	defparam padd_1.ADD_SUB=1'b0;
	defparam padd_1.BSEL_MODE=1'b1;
	defparam padd_1.SOREG=1'b0;
	defparam padd_1.PADD_RESET_MODE="SYNC";

	PADD9 padd_2(
		.A({9'h3}),
		.B({9'h4}),
		.SI({9{gnd}}),
		.SBI(sob1),
		.ASEL(gnd),
		.CE(1'b1),
		.CLK(clk),
		.RESET(reset),
		.SO(),
		.SBO(sob0),
		.DOUT(product2[8:0])
	);
	defparam padd_2.AREG=1'b0;
	defparam padd_2.BREG=1'b1;
	defparam padd_2.ADD_SUB=1'b0;
	defparam padd_2.BSEL_MODE=1'b1;
	defparam padd_2.SOREG=1'b0;
	defparam padd_2.PADD_RESET_MODE="SYNC";

	PADD9 padd_3(
		.A({9'h4}),
		.B({9'h3}),
		.SI({9{gnd}}),
		.SBI(sob2),
		.ASEL(gnd),
		.CE(1'b1),
		.CLK(clk),
		.RESET(reset),
		.SO(),
		.SBO(sob1),
		.DOUT(product3[8:0])
	);
	defparam padd_3.AREG=1'b0;
	defparam padd_3.BREG=1'b1;
	defparam padd_3.ADD_SUB=1'b0;
	defparam padd_3.BSEL_MODE=1'b1;
	defparam padd_3.SOREG=1'b0;
	defparam padd_3.PADD_RESET_MODE="SYNC";

	PADD9 padd_4(
		.A({9'h123}),
		.B({9'hd}),
		.SI({9{gnd}}),
		.SBI({9{gnd}}),
		.ASEL(gnd),
		.CE(1'b1),
		.CLK(clk),
		.RESET(reset),
		.SO(),
		.SBO(sob2),
		.DOUT(product4[8:0])
	);
	defparam padd_4.AREG=1'b0;
	defparam padd_4.BREG=1'b1;
	defparam padd_4.ADD_SUB=1'b0;
	defparam padd_4.BSEL_MODE=1'b0;
	defparam padd_4.SOREG=1'b0;
	defparam padd_4.PADD_RESET_MODE="SYNC";
	endmodule

`define FIRMWARE "riscv-firmware/padd9.hex"
`include "dsp-riscv.v"

