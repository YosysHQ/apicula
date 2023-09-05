`default_nettype none
/*
* This example allows you to generate several OSER10 primitives and then check
* them with a logic analyzer. The PCLK, FCLK and Q outputs of the primitives
* are connected to the board pins.
*/
module top(input wire clk, 
	input wire rst_i,
	output wire io16,
	output wire pclk_o,
    output wire fclk_o);

	wire rst = rst_i ^ `INV_BTN;
	OSER16 oser(
		.D0(1'b0),
		.D1(1'b1),
		.D2(1'b0),
		.D3(1'b1),
		.D4(1'b0),
		.D5(1'b1),
		.D6(1'b0),
		.D7(1'b1),
		.D8(1'b0),
		.D9(1'b1),
		.D10(1'b0),
		.D11(1'b1),
		.D12(1'b0),
		.D13(1'b1),
		.D14(1'b0),
		.D15(1'b1),
		.FCLK(fclk_w),
		.PCLK(pclk_o),
		.RESET(1'b0),
		.Q(io16)
	);
	defparam oser.GSREN = "false";
	defparam oser.LSREN = "true";

	wire clk_w;
	wire pclk_w;
	wire fclk_w;

	assign pclk_o = pclk_w;
	assign fclk_o = fclk_w;

    reg [2:0]pclk_r;
    wire fclk_w;

    always @(posedge fclk_w) begin
		if (!rst) begin
			pclk_r <= 3'b00;
		end else begin
			pclk_r <= pclk_r + 3'b01;
		end
    end
    assign pclk_w = pclk_r[2];

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
