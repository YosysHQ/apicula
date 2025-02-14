`default_nettype none
(* top *)
module top
(
	input wire rst_i,
	input wire key_i,
	input wire clk,

	output	wire LCD_CLK,
	output	wire LCD_HYNC,
	output	wire LCD_SYNC,
	output	wire LCD_DEN,
	output	wire [4:0]	LCD_R,
	output	wire [5:0]	LCD_G,
	output	wire [4:0]	LCD_B
);

	wire rst = rst_i ^ `INV_BTN;
	wire key = key_i ^ `INV_BTN;
	wire pixel_clk;
	wire write_clk;
	wire gnd;
	assign gnd = 1'b0;

	rPLL pll(
	    .CLKOUT(pixel_clk),  // 9MHz
		.CLKOUTD(write_clk),
		.CLKIN(clk),
		.CLKFB(gnd),
		.RESET(!rst),
		.RESET_P(!rst),
		.FBDSEL({gnd, gnd, gnd, gnd, gnd, gnd}),
		.IDSEL({gnd, gnd, gnd, gnd, gnd, gnd}),
		.ODSEL({gnd, gnd, gnd, gnd, gnd, gnd}),
		.DUTYDA({gnd, gnd, gnd, gnd}),
		.PSDA({gnd, gnd, gnd, gnd}),
		.FDLY({gnd, gnd, gnd, gnd})
	);
	defparam pll.DEVICE = `PLL_DEVICE;
	defparam pll.FCLKIN = `PLL_FCLKIN;
	defparam pll.FBDIV_SEL = `PLL_FBDIV_SEL_LCD;
	defparam pll.IDIV_SEL =  `PLL_IDIV_SEL_LCD;
	defparam pll.ODIV_SEL = `PLL_ODIV_SEL;
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
	defparam pll.DYN_SDIV_SEL=128;
	defparam pll.PSDA_SEL="0000";

	assign		LCD_CLK		=	pixel_clk;

    reg         [15:0]  pixel_count;
    reg         [15:0]  line_count;

	/* 480x272 4.3" LCD with SC7283 driver, pixel freq = 9MHz */
	localparam      VBackPorch = 16'd12;
	localparam      VPulse 	= 16'd4;
	localparam      HightPixel  = 16'd272;
	localparam      VFrontPorch= 16'd8;

	localparam      HBackPorch = 16'd43;
	localparam      HPulse 	= 16'd4;
	localparam      WidthPixel  = 16'd480;
	localparam      HFrontPorch= 16'd8;


    localparam      PixelForHS  =   WidthPixel + HBackPorch + HFrontPorch;  	
    localparam      LineForVS   =   HightPixel + VBackPorch + VFrontPorch;

    always @(posedge pixel_clk or negedge rst)begin
        if (!rst) begin
            line_count       <=  16'b0;    
            pixel_count      <=  16'b0;
            end
        else if (pixel_count == PixelForHS) begin
            pixel_count      <=  16'b0;
            line_count       <=  line_count + 1'b1;
            end
        else if (line_count == LineForVS) begin
            line_count       <=  16'b0;
            pixel_count      <=  16'b0;
            end
        else begin
            pixel_count       <=  pixel_count + 1'b1;
        end
    end


    assign  LCD_HYNC = ((pixel_count >= HPulse) && (pixel_count <= (PixelForHS - HFrontPorch))) ? 1'b0 : 1'b1;
	assign  LCD_SYNC = (((line_count >= VPulse) && (line_count <= (LineForVS - 0)))) ? 1'b0 : 1'b1;

    assign  LCD_DEN = ((pixel_count >= HBackPorch) &&
                        (pixel_count <= PixelForHS - HFrontPorch) &&
                        (line_count >= VBackPorch) &&
                        (line_count <= LineForVS - VFrontPorch - 1)) ? 1'b1 : 1'b0;

	wire [8:0] rom_data;
	reg  [10:0] read_addr;
	reg [16:0] write_addr;
	reg write_ce;

    image_rom image(
        .clk(pixel_clk),
        .reset(!rst),
        .ad(write_addr[16:5]),
        .data(rom_data)
    );	

	wire [8:0] dout;

	video_ram vmem(
		.clk(pixel_clk),
		.write_clk(write_clk),
		.reset(!rst),
		.write_reset(!rst),
		.write_ce(write_ce),
		.read_wre(!key),
		.read_ad(read_addr),
		.read_data(dout),
		.write_ad(write_addr[15:5]),
		.write_data(rom_data)
	);

	always @(posedge write_clk or negedge rst ) begin
		if (!rst) begin
			write_ce <= 1;
			write_addr <= 0;
		end else begin
			write_addr <= write_addr + 1;
		end
	end

`define START_X 16'd160
`define STOP_X  (`START_X + 16'd256)
`define START_Y 16'd18
`define STOP_Y  (`START_Y + 16'd256)
 
	wire [7:0] vmem_start_col;
	wire [7:0] vmem_start_row;
	assign vmem_start_col = pixel_count - `START_X;
	assign vmem_start_row = line_count - `START_Y;
	
	always @(negedge pixel_clk) begin
		read_addr <= {vmem_start_row[7:2], vmem_start_col[7:2]}; 
	end

	wire is_out_x = pixel_count < `START_X || pixel_count >= `STOP_X;
	wire is_out_y = line_count < `START_Y || line_count >= `STOP_Y;

	reg [18:0] color;
	always @(posedge pixel_clk) begin
		if (is_out_x || is_out_y) begin
			color <= {line_count, 3'b000} + {pixel_count, 3'b000};
		end else begin
			color <= dout;
		end
	end

    assign LCD_R = color[8:4];
    assign LCD_G = color[8:3];
    assign LCD_B = color[8:4];
endmodule

