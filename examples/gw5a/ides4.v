`default_nettype none
module top(input wire clk, 
	input wire rst_i, 
	input wire fclk_i,
	input wire data_i,
	output wire pclk_o,
	output wire [7:0]mled);

	wire rst = rst_i ^ `INV_BTN;
    IDES4 ides(
        .D(data_i),
		.FCLK(fclk_i),
		.PCLK(pclk_o),
		.CALIB(1'b0),
		.RESET(!rst),
        .Q0(mled[0]),
        .Q1(mled[1]),
        .Q2(mled[2]),
        .Q3(mled[3])
    );


    reg pclk_r;
    always @(posedge fclk_i) begin
        pclk_r <= !pclk_r;
    end
	assign pclk_o = pclk_r;

endmodule
