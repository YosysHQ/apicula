`default_nettype none

`define START_X 16'd112
`define STOP_X  (`START_X + 16'd256)
`define START_Y 16'd8
`define STOP_Y  (`START_Y + 16'd256)

module display(input wire pixel_clk, input wire rst, output wire [15:0] x, output wire [15:0] y,
    output wire LCD_HYNC, output wire LCD_SYNC, output wire LCD_DEN);

	/* 480x272 4.3" LCD with SC7283 driver, pixel freq = 9MHz */
	localparam      VBackPorch =  16'd12;
	localparam      VPulse 	=     16'd4;
	localparam      HeightPixel = 16'd272;
	localparam      VFrontPorch=  16'd8;

	localparam      HBackPorch =  16'd43;
	localparam      HPulse 	=     16'd4;
	localparam      WidthPixel  = 16'd480;
	localparam      HFrontPorch=  16'd8;

    localparam      PixelForHS  = WidthPixel + HFrontPorch;
    localparam      LineForVS   = HeightPixel + VFrontPorch;
    localparam      TotalWidth  = PixelForHS + HPulse + HBackPorch;
    localparam      TotalHeight = LineForVS + VPulse + VBackPorch;

    reg [15:0] line_count;
    reg [15:0] pixel_count;

    assign x = pixel_count;
    assign y = line_count;

    always @(posedge pixel_clk or negedge rst)begin
        if (!rst) begin
            pixel_count <= 16'b0;
            line_count  <= 16'b0;
        end else begin 
            pixel_count <= pixel_count + 1'b1;
            if (pixel_count ==  TotalWidth - 1) begin
                pixel_count <= 16'b0;
                line_count  <= line_count + 16'b1;
                if (line_count == TotalHeight - 1) begin
                    pixel_count <= 16'b0;
                    line_count  <= 16'b0;
                end
            end
        end
    end

    assign  LCD_HYNC = !(pixel_count >= PixelForHS && pixel_count < PixelForHS + HPulse);
	assign  LCD_SYNC = !(line_count >= LineForVS && line_count < LineForVS + VPulse);

    assign  LCD_DEN = (pixel_count < WidthPixel) && (line_count < HeightPixel);
endmodule
// vim: set et sw=4 ts=4:
