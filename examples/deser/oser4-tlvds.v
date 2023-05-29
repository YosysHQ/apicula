`default_nettype none
/*
* This example allows you to generate several OSER4 primitives and then check
* them with a logic analyzer. The PCLK, FCLK and Q0 outputs of the primitives
* are connected to the board pins.
* The exception is the variant for Tangnano9k - here 6 LEDs  on the board are used.
*/
`define CH 2
module top(input wire clk_i, 
	input wire nrst_i,
	output wire [(2 * `CH) - 1:0]q_o,
	output wire pclk_o,
    output wire fclk_o);

	genvar i;
	generate
	  for (i = 0; i < `CH; i = i + 1) begin
		OSER4 os(
			.D0(1'b1),
			.D1(1'b0),
			.D2(1'b1),
			.D3(1'b0),
			.FCLK(fclk_w),
			.PCLK(pclk_w),
			.RESET(1'b0),
			.TX0(1'b0),
			.TX1(1'b0),
			.Q0(dso_w)
		);
		wire dso_w;
		defparam os.GSREN = "false";
		defparam os.LSREN = "true";
		TLVDS_OBUF dso(
			.O(q_o[2 * i]),
			.OB(q_o[1 + 2 * i]),
			.I(dso_w)
		);
	  end
	endgenerate

	wire clk_w;
	wire pclk_w;
	wire fclk_w;
	assign fclk_w = tick_w;

	assign pclk_o = pclk_w;
	assign fclk_o = fclk_w;

	reg [24:0] ctr_q;
	wire [24:0] ctr_d;
	wire tick_w;

	// Sequential code (flip-flop)
	always @(posedge clk_i)
		ctr_q <= ctr_d;

	// Combinational code (boolean logic)
	assign ctr_d = ctr_q + 1'b1;
	assign tick_w = |ctr_q[24:23];
	//assign tick_w = ctr_q[10];


    reg [1:0]pclk_r;
    always @(posedge tick_w) begin
        pclk_r <= pclk_r + 2'b01;
    end
    assign pclk_w = pclk_r[1];
endmodule
