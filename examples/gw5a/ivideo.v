`default_nettype none
module top(input wire clk, 
	input wire rst_i, 
	input wire fclk_i,
	input wire tlvds_p,
    input wire tlvds_n,
	output wire pclk_o,
	output wire [7:0]mled);

	wire rst = rst_i ^ `INV_BTN;
	wire data_i;
    IVIDEO ides(
        .D(data_i),
		.FCLK(fclk_i),
		.PCLK(pclk_o),
		.CALIB(1'b0),
		.RESET(!rst),
        .Q0(mled[0]),
        .Q1(mled[1]),
        .Q2(mled[2]),
        .Q3(mled[3]),
        .Q4(mled[4]),
        .Q5(mled[5]),
        .Q6(mled[6])
    );

    TLVDS_IBUF in(
       .I(tlvds_p),
       .IB(tlvds_n),
       .O(data_i)
	);

	// div by 3.5
	reg [6:0]cnt_r;
	reg ps0_r;
	reg ps3_r;
	reg ps4_r;
	always @(posedge fclk_i) begin
		if (!rst) begin
			cnt_r[6:0] <= 7'b000_0001;
		end else begin
			cnt_r[6:0] <= {cnt_r[5:0], cnt_r[6]};
		end
	end

	always @(negedge fclk_i) begin
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
    assign pclk_o = (ps0_r | cnt_r[0] | cnt_r[1]) | (ps3_r | ps4_r | cnt_r[4]);
endmodule
