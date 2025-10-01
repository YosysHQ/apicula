`default_nettype none

`define START_X 16'd192
`define STOP_X  (`START_X + 16'd256)
`define START_Y 16'd112
`define STOP_Y  (`START_Y + 16'd256)

module display(input wire pixel_clk, input wire rst, output wire [15:0] x, output wire [15:0] y,
    output wire LCD_HYNC, output wire LCD_SYNC, output wire LCD_DEN);

	/* 640x48072 pixel freq = 25MHz */
	localparam      VBackPorch =  16'd33;
	localparam      VPulse 	=     16'd2;
	localparam      HeightPixel = 16'd480;
	localparam      VFrontPorch=  16'd10;

	localparam      HBackPorch =  16'd48;
	localparam      HPulse 	=     16'd96;
	localparam      WidthPixel  = 16'd640;
	localparam      HFrontPorch=  16'd16;

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
