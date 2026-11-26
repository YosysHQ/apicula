`default_nettype none
// GW5A MULTALU27X18: DOUT = CASI/0 + PRE_LOAD/DOUT +- C/0 +- M0, with M0 =
// A*B, (A +- D)*B, SIA*B or (SIA +- D)*B, signed (UG305 4.2.1). Rows (48 bits;
// ACC terms accumulate once per tick):
//   0  0x123456 * 0x1abc - C 0x10000000, every register on, SYNC reset
//   1  pre-adder (A - D) * B: (100 - 300) * -7 = 1400, A not registered
//   2  pre-adder (SIA + D) * B: (node 1's A (100, through SOA) + 23) * 0x123
//      = 35793
//   3  ACC: DOUT + (-3 * 0x55) + C 1000 per clock, registers off but the output
//   4  CASI from node 2 + C 0x1000 + 2*3 = 35793 + 4096 + 6 = 39895
module dsp_multalu27x18(input wire clk, input wire reset,
	output wire [63:0] product,
	output wire [63:0] product1,
	output wire [63:0] product2,
	output wire [63:0] product3,
	output wire [63:0] product4);

	wire [47:0] d0, d1, d2, d3, d4, caso2;
	wire [26:0] soa1;
	assign product = {16'b0, d0};
	assign product1 = {16'b0, d1};
	assign product2 = {16'b0, d2};
	assign product3 = {16'b0, d3};
	assign product4 = {16'b0, d4};

	MULTALU27X18 #(
		.AREG_CLK("CLK0"), .BREG_CLK("CLK0"), .C_IREG_CLK("CLK0"), .PREG_CLK("CLK0"), .C_PREG_CLK("CLK0"),
		.OREG_CLK("CLK0"), .MULT_RESET_MODE("SYNC"), .PRE_LOAD(48'h0),
		.DYN_P_SEL("FALSE"), .P_SEL(1'b0), .DYN_P_ADDSUB("FALSE"), .P_ADDSUB(1'b0),
		.DYN_A_SEL("FALSE"), .A_SEL(1'b0),
		.DYN_ADD_SUB_0("FALSE"), .ADD_SUB_0(1'b0), .DYN_ADD_SUB_1("FALSE"), .ADD_SUB_1(1'b1),
		.DYN_C_SEL("FALSE"), .C_SEL(1'b1), .DYN_CASI_SEL("FALSE"), .CASI_SEL(1'b0),
		.DYN_ACC_SEL("FALSE"), .ACC_SEL(1'b0)
	) r0(.A(27'h123456), .B(18'h1abc), .C(48'h10000000), .D(26'h0), .SIA(27'h0), .CASI(48'h0),
		.ACCSEL(1'b0), .PSEL(1'b0), .ASEL(1'b0), .PADDSUB(1'b0), .CSEL(1'b0), .CASISEL(1'b0), .ADDSUB(2'b00),
		.CLK({1'b0, clk}), .CE(2'b11), .RESET({1'b0, reset}), .DOUT(d0), .CASO(), .SOA());

	MULTALU27X18 #(
		.AREG_CLK("BYPASS"), .BREG_CLK("CLK0"), .DREG_CLK("CLK0"),
		.OREG_CLK("CLK0"), .MULT_RESET_MODE("ASYNC"), .PRE_LOAD(48'h0),
		.DYN_P_SEL("FALSE"), .P_SEL(1'b1), .DYN_P_ADDSUB("FALSE"), .P_ADDSUB(1'b1),
		.DYN_A_SEL("FALSE"), .A_SEL(1'b0),
		.DYN_ADD_SUB_0("FALSE"), .ADD_SUB_0(1'b0), .DYN_ADD_SUB_1("FALSE"), .ADD_SUB_1(1'b0),
		.DYN_C_SEL("FALSE"), .C_SEL(1'b0), .DYN_CASI_SEL("FALSE"), .CASI_SEL(1'b0),
		.DYN_ACC_SEL("FALSE"), .ACC_SEL(1'b0)
	) r1(.A(27'd100), .B(18'h3fff9), .C(48'h0), .D(26'd300), .SIA(27'h0), .CASI(48'h0),
		.ACCSEL(1'b0), .PSEL(1'b0), .ASEL(1'b0), .PADDSUB(1'b0), .CSEL(1'b0), .CASISEL(1'b0), .ADDSUB(2'b00),
		.CLK({1'b0, clk}), .CE(2'b11), .RESET({1'b0, reset}), .DOUT(d1), .CASO(), .SOA(soa1));

	MULTALU27X18 #(
		.AREG_CLK("CLK0"), .BREG_CLK("CLK0"),
		.OREG_CLK("CLK0"), .MULT_RESET_MODE("ASYNC"), .PRE_LOAD(48'h0),
		.DYN_P_SEL("FALSE"), .P_SEL(1'b1), .DYN_P_ADDSUB("FALSE"), .P_ADDSUB(1'b0),
		.DYN_A_SEL("FALSE"), .A_SEL(1'b1),
		.DYN_ADD_SUB_0("FALSE"), .ADD_SUB_0(1'b0), .DYN_ADD_SUB_1("FALSE"), .ADD_SUB_1(1'b0),
		.DYN_C_SEL("FALSE"), .C_SEL(1'b0), .DYN_CASI_SEL("FALSE"), .CASI_SEL(1'b0),
		.DYN_ACC_SEL("FALSE"), .ACC_SEL(1'b0)
	) r2(.A(27'h0), .B(18'h123), .C(48'h0), .D(26'd23), .SIA(soa1), .CASI(48'h0),
		.ACCSEL(1'b0), .PSEL(1'b0), .ASEL(1'b0), .PADDSUB(1'b0), .CSEL(1'b0), .CASISEL(1'b0), .ADDSUB(2'b00),
		.CLK({1'b0, clk}), .CE(2'b11), .RESET({1'b0, reset}), .DOUT(d2), .CASO(caso2), .SOA());

	MULTALU27X18 #(
		.OREG_CLK("CLK0"), .MULT_RESET_MODE("ASYNC"), .PRE_LOAD(48'h0),
		.DYN_P_SEL("FALSE"), .P_SEL(1'b0), .DYN_P_ADDSUB("FALSE"), .P_ADDSUB(1'b0),
		.DYN_A_SEL("FALSE"), .A_SEL(1'b0),
		.DYN_ADD_SUB_0("FALSE"), .ADD_SUB_0(1'b0), .DYN_ADD_SUB_1("FALSE"), .ADD_SUB_1(1'b0),
		.DYN_C_SEL("FALSE"), .C_SEL(1'b1), .DYN_CASI_SEL("FALSE"), .CASI_SEL(1'b0),
		.DYN_ACC_SEL("FALSE"), .ACC_SEL(1'b1)
	) r3(.A(27'h7fffffd), .B(18'h55), .C(48'd1000), .D(26'h0), .SIA(27'h0), .CASI(48'h0),
		.ACCSEL(1'b0), .PSEL(1'b0), .ASEL(1'b0), .PADDSUB(1'b0), .CSEL(1'b0), .CASISEL(1'b0), .ADDSUB(2'b00),
		.CLK({1'b0, clk}), .CE(2'b11), .RESET({1'b0, reset}), .DOUT(d3), .CASO(), .SOA());

	MULTALU27X18 #(
		.AREG_CLK("CLK0"), .BREG_CLK("CLK0"),
		.OREG_CLK("CLK0"), .MULT_RESET_MODE("ASYNC"), .PRE_LOAD(48'h0),
		.DYN_P_SEL("FALSE"), .P_SEL(1'b0), .DYN_P_ADDSUB("FALSE"), .P_ADDSUB(1'b0),
		.DYN_A_SEL("FALSE"), .A_SEL(1'b0),
		.DYN_ADD_SUB_0("FALSE"), .ADD_SUB_0(1'b0), .DYN_ADD_SUB_1("FALSE"), .ADD_SUB_1(1'b0),
		.DYN_C_SEL("FALSE"), .C_SEL(1'b1), .DYN_CASI_SEL("FALSE"), .CASI_SEL(1'b1),
		.DYN_ACC_SEL("FALSE"), .ACC_SEL(1'b0)
	) r4(.A(27'd2), .B(18'd3), .C(48'h1000), .D(26'h0), .SIA(27'h0), .CASI(caso2),
		.ACCSEL(1'b0), .PSEL(1'b0), .ASEL(1'b0), .PADDSUB(1'b0), .CSEL(1'b0), .CASISEL(1'b0), .ADDSUB(2'b00),
		.CLK({1'b0, clk}), .CE(2'b11), .RESET({1'b0, reset}), .DOUT(d4), .CASO(), .SOA());
endmodule
