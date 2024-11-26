`default_nettype none
module top(input wire clk, 
	input wire rst_i, 
	input wire fclk_i,
	input wire data_i,
	output wire pclk_o,
	output wire [7:0]q_o);

	wire rst = rst_i ^ `INV_BTN;
    IDES4 ides(
        .D(data_i),
		.FCLK(fclk_i),
		.PCLK(pclk_o),
		.CALIB(1'b0),
		.RESET(!rst),
        .Q0(q_o[0]),
        .Q1(q_o[1]),
        .Q2(q_o[2]),
        .Q3(q_o[3])
    );
	defparam ides.GSREN="false";
	defparam ides.LSREN="true";

	IEM iem0(
        .D(data_i),
        .CLK(pclk_o),
        .MCLK(clk),
        .LAG(q_o[5]),
        .LEAD(q_o[6]),
        .RESET(!rst)
    );		

    reg pclk_r;
    always @(posedge fclk_i) begin
        pclk_r <= !pclk_r;
    end
	assign pclk_o = pclk_r;

endmodule
