module top;

	wire clk;
	(* BEL="R5C20_IOBA", keep *)
	GENERIC_IOB #(.INPUT_USED(1), .OUTPUT_USED(0)) clk_ibuf (.O(clk));

	wire [2:0] leds;
	(* BEL="R11C7_IOBA", keep *)
	GENERIC_IOB #(.INPUT_USED(0), .OUTPUT_USED(1)) led2_obuf (.I(leds[2]));
	(* BEL="R11C10_IOBA", keep *)
	GENERIC_IOB #(.INPUT_USED(0), .OUTPUT_USED(1)) led1_obuf (.I(leds[1]));
	(* BEL="R11C10_IOBB", keep *)
	GENERIC_IOB #(.INPUT_USED(0), .OUTPUT_USED(1)) led0_obuf (.I(leds[0]));

reg [25:0] ctr;
always @(posedge clk)
	ctr <= ctr + 1'b1;

assign leds = ctr[25:23];

endmodule
