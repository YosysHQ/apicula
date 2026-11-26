`default_nettype none
// GW5A MULTADDALU12X12: DOUT = CASI/0 + PRE_LOAD/DOUT +- A0*B0 +- A1*B1,
// signed (UG305 4.3.1). Rows (48 bits; ACC terms accumulate once per tick):
//   0  3*4 + 2*5, every register on, B and the output on CLK1/CE1/RESET1
//   1  PRE_LOAD 0xcafe + 0x7ff*-1 - (-0x800*-0x800), the subtract from
//      ADDSUB[1] (DYN_ADD_SUB_1) once go is set
//   2  ACC: DOUT + 3*4 + 2*5 per clock, registers off but the output
//   3  dynamic ACCSEL, low until the first clock: PRE_LOAD 2^32 - (-5*7) on
//      the first clock, then + 35 per clock
//   4  CASI from node 1 + 0x10*0x10 - 1*1. With DYN_CASI_SEL = "TRUE"
//      (dsp-casisel-bugs) CASISEL selects CASI once go is set; that
//      CASISEL acts inverted on the board, #664.
module dsp_multaddalu12x12 #(parameter DYN_CASI_SEL = "FALSE") (input wire clk, input wire reset,
	output wire [63:0] product,
	output wire [63:0] product1,
	output wire [63:0] product2,
	output wire [63:0] product3,
	output wire [63:0] product4);

	wire [47:0] d0, d1, d2, d3, d4, caso1;
	assign product = {16'b0, d0};
	assign product1 = {16'b0, d1};
	assign product2 = {16'b0, d2};
	assign product3 = {16'b0, d3};
	assign product4 = {16'b0, d4};

	// Dynamic controls, low until the first clock: ACCSEL of node 3, ADDSUB[1]
	// of node 1, CASISEL of node 4 (with DYN_CASI_SEL). The static settings
	// are the opposite.
	reg go = 1'b0;
	always @(posedge clk)
		go <= 1'b1;

	MULTADDALU12X12 #(
		.A0REG_CLK("CLK0"), .B0REG_CLK("CLK1"), .B0REG_CE("CE1"), .B0REG_RESET("RESET1"),
		.A1REG_CLK("CLK0"), .B1REG_CLK("CLK1"), .B1REG_CE("CE1"), .B1REG_RESET("RESET1"),
		.PREG0_CLK("CLK0"), .PREG1_CLK("CLK0"),
		.OREG_CLK("CLK1"), .OREG_CE("CE1"), .OREG_RESET("RESET1"),
		.MULT_RESET_MODE("ASYNC"), .PRE_LOAD(48'h0),
		.DYN_ADD_SUB_0("FALSE"), .ADD_SUB_0(1'b0), .DYN_ADD_SUB_1("FALSE"), .ADD_SUB_1(1'b0),
		.DYN_CASI_SEL("FALSE"), .CASI_SEL(1'b0), .DYN_ACC_SEL("FALSE"), .ACC_SEL(1'b0)
	) n0(.A0(12'd3), .B0(12'd4), .A1(12'd2), .B1(12'd5), .CASI(48'b0), .ACCSEL(1'b0), .CASISEL(1'b0),
		.ADDSUB(2'b00), .CLK({clk, clk}), .CE(2'b11), .RESET({reset, reset}), .DOUT(d0), .CASO());

	MULTADDALU12X12 #(
		.A0REG_CLK("CLK0"), .B0REG_CLK("CLK0"), .A1REG_CLK("CLK0"), .B1REG_CLK("CLK0"),
		.OREG_CLK("CLK0"),
		.MULT_RESET_MODE("ASYNC"), .PRE_LOAD(48'hcafe),
		.DYN_ADD_SUB_0("FALSE"), .ADD_SUB_0(1'b0), .DYN_ADD_SUB_1("TRUE"), .ADD_SUB_1(1'b0),
		.DYN_CASI_SEL("FALSE"), .CASI_SEL(1'b0), .DYN_ACC_SEL("FALSE"), .ACC_SEL(1'b0)
	) n1(.A0(12'h7ff), .B0(12'hfff), .A1(12'h800), .B1(12'h800), .CASI(48'b0), .ACCSEL(1'b0), .CASISEL(1'b0),
		.ADDSUB({go, 1'b0}), .CLK({1'b0, clk}), .CE(2'b11), .RESET({1'b0, reset}), .DOUT(d1), .CASO(caso1));

	MULTADDALU12X12 #(
		.OREG_CLK("CLK0"),
		.MULT_RESET_MODE("ASYNC"), .PRE_LOAD(48'h0),
		.DYN_ADD_SUB_0("FALSE"), .ADD_SUB_0(1'b0), .DYN_ADD_SUB_1("FALSE"), .ADD_SUB_1(1'b0),
		.DYN_CASI_SEL("FALSE"), .CASI_SEL(1'b0), .DYN_ACC_SEL("FALSE"), .ACC_SEL(1'b1)
	) n2(.A0(12'd3), .B0(12'd4), .A1(12'd2), .B1(12'd5), .CASI(48'b0), .ACCSEL(1'b0), .CASISEL(1'b0),
		.ADDSUB(2'b00), .CLK({1'b0, clk}), .CE(2'b11), .RESET({1'b0, reset}), .DOUT(d2), .CASO());

	MULTADDALU12X12 #(
		.OREG_CLK("CLK0"),
		.MULT_RESET_MODE("ASYNC"), .PRE_LOAD(48'h1_0000_0000),
		.DYN_ADD_SUB_0("FALSE"), .ADD_SUB_0(1'b1), .DYN_ADD_SUB_1("FALSE"), .ADD_SUB_1(1'b0),
		.DYN_CASI_SEL("FALSE"), .CASI_SEL(1'b0), .DYN_ACC_SEL("TRUE"), .ACC_SEL(1'b0)
	) n3(.A0(12'hffb), .B0(12'd7), .A1(12'd0), .B1(12'd0), .CASI(48'b0), .ACCSEL(go), .CASISEL(1'b0),
		.ADDSUB(2'b00), .CLK({1'b0, clk}), .CE(2'b11), .RESET({1'b0, reset}), .DOUT(d3), .CASO());

	MULTADDALU12X12 #(
		.A0REG_CLK("CLK0"), .B0REG_CLK("CLK0"), .A1REG_CLK("CLK0"), .B1REG_CLK("CLK0"),
		.OREG_CLK("CLK0"),
		.MULT_RESET_MODE("ASYNC"), .PRE_LOAD(48'h0),
		.DYN_ADD_SUB_0("FALSE"), .ADD_SUB_0(1'b0), .DYN_ADD_SUB_1("FALSE"), .ADD_SUB_1(1'b1),
		.DYN_CASI_SEL(DYN_CASI_SEL), .CASI_SEL(DYN_CASI_SEL != "TRUE"), .DYN_ACC_SEL("FALSE"), .ACC_SEL(1'b0)
	) n4(.A0(12'h10), .B0(12'h10), .A1(12'd1), .B1(12'd1), .CASI(caso1), .ACCSEL(1'b0), .CASISEL(go),
		.ADDSUB(2'b00), .CLK({1'b0, clk}), .CE(2'b11), .RESET({1'b0, reset}), .DOUT(d4), .CASO());
endmodule
