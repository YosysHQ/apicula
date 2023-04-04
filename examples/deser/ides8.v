`default_nettype none
module top(input wire clk_i, 
	input wire nrst_i, 
	input wire fclk_i,
	input wire data_i,
	output wire pclk_o,
	output wire [7:0]q_o);

    IDES8 ides(
        .D(data_i),
		.FCLK(fclk_i),
		.PCLK(pclk_o),
		.CALIB(1'b0),
		.RESET(!nrst_i),
        .Q0(q_o[0]),
        .Q1(q_o[1]),
        .Q2(q_o[2]),
        .Q3(q_o[3]),
        .Q4(q_o[4]),
        .Q5(q_o[5]),
        .Q6(q_o[6]),
        .Q7(q_o[7]),
    );
	defparam ides.GSREN="false";
	defparam ides.LSREN="true";

    reg [1:0]pclk_r;

    always @(posedge fclk_i) begin
		if (!nrst_i) begin
			pclk_r <= 2'b00;
		end else begin
	        pclk_r <= pclk_r + 2'b01;
		end
    end
    assign pclk_o = pclk_r[1];
	
endmodule
