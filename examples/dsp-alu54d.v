`default_nettype none
// alu0 mode 0 - simple substraction with accumulator in C
// alu1 mode 1 - addition with CASI and accumulator in A
// alu2 mode 2 - addition with CASI
module idsp(input wire clk, input wire reset,
	output wire [63:0] product, 
	output wire [63:0] product1, 
	output wire [63:0] product2, 
	output wire [63:0] product3, 
	output wire [63:0] product4
	);

wire [17:0] soa;
wire [17:0] sob;
wire [17:0] soa0;
wire [17:0] sob0;
wire [17:0] soa1;
wire [17:0] sob1;
wire [17:0] soa2;
wire [17:0] sob2;
wire gnd = 1'b0;

wire [54:0]caso;
wire [54:0]caso0;

ALU54D alu0(
	.A(54'hde1ec7ab1e),
	.B(54'hcad),
	.DOUT(product[53:0]),
	.CASI(gnd),
	.CASO(caso),
	.ASIGN(gnd),
	.BSIGN(gnd),
	.ACCLOAD(1'b1),
	.CLK(clk),
	.CE(1'b1),
	.RESET(reset)
);
	defparam alu0.AREG=1'b0;
	defparam alu0.BREG=1'b0;
	defparam alu0.ASIGN_REG=1'b0;
	defparam alu0.BSIGN_REG=1'b0;
	defparam alu0.ACCLOAD_REG=1'b0;
	defparam alu0.OUT_REG=1'b1;
	defparam alu0.B_ADD_SUB=1'b1;
	defparam alu0.C_ADD_SUB=1'b0;
	defparam alu0.ALUD_MODE=2'b0;
	defparam alu0.ALU_RESET_MODE="SYNC";

ALU54D alu1(
	.A(54'h1111),
	.B(54'h2),
	.DOUT(product1[53:0]),
	.CASI(caso),
	.CASO(caso0),
	.ASIGN(gnd),
	.BSIGN(gnd),
	.ACCLOAD(gnd),
	.CLK(clk),
	.CE(1'b1),
	.RESET(reset)
);
	defparam alu1.AREG=1'b1;
	defparam alu1.BREG=1'b0;
	defparam alu1.ASIGN_REG=1'b0;
	defparam alu1.BSIGN_REG=1'b0;
	defparam alu1.ACCLOAD_REG=1'b0;
	defparam alu1.OUT_REG=1'b0;
	defparam alu1.B_ADD_SUB=1'b0;
	defparam alu1.C_ADD_SUB=1'b0;
	defparam alu1.ALUD_MODE=1;
	defparam alu1.ALU_RESET_MODE="SYNC";

ALU54D alu2(
	.A(54'h100000000),
	.B(54'h00000f000),
	.DOUT(product2[53:0]),
	.CASI(caso0),
	.CASO(),
	.ASIGN(gnd),
	.BSIGN(gnd),
	.ACCLOAD(gnd),
	.CLK(clk),
	.CE(1'b1),
	.RESET(reset)
);
	defparam alu2.AREG=1'b1;
	defparam alu2.BREG=1'b1;
	defparam alu2.ASIGN_REG=1'b1;
	defparam alu2.BSIGN_REG=1'b1;
	defparam alu2.ACCLOAD_REG=1'b1;
	defparam alu2.OUT_REG=1'b0;
	defparam alu2.B_ADD_SUB=1'b0;
	defparam alu2.C_ADD_SUB=1'b0;
	defparam alu2.ALUD_MODE=2;
	defparam alu2.ALU_RESET_MODE="SYNC";
endmodule

`define FIRMWARE "riscv-firmware/alu54d.hex"
`include "dsp-riscv.v"

