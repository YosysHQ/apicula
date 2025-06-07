`default_nettype none
// A is propagated along the chain, the products are equal to zero until A reaches them.
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
wire gnd = 1'b0;

MULT18X18 mult_0(
	.A({18'h12345}),
	.B({18'hfd}),
	.SIA({18{gnd}}),
	.SIB({18{gnd}}),
	.ASIGN(gnd),
	.BSIGN(gnd),
	.ASEL(gnd),
	.BSEL(gnd),
	.CE(1'b1),
	.CLK(clk),
	.RESET(reset),
	.SOA(soa),
	.SOB(sob),
	.DOUT(product)
);
defparam mult_0.AREG=1'b1;
defparam mult_0.BREG=1'b1;
defparam mult_0.OUT_REG=1'b0;
defparam mult_0.PIPE_REG=1'b0;
defparam mult_0.ASIGN_REG=1'b0;
defparam mult_0.BSIGN_REG=1'b0;
defparam mult_0.SOA_REG=1'b0;
defparam mult_0.MULT_RESET_MODE="SYNC";

MULT18X18 mult_1(
	.A({18'h2}),
	.B({18'h2}),
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
	.DOUT(product1)
);
defparam mult_1.AREG=1'b1;
defparam mult_1.BREG=1'b1;
defparam mult_1.OUT_REG=1'b1;
defparam mult_1.PIPE_REG=1'b0;
defparam mult_1.ASIGN_REG=1'b0;
defparam mult_1.BSIGN_REG=1'b0;
defparam mult_1.SOA_REG=1'b1;
defparam mult_1.MULT_RESET_MODE="SYNC";

MULT18X18 mult_2(
	.A({18'h4}),
	.B({18'h4}),
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
	.DOUT(product2)
);
defparam mult_2.AREG=1'b1;
defparam mult_2.BREG=1'b1;
defparam mult_2.OUT_REG=1'b0;
defparam mult_2.PIPE_REG=1'b0;
defparam mult_2.ASIGN_REG=1'b0;
defparam mult_2.BSIGN_REG=1'b0;
defparam mult_2.SOA_REG=1'b0;
defparam mult_2.MULT_RESET_MODE="SYNC";

MULT18X18 mult_3(
	.A({18'h4}),
	.B({18'h5}),
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
	.DOUT(product3)
);
defparam mult_3.AREG=1'b1;
defparam mult_3.BREG=1'b1;
defparam mult_3.OUT_REG=1'b0;
defparam mult_3.PIPE_REG=1'b0;
defparam mult_3.ASIGN_REG=1'b0;
defparam mult_3.BSIGN_REG=1'b0;
defparam mult_3.SOA_REG=1'b1;
defparam mult_3.MULT_RESET_MODE="SYNC";

MULT18X18 mult_4(
	.A({18'h4}),
	.B({18'h6}),
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
	.DOUT(product4)
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

`define FIRMWARE "riscv-firmware/mult18x18.hex"
`include "dsp-riscv.v"

