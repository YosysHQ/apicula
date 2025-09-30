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
	wire pixel_clk;
	wire write_clk;
	wire gnd;
	assign gnd = 1'b0;


	clock_pll clok_pll(
		.clk(clk),
		.rst(rst),
		.write_clk(write_clk),
		.pixel_clk(pixel_clk));

	assign		LCD_CLK		=	pixel_clk;

    reg         [15:0]  pixel_count;
    reg         [15:0]  line_count;

	display display(
		.pixel_clk(pixel_clk),
		.rst(rst),
		.x(pixel_count),
		.y(line_count),
		.LCD_HYNC(LCD_HYNC),
		.LCD_SYNC(LCD_SYNC),
		.LCD_DEN(LCD_DEN)
	);

	wire [17:0] rom_data;
	reg  [10:0] read_addr;
	reg [16:0] write_addr;
	reg write_ce;

    image_rom image(
        .clk(pixel_clk),
        .reset(!rst),
        .ad(write_addr[16:6]),
        .data(rom_data)
    );	

	wire [17:0] dout;

	video_ram vmem(
		.clk(pixel_clk),
		.write_clk(write_clk),
		.reset(!rst),
		.write_reset(!rst),
		.write_ce(write_ce),
		.read_wre(!key_i),
		.read_ad(read_addr[10:1]),
		.read_data(dout),
		.write_ad(write_addr[15:6]),
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

	wire [7:0] vmem_start_col;
	wire [7:0] vmem_start_row;
	assign vmem_start_col = pixel_count - `START_X;
	assign vmem_start_row = line_count - `START_Y;
	
	always @(negedge pixel_clk) begin
		if (pixel_count[2]) begin
			read_addr <= {vmem_start_row[6:2], vmem_start_col[7:2]}; 
		end
	end

	wire is_out_x = pixel_count < `START_X || pixel_count >= `STOP_X;
	wire is_out_y = line_count < `START_Y || line_count >= `STOP_Y;

	reg [18:0] color;
	always @(posedge pixel_clk) begin
		if (is_out_x || is_out_y) begin
			color <= line_count + pixel_count;
		end else begin
			color <= dout;
		end
	end

    assign LCD_R = LCD_DEN ? color[17:13] : 0;
    assign LCD_G = LCD_DEN ? color[17:12] : 0;
    assign LCD_B = LCD_DEN ? color[17:13] : 0;
endmodule

