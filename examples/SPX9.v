`default_nettype none
(* top *)
module top
(
	input wire rst_i,
	input wire clk,

	output	wire LCD_CLK,
	output	wire LCD_HYNC,
	output	wire LCD_SYNC,
	output	wire LCD_DEN,
	output	wire [`R_MSB:0]	LCD_R,
	output	wire [`G_MSB:0]	LCD_G,
	output	wire [`B_MSB:0]	LCD_B
);

	wire rst = rst_i ^ `INV_BTN;
	wire pixel_clk;
	wire write_clk;

	wire gnd;
	assign gnd = 1'b0;

	clock_pll clock_pll(
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

	wire [8:0] rom_data;
	wire [10:0] read_addr;
	reg [16:0] write_addr;

    image_rom image(
        .clk(pixel_clk),
        .reset(!rst),
        .ad(write_addr[16:5]),
        .data(rom_data)
    );	

	wire [8:0] dout;
	reg [10:0] rw_addr;

	video_ram vmem(
		.clk(pixel_clk),
		.reset(!rst),
		.wre(!LCD_DEN),
		.ad(rw_addr),
		.read_data(dout),
		.write_data(rom_data)
	);


	wire [7:0] vmem_start_col;
	wire [7:0] vmem_start_row;
	assign vmem_start_col = pixel_count - `START_X;
	assign vmem_start_row = line_count - `START_Y;
	
	assign read_addr = {vmem_start_row[7:2], vmem_start_col[7:2]}; 

	wire is_out_x = pixel_count < `START_X || pixel_count >= `STOP_X;
	wire is_out_y = line_count < `START_Y || line_count >= `STOP_Y;

	always @(negedge pixel_clk) begin
		if (is_out_x) begin
			rw_addr <= write_addr[15:5];
		end else begin
			rw_addr <= read_addr;
		end
	end

	reg [15:0] color;
	always @(posedge pixel_clk) begin
		if (is_out_x || is_out_y) begin
			color = line_count + pixel_count;
		end else begin
			color = {dout[8:4], dout[8:3], dout[8:4]};
		end
	end

	always @(posedge write_clk or negedge rst) begin
        if (!rst) begin
            write_addr <= 0;
        end else begin
            write_addr <= write_addr + 1;
        end
    end

    assign LCD_R = LCD_DEN ? color[4:0]   >> (4 - `R_MSB) : 0;
    assign LCD_G = LCD_DEN ? color[10:5]  >> (5 - `G_MSB) : 0;
    assign LCD_B = LCD_DEN ? color[15:11] >> (4 - `B_MSB) : 0;

endmodule

