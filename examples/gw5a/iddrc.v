`default_nettype none
module top(input wire clk, 
	input wire rst_i, 
	input wire fclk_i,
	input wire data_i,
	output wire [7:0]mled);

	assign mled[2] = !rst_i;
    IDDRC id(
        .D(data_i),
		.CLK(fclk_i),
		.CLEAR(!rst_i),
        .Q0(mled[0]),
        .Q1(mled[1])
    );
	defparam id.Q0_INIT=1'b0;
	defparam id.Q1_INIT=1'b0;

	// dummy DFF
	assign mled[4] = dummy_r;
	reg dummy_r;
	always @(posedge fclk_i) begin
		dummy_r <= !dummy_r;
	end
endmodule
