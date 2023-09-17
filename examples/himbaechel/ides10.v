`default_nettype none
module top(input wire clk, 
	input wire rst_i, 
	input wire fclk_i,
	input wire data_i,
	output wire pclk_o,
	output wire [7:0]q_o);

	wire rst = rst_i ^ `INV_BTN;
	wire dummy[1:0];

    IDES10 ides(
        .D(data_i),
		.FCLK(fclk_i),
		.PCLK(pclk_o),
		.CALIB(1'b0),
		.RESET(!rst),
        .Q0(q_o[0]),
        .Q1(q_o[1]),
        .Q2(q_o[2]),
        .Q3(q_o[3]),
        .Q4(q_o[4]),
        .Q5(q_o[5]),
        .Q6(q_o[6]),
        .Q7(q_o[7]),
        .Q8(dummy[0]),
        .Q9(dummy[1])
    );
	defparam ides.GSREN="false";
	defparam ides.LSREN="true";

	// div by 5
	reg [2:0] count;
	wire clkA;
	reg clkB;
	always @(posedge fclk_i) begin
		if (!rst) begin
			count <= 0;
		end else begin 
			if (count == 3'd4) begin
				count <= 0;
			end else begin
				count <= count+1;
			end
		end 
	end
	assign clkA = count[1];

	always@(negedge fclk_i) begin
		clkB <= clkA;
	end
	assign pclk_o = clkA | clkB;
endmodule
