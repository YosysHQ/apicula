`default_nettype none
module idsp(input wire clk, input wire reset, input wire key,
	output wire [63:0] product, 
	output wire [63:0] product1, 
	output wire [63:0] product2, 
	output wire [63:0] product3, 
	output wire [63:0] product4);

wire ce = 1'b1;
wire [26:0] in_a = 27'hcafe;
wire [17:0] in_b = 18'h2;
wire [47:0] in_c = 48'h1;
wire [25:0] in_d = 26'h10;

wire [47:0] caso[3:0];
wire [26:0] soa[3:0];

// result (caso) = (0xcafe + 0x10) * 2 + 1 = 0x1961d
// soa = 0xcafe
MULTALU27X18 m0 (
    .DOUT(product),
    .CASO(caso[0]),
    .SOA(soa[0]),
    .A(in_a),
    .B(in_b),
    .C(in_c),
    .D(in_d),
    .SIA(27'h0),
    .CASI(48'h0),
    .ACCSEL(1'b0),
    .CASISEL(1'b0),
    .ASEL(1'b0),
    .PSEL(1'b0),
    .CSEL(1'b0),
    .ADDSUB({1'b0,1'b0}),
    .PADDSUB(1'b0),
    .CLK({1'b0,clk}),
    .CE({1'b0,ce}),
    .RESET({1'b0,reset})
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
defparam m0.C_IREG_CLK = "CLK0";
defparam m0.C_IREG_CE = "CE0";
defparam m0.C_IREG_RESET = "RESET0";
defparam m0.PSEL_IREG_CLK = "BYPASS";
defparam m0.PSEL_IREG_CE = "CE0";
defparam m0.PSEL_IREG_RESET = "RESET0";
defparam m0.PADDSUB_IREG_CLK = "BYPASS";
defparam m0.PADDSUB_IREG_CE = "CE0";
defparam m0.PADDSUB_IREG_RESET = "RESET0";
defparam m0.ADDSUB0_IREG_CLK = "BYPASS";
defparam m0.ADDSUB0_IREG_CE = "CE0";
defparam m0.ADDSUB0_IREG_RESET = "RESET0";
defparam m0.ADDSUB1_IREG_CLK = "BYPASS";
defparam m0.ADDSUB1_IREG_CE = "CE0";
defparam m0.ADDSUB1_IREG_RESET = "RESET0";
defparam m0.CSEL_IREG_CLK = "BYPASS";
defparam m0.CSEL_IREG_CE = "CE0";
defparam m0.CSEL_IREG_RESET = "RESET0";
defparam m0.CASISEL_IREG_CLK = "BYPASS";
defparam m0.CASISEL_IREG_CE = "CE0";
defparam m0.CASISEL_IREG_RESET = "RESET0";
defparam m0.ACCSEL_IREG_CLK = "BYPASS";
defparam m0.ACCSEL_IREG_CE = "CE0";
defparam m0.ACCSEL_IREG_RESET = "RESET0";
defparam m0.PREG_CLK = "BYPASS";
defparam m0.PREG_CE = "CE0";
defparam m0.PREG_RESET = "RESET0";
defparam m0.ADDSUB0_PREG_CLK = "BYPASS";
defparam m0.ADDSUB0_PREG_CE = "CE0";
defparam m0.ADDSUB0_PREG_RESET = "RESET0";
defparam m0.ADDSUB1_PREG_CLK = "BYPASS";
defparam m0.ADDSUB1_PREG_CE = "CE0";
defparam m0.ADDSUB1_PREG_RESET = "RESET0";
defparam m0.CSEL_PREG_CLK = "BYPASS";
defparam m0.CSEL_PREG_CE = "CE0";
defparam m0.CSEL_PREG_RESET = "RESET0";
defparam m0.CASISEL_PREG_CLK = "BYPASS";
defparam m0.CASISEL_PREG_CE = "CE0";
defparam m0.CASISEL_PREG_RESET = "RESET0";
defparam m0.ACCSEL_PREG_CLK = "BYPASS";
defparam m0.ACCSEL_PREG_CE = "CE0";
defparam m0.ACCSEL_PREG_RESET = "RESET0";
defparam m0.C_PREG_CLK = "CLK0";
defparam m0.C_PREG_CE = "CE0";
defparam m0.C_PREG_RESET = "RESET0";
defparam m0.FB_PREG_EN = "FALSE";
defparam m0.SOA_PREG_EN = "FALSE";
defparam m0.OREG_CLK = "CLK0";
defparam m0.OREG_CE = "CE0";
defparam m0.OREG_RESET = "RESET0";
defparam m0.MULT_RESET_MODE = "SYNC";
defparam m0.PRE_LOAD = 48'h000000000000;
defparam m0.DYN_P_SEL = "FALSE";
defparam m0.P_SEL = 1'b1;
defparam m0.DYN_P_ADDSUB = "FALSE";
defparam m0.P_ADDSUB = 1'b0;
defparam m0.DYN_A_SEL = "FALSE";
defparam m0.A_SEL = 1'b0;
defparam m0.DYN_ADD_SUB_0 = "FALSE";
defparam m0.ADD_SUB_0 = 1'b0;
defparam m0.DYN_ADD_SUB_1 = "FALSE";
defparam m0.ADD_SUB_1 = 1'b0;
defparam m0.DYN_C_SEL = "FALSE";
defparam m0.C_SEL = 1'b1;
defparam m0.DYN_CASI_SEL = "FALSE";
defparam m0.CASI_SEL = 1'b0;
defparam m0.DYN_ACC_SEL = "FALSE";
defparam m0.ACC_SEL = 1'b0;
defparam m0.MULT12X12_EN = "FALSE";

// result = (0xcafe + 0x10) * 2 + 1 + 0x1961d = 0x32c3a
// soa = 0xcafe
MULTALU27X18 m1 (
    .DOUT(product1),
    .CASO(),
    .SOA(soa[1]),
    .A(27'h0),
    .B(in_b),
    .C(in_c),
    .D(in_d),
    .SIA(soa[0]),
    .CASI(caso[0]),
    .ACCSEL(1'b0),
    .CASISEL(1'b0),
    .ASEL(1'b0),
    .PSEL(1'b0),
    .CSEL(1'b0),
    .ADDSUB({1'b0,1'b0}),
    .PADDSUB(1'b0),
    .CLK({1'b0,clk}),
    .CE({1'b0,ce}),
    .RESET({1'b0,reset})
);

defparam m1.AREG_CLK = "CLK0";
defparam m1.AREG_CE = "CE0";
defparam m1.AREG_RESET = "RESET0";
defparam m1.BREG_CLK = "CLK0";
defparam m1.BREG_CE = "CE0";
defparam m1.BREG_RESET = "RESET0";
defparam m1.DREG_CLK = "BYPASS";
defparam m1.DREG_CE = "CE0";
defparam m1.DREG_RESET = "RESET0";
defparam m1.C_IREG_CLK = "BYPASS";
defparam m1.C_IREG_CE = "CE0";
defparam m1.C_IREG_RESET = "RESET0";
defparam m1.PSEL_IREG_CLK = "BYPASS";
defparam m1.PSEL_IREG_CE = "CE0";
defparam m1.PSEL_IREG_RESET = "RESET0";
defparam m1.PADDSUB_IREG_CLK = "BYPASS";
defparam m1.PADDSUB_IREG_CE = "CE0";
defparam m1.PADDSUB_IREG_RESET = "RESET0";
defparam m1.ADDSUB0_IREG_CLK = "BYPASS";
defparam m1.ADDSUB0_IREG_CE = "CE0";
defparam m1.ADDSUB0_IREG_RESET = "RESET0";
defparam m1.ADDSUB1_IREG_CLK = "BYPASS";
defparam m1.ADDSUB1_IREG_CE = "CE0";
defparam m1.ADDSUB1_IREG_RESET = "RESET0";
defparam m1.CSEL_IREG_CLK = "BYPASS";
defparam m1.CSEL_IREG_CE = "CE0";
defparam m1.CSEL_IREG_RESET = "RESET0";
defparam m1.CASISEL_IREG_CLK = "BYPASS";
defparam m1.CASISEL_IREG_CE = "CE0";
defparam m1.CASISEL_IREG_RESET = "RESET0";
defparam m1.ACCSEL_IREG_CLK = "BYPASS";
defparam m1.ACCSEL_IREG_CE = "CE0";
defparam m1.ACCSEL_IREG_RESET = "RESET0";
defparam m1.PREG_CLK = "BYPASS";
defparam m1.PREG_CE = "CE0";
defparam m1.PREG_RESET = "RESET0";
defparam m1.ADDSUB0_PREG_CLK = "BYPASS";
defparam m1.ADDSUB0_PREG_CE = "CE0";
defparam m1.ADDSUB0_PREG_RESET = "RESET0";
defparam m1.ADDSUB1_PREG_CLK = "BYPASS";
defparam m1.ADDSUB1_PREG_CE = "CE0";
defparam m1.ADDSUB1_PREG_RESET = "RESET0";
defparam m1.CSEL_PREG_CLK = "BYPASS";
defparam m1.CSEL_PREG_CE = "CE0";
defparam m1.CSEL_PREG_RESET = "RESET0";
defparam m1.CASISEL_PREG_CLK = "BYPASS";
defparam m1.CASISEL_PREG_CE = "CE0";
defparam m1.CASISEL_PREG_RESET = "RESET0";
defparam m1.ACCSEL_PREG_CLK = "BYPASS";
defparam m1.ACCSEL_PREG_CE = "CE0";
defparam m1.ACCSEL_PREG_RESET = "RESET0";
defparam m1.C_PREG_CLK = "BYPASS";
defparam m1.C_PREG_CE = "CE0";
defparam m1.C_PREG_RESET = "RESET0";
defparam m1.FB_PREG_EN = "FALSE";
defparam m1.SOA_PREG_EN = "FALSE";
defparam m1.OREG_CLK = "CLK0";
defparam m1.OREG_CE = "CE0";
defparam m1.OREG_RESET = "RESET0";
defparam m1.MULT_RESET_MODE = "SYNC";
defparam m1.PRE_LOAD = 48'h000000000000;
defparam m1.DYN_P_SEL = "FALSE";
defparam m1.P_SEL = 1'b1;
defparam m1.DYN_P_ADDSUB = "FALSE";
defparam m1.P_ADDSUB = 1'b0;
defparam m1.DYN_A_SEL = "FALSE";
defparam m1.A_SEL = 1'b1;
defparam m1.DYN_ADD_SUB_0 = "FALSE";
defparam m1.ADD_SUB_0 = 1'b0;
defparam m1.DYN_ADD_SUB_1 = "FALSE";
defparam m1.ADD_SUB_1 = 1'b0;
defparam m1.DYN_C_SEL = "FALSE";
defparam m1.C_SEL = 1'b1;
defparam m1.DYN_CASI_SEL = "FALSE";
defparam m1.CASI_SEL = 1'b1;
defparam m1.DYN_ACC_SEL = "FALSE";
defparam m1.ACC_SEL = 1'b0;
defparam m1.MULT12X12_EN = "FALSE";

// result = (0xcafe + 0x10) * 2 = 0x1961c
// soa = 0xcafe
MULTALU27X18 m2 (
    .DOUT(product2),
    .CASO(),
    .SOA(soa[2]),
    .A(27'h0),
    .B(in_b),
    .C(in_c),
    .D(in_d),
    .SIA(soa[1]),
    .CASI(),
    .ACCSEL(1'b0),
    .CASISEL(1'b0),
    .ASEL(1'b0),
    .PSEL(1'b0),
    .CSEL(1'b0),
    .ADDSUB({1'b0,1'b0}),
    .PADDSUB(1'b0),
    .CLK({1'b0,clk}),
    .CE({1'b0,ce}),
    .RESET({1'b0,reset})
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
defparam m2.C_IREG_CLK = "BYPASS";
defparam m2.C_IREG_CE = "CE0";
defparam m2.C_IREG_RESET = "RESET0";
defparam m2.PSEL_IREG_CLK = "BYPASS";
defparam m2.PSEL_IREG_CE = "CE0";
defparam m2.PSEL_IREG_RESET = "RESET0";
defparam m2.PADDSUB_IREG_CLK = "BYPASS";
defparam m2.PADDSUB_IREG_CE = "CE0";
defparam m2.PADDSUB_IREG_RESET = "RESET0";
defparam m2.ADDSUB0_IREG_CLK = "BYPASS";
defparam m2.ADDSUB0_IREG_CE = "CE0";
defparam m2.ADDSUB0_IREG_RESET = "RESET0";
defparam m2.ADDSUB1_IREG_CLK = "BYPASS";
defparam m2.ADDSUB1_IREG_CE = "CE0";
defparam m2.ADDSUB1_IREG_RESET = "RESET0";
defparam m2.CSEL_IREG_CLK = "BYPASS";
defparam m2.CSEL_IREG_CE = "CE0";
defparam m2.CSEL_IREG_RESET = "RESET0";
defparam m2.CASISEL_IREG_CLK = "BYPASS";
defparam m2.CASISEL_IREG_CE = "CE0";
defparam m2.CASISEL_IREG_RESET = "RESET0";
defparam m2.ACCSEL_IREG_CLK = "BYPASS";
defparam m2.ACCSEL_IREG_CE = "CE0";
defparam m2.ACCSEL_IREG_RESET = "RESET0";
defparam m2.PREG_CLK = "BYPASS";
defparam m2.PREG_CE = "CE0";
defparam m2.PREG_RESET = "RESET0";
defparam m2.ADDSUB0_PREG_CLK = "BYPASS";
defparam m2.ADDSUB0_PREG_CE = "CE0";
defparam m2.ADDSUB0_PREG_RESET = "RESET0";
defparam m2.ADDSUB1_PREG_CLK = "BYPASS";
defparam m2.ADDSUB1_PREG_CE = "CE0";
defparam m2.ADDSUB1_PREG_RESET = "RESET0";
defparam m2.CSEL_PREG_CLK = "BYPASS";
defparam m2.CSEL_PREG_CE = "CE0";
defparam m2.CSEL_PREG_RESET = "RESET0";
defparam m2.CASISEL_PREG_CLK = "BYPASS";
defparam m2.CASISEL_PREG_CE = "CE0";
defparam m2.CASISEL_PREG_RESET = "RESET0";
defparam m2.ACCSEL_PREG_CLK = "BYPASS";
defparam m2.ACCSEL_PREG_CE = "CE0";
defparam m2.ACCSEL_PREG_RESET = "RESET0";
defparam m2.C_PREG_CLK = "BYPASS";
defparam m2.C_PREG_CE = "CE0";
defparam m2.C_PREG_RESET = "RESET0";
defparam m2.FB_PREG_EN = "FALSE";
defparam m2.SOA_PREG_EN = "FALSE";
defparam m2.OREG_CLK = "CLK0";
defparam m2.OREG_CE = "CE0";
defparam m2.OREG_RESET = "RESET0";
defparam m2.MULT_RESET_MODE = "SYNC";
defparam m2.PRE_LOAD = 48'h000000000000;
defparam m2.DYN_P_SEL = "FALSE";
defparam m2.P_SEL = 1'b1;
defparam m2.DYN_P_ADDSUB = "FALSE";
defparam m2.P_ADDSUB = 1'b0;
defparam m2.DYN_A_SEL = "FALSE";
defparam m2.A_SEL = 1'b1;
defparam m2.DYN_ADD_SUB_0 = "FALSE";
defparam m2.ADD_SUB_0 = 1'b0;
defparam m2.DYN_ADD_SUB_1 = "FALSE";
defparam m2.ADD_SUB_1 = 1'b0;
defparam m2.DYN_C_SEL = "FALSE";
defparam m2.C_SEL = 1'b0;
defparam m2.DYN_CASI_SEL = "FALSE";
defparam m2.CASI_SEL = 1'b0;
defparam m2.DYN_ACC_SEL = "FALSE";
defparam m2.ACC_SEL = 1'b0;
defparam m2.MULT12X12_EN = "FALSE";

// result (caso) = 0xcafe * 2 + 1 = 0x195fd
// caso = 0x195fd
MULTALU27X18 m3 (
    .DOUT(product3),
    .CASO(caso[3]),
    .SOA(),
    .A(27'h0),
    .B(in_b),
    .C(in_c),
    .D(in_d),
    .SIA(soa[2]),
    .CASI(),
    .ACCSEL(1'b0),
    .CASISEL(1'b0),
    .ASEL(1'b0),
    .PSEL(1'b0),
    .CSEL(1'b0),
    .ADDSUB({1'b0,1'b0}),
    .PADDSUB(1'b0),
    .CLK({1'b0,clk}),
    .CE({1'b0,ce}),
    .RESET({1'b0,reset})
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
defparam m3.C_IREG_CLK = "BYPASS";
defparam m3.C_IREG_CE = "CE0";
defparam m3.C_IREG_RESET = "RESET0";
defparam m3.PSEL_IREG_CLK = "BYPASS";
defparam m3.PSEL_IREG_CE = "CE0";
defparam m3.PSEL_IREG_RESET = "RESET0";
defparam m3.PADDSUB_IREG_CLK = "BYPASS";
defparam m3.PADDSUB_IREG_CE = "CE0";
defparam m3.PADDSUB_IREG_RESET = "RESET0";
defparam m3.ADDSUB0_IREG_CLK = "BYPASS";
defparam m3.ADDSUB0_IREG_CE = "CE0";
defparam m3.ADDSUB0_IREG_RESET = "RESET0";
defparam m3.ADDSUB1_IREG_CLK = "BYPASS";
defparam m3.ADDSUB1_IREG_CE = "CE0";
defparam m3.ADDSUB1_IREG_RESET = "RESET0";
defparam m3.CSEL_IREG_CLK = "BYPASS";
defparam m3.CSEL_IREG_CE = "CE0";
defparam m3.CSEL_IREG_RESET = "RESET0";
defparam m3.CASISEL_IREG_CLK = "BYPASS";
defparam m3.CASISEL_IREG_CE = "CE0";
defparam m3.CASISEL_IREG_RESET = "RESET0";
defparam m3.ACCSEL_IREG_CLK = "BYPASS";
defparam m3.ACCSEL_IREG_CE = "CE0";
defparam m3.ACCSEL_IREG_RESET = "RESET0";
defparam m3.PREG_CLK = "BYPASS";
defparam m3.PREG_CE = "CE0";
defparam m3.PREG_RESET = "RESET0";
defparam m3.ADDSUB0_PREG_CLK = "BYPASS";
defparam m3.ADDSUB0_PREG_CE = "CE0";
defparam m3.ADDSUB0_PREG_RESET = "RESET0";
defparam m3.ADDSUB1_PREG_CLK = "BYPASS";
defparam m3.ADDSUB1_PREG_CE = "CE0";
defparam m3.ADDSUB1_PREG_RESET = "RESET0";
defparam m3.CSEL_PREG_CLK = "BYPASS";
defparam m3.CSEL_PREG_CE = "CE0";
defparam m3.CSEL_PREG_RESET = "RESET0";
defparam m3.CASISEL_PREG_CLK = "BYPASS";
defparam m3.CASISEL_PREG_CE = "CE0";
defparam m3.CASISEL_PREG_RESET = "RESET0";
defparam m3.ACCSEL_PREG_CLK = "BYPASS";
defparam m3.ACCSEL_PREG_CE = "CE0";
defparam m3.ACCSEL_PREG_RESET = "RESET0";
defparam m3.C_PREG_CLK = "BYPASS";
defparam m3.C_PREG_CE = "CE0";
defparam m3.C_PREG_RESET = "RESET0";
defparam m3.FB_PREG_EN = "FALSE";
defparam m3.SOA_PREG_EN = "FALSE";
defparam m3.OREG_CLK = "CLK0";
defparam m3.OREG_CE = "CE0";
defparam m3.OREG_RESET = "RESET0";
defparam m3.MULT_RESET_MODE = "SYNC";
defparam m3.PRE_LOAD = 48'h000000000000;
defparam m3.DYN_P_SEL = "FALSE";
defparam m3.P_SEL = 1'b0;
defparam m3.DYN_P_ADDSUB = "FALSE";
defparam m3.P_ADDSUB = 1'b0;
defparam m3.DYN_A_SEL = "FALSE";
defparam m3.A_SEL = 1'b1;
defparam m3.DYN_ADD_SUB_0 = "FALSE";
defparam m3.ADD_SUB_0 = 1'b0;
defparam m3.DYN_ADD_SUB_1 = "FALSE";
defparam m3.ADD_SUB_1 = 1'b0;
defparam m3.DYN_C_SEL = "FALSE";
defparam m3.C_SEL = 1'b1;
defparam m3.DYN_CASI_SEL = "FALSE";
defparam m3.CASI_SEL = 1'b0;
defparam m3.DYN_ACC_SEL = "FALSE";
defparam m3.ACC_SEL = 1'b0;
defparam m3.MULT12X12_EN = "FALSE";

// result (caso) = 0xbeef * 2 + 1 + 0x195fd = 0x313dc
// soa = 0xbeef
MULTALU27X18 m4 (
    .DOUT(product4),
    .CASO(),
    .SOA(),
    .A(27'hbeef),
    .B(in_b),
    .C(in_c),
    .D(in_d),
    .SIA(),
    .CASI(caso[3]),
    .ACCSEL(1'b0),
    .CASISEL(1'b0),
    .ASEL(1'b0),
    .PSEL(1'b0),
    .CSEL(1'b0),
    .ADDSUB({1'b0,1'b0}),
    .PADDSUB(1'b0),
    .CLK({1'b0,clk}),
    .CE({1'b0,ce}),
    .RESET({1'b0,reset})
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
defparam m4.C_IREG_CLK = "BYPASS";
defparam m4.C_IREG_CE = "CE0";
defparam m4.C_IREG_RESET = "RESET0";
defparam m4.PSEL_IREG_CLK = "BYPASS";
defparam m4.PSEL_IREG_CE = "CE0";
defparam m4.PSEL_IREG_RESET = "RESET0";
defparam m4.PADDSUB_IREG_CLK = "BYPASS";
defparam m4.PADDSUB_IREG_CE = "CE0";
defparam m4.PADDSUB_IREG_RESET = "RESET0";
defparam m4.ADDSUB0_IREG_CLK = "BYPASS";
defparam m4.ADDSUB0_IREG_CE = "CE0";
defparam m4.ADDSUB0_IREG_RESET = "RESET0";
defparam m4.ADDSUB1_IREG_CLK = "BYPASS";
defparam m4.ADDSUB1_IREG_CE = "CE0";
defparam m4.ADDSUB1_IREG_RESET = "RESET0";
defparam m4.CSEL_IREG_CLK = "BYPASS";
defparam m4.CSEL_IREG_CE = "CE0";
defparam m4.CSEL_IREG_RESET = "RESET0";
defparam m4.CASISEL_IREG_CLK = "BYPASS";
defparam m4.CASISEL_IREG_CE = "CE0";
defparam m4.CASISEL_IREG_RESET = "RESET0";
defparam m4.ACCSEL_IREG_CLK = "BYPASS";
defparam m4.ACCSEL_IREG_CE = "CE0";
defparam m4.ACCSEL_IREG_RESET = "RESET0";
defparam m4.PREG_CLK = "BYPASS";
defparam m4.PREG_CE = "CE0";
defparam m4.PREG_RESET = "RESET0";
defparam m4.ADDSUB0_PREG_CLK = "BYPASS";
defparam m4.ADDSUB0_PREG_CE = "CE0";
defparam m4.ADDSUB0_PREG_RESET = "RESET0";
defparam m4.ADDSUB1_PREG_CLK = "BYPASS";
defparam m4.ADDSUB1_PREG_CE = "CE0";
defparam m4.ADDSUB1_PREG_RESET = "RESET0";
defparam m4.CSEL_PREG_CLK = "BYPASS";
defparam m4.CSEL_PREG_CE = "CE0";
defparam m4.CSEL_PREG_RESET = "RESET0";
defparam m4.CASISEL_PREG_CLK = "BYPASS";
defparam m4.CASISEL_PREG_CE = "CE0";
defparam m4.CASISEL_PREG_RESET = "RESET0";
defparam m4.ACCSEL_PREG_CLK = "BYPASS";
defparam m4.ACCSEL_PREG_CE = "CE0";
defparam m4.ACCSEL_PREG_RESET = "RESET0";
defparam m4.C_PREG_CLK = "BYPASS";
defparam m4.C_PREG_CE = "CE0";
defparam m4.C_PREG_RESET = "RESET0";
defparam m4.FB_PREG_EN = "FALSE";
defparam m4.SOA_PREG_EN = "FALSE";
defparam m4.OREG_CLK = "CLK0";
defparam m4.OREG_CE = "CE0";
defparam m4.OREG_RESET = "RESET0";
defparam m4.MULT_RESET_MODE = "SYNC";
defparam m4.PRE_LOAD = 48'h000000000000;
defparam m4.DYN_P_SEL = "FALSE";
defparam m4.P_SEL = 1'b0;
defparam m4.DYN_P_ADDSUB = "FALSE";
defparam m4.P_ADDSUB = 1'b0;
defparam m4.DYN_A_SEL = "FALSE";
defparam m4.A_SEL = 1'b0;
defparam m4.DYN_ADD_SUB_0 = "FALSE";
defparam m4.ADD_SUB_0 = 1'b0;
defparam m4.DYN_ADD_SUB_1 = "FALSE";
defparam m4.ADD_SUB_1 = 1'b0;
defparam m4.DYN_C_SEL = "FALSE";
defparam m4.C_SEL = 1'b1;
defparam m4.DYN_CASI_SEL = "FALSE";
defparam m4.CASI_SEL = 1'b1;
defparam m4.DYN_ACC_SEL = "FALSE";
defparam m4.ACC_SEL = 1'b0;
defparam m4.MULT12X12_EN = "FALSE";

endmodule

`define FIRMWARE "../riscv-firmware/multalu27x18.hex"
`include "dsp-riscv.v"

