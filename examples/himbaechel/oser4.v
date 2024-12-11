`default_nettype none
/*
* This example allows you to generate several OSER10 primitives and then check
* them with a logic analyzer. The PCLK, FCLK and Q outputs of the primitives
* are connected to the board pins.
*/
module top(input wire clk, 
	input wire rst_i,
	output wire oser_out,
	output wire pclk_o,
    output wire fclk_o);

	wire aux_wire;
	IODELAY delay0(
		.DI(aux_wire),
		.DO(oser_out),
		.SDTAP(1'b0),
		.SETN(1'b1),
		.VALUE(1'b0),
		.DF()
	);

	defparam delay0.C_STATIC_DLY=100;

	wire rst = rst_i ^ `INV_BTN;
	OSER4 os(
		.D0(1'b0),
		.D1(1'b1),
		.D2(1'b0),
		.D3(1'b1),
		.TX0(1'b1),
		.TX1(1'b1),
		.FCLK(fclk_w),
		.PCLK(pclk_w),
		.RESET(1'b0),
		.Q0(aux_wire),
		.Q1()
	);
	defparam os.GSREN = "false";
	defparam os.LSREN = "true";

	wire clk_w;
	wire pclk_w;
	wire fclk_w;

	assign pclk_o = pclk_w;
	assign fclk_o = fclk_w;

	reg clkB;

	always@(negedge fclk_w) begin
		clkB <= ~clkB;
	end
	assign pclk_w = clkB;

	// slow 
	reg [24:0] ctr_q;
	wire [24:0] ctr_d;
	wire tick_w;

	// Sequential code (flip-flop)
	always @(posedge clk)
		ctr_q <= ctr_d;

	// Combinational code (boolean logic)
	assign ctr_d = ctr_q + 1'b1;
	assign tick_w = ctr_q[24];

	assign fclk_w = tick_w;
endmodule
