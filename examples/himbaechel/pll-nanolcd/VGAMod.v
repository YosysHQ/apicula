module VGAMod
(
    input                   CLK,
    input                   nRST,

    input                   PixelClk,

    output                  LCD_DE,
    output                  LCD_HSYNC,
    output                  LCD_VSYNC,

	output          [4:0]   LCD_B,
	output          [5:0]   LCD_G,
	output          [4:0]   LCD_R
);

    reg         [15:0]  PixelCount;
    reg         [15:0]  LineCount;

	//pulse include in back pulse; t=pulse, sync act; t=bp, data act; t=bp+height, data end
	
	/* 480x272 4.3" LCD with SC7283 driver, pixel freq = 9MHz */
	localparam      V_BackPorch = 16'd12;
	localparam      V_Pulse 	= 16'd4;
	localparam      HightPixel  = 16'd272;
	localparam      V_FrontPorch= 16'd8;

	localparam      H_BackPorch = 16'd43;
	localparam      H_Pulse 	= 16'd4;
	localparam      WidthPixel  = 16'd480;
	localparam      H_FrontPorch= 16'd8;

	/*localparam      V_BackPorch = 16'd12; 
	localparam      V_Pulse 	= 16'd11; 
	localparam      HightPixel  = 16'd272;
	localparam      V_FrontPorch= 16'd8; 
	
	localparam      H_BackPorch = 16'd50; 
	localparam      H_Pulse 	= 16'd10; 
	localparam      WidthPixel  = 16'd480;
	localparam      H_FrontPorch= 16'd8;    */
/*
	localparam      V_BackPorch = 16'd0; //6
	localparam      V_Pulse 	= 16'd5; 
	localparam      HightPixel  = 16'd480;
	localparam      V_FrontPorch= 16'd45; //62

	localparam      H_BackPorch = 16'd182; 	//NOTE: 高像素时钟时，增加这里的延迟，方便K210加入中断
	localparam      H_Pulse 	= 16'd1; 
	localparam      WidthPixel  = 16'd800;
	localparam      H_FrontPorch= 16'd210;
*/	

    localparam      PixelForHS  =   WidthPixel + H_BackPorch + H_FrontPorch;  	
    localparam      LineForVS   =   HightPixel + V_BackPorch + V_FrontPorch;

    always @(  posedge PixelClk or negedge nRST  )begin
        if( !nRST ) begin
            LineCount       <=  16'b0;    
            PixelCount      <=  16'b0;
            end
        else if(  PixelCount  ==  PixelForHS ) begin
            PixelCount      <=  16'b0;
            LineCount       <=  LineCount + 1'b1;
            end
        else if(  LineCount  == LineForVS  ) begin
            LineCount       <=  16'b0;
            PixelCount      <=  16'b0;
            end
        else begin
            PixelCount       <=  PixelCount + 1'b1;
        end
    end

	reg			[9:0]  Data_R;
	reg			[9:0]  Data_G;
	reg			[9:0]  Data_B;

    always @(  posedge PixelClk or negedge nRST  )begin
        if( !nRST ) begin
			Data_R <= 9'b0;
			Data_G <= 9'b0;
			Data_B <= 9'b0;
            end
        else begin
			end
	end

	//注意这里HSYNC和VSYNC负极性
    assign  LCD_HSYNC = (( PixelCount >= H_Pulse)&&( PixelCount <= (PixelForHS-H_FrontPorch))) ? 1'b0 : 1'b1;
    //assign  LCD_VSYNC = ((( LineCount  >= 0 )&&( LineCount  <= (V_Pulse-1) )) ) ? 1'b1 : 1'b0;		//这里不减一的话，图片底部会往下拖尾？
	assign  LCD_VSYNC = ((( LineCount  >= V_Pulse )&&( LineCount  <= (LineForVS-0) )) ) ? 1'b0 : 1'b1;
    //assign  FIFO_RST  = (( PixelCount ==0)) ? 1'b1 : 1'b0;  //留给主机H_BackPorch的时间进入中断，发送数据

    assign  LCD_DE = (  ( PixelCount >= H_BackPorch )&&
                        ( PixelCount <= PixelForHS-H_FrontPorch ) &&
                        ( LineCount >= V_BackPorch ) &&
                        ( LineCount <= LineForVS-V_FrontPorch-1 ))  ? 1'b1 : 1'b0;
						//这里不减一，会抖动

    assign  LCD_R   =   (PixelCount<110)? 5'b00000 : 
                        (PixelCount<132 ? 5'b00001 :    
                        (PixelCount<154 ? 5'b00010 :    
                        (PixelCount<176 ? 5'b00100 :    
                        (PixelCount<198 ? 5'b01000 :    
                        (PixelCount<220 ? 5'b10000 :  5'b00000 )))));

    assign  LCD_G   =   (PixelCount<220)? 6'b000000 : 
                        (PixelCount<242 ? 6'b000001 :    
                        (PixelCount<264 ? 6'b000010 :    
                        (PixelCount<286 ? 6'b000100 :    
                        (PixelCount<308 ? 6'b001000 :    
                        (PixelCount<330 ? 6'b010000 :  
                        (PixelCount<352 ? 6'b100000 : 6'b000000 ))))));

    assign  LCD_B   =   (PixelCount<352)? 5'b00000 : 
                        (PixelCount<374 ? 5'b00001 :    
                        (PixelCount<396 ? 5'b00010 :    
                        (PixelCount<418 ? 5'b00100 :    
                        (PixelCount<440 ? 5'b01000 :    
                        (PixelCount<462 ? 5'b10000 :  5'b00000 )))));

endmodule
