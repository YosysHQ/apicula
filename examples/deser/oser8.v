`default_nettype none
/*
* This example allows you to generate several OSER8 primitives and then check
* them with a logic analyzer. The PCLK, FCLK and Q0 outputs of the primitives
* are connected to the board pins.
* The exception is the variant for Tangnano9k - here 6 LEDs  on the board are used.
*/
`define CH 4
module top(input wire clk_i, 
	input wire nrst_i,
	output wire [`CH - 1:0]q_o,
	output wire pclk_o,
    output wire fclk_o);

	genvar i;
	generate
	  for (i = 0; i < `CH; i = i + 1) begin
		OSER8 os8(
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
			.Q0(q_o[i])
		);
		defparam os8.GSREN = "false";
		defparam os8.LSREN = "true";
		defparam os8.TXCLK_POL = 0;
		defparam os8.HWL = "false";
	  end
	endgenerate

    reg [1:0]pclk_r;
    wire fclk_w;

    always @(posedge fclk_w) begin
		if (!nrst_i) begin
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
	always @(posedge clk_i)
		ctr_q <= ctr_d;

	// Combinational code (boolean logic)
	assign ctr_d = ctr_q + 1'b1;
	assign tick_w = ctr_q[24];

	assign fclk_w = tick_w;
endmodule
