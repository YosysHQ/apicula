`default_nettype none
module idsp(input wire clk, input wire reset, 
	output wire [63:0] product, 
	output wire [63:0] product1, 
	output wire [63:0] product2, 
	output wire [63:0] product3, 
	output wire [63:0] product4);

wire gnd = 1'b0;

MULT12X12 mult_0(
	.A({12'h345}),
	.B({12'hfd}),
	.CE(2'b01),
	.CLK({gnd, clk}),
	.RESET({reset, reset}),
	.DOUT(product)
);
defparam mult_0.AREG_CLK="CLK0";
defparam mult_0.BREG_CLK="CLK0";
defparam mult_0.OREG_CLK="BYPASS";
defparam mult_0.PREG_CLK="BYPASS";
defparam mult_0.MULT_RESET_MODE="SYNC";

MULT12X12 mult_1(
	.A({product[11:0]}),
	.B({product[23:12]}),
	.CE(2'b11),
	.CLK({clk, gnd}),
	.RESET({reset, reset}),
	.DOUT(product1)
);
defparam mult_1.AREG_CLK="CLK1";
defparam mult_1.BREG_CLK="CLK1";
defparam mult_1.OREG_CLK="CLK1";
defparam mult_1.PREG_CLK="BYPASS";
defparam mult_1.MULT_RESET_MODE="SYNC";

MULT12X12 mult_2(
	.A({product1[11:0]}),
	.B({product1[23:12]}),
	.CE(2'b11),
	.CLK({clk, gnd}),
	.RESET({reset, reset}),
	.DOUT(product2)
);
defparam mult_2.AREG_CLK="CLK1";
defparam mult_2.BREG_CLK="CLK1";
defparam mult_2.OREG_CLK="BYPASS";
defparam mult_2.PREG_CLK="BYPASS";
defparam mult_2.MULT_RESET_MODE="SYNC";

MULT12X12 mult_3(
	.A({product2[11:0]}),
	.B({product2[23:12]}),
	.CE(2'b11),
	.CLK({clk, gnd}),
	.RESET({reset, reset}),
	.DOUT(product3)
);
defparam mult_3.AREG_CLK="CLK1";
defparam mult_3.BREG_CLK="CLK1";
defparam mult_3.OREG_CLK="BYPASS";
defparam mult_3.PREG_CLK="BYPASS";
defparam mult_3.MULT_RESET_MODE="SYNC";

MULT12X12 mult_4(
	.A({product3[11:0]}),
	.B({product3[23:12]}),
	.CE(2'b11),
	.CLK({clk, clk}),
	.RESET({reset, reset}),
	.DOUT(product4)
);
defparam mult_3.AREG_CLK="CLK1";
defparam mult_3.BREG_CLK="CLK1";
defparam mult_3.OREG_CLK="CLK0";
defparam mult_3.PREG_CLK="BYPASS";
defparam mult_3.MULT_RESET_MODE="SYNC";
endmodule

`define FIRMWARE "../riscv-firmware/mult12x12.hex"
`include "dsp-riscv.v"

