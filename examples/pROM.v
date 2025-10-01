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
	wire gnd;
	assign gnd = 1'b0;

	clock_pll clok_pll(
		.clk(clk),
		.rst(rst),
		.write_clk(),
		.pixel_clk(pixel_clk));

	assign		LCD_CLK		=	pixel_clk;

    reg         [15:0]  pixel_count;
    reg         [15:0]  line_count;


	wire [7:0] dout;
	reg [11:0] addr;

    image_rom image(
        .clk(pixel_clk),
        .reset(!rst),
        .ad(addr),
        .data(dout)
    );	

	display display(
		.pixel_clk(pixel_clk),
		.rst(rst),
		.x(pixel_count),
		.y(line_count),
		.LCD_HYNC(LCD_HYNC),
		.LCD_SYNC(LCD_SYNC),
		.LCD_DEN(LCD_DEN)
	);

	wire [7:0] vmem_start_col;
	wire [7:0] vmem_start_row;
	assign vmem_start_col = pixel_count - `START_X;
	assign vmem_start_row = line_count - `START_Y;
	
	always @(negedge pixel_clk) begin
		addr = {vmem_start_row[7:2], vmem_start_col[7:2]}; 
	end

	wire is_out_x = pixel_count < `START_X || pixel_count >= `STOP_X;
	wire is_out_y = line_count < `START_Y || line_count >= `STOP_Y;

	reg [15:0] color;
	always @(negedge pixel_clk) begin
		if (is_out_x || is_out_y) begin
			color = line_count + pixel_count;
		end else begin
			color = {dout[4:0], dout[5:0], dout[4:0]};
		end
	end

    assign LCD_R = LCD_DEN ? color[4:0]   >> (4 - `R_MSB) : 0;
    assign LCD_G = LCD_DEN ? color[10:5]  >> (5 - `G_MSB) : 0;
    assign LCD_B = LCD_DEN ? color[15:11] >> (4 - `B_MSB) : 0;

endmodule

