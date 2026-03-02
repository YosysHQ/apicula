`default_nettype none
module idsp(input wire clk, input wire reset, input wire key,
	output wire [63:0] product, 
	output wire [63:0] product1, 
	output wire [63:0] product2, 
	output wire [63:0] product3, 
	output wire [63:0] product4);

	wire ce = 1'b1;

	wire [26:0] in_a = 27'hcafe;
	wire [35:0] in_b = 18'h2;
	wire [25:0] in_d = 26'h10;

// result = (0xcafe + 0x10) * 2 = 0x1961c
MULT27X36 m0 (
    .DOUT(product),
    .A(in_a),
    .B(in_b),
    .D(in_d),
    .PSEL(1'b0),
    .PADDSUB(1'b0),
    .CLK({1'b0, clk}),
    .CE({ce, ce}),
    .RESET({1'b0, reset})
);

defparam m0.AREG_CLK = "CLK0";
defparam m0.AREG_CE = "CE0";
defparam m0.AREG_RESET = "RESET0";
defparam m0.BREG_CLK = "CLK0";
defparam m0.BREG_CE = "CE0";
defparam m0.BREG_RESET = "RESET0";
defparam m0.DREG_CLK = "CLK0";
defparam m0.DREG_CE = "CE0";
defparam m0.DREG_RESET = "RESET0";
defparam m0.PADDSUB_IREG_CLK = "BYPASS";
defparam m0.PADDSUB_IREG_CE = "CE0";
defparam m0.PADDSUB_IREG_RESET = "RESET0";
defparam m0.PREG_CLK = "BYPASS";
defparam m0.PREG_CE = "CE0";
defparam m0.PREG_RESET = "RESET0";
defparam m0.PSEL_IREG_CLK = "BYPASS";
defparam m0.PSEL_IREG_CE = "CE0";
defparam m0.PSEL_IREG_RESET = "RESET0";
defparam m0.OREG_CLK = "CLK0";
defparam m0.OREG_CE = "CE0";
defparam m0.OREG_RESET = "RESET0";
defparam m0.MULT_RESET_MODE = "ASYNC";
defparam m0.DYN_P_SEL = "FALSE";
defparam m0.P_SEL = 1'b1;
defparam m0.DYN_P_ADDSUB = "FALSE";
defparam m0.P_ADDSUB = 1'b0;


// result = (0x1961c + 0x10) * 2 = 0x32c58
MULT27X36 m1 (
    .DOUT(product1),
    .A(product[26:0]),
    .B(in_b),
    .D(in_d),
    .PSEL(1'b0),
    .PADDSUB(1'b0),
    .CLK({1'b0, clk}),
    .CE({ce, ce}),
    .RESET({1'b0, reset})
);

defparam m1.AREG_CLK = "CLK0";
defparam m1.AREG_CE = "CE0";
defparam m1.AREG_RESET = "RESET0";
defparam m1.BREG_CLK = "CLK0";
defparam m1.BREG_CE = "CE0";
defparam m1.BREG_RESET = "RESET0";
defparam m1.DREG_CLK = "CLK0";
defparam m1.DREG_CE = "CE0";
defparam m1.DREG_RESET = "RESET0";
defparam m1.PADDSUB_IREG_CLK = "BYPASS";
defparam m1.PADDSUB_IREG_CE = "CE0";
defparam m1.PADDSUB_IREG_RESET = "RESET0";
defparam m1.PREG_CLK = "BYPASS";
defparam m1.PREG_CE = "CE0";
defparam m1.PREG_RESET = "RESET0";
defparam m1.PSEL_IREG_CLK = "BYPASS";
defparam m1.PSEL_IREG_CE = "CE0";
defparam m1.PSEL_IREG_RESET = "RESET0";
defparam m1.OREG_CLK = "CLK0";
defparam m1.OREG_CE = "CE0";
defparam m1.OREG_RESET = "RESET0";
defparam m1.MULT_RESET_MODE = "ASYNC";
defparam m1.DYN_P_SEL = "FALSE";
defparam m1.P_SEL = 1'b1;
defparam m1.DYN_P_ADDSUB = "FALSE";
defparam m1.P_ADDSUB = 1'b0;

// result = (0xcafe + 0x100) * 2 = 0x197fc
MULT27X36 m2 (
    .DOUT(product2),
    .A(in_a),
    .B(in_b),
    .D(26'h100),
    .PSEL(1'b0),
    .PADDSUB(1'b0),
    .CLK({1'b0, clk}),
    .CE({ce, ce}),
    .RESET({1'b0, reset})
);

defparam m2.AREG_CLK = "CLK0";
defparam m2.AREG_CE = "CE0";
defparam m2.AREG_RESET = "RESET0";
defparam m2.BREG_CLK = "CLK0";
defparam m2.BREG_CE = "CE0";
defparam m2.BREG_RESET = "RESET0";
defparam m2.DREG_CLK = "CLK0";
defparam m2.DREG_CE = "CE0";
defparam m2.DREG_RESET = "RESET0";
defparam m2.PADDSUB_IREG_CLK = "BYPASS";
defparam m2.PADDSUB_IREG_CE = "CE0";
defparam m2.PADDSUB_IREG_RESET = "RESET0";
defparam m2.PREG_CLK = "BYPASS";
defparam m2.PREG_CE = "CE0";
defparam m2.PREG_RESET = "RESET0";
defparam m2.PSEL_IREG_CLK = "BYPASS";
defparam m2.PSEL_IREG_CE = "CE0";
defparam m2.PSEL_IREG_RESET = "RESET0";
defparam m2.OREG_CLK = "CLK0";
defparam m2.OREG_CE = "CE0";
defparam m2.OREG_RESET = "RESET0";
defparam m2.MULT_RESET_MODE = "ASYNC";
defparam m2.DYN_P_SEL = "FALSE";
defparam m2.P_SEL = 1'b1;
defparam m2.DYN_P_ADDSUB = "FALSE";
defparam m2.P_ADDSUB = 1'b0;

// result (0xcafe + 0x5) * 0x100 = 0xcb0300
MULT27X36 m3 (
    .DOUT(product3),
    .A(in_a),
    .B(36'h100),
    .D(26'h5),
    .PSEL(1'b0),
    .PADDSUB(1'b0),
    .CLK({1'b0, clk}),
    .CE({ce, ce}),
    .RESET({1'b0, reset})
);

defparam m3.AREG_CLK = "CLK0";
defparam m3.AREG_CE = "CE0";
defparam m3.AREG_RESET = "RESET0";
defparam m3.BREG_CLK = "CLK0";
defparam m3.BREG_CE = "CE0";
defparam m3.BREG_RESET = "RESET0";
defparam m3.DREG_CLK = "CLK0";
defparam m3.DREG_CE = "CE0";
defparam m3.DREG_RESET = "RESET0";
defparam m3.PADDSUB_IREG_CLK = "BYPASS";
defparam m3.PADDSUB_IREG_CE = "CE0";
defparam m3.PADDSUB_IREG_RESET = "RESET0";
defparam m3.PREG_CLK = "BYPASS";
defparam m3.PREG_CE = "CE0";
defparam m3.PREG_RESET = "RESET0";
defparam m3.PSEL_IREG_CLK = "BYPASS";
defparam m3.PSEL_IREG_CE = "CE0";
defparam m3.PSEL_IREG_RESET = "RESET0";
defparam m3.OREG_CLK = "CLK0";
defparam m3.OREG_CE = "CE0";
defparam m3.OREG_RESET = "RESET0";
defparam m3.MULT_RESET_MODE = "ASYNC";
defparam m3.DYN_P_SEL = "FALSE";
defparam m3.P_SEL = 1'b1;
defparam m3.DYN_P_ADDSUB = "FALSE";
defparam m3.P_ADDSUB = 1'b0;

// result = 0xcb0300 + 0x123 = 0xcb0423
MULT27X36 m4 (
    .DOUT(product4),
    .A(product3[26:0]),
    .B(36'h1),
    .D(26'h123),
    .PSEL(1'b0),
    .PADDSUB(1'b0),
    .CLK({1'b0, clk}),
    .CE({ce, ce}),
    .RESET({1'b0, reset})
);

defparam m4.AREG_CLK = "CLK0";
defparam m4.AREG_CE = "CE0";
defparam m4.AREG_RESET = "RESET0";
defparam m4.BREG_CLK = "CLK0";
defparam m4.BREG_CE = "CE0";
defparam m4.BREG_RESET = "RESET0";
defparam m4.DREG_CLK = "CLK0";
defparam m4.DREG_CE = "CE0";
defparam m4.DREG_RESET = "RESET0";
defparam m4.PADDSUB_IREG_CLK = "BYPASS";
defparam m4.PADDSUB_IREG_CE = "CE0";
defparam m4.PADDSUB_IREG_RESET = "RESET0";
defparam m4.PREG_CLK = "BYPASS";
defparam m4.PREG_CE = "CE0";
defparam m4.PREG_RESET = "RESET0";
defparam m4.PSEL_IREG_CLK = "BYPASS";
defparam m4.PSEL_IREG_CE = "CE0";
defparam m4.PSEL_IREG_RESET = "RESET0";
defparam m4.OREG_CLK = "CLK0";
defparam m4.OREG_CE = "CE0";
defparam m4.OREG_RESET = "RESET0";
defparam m4.MULT_RESET_MODE = "ASYNC";
defparam m4.DYN_P_SEL = "FALSE";
defparam m4.P_SEL = 1'b1;
defparam m4.DYN_P_ADDSUB = "FALSE";
defparam m4.P_ADDSUB = 1'b0;

endmodule

`define FIRMWARE "../riscv-firmware/mult27x36.hex"
`include "dsp-riscv.v"

