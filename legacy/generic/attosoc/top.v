module top;

	wire clk;
	(* BEL="R29C29_IOBA", keep *)
	GENERIC_IOB #(.INPUT_USED(1), .OUTPUT_USED(0)) clk_ibuf (.O(clk));

	wire [7:0] leds;
	(* BEL="R1C8_IOBA", keep *)
	GENERIC_IOB #(.INPUT_USED(0), .OUTPUT_USED(1)) led7_obuf (.I(leds[7]));
	(* BEL="R1C8_IOBB", keep *)
	GENERIC_IOB #(.INPUT_USED(0), .OUTPUT_USED(1)) led6_obuf (.I(leds[6]));
	(* BEL="R1C10_IOBA", keep *)
	GENERIC_IOB #(.INPUT_USED(0), .OUTPUT_USED(1)) led5_obuf (.I(leds[5]));
	(* BEL="R1C10_IOBB", keep *)
	GENERIC_IOB #(.INPUT_USED(0), .OUTPUT_USED(1)) led4_obuf (.I(leds[4]));
	(* BEL="R1C11_IOBA", keep *)
	GENERIC_IOB #(.INPUT_USED(0), .OUTPUT_USED(1)) led3_obuf (.I(leds[3]));
	(* BEL="R1C11_IOBB", keep *)
	GENERIC_IOB #(.INPUT_USED(0), .OUTPUT_USED(1)) led2_obuf (.I(leds[2]));
	(* BEL="R1C12_IOBA", keep *)
	GENERIC_IOB #(.INPUT_USED(0), .OUTPUT_USED(1)) led1_obuf (.I(leds[1]));
	(* BEL="R1C12_IOBB", keep *)
	GENERIC_IOB #(.INPUT_USED(0), .OUTPUT_USED(1)) led0_obuf (.I(leds[0]));

attosoc soc(
	.clk(clk),
	.led(leds)
);

endmodule
