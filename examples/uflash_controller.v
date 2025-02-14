/* Copyright 2024 Grug Huhler.  License SPDX BSD-2-Clause.
 
   This module implements a controller for the user flash on the Tang
   Nano 9K FPGA development board.  The controller integrates with
   the PicoRV32 mini-SoC bus scheme.  It also instantiates the
   actual flash.  Note: the Tang Nano 20K does not contain user
   flash.

   See document UG295 "Gowin User Flash".

   The Flash is 608 Kbits, 32-bits wide, organized into 304 rows of 64
   columns each.  The erase page size is 2048 bytes, so there are
   38 pages that may be separately erased.

   This controller expects a system clock no more than 40 Mhz.  The
   actual clock frequency must be passed to the module via the
   CLK_FREQ parameter.

   Leave at least 10 millisconds between a write and an erase and do
   not write the same address twice without an erase between the writes.
   The controller does not enforce these rules.

   Reads can be 8, 16, or 32 bits wide.  Erasing is done on a page basis.
   To erase a page, do an 8 bit write to a 32-bit aligned address in the
   page. To program (write), do a 32-bit write to the address to be
   programmed.
*/

module uflash #(parameter CLK_FREQ=5400000)
(
 input wire         reset_n,
 input wire         clk,
 input wire         sel,
 input wire [3:0]   wstrb,
 input wire [14:0]  addr, // word address, 9-bits row, 6 bits col
 input wire [31:0]  data_i,
 output wire        ready,
 output wire [31:0] data_o
);

   // state machine states
   localparam IDLE = 'd0;
   localparam READ1 = 'd1;
   localparam READ2 = 'd2;
   localparam ERASE1 = 'd3;
   localparam ERASE2 = 'd4; 
   localparam ERASE3 = 'd5; 
   localparam ERASE4 = 'd6; 
   localparam ERASE5 = 'd7;
   localparam WRITE1 = 'd8;
   localparam WRITE2 = 'd9;
   localparam WRITE3 = 'd10;
   localparam WRITE4 = 'd11;
   localparam WRITE5 = 'd12;
   localparam WRITE6 = 'd13;
   localparam WRITE7 = 'd14;
   localparam DONE = 'd15;

   // clocks required in state when > 1
   localparam E2_CLKS = $rtoi(CLK_FREQ * 6.0e-6) + 1;
   localparam E3_CLKS = $rtoi(CLK_FREQ * 120.0e-3) + 1;
   localparam E4_CLKS = $rtoi(CLK_FREQ * 6.0e-6) + 1;
   localparam E5_CLKS = $rtoi(CLK_FREQ * 11.0e-6) + 1;
   localparam W2_CLKS = $rtoi(CLK_FREQ * 6.0e-6) + 1;
   localparam W3_CLKS = $rtoi(CLK_FREQ * 11.0e-6) + 1;
   localparam W4_CLKS = $rtoi(CLK_FREQ * 16.0e-6) + 1;
   localparam W6_CLKS = $rtoi(CLK_FREQ * 6.0e-6) + 1;
   localparam W7_CLKS = $rtoi(CLK_FREQ * 11.0e-6) + 1;

   reg xe = 1'b0;
   reg ye = 1'b0;
   reg se = 1'b0;
   reg erase = 1'b0;
   reg nvstr = 1'b0;
   reg prog = 1'b0;
   reg [3:0] state = IDLE;
   reg [23:0] cycle_count;

   assign ready = state == DONE;

   always @(posedge clk or negedge reset_n)
     if (!reset_n) begin
        state <= IDLE;
        se <= 1'b0;
        xe <= 1'b0;
        ye <= 1'b0;
        erase <= 1'b0;
        nvstr <= 1'b0;
        prog <= 1'b0;
        cycle_count <= 'd0;
     end
     else
       case (state)
         IDLE: begin
            if (sel) begin
               if (wstrb == 'b0) begin
                  // Read
                  state <= READ1;
                  xe <= 1'b1;
                  ye <= 1'b1;
               end
               else if (&wstrb) begin
                  // Write
                  state <= WRITE1;
                  xe <= 1'b1;
               end else if (wstrb == 'b1) begin
                  // Erase
                  ye <= 1'b0;
                  se <= 1'b0;
                  xe <= 1'b1;
                  erase <= 1'b0;
                  nvstr <= 1'b0;
                  state <= ERASE1;
               end else begin
                  // Unsupported
                  state <= DONE;
               end
            end
            else
              state <= IDLE;
         end
         READ1: begin
            se <= 1'b1;
            state <= READ2;
         end
         READ2: begin
            se <= 1'b0;
            state <= DONE;
         end
         ERASE1: begin
            state <= ERASE2;
            cycle_count <= 'd0;
            erase <= 1'b1;
         end
         ERASE2: begin
            if (cycle_count < E2_CLKS) begin
               state <= ERASE2;
               cycle_count <= cycle_count + 1;
            end
            else begin
               state <= ERASE3;
               cycle_count <= 'd0;
               nvstr <= 1'b1;
            end
         end
         ERASE3: begin
            if (cycle_count < E3_CLKS) begin
               state <= ERASE3;
               cycle_count <= cycle_count + 1;
            end
            else begin
               state <= ERASE4;
               cycle_count <= 'd0;
               erase <= 1'b0;
            end
         end
         ERASE4: begin
            if (cycle_count < E4_CLKS) begin
               state <= ERASE4;
               cycle_count <= cycle_count + 1;
            end
            else begin
               state <= ERASE5;
               cycle_count <= 'd0;
               nvstr <= 1'b0;
            end
         end
         ERASE5: begin
            if (cycle_count < E5_CLKS) begin
               state <= ERASE5;
               cycle_count <= cycle_count + 1;
            end
            else begin
               state <= DONE;
               cycle_count <= 'd0;
               xe <= 1'b0;
            end
         end
         WRITE1: begin
            state <= WRITE2;
            prog <= 1'b1;
         end
         WRITE2: begin
            if (cycle_count < W2_CLKS) begin
               state <= WRITE2;
               cycle_count <= cycle_count + 1;
            end
            else begin
               state <= WRITE3;
               cycle_count <= 'd0;
               nvstr <= 1'b1;
            end
         end
         WRITE3: begin
            if (cycle_count < W3_CLKS) begin
               state <= WRITE3;
               cycle_count <= cycle_count + 1;
            end
            else begin
               state <= WRITE4;
               cycle_count <= 'd0;
               ye <= 1'b1;
            end
         end
         WRITE4: begin
            if (cycle_count < W4_CLKS) begin
               state <= WRITE4;
               cycle_count <= cycle_count + 1;
            end
            else begin
               state <= WRITE5;
               cycle_count <= 'd0;
               ye <= 1'b0;
            end
         end
         WRITE5: begin
            state <= WRITE6;
            prog <= 1'b0;
         end
         WRITE6: begin
            if (cycle_count < W6_CLKS) begin
               state <= WRITE6;
               cycle_count <= cycle_count + 1;
            end
            else begin
               state <= WRITE7;
               cycle_count <= 'd0;
               nvstr <= 1'b0;
            end
         end
         WRITE7: begin
            if (cycle_count < W7_CLKS) begin
               state <= WRITE7;
               cycle_count <= cycle_count + 1;
            end
            else begin
               state <= DONE;
               cycle_count <= 'd0;
               xe <= 1'b0;
            end
         end
         DONE: begin
            state <= IDLE;
            xe <= 1'b0;
            ye <= 1'b0;
            se <= 1'b0;
            erase <= 1'b0;
            nvstr <= 1'b0;
            prog <= 1'b0;
         end
       endcase

`ifdef HAS_FLASH608K	   
   (* keep *)
   FLASH608K uflash_hw0 (
     .DOUT(data_o), //output [31:0] dout
     .XE(xe), //input xe
     .YE(ye), //input ye
     .SE(se), //input se
     .PROG(prog), //input prog
     .ERASE(erase), //input erase
     .NVSTR(nvstr), //input nvstr
     .XADR(addr[14:6]), //input [8:0] xadr
     .YADR(addr[5:0]), //input [5:0] yadr
     .DIN(data_i) //input [31:0] din
    );
`else
   (* keep *)
   FLASH64KZ uflash_hw0 (
     .DOUT(data_o), //output [31:0] dout
     .XE(xe), //input xe
     .YE(ye), //input ye
     .SE(se), //input se
     .PROG(prog), //input prog
     .ERASE(erase), //input erase
     .NVSTR(nvstr), //input nvstr
     .XADR(addr[10:6]), //input [4:0] xadr
     .YADR(addr[5:0]), //input [5:0] yadr
     .DIN(data_i) //input [31:0] din
    );
`endif

endmodule
