`default_nettype none
// A is distributed along the chain, the registers are turned on, since this
// is a multiplication, then until A reaches a specific multiplier, the
// product will be equal to 0

module idsp(input wire clk, input wire reset, 
	output wire [63:0] product, 
	output wire [63:0] product1, 
	output wire [63:0] product2, 
	output wire [63:0] product3, 
	output wire [63:0] product4);

wire [8:0] soa;
wire [8:0] sob;
wire [8:0] soa0;
wire [8:0] sob0;
wire [8:0] soa1;
wire [8:0] sob1;
wire [8:0] soa2;
wire [8:0] sob2;
wire gnd = 1'b0;

MULT9X9 mult_0(
	.A({9'h123}),
	.B({9'hfd}),
	.SIA({9{gnd}}),
	.SIB({9{gnd}}),
	.ASIGN(gnd),
	.BSIGN(gnd),
	.ASEL(gnd),
	.BSEL(gnd),
	.CE(1'b1),
	.CLK(clk),
	.RESET(reset),
	.SOA(soa),
	.SOB(sob),
	.DOUT(product[17:0])
);
defparam mult_0.AREG=1'b1;
defparam mult_0.BREG=1'b1;
defparam mult_0.OUT_REG=1'b0;
defparam mult_0.PIPE_REG=1'b0;
defparam mult_0.ASIGN_REG=1'b0;
defparam mult_0.BSIGN_REG=1'b0;
defparam mult_0.SOA_REG=1'b0;
defparam mult_0.MULT_RESET_MODE="SYNC";

MULT9X9 mult_1(
	.A({9'h2}),
	.B({9'h2}),
	.SIA(soa),
	.SIB(sob),
	.ASIGN(gnd),
	.BSIGN(gnd),
	.ASEL(1'b1),
	.BSEL(gnd),
	.CE(1'b1),
	.CLK(clk),
	.RESET(reset),
	.SOA(soa0),
	.SOB(sob0),
	.DOUT(product1[17:0])
);
defparam mult_1.AREG=1'b1;
defparam mult_1.BREG=1'b1;
defparam mult_1.OUT_REG=1'b1;
defparam mult_1.PIPE_REG=1'b0;
defparam mult_1.ASIGN_REG=1'b0;
defparam mult_1.BSIGN_REG=1'b0;
defparam mult_1.SOA_REG=1'b1;
defparam mult_1.MULT_RESET_MODE="SYNC";

MULT9X9 mult_2(
	.A({9'h4}),
	.B({9'h4}),
	.SIA(soa0),
	.SIB(sob0),
	.ASIGN(gnd),
	.BSIGN(gnd),
	.ASEL(1'b1),
	.BSEL(gnd),
	.CE(1'b1),
	.CLK(clk),
	.RESET(reset),
	.SOA(soa1),
	.SOB(sob1),
	.DOUT(product2[17:0])
);
defparam mult_2.AREG=1'b1;
defparam mult_2.BREG=1'b1;
defparam mult_2.OUT_REG=1'b0;
defparam mult_2.PIPE_REG=1'b0;
defparam mult_2.ASIGN_REG=1'b0;
defparam mult_2.BSIGN_REG=1'b0;
defparam mult_2.SOA_REG=1'b0;
defparam mult_2.MULT_RESET_MODE="SYNC";

MULT9X9 mult_3(
	.A({9'h4}),
	.B({9'h5}),
	.SIA(soa1),
	.SIB(sob1),
	.ASIGN(gnd),
	.BSIGN(gnd),
	.ASEL(1'b1),
	.BSEL(gnd),
	.CE(1'b1),
	.CLK(clk),
	.RESET(reset),
	.SOA(soa2),
	.SOB(sob2),
	.DOUT(product3[17:0])
);
defparam mult_3.AREG=1'b1;
defparam mult_3.BREG=1'b1;
defparam mult_3.OUT_REG=1'b0;
defparam mult_3.PIPE_REG=1'b0;
defparam mult_3.ASIGN_REG=1'b0;
defparam mult_3.BSIGN_REG=1'b0;
defparam mult_3.SOA_REG=1'b1;
defparam mult_3.MULT_RESET_MODE="SYNC";

MULT9X9 mult_4(
	.A({9'h4}),
	.B({9'h6}),
	.SIA(soa2),
	.SIB(sob2),
	.ASIGN(gnd),
	.BSIGN(gnd),
	.ASEL(1'b1),
	.BSEL(gnd),
	.CE(1'b1),
	.CLK(clk),
	.RESET(reset),
	.SOA(),
	.SOB(),
	.DOUT(product4[17:0])
);
defparam mult_4.AREG=1'b1;
defparam mult_4.BREG=1'b1;
defparam mult_4.OUT_REG=1'b1;
defparam mult_4.PIPE_REG=1'b0;
defparam mult_4.ASIGN_REG=1'b0;
defparam mult_4.BSIGN_REG=1'b0;
defparam mult_4.SOA_REG=1'b0;
defparam mult_4.MULT_RESET_MODE="SYNC";
endmodule

`define FIRMWARE "riscv-firmware/mult9x9.hex"
`include "dsp-riscv.v"

