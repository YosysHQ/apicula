(* top *)
module TOP
(
	input			rst,
    input           clk,

	output			LCD_CLK,
	output			LCD_HYNC,
	output			LCD_SYNC,
	output			LCD_DEN,
	output	[4:0]	LCD_R,
	output	[5:0]	LCD_G,
	output	[4:0]	LCD_B,

	output [2:0] led

);

	wire CLK_SYS;	
	wire CLK_PIX;
	wire LED_R;
	wire LED_G;
	wire LED_B;

/* //使用内部时钟
    Gowin_OSC chip_osc(
        .oscout(oscout_o) //output oscout
    );
*/
rPLL pll(
	    .CLKOUT(CLK_SYS),  // 90MHz
		.CLKIN(clk),
		.CLKOUTD(CLK_PIX), // 9MHz
		.CLKFB(GND),
		.FBDSEL({GND,GND,GND,GND,GND,GND}),
		.IDSEL({GND,GND,GND,GND,GND,GND}),
		.ODSEL({GND,GND,GND,GND,GND,GND}),
		.DUTYDA({GND,GND,GND,GND}),
		.PSDA({GND,GND,GND,GND}),
		.FDLY({GND,GND,GND,GND})
	);
	defparam pll.DEVICE = `PLL_DEVICE;
	defparam pll.FCLKIN = `PLL_FCLKIN;
	defparam pll.FBDIV_SEL = `PLL_FBDIV_SEL_LCD;
	defparam pll.IDIV_SEL =  `PLL_IDIV_SEL_LCD;
	defparam pll.ODIV_SEL =  8;           // 90MHz sys clock
	defparam pll.CLKFB_SEL="internal";
	defparam pll.CLKOUTD3_SRC="CLKOUT";
	defparam pll.CLKOUTD_BYPASS="false";
	defparam pll.CLKOUTD_SRC="CLKOUT";
	defparam pll.CLKOUTP_BYPASS="false";
	defparam pll.CLKOUTP_DLY_STEP=0;
	defparam pll.CLKOUTP_FT_DIR=1'b1;
	defparam pll.CLKOUT_BYPASS="false";
	defparam pll.CLKOUT_DLY_STEP=0;
	defparam pll.CLKOUT_FT_DIR=1'b1;
	defparam pll.DUTYDA_SEL="1000";
	defparam pll.DYN_DA_EN="false";
	defparam pll.DYN_FBDIV_SEL="false";
	defparam pll.DYN_IDIV_SEL="false";
	defparam pll.DYN_ODIV_SEL="false";
	defparam pll.DYN_SDIV_SEL=10;      // 90MHz / 10 = 9MHz --- pixel clock
	defparam pll.PSDA_SEL="0000";

assign led[0] = LED_R;
assign led[1] = LED_G;
assign led[2] = LED_B;

	VGAMod	D1
	(
		.CLK		(	CLK_SYS     ),
		.nRST		(	rst		),

		.PixelClk	(	CLK_PIX		),
		.LCD_DE		(	LCD_DEN	 	),
		.LCD_HSYNC	(	LCD_HYNC 	),
    	.LCD_VSYNC	(	LCD_SYNC 	),

		.LCD_B		(	LCD_B		),
		.LCD_G		(	LCD_G		),
		.LCD_R		(	LCD_R		)
	);

	assign		LCD_CLK		=	CLK_PIX;

    //RGB LED TEST
    reg 	[31:0] Count;
    reg     [1:0] rgb_data;
	always @(  posedge CLK_SYS or negedge rst  )
	begin
		if(  !rst  )
		begin
		Count		<= 32'd0;
        rgb_data    <= 2'b00;
		end
		else if ( Count == 12000000 )
		begin
			Count <= 4'b0;
            rgb_data <= rgb_data + 1'b1;
		end
		else
		Count <= Count + 1'b1;
	end
    assign  LED_R = ~(rgb_data == 2'b01);
    assign  LED_G = ~(rgb_data == 2'b10);
    assign  LED_B = ~(rgb_data == 2'b11);

endmodule
