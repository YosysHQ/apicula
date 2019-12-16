module top;

  wire XTAL_IN;
	(* BEL="R5C20_IOBA", keep *)
	GENERIC_IOB #(.INPUT_USED(1), .OUTPUT_USED(0)) clk_ibuf (.O(XTAL_IN));
  wire nRST;
	(* BEL="R11C3_IOBB", keep *)
	GENERIC_IOB #(.INPUT_USED(1), .OUTPUT_USED(0)) rst_ibuf (.O(nRST));


	wire LCD_CLK;
	(* BEL="R7C1_IOBB", keep *)
	GENERIC_IOB #(.INPUT_USED(0), .OUTPUT_USED(1)) lcd_clk_obuf (.I(LCD_CLK));
	wire LCD_HYNC;
	(* BEL="R7C1_IOBA", keep *)
	GENERIC_IOB #(.INPUT_USED(0), .OUTPUT_USED(1)) lcd_hync_obuf (.I(LCD_HYNC));
	wire LCD_SYNC;
	(* BEL="R1C5_IOBB", keep *)
	GENERIC_IOB #(.INPUT_USED(0), .OUTPUT_USED(1)) lcd_sync_obuf (.I(LCD_SYNC));
	wire LCD_DEN;
	(* BEL="R6C1_IOBC", keep *)
	GENERIC_IOB #(.INPUT_USED(0), .OUTPUT_USED(1)) lcd_den_obuf (.I(LCD_DEN));

	wire	[4:0]	LCD_R;
	(* BEL="R7C20_IOBA", keep *)
	GENERIC_IOB #(.INPUT_USED(0), .OUTPUT_USED(1)) lcd_r0_obuf (.I(LCD_R[0]));
	(* BEL="R6C20_IOBH", keep *)
	GENERIC_IOB #(.INPUT_USED(0), .OUTPUT_USED(1)) lcd_r1_obuf (.I(LCD_R[1]));
	(* BEL="R6C20_IOBG", keep *)
	GENERIC_IOB #(.INPUT_USED(0), .OUTPUT_USED(1)) lcd_r2_obuf (.I(LCD_R[2]));
	(* BEL="R6C20_IOBF", keep *)
	GENERIC_IOB #(.INPUT_USED(0), .OUTPUT_USED(1)) lcd_r3_obuf (.I(LCD_R[3]));
	(* BEL="R6C20_IOBD", keep *)
	GENERIC_IOB #(.INPUT_USED(0), .OUTPUT_USED(1)) lcd_r4_obuf (.I(LCD_R[4]));
	wire	[5:0]	LCD_G;
	(* BEL="R6C20_IOBC", keep *)
	GENERIC_IOB #(.INPUT_USED(0), .OUTPUT_USED(1)) lcd_g0_obuf (.I(LCD_G[0]));
	(* BEL="R6C20_IOBB", keep *)
	GENERIC_IOB #(.INPUT_USED(0), .OUTPUT_USED(1)) lcd_g1_obuf (.I(LCD_G[1]));
	(* BEL="R6C20_IOBA", keep *)
	GENERIC_IOB #(.INPUT_USED(0), .OUTPUT_USED(1)) lcd_g2_obuf (.I(LCD_G[2]));
	(* BEL="R1C17_IOBB", keep *)
	GENERIC_IOB #(.INPUT_USED(0), .OUTPUT_USED(1)) lcd_g3_obuf (.I(LCD_G[3]));
	(* BEL="R1C17_IOBA", keep *)
	GENERIC_IOB #(.INPUT_USED(0), .OUTPUT_USED(1)) lcd_g4_obuf (.I(LCD_G[4]));
	(* BEL="R1C14_IOBB", keep *)
	GENERIC_IOB #(.INPUT_USED(0), .OUTPUT_USED(1)) lcd_g5_obuf (.I(LCD_G[5]));
	wire	[4:0]	LCD_B;
	(* BEL="R1C14_IOBA", keep *)
	GENERIC_IOB #(.INPUT_USED(0), .OUTPUT_USED(1)) lcd_b0_obuf (.I(LCD_B[0]));
	(* BEL="R1C10_IOBB", keep *)
	GENERIC_IOB #(.INPUT_USED(0), .OUTPUT_USED(1)) lcd_b1_obuf (.I(LCD_B[1]));
	(* BEL="R1C10_IOBA", keep *)
	GENERIC_IOB #(.INPUT_USED(0), .OUTPUT_USED(1)) lcd_b2_obuf (.I(LCD_B[2]));
	(* BEL="R1C7_IOBB", keep *)
	GENERIC_IOB #(.INPUT_USED(0), .OUTPUT_USED(1)) lcd_b3_obuf (.I(LCD_B[3]));
	(* BEL="R1C7_IOBA", keep *)
	GENERIC_IOB #(.INPUT_USED(0), .OUTPUT_USED(1)) lcd_b4_obuf (.I(LCD_B[4]));

	wire		CLK_SYS;	
	wire		CLK_PIX;

assign CLK_SYS = XTAL_IN;
assign CLK_PIX = XTAL_IN;

	VGAMod	D1
	(
		.CLK		(	CLK_SYS     ),
		.nRST		(	nRST		),

		.PixelClk	(	CLK_PIX		),
		.LCD_DE		(	LCD_DEN	 	),
		.LCD_HSYNC	(	LCD_HYNC 	),
    	.LCD_VSYNC	(	LCD_SYNC 	),

		.LCD_B		(	LCD_B		),
		.LCD_G		(	LCD_G		),
		.LCD_R		(	LCD_R		)
	);

	assign		LCD_CLK		=	CLK_PIX;

endmodule
