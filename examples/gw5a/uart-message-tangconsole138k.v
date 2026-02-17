module top(input clk, output uart_tx, output [4:0] led);


reg [18:0] ctr = 1'b0;
reg tick = 1'b0;
reg [12:0] message_ctr = 1'b0;

reg [7:0] tx_data;
reg [7:0] message[8191:0];
initial $readmemh("message.hex", message);

always @(posedge clk) begin
	{tick, ctr} <= ctr + 1'b1;
	if (tick) message_ctr <= message_ctr + 1'b1;
	tx_data <= message[message_ctr];
end

uart_tx #(
	.baud(115200),
	.clk_freq(50000000)
) uart_tx_i (
	.clk(clk),
	.tx_start(tick),
	.tx_data(tx_data),
	.tx(uart_tx)
);

assign led = {message_ctr, 1'b0};

endmodule

/*
 *  icebreaker examples - Async uart tx module
 *
 *  Copyright (C) 2018 Piotr Esden-Tempski <piotr@esden.net>
 *
 *  Permission to use, copy, modify, and/or distribute this software for any
 *  purpose with or without fee is hereby granted, provided that the above
 *  copyright notice and this permission notice appear in all copies.
 *
 *  THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES
 *  WITH REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF
 *  MERCHANTABILITY AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR
 *  ANY SPECIAL, DIRECT, INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES
 *  WHATSOEVER RESULTING FROM LOSS OF USE, DATA OR PROFITS, WHETHER IN AN
 *  ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF
 *  OR IN CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.
 */

/***
 * This module generates a bit baud tick multiplied by the oversampling parameter.
 */
module baud_tick_gen(
	input clk, enable,
	output tick);
parameter clk_freq = 12000000;
parameter baud = 115200;
parameter oversampling = 1;

function integer log2(input integer v); begin log2=0; while(v >> log2) log2 = log2 + 1; end endfunction

localparam acc_width = log2(clk_freq / baud) + 8; // +/- 2% max timing error over a byte

reg [acc_width:0] acc = 0;

localparam shiftlimiter = log2((baud * oversampling) >> (31 - acc_width)); // this makes sure inc calculation doesn't overflow (verilog uses 32bit variables internally)
localparam inc = ((baud * oversampling << (acc_width - shiftlimiter)) + (clk_freq >> (shiftlimiter + 1))) / (clk_freq >> shiftlimiter); // Calculate accumulate increment
//initial $display("acc_width %d, shiftlimit %d, inc %d", acc_width, shiftlimiter, inc);

always @(posedge clk) if (enable) acc <= acc[acc_width-1:0] + inc[acc_width:0]; else acc <= inc[acc_width:0];
assign tick = acc[acc_width];

endmodule


module uart_tx(
	input clk,
	input tx_start,
	input [7:0] tx_data,
	output tx,
	output tx_busy);

parameter clk_freq = 12000000;
parameter baud = 115200;

wire bit_tick;
baud_tick_gen #(clk_freq, baud) tickgen(.clk(clk), .enable(tx_busy), .tick(bit_tick));

localparam
	IDLE      = 4'b0000, // tx = high
	BIT_START = 4'b0100, // tx = low
	BIT0      = 4'b1000, // tx = data bit 0
	BIT1      = 4'b1001, // tx = data bit 1
	BIT2      = 4'b1010, // tx = data bit 2
	BIT3      = 4'b1011, // tx = data bit 3
	BIT4      = 4'b1100, // tx = data bit 4
	BIT5      = 4'b1101, // tx = data bit 5
	BIT6      = 4'b1110, // tx = data bit 6
	BIT7      = 4'b1111, // tx = data bit 7
	BIT_STOP1 = 4'b0010, // tx = high
	BIT_STOP2 = 4'b0011; // tx = high

reg [3:0] tx_state = IDLE;
wire tx_ready = (tx_state == 0);
assign tx_busy = ~tx_ready;

reg [7:0] tx_shift = 0;
always @(posedge clk)
begin
	if (tx_ready & tx_start)
		tx_shift <= tx_data;
	else
	if (tx_state[3] & bit_tick)
		tx_shift <= (tx_shift >> 1);

	case (tx_state)
		IDLE:      if(tx_start) tx_state <= BIT_START;
		BIT_START: if(bit_tick) tx_state <= BIT0;
		BIT0:      if(bit_tick) tx_state <= BIT1;
		BIT1:      if(bit_tick) tx_state <= BIT2;
		BIT2:      if(bit_tick) tx_state <= BIT3;
		BIT3:      if(bit_tick) tx_state <= BIT4;
		BIT4:      if(bit_tick) tx_state <= BIT5;
		BIT5:      if(bit_tick) tx_state <= BIT6;
		BIT6:      if(bit_tick) tx_state <= BIT7;
		BIT7:      if(bit_tick) tx_state <= BIT_STOP1;
		BIT_STOP1: if(bit_tick) tx_state <= BIT_STOP2;
		BIT_STOP2: if(bit_tick) tx_state <= IDLE;
		default:   if(bit_tick) tx_state <= IDLE;
	endcase

end

//           high if state START, STOP1, STOP2
//           |                high if transmitting bits and bit is 1
//           |                |
//           V                V
assign tx = (tx_state < 4) | (tx_state[3] & tx_shift[0]);

endmodule
