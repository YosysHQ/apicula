/* Using an oscilloscope you can see on pins tlvds_p and tlvds_n the signal with changing polarity.
* You can also use a 100 Ohm resistor and two LEDs connected in opposite directions between these pins.
* ODDR needs 4 clock cycles to start working, so be patient:)
*/
module top (
    input clk,
	input rst_i,
    output elvds_p,
    output elvds_n,
	output LED_B
);

	ELVDS_TBUF diff_buf(
			.OEN(w_oen),
			.O(elvds_p),
			.OB(elvds_n),
			.I(oser_out)
		);

	OSER10 os(
		.D0(1'b0),
		.D1(1'b1),
		.D2(1'b0),
		.D3(1'b1),
		.D4(1'b0),
		.D5(1'b1),
		.D6(1'b0),
		.D7(1'b1),
		.D8(1'b0),
		.D9(1'b1),
		.FCLK(fclk_w),
		.PCLK(pclk_w),
		.RESET(1'b0),
		.Q(oser_out)
	);
	defparam os.GSREN = "false";
	defparam os.LSREN = "true";

	wire clk_w;
	wire pclk_w;
	wire fclk_w;

	assign pclk_o = pclk_w;
	assign fclk_o = fclk_w;

	reg [2:0] count;
	wire clkA;
	reg clkB;
	always @(posedge fclk_w) begin
		if (!rst_i) begin
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

	always@(negedge fclk_w) begin
		clkB <= clkA;
	end
	assign pclk_w = clkA | clkB;

	// slow 
	reg [24:0] ctr_q;
	wire [24:0] ctr_d;
	wire tick_w;

	// Sequential code (flip-flop)
	always @(posedge clk)
		ctr_q <= ctr_d;

	// Combinational code (boolean logic)
	assign ctr_d = ctr_q + 1'b1;
	assign tick_w = ctr_q[24];

	assign fclk_w = tick_w;
	assign LED_B = tick_w;
endmodule

