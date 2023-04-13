`default_nettype none
module top(input wire clk_i,
	input wire nrst_i,
	input wire fclk_i,
	input wire data_i,
	output wire pclk_o,
	output wire [9:0]q_o);

	wire [5:0]dummy_w;

    IDES16 ides(
        .D(data_i),
		.FCLK(fclk_i),
		.PCLK(pclk_o),
		.CALIB(1'b0),
		.RESET(!nrst_i),
//`define SECOND_HALF
`ifndef SECOND_HALF
        .Q0(q_o[0]),
        .Q1(q_o[1]),
        .Q2(q_o[2]),
        .Q3(q_o[3]),
        .Q4(q_o[4]),
        .Q5(q_o[5]),
        .Q6(q_o[6]),
        .Q7(q_o[7]),
        .Q8(q_o[8]),
        .Q9(q_o[9]),
        .Q10(dummy_w[0]),
        .Q11(dummy_w[1]),
        .Q12(dummy_w[2]),
        .Q13(dummy_w[3]),
        .Q14(dummy_w[4]),
        .Q15(dummy_w[5])
`else
        .Q0(dummy_w[0]),
        .Q1(dummy_w[1]),
        .Q2(dummy_w[2]),
        .Q3(dummy_w[3]),
        .Q4(dummy_w[4]),
        .Q5(dummy_w[5]),
        .Q6(q_o[6]),
        .Q7(q_o[7]),
        .Q8(q_o[8]),
        .Q9(q_o[9]),
        .Q10(q_o[0]),
        .Q11(q_o[1]),
        .Q12(q_o[2]),
        .Q13(q_o[3]),
        .Q14(q_o[4]),
        .Q15(q_o[5])
`endif
    );
	defparam ides.GSREN="false";
	defparam ides.LSREN="true";

    reg [2:0]pclk_r;
    wire fclk_w;

    always @(posedge fclk_w) begin
		if (!nrst_i) begin
			pclk_r <= 3'b00;
		end else begin
	        pclk_r <= pclk_r + 3'b01;
		end
    end
    assign pclk_o = pclk_r[2];
	assign fclk_w = fclk_i;
endmodule
