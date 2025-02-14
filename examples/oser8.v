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

	wire rst = rst_i ^ `INV_BTN;
	OSER8 os(
		.D0(1'b0),
		.D1(1'b1),
		.D2(1'b0),
		.D3(1'b1),
		.D4(1'b0),
		.D5(1'b1),
		.D6(1'b0),
		.D7(1'b1),
		.TX0(1'b1),
		.TX1(1'b1),
		.TX2(1'b1),
		.TX3(1'b1),
		.FCLK(fclk_w),
		.PCLK(pclk_r[1]),
		.RESET(1'b0),
		.Q0(oser_out)
	);
	defparam os.GSREN = "false";
	defparam os.LSREN = "true";
	defparam os.TXCLK_POL = 0;
	defparam os.HWL = "false";

    reg [1:0]pclk_r;
    wire fclk_w;

    always @(posedge fclk_w) begin
		if (!rst) begin
			pclk_r <= 2'b00;
		end else begin
	        pclk_r <= pclk_r + 2'b01;
		end
    end
    assign pclk_o = pclk_r[1];
	assign fclk_o = fclk_w;

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
