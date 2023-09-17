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
	OVIDEO os(
		.D0(1'b1),
		.D1(1'b0),
		.D2(1'b1),
		.D3(1'b0),
		.D4(1'b1),
		.D5(1'b0),
		.D6(1'b1),
		.FCLK(fclk_w),
		.PCLK(pclk_w),
		.RESET(1'b0),
		.Q(oser_out)
	);
	defparam os.GSREN = "false";
	defparam os.LSREN = "true";

	wire clk_w;
	wire pclk_w;
	wire fclk_w;

	assign pclk_o = pclk_w;
	assign fclk_o = fclk_w;
	
	// div by 3.5
	reg [6:0]cnt_r;
	reg ps0_r;
	reg ps3_r;
	reg ps4_r;
	always @(posedge fclk_w) begin
		if (!rst) begin
			cnt_r[6:0] <= 7'b000_0001;
		end else begin
			cnt_r[6:0] <= {cnt_r[5:0], cnt_r[6]};
		end
	end

	always @(negedge fclk_w) begin
		if (!rst) begin
			ps0_r <= 1'b0;
			ps3_r <= 1'b0;
			ps4_r <= 1'b0;
		end else begin
			ps0_r <= cnt_r[0];
			ps3_r <= cnt_r[3];
			ps4_r <= cnt_r[4];
		end
	end
    assign pclk_w = (ps0_r | cnt_r[0] | cnt_r[1]) | (ps3_r | ps4_r | cnt_r[4]);
	
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
