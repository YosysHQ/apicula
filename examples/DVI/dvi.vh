`ifndef DVI_VH
`define DVI_VH

// Active screen dimensions width
localparam [31:0]          W_H_RES       = 10;
localparam [31:0]          W_V_RES       = 9;

localparam [W_H_RES-1:0]   FRAME_WIDTH   = 640;
localparam [W_V_RES-1:0]   FRAME_HEIGHT  = 480;

// Total screen dimensions width (active + blanking)
localparam [31:0]          W_H_TOTAL     = 10;
localparam [31:0]          W_V_TOTAL     = 10;

// Timings
localparam [W_H_TOTAL-1:0] HSYNC_PULSE   = 96;
localparam [W_H_TOTAL-1:0] H_FRONT_PORCH = 16;
localparam [W_H_TOTAL-1:0] H_BACK_PORCH  = 48;

localparam [W_V_TOTAL-1:0] VSYNC_PULSE   = 2;
localparam [W_V_TOTAL-1:0] V_FRONT_PORCH = 10;
localparam [W_V_TOTAL-1:0] V_BACK_PORCH  = 33;

// HSYNC
localparam [W_H_TOTAL-1:0] HSYNC_START   = FRAME_WIDTH + H_FRONT_PORCH;
localparam [W_H_TOTAL-1:0] HSYNC_END     = HSYNC_START + HSYNC_PULSE;

// VSYNC
localparam [W_V_TOTAL-1:0] VSYNC_START   = FRAME_HEIGHT + V_FRONT_PORCH;
localparam [W_V_TOTAL-1:0] VSYNC_END     = VSYNC_START + VSYNC_PULSE;

localparam [W_H_TOTAL-1:0] H_TOTAL       = HSYNC_END + H_BACK_PORCH;
localparam [W_V_TOTAL-1:0] V_TOTAL       = VSYNC_END + V_BACK_PORCH;

localparam [31:0]          W_COLOR       = 8;
localparam [31:0]          DEL_CYCLES    = 6;

`endif
