`include "dvi.vh"

`default_nettype none

module dvi_sync (
    input  wire               clk,
    input  wire               rst,
    output reg                hsync_o,
    output reg                vsync_o,
    output reg  [W_H_RES-1:0] pixel_x_o,
    output reg  [W_V_RES-1:0] pixel_y_o,
    output reg                visible_range_o
);

reg                 h_cnt_max;
reg [W_H_TOTAL-1:0] h_cnt_next;
reg [W_H_TOTAL-1:0] h_cnt;
reg [W_V_TOTAL-1:0] v_cnt_next;
reg [W_V_TOTAL-1:0] v_cnt;

always @* begin
    h_cnt_max  = h_cnt == (H_TOTAL - 1);
    h_cnt_next = h_cnt_max ? 0 : h_cnt + 1'b1;
    v_cnt_next = v_cnt;

    if (h_cnt_max) begin
        v_cnt_next = v_cnt + 1'b1;

        if (v_cnt == (V_TOTAL - 1))
            v_cnt_next = 0;
    end
end

always @(posedge clk) begin
    if (rst) begin
        h_cnt <= 0;
        v_cnt <= 0;
    end else begin
        h_cnt <= h_cnt_next;
        v_cnt <= v_cnt_next;
    end
end

// Register outputs
always @(posedge clk)
    if (rst) begin
        hsync_o         <= 0;
        vsync_o         <= 0;
        pixel_x_o       <= 0;
        pixel_y_o       <= 0;
        visible_range_o <= 1'b1;
    end else begin
        hsync_o         <= !(h_cnt_next >= HSYNC_START && h_cnt_next < HSYNC_END);
        vsync_o         <= !(v_cnt_next >= VSYNC_START && v_cnt_next < VSYNC_END);

        pixel_x_o       <=  (h_cnt_next > FRAME_WIDTH  - 1) ? 0 : h_cnt_next[W_H_RES-1:0];
        pixel_y_o       <=  (v_cnt_next > FRAME_HEIGHT - 1) ? 0 : v_cnt_next[W_V_RES-1:0];

        visible_range_o <=  ((h_cnt_next < FRAME_WIDTH) && (v_cnt_next < FRAME_HEIGHT));
    end

endmodule

`resetall
