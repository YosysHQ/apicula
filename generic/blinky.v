module top;

	wire clk;
	(* BEL="R29C29_IOB0", keep *)
	GENERIC_IOB #(.INPUT_USED(1), .OUTPUT_USED(0)) clk_ibuf (.O(clk));

	wire [7:0] leds;
	(* BEL="R1C8_IOB0", keep *)
	GENERIC_IOB #(.INPUT_USED(0), .OUTPUT_USED(1)) led7_obuf (.I(leds[7]));
	(* BEL="R1C8_IOB1", keep *)
	GENERIC_IOB #(.INPUT_USED(0), .OUTPUT_USED(1)) led6_obuf (.I(leds[6]));
	(* BEL="R1C10_IOB0", keep *)
	GENERIC_IOB #(.INPUT_USED(0), .OUTPUT_USED(1)) led5_obuf (.I(leds[5]));
	(* BEL="R1C10_IOB1", keep *)
	GENERIC_IOB #(.INPUT_USED(0), .OUTPUT_USED(1)) led4_obuf (.I(leds[4]));
	(* BEL="R1C11_IOB0", keep *)
	GENERIC_IOB #(.INPUT_USED(0), .OUTPUT_USED(1)) led3_obuf (.I(leds[3]));
	(* BEL="R1C11_IOB1", keep *)
	GENERIC_IOB #(.INPUT_USED(0), .OUTPUT_USED(1)) led2_obuf (.I(leds[2]));
	(* BEL="R1C12_IOB0", keep *)
	GENERIC_IOB #(.INPUT_USED(0), .OUTPUT_USED(1)) led1_obuf (.I(leds[1]));
	(* BEL="R1C12_IOB1", keep *)
	GENERIC_IOB #(.INPUT_USED(0), .OUTPUT_USED(1)) led0_obuf (.I(leds[0]));

reg [25:0] ctr;
always @(posedge clk)
	ctr <= ctr + 1'b1;

assign leds = ctr[25:18];

endmodule
