 /*
 * Copyright (c) 2020, Bruno Levy
 * All rights reserved.
 * 
 * Redistribution and use in source and binary forms, with or without
 * modification, are permitted provided that the following conditions are met:
 * 
 * 1. Redistributions of source code must retain the above copyright notice, this
 *    list of conditions and the following disclaimer.
 * 
 * 2. Redistributions in binary form must reproduce the above copyright notice,
 *    this list of conditions and the following disclaimer in the documentation
 *    and/or other materials provided with the distribution.
 * 
 * 3. Neither the name of the copyright holder nor the names of its
 *    contributors may be used to endorse or promote products derived from
 *    this software without specific prior written permission.
 * 
 * THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
 * AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
 * IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
 * DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
 * FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
 * DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
 * SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
 * CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
 * OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
 * OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
 */
module corescore_emitter_uart
  #(
    parameter clk_freq_hz = 0,
    parameter baud_rate = 57600)
  (
   input wire 	    i_clk,
   input wire 	    i_rst,
   input wire [7:0] i_data,
   input wire 	    i_valid,
   output reg 	    o_ready,
   output wire 	    o_uart_tx
);

   localparam START_VALUE = clk_freq_hz/baud_rate;
   
   localparam WIDTH = $clog2(START_VALUE);
   
   reg [WIDTH:0]  cnt = 0;
   
   reg [9:0] 	    data;

   assign o_uart_tx = data[0] | !(|data);

   always @(posedge i_clk) begin
      if (cnt[WIDTH] & !(|data)) begin
	 o_ready <= 1'b1;
      end else if (i_valid & o_ready) begin
	 o_ready <= 1'b0;
      end

      if (o_ready | cnt[WIDTH])
	cnt <= {1'b0,START_VALUE[WIDTH-1:0]};
      else
	cnt <= cnt-1;
      
      if (cnt[WIDTH])
	data <= {1'b0, data[9:1]};
      else if (i_valid & o_ready)
	data <= {1'b1, i_data, 1'b0};
   end

endmodule

