`default_nettype none
// A (0xf12) travels from the first to the last PADD18.
// Registers at A and B are turned on, and addition occurs only in the first
// primitive, all others are subtracted.  module idsp(input wire clk, input
// wire reset, 

module idsp(input wire clk, input wire reset, 
	output wire [63:0] product, 
	output wire [63:0] product1, 
	output wire [63:0] product2, 
	output wire [63:0] product3, 
	output wire [63:0] product4);

	wire [17:0] sob;
	wire [17:0] sob1;
	wire [17:0] sob2;
	wire [17:0] sob3;
	wire [17:0] sob4;
	wire gnd = 1'b0;

	PADD18 padd18_0(
		.A({18'hf12}),
		.B({18'h6}),
		.SI({18{gnd}}),
		.SBI({18{gnd}}),
		.ASEL(gnd),
		.CE(1'b1),
		.CLK(clk),
		.RESET(reset),
		.SO(sob),
		.SBO(),
		.DOUT(product[17:0])
	);
	defparam padd18_0.AREG=1'b1;
	defparam padd18_0.BREG=1'b1;
	defparam padd18_0.ADD_SUB=1'b0;
	defparam padd18_0.BSEL_MODE=1'b0;
	defparam padd18_0.SOREG=1'b0;
	defparam padd18_0.PADD_RESET_MODE="SYNC";

	PADD18 padd18_1(
		.A({18'h2}),
		.B({18'hf12}),
		.SI(sob),
		.SBI({18{gnd}}),
		.ASEL(1'b1),
		.CE(1'b1),
		.CLK(clk),
		.RESET(reset),
		.SO(sob1),
		.SBO(),
		.DOUT(product1[17:0])
	);
	defparam padd18_1.AREG=1'b1;
	defparam padd18_1.BREG=1'b1;
	defparam padd18_1.ADD_SUB=1'b1;
	defparam padd18_1.BSEL_MODE=1'b0;
	defparam padd18_1.SOREG=1'b0;
	defparam padd18_1.PADD_RESET_MODE="SYNC";

	PADD18 padd18_2(
		.A({18'h3}),
		.B({18'h8f12}),
		.SI(sob1),
		.SBI({18{gnd}}),
		.ASEL(1'b1),
		.CE(1'b1),
		.CLK(clk),
		.RESET(reset),
		.SO(sob2),
		.SBO(),
		.DOUT(product2[17:0])
	);
	defparam padd18_2.AREG=1'b1;
	defparam padd18_2.BREG=1'b1;
	defparam padd18_2.ADD_SUB=1'b1;
	defparam padd18_2.BSEL_MODE=1'b0;
	defparam padd18_2.SOREG=1'b0;
	defparam padd18_2.PADD_RESET_MODE="SYNC";

	PADD18 padd18_3(
		.A({18'h4}),
		.B({18'haf12}),
		.SI(sob2),
		.SBI({18{gnd}}),
		.ASEL(1'b1),
		.CE(1'b1),
		.CLK(clk),
		.RESET(reset),
		.SO(sob3),
		.SBO(),
		.DOUT(product3[17:0])
	);
	defparam padd18_3.AREG=1'b1;
	defparam padd18_3.BREG=1'b1;
	defparam padd18_3.ADD_SUB=1'b1;
	defparam padd18_3.BSEL_MODE=1'b0;
	defparam padd18_3.SOREG=1'b0;
	defparam padd18_3.PADD_RESET_MODE="SYNC";

	PADD18 padd18_4(
		.A({18'h123}),
		.B({18'hff12}),
		.SI(sob3),
		.SBI({18{gnd}}),
		.ASEL(1'b1),
		.CE(1'b1),
		.CLK(clk),
		.RESET(reset),
		.SO(sob4),
		.SBO(),
		.DOUT(product4[17:0])
	);
	defparam padd18_4.AREG=1'b1;
	defparam padd18_4.BREG=1'b1;
	defparam padd18_4.ADD_SUB=1'b1;
	defparam padd18_4.BSEL_MODE=1'b0;
	defparam padd18_4.SOREG=1'b0;
	defparam padd18_4.PADD_RESET_MODE="SYNC";
endmodule

`define FIRMWARE "riscv-firmware/padd18.hex"
`include "dsp-riscv.v"

