`include "dvi.vh"

`default_nettype none

module dvi_top (
    input  wire               serial_clk,
    input  wire               pixel_clk,
    input  wire               rst,

    input  wire [W_COLOR-1:0] red_i,
    input  wire [W_COLOR-1:0] green_i,
    input  wire [W_COLOR-1:0] blue_i,

    output wire [W_H_RES-1:0] px_x_o,
    output wire [W_V_RES-1:0] px_y_o,

    output wire               red_serial_o,
    output wire               green_serial_o,
    output wire               blue_serial_o
);

wire       hsync;
wire       vsync;
wire       in_range;

wire [9:0] red_tmds;
wire [9:0] green_tmds;
wire [9:0] blue_tmds;

// ------------------------------------------------------------------------
// Sync
// ------------------------------------------------------------------------

dvi_sync dvi_sync (
    .clk             (pixel_clk),
    .rst             (rst      ),
    .hsync_o         (hsync    ),
    .vsync_o         (vsync    ),
    .pixel_x_o       (px_x_o   ),
    .pixel_y_o       (px_y_o   ),
    .visible_range_o (in_range )
);

// ------------------------------------------------------------------------
// Encode
// ------------------------------------------------------------------------

tmds_encoder blue_encoder (
    .clk   (pixel_clk),
    .rst   (rst      ),
    .C0    (hsync    ),
    .C1    (vsync    ),
    .DE    (in_range ),
    .D     (blue_i   ),
    .q_out (blue_tmds)
);

tmds_encoder green_encoder (
    .clk   (pixel_clk ),
    .rst   (rst       ),
    .C0    (1'b0      ),
    .C1    (1'b0      ),
    .DE    (in_range  ),
    .D     (green_i   ),
    .q_out (green_tmds)
);

tmds_encoder red_encoder (
    .clk   (pixel_clk ),
    .rst   (rst       ),
    .C0    (1'b0      ),
    .C1    (1'b0      ),
    .DE    (in_range  ),
    .D     (red_i     ),
    .q_out (red_tmds  )
);

// ------------------------------------------------------------------------
// Serialize
// ------------------------------------------------------------------------

OSER10 red_serializer (
    .PCLK  (pixel_clk   ),
    .FCLK  (serial_clk  ),
    .RESET (rst         ),
    .D0    (red_tmds[0] ),
    .D1    (red_tmds[1] ),
    .D2    (red_tmds[2] ),
    .D3    (red_tmds[3] ),
    .D4    (red_tmds[4] ),
    .D5    (red_tmds[5] ),
    .D6    (red_tmds[6] ),
    .D7    (red_tmds[7] ),
    .D8    (red_tmds[8] ),
    .D9    (red_tmds[9] ),
    .Q     (red_serial_o)
);

OSER10 green_serializer (
    .PCLK  (pixel_clk     ),
    .FCLK  (serial_clk    ),
    .RESET (rst           ),
    .D0    (green_tmds[0] ),
    .D1    (green_tmds[1] ),
    .D2    (green_tmds[2] ),
    .D3    (green_tmds[3] ),
    .D4    (green_tmds[4] ),
    .D5    (green_tmds[5] ),
    .D6    (green_tmds[6] ),
    .D7    (green_tmds[7] ),
    .D8    (green_tmds[8] ),
    .D9    (green_tmds[9] ),
    .Q     (green_serial_o)
);

OSER10 blue_serializer (
    .PCLK  (pixel_clk    ),
    .FCLK  (serial_clk   ),
    .RESET (rst          ),
    .D0    (blue_tmds[0] ),
    .D1    (blue_tmds[1] ),
    .D2    (blue_tmds[2] ),
    .D3    (blue_tmds[3] ),
    .D4    (blue_tmds[4] ),
    .D5    (blue_tmds[5] ),
    .D6    (blue_tmds[6] ),
    .D7    (blue_tmds[7] ),
    .D8    (blue_tmds[8] ),
    .D9    (blue_tmds[9] ),
    .Q     (blue_serial_o)
);

endmodule

`resetall
