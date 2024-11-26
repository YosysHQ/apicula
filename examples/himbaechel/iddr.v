`default_nettype none
module top(input wire clk, 
	input wire rst_i, 
	input wire fclk_i,
	input wire data_i,
	output wire [7:0]q_o);

	assign q_o[2] = !rst_i;
    IDDR id(
        .D(data_i),
		.CLK(fclk_i),
        .Q0(q_o[0]),
        .Q1(q_o[1])
    );
	defparam id.Q0_INIT=1'b0;
	defparam id.Q1_INIT=1'b0;

	IEM iem0(
		.D(data_i),
		.CLK(fclk_i),
		.MCLK(clk),
		.LAG(q_o[5]),
		.LEAD(q_o[6]),
		.RESET(!rst_i)
	);

	// dummy DFF
	assign q_o[4] = dummy_r;
	reg dummy_r;
	always @(posedge fclk_i) begin
		if (!rst_i) begin
			dummy_r <= 0;
		end else begin
			dummy_r <= !dummy_r;
		end
	end
endmodule
