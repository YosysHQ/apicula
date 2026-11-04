/*
Expected Result:
A new colour should wipe across the screen over a couple of seconds. This should happen repeatedly.
*/

`include "dvi.vh"

`default_nettype none

module dvi_pattern (
    input  wire       clk,
    input  wire       rst_i,
    output wire       tmds_clk_n,
    output wire       tmds_clk_p,
    output wire [2:0] tmds_d_n,
    output wire [2:0] tmds_d_p,
    output wire       div_led
);

// ------------------------------------------------------------------------
// Local signals declaration
// ------------------------------------------------------------------------

wire               clk_pixel;
wire               clk_pixel_x5;
wire               pll_lock;
reg [23:0]         counter;           // Debug clk_pixel counter for led output

wire               rst_n;
reg                rst;
reg [3:0]          reset_cnt = 15;    // reset for 15 cycles

wire               red_serial;
wire               green_serial;
wire               blue_serial;

wire [23:0]        rgb;
wire [W_H_RES-1:0] px_x;
wire [W_V_RES-1:0] px_y;

wire               next;              // Generate new color
reg [W_H_RES-1:0]  screen_partition;  // Old/new color divider
reg [23:0]         old_color;
reg [23:0]         new_color;
reg [23:0]         lfsr_out;

// ------------------------------------------------------------------------
// Reset generation
// ------------------------------------------------------------------------

assign rst_n = rst_i ^ `INV_BTN;

always @(posedge clk) begin
    if (reset_cnt > 0) begin
        reset_cnt <= reset_cnt - 1'b1;
        rst       <= 1'b1;
    end else begin
        rst       <= !rst_n;
    end
end

// ------------------------------------------------------------------------
// Pixel/serial clock generation
// ------------------------------------------------------------------------

PLL480 pll_dvi (
    .clkin  (clk         ),
    .clkout (clk_pixel_x5),
    .lock   (pll_lock    )
);

CLKDIV #(
    .DIV_MODE("5")
) clk_div (
    .CLKOUT (clk_pixel   ),
    .HCLKIN (clk_pixel_x5),
    .RESETN (pll_lock    )
);

always @(posedge clk_pixel)
    if (rst)
        counter <= 0;
    else
        counter <= counter + 1'b1;

assign div_led = counter[23];

// ------------------------------------------------------------------------
// Image pattern generation
// ------------------------------------------------------------------------

// 24-bit LFSR
always @(posedge clk_pixel) begin
    if (rst)
        lfsr_out <= 24'hFA311;
    else if (next)
        lfsr_out <= {lfsr_out[22:0], ((lfsr_out[23] ^~ lfsr_out[22]) ^~ lfsr_out[21]) ^~ lfsr_out[16]};
end

always @(posedge clk_pixel) begin
    if (rst) begin
        screen_partition <= 0;
        old_color        <= 0;
        new_color        <= 0;
    end else if (next) begin
        screen_partition <= 0;
        old_color        <= new_color;
        new_color        <= lfsr_out;
    end else if ((px_x == FRAME_WIDTH-1) && (px_y == FRAME_HEIGHT-1)) begin
        screen_partition <= screen_partition + 1'b1;
    end
end

assign next = screen_partition == (FRAME_WIDTH - 1);
assign rgb  = (px_x < screen_partition) ? new_color : old_color;

// ------------------------------------------------------------------------
// DVI driver
// ------------------------------------------------------------------------

dvi_top dvi_top (
    .serial_clk     (clk_pixel_x5),
    .pixel_clk      (clk_pixel   ),
    .rst            (rst         ),
    .red_i          (rgb[23:16]  ),
    .green_i        (rgb[15:8]   ),
    .blue_i         (rgb[7:0]    ),
    .px_x_o         (px_x        ),
    .px_y_o         (px_y        ),
    .red_serial_o   (red_serial  ),
    .green_serial_o (green_serial),
    .blue_serial_o  (blue_serial )
);

// ------------------------------------------------------------------------
// LVDS output
// ------------------------------------------------------------------------

generate if (`IS_ELVDS) begin : gen_elvds_obuf

    ELVDS_OBUF tmds_bufds [3:0] (
        .I  ({clk_pixel, red_serial, green_serial, blue_serial}),
        .O  ({tmds_clk_p, tmds_d_p}                            ),
        .OB ({tmds_clk_n, tmds_d_n}                            )
    );

end else begin : gen_tlvds_obuf

    TLVDS_OBUF tmds_bufds [3:0] (
        .I  ({clk_pixel, red_serial, green_serial, blue_serial}),
        .O  ({tmds_clk_p, tmds_d_p}                            ),
        .OB ({tmds_clk_n, tmds_d_n}                            )
    );

end endgenerate

endmodule

`resetall
