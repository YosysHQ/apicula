`default_nettype none

// Hardware-in-the-loop latch test
//
// Exercises transparent latches with runtime-generated data and verifies
// hold behavior. Each test:
//   1. Loads a counter-derived value with gate open (transparent)
//   2. Closes gate, then changes input to complement
//   3. Compares: held value must equal the transparent value
//
// Output per tick:
//   T0:PASS  (or T0:FAIL)
//   T1:PASS
//   T2:PASS
//   T3:PASS

module top (
	input clk,
	output TXD
);

// Auto-reset on power-up
reg [3:0] por_cnt = 0;
wire por_done = por_cnt[3];
always @(posedge clk)
	if (!por_done) por_cnt <= por_cnt + 1;

wire rst = !por_done;

// ---- UART transmitter ----
wire uart_ready;
reg [7:0] uart_data;
reg uart_valid;

corescore_emitter_uart #(
	.clk_freq_hz(`CPU_FREQ * 1000000),
	.baud_rate(115200)
) uart (
	.i_clk(clk),
	.i_rst(rst),
	.i_data(uart_data),
	.i_valid(uart_valid),
	.o_ready(uart_ready),
	.o_uart_tx(TXD)
);

// ---- Data source (runtime counter, prevents constant folding) ----
reg [7:0] data_cnt;
always @(posedge clk)
	data_cnt <= data_cnt + 8'd1;

// ---- Latch under test ----
reg [7:0] latch_in;
reg gate;
reg [7:0] latch_q;

always @*
	if (gate) latch_q = latch_in;

// ---- Test results ----
reg [3:0] test_pass;  // 1 bit per test
reg [7:0] transparent_val;

// ---- State machine ----
localparam S_LOAD      = 0;  // Load counter value, open gate
localparam S_CAPTURE_T = 1;  // Capture transparent value, close gate
localparam S_HOLD      = 2;  // Change input while gate is closed
localparam S_COMPARE   = 3;  // Compare held value with transparent
localparam S_NEXT      = 4;  // Next test or start sending
localparam S_SEND      = 5;  // Send character
localparam S_SEND_WAIT = 6;  // Wait for UART

reg [2:0] state;
reg [1:0] test_idx;

// ---- Message generation ----
// Per test: "Tn:PASS\n" or "Tn:FAIL\n" = 8 chars
// After tests: "--- tick ---\n" = 13 chars
// Total = 4*8 + 13 = 45 chars
localparam MSG_LEN = 45;

reg [5:0] msg_idx;
reg [7:0] msg_char;

always @* begin
	msg_char = 8'h00;
	if (msg_idx < 32) begin
		case (msg_idx % 8)
			0: msg_char = "T";
			1: msg_char = 8'h30 + {6'd0, msg_idx[4:3]};  // '0'-'3'
			2: msg_char = ":";
			3: msg_char = test_pass[msg_idx[4:3]] ? "P" : "F";
			4: msg_char = test_pass[msg_idx[4:3]] ? "A" : "A";
			5: msg_char = test_pass[msg_idx[4:3]] ? "S" : "I";
			6: msg_char = test_pass[msg_idx[4:3]] ? "S" : "L";
			7: msg_char = 8'h0a;
			default: msg_char = 8'h00;
		endcase
	end else begin
		case (msg_idx - 32)
			0:  msg_char = "-";
			1:  msg_char = "-";
			2:  msg_char = "-";
			3:  msg_char = " ";
			4:  msg_char = "t";
			5:  msg_char = "i";
			6:  msg_char = "c";
			7:  msg_char = "k";
			8:  msg_char = " ";
			9:  msg_char = "-";
			10: msg_char = "-";
			11: msg_char = "-";
			12: msg_char = 8'h0a;
			default: msg_char = 8'h00;
		endcase
	end
end

// ---- Main logic ----
always @(posedge clk) begin
	if (rst) begin
		state <= S_LOAD;
		test_idx <= 0;
		msg_idx <= 0;
		uart_valid <= 1'b0;
		gate <= 1'b0;
	end else case (state)
		S_LOAD: begin
			// Load current counter value with gate open
			latch_in <= data_cnt;
			gate <= 1'b1;
			state <= S_CAPTURE_T;
		end

		S_CAPTURE_T: begin
			// Capture transparent readback, close gate
			transparent_val <= latch_q;
			gate <= 1'b0;
			state <= S_HOLD;
		end

		S_HOLD: begin
			// Now change input — gate is already closed
			latch_in <= ~data_cnt;
			state <= S_COMPARE;
		end

		S_COMPARE: begin
			// Held value should still match transparent value
			test_pass[test_idx] <= (latch_q == transparent_val);
			state <= S_NEXT;
		end

		S_NEXT: begin
			if (test_idx == 2'd3) begin
				test_idx <= 0;
				msg_idx <= 0;
				state <= S_SEND;
			end else begin
				test_idx <= test_idx + 1;
				state <= S_LOAD;
			end
		end

		S_SEND: begin
			if (uart_ready) begin
				uart_data <= msg_char;
				uart_valid <= 1'b1;
				state <= S_SEND_WAIT;
			end
		end

		S_SEND_WAIT: begin
			uart_valid <= 1'b0;
			if (msg_idx == MSG_LEN - 1) begin
				state <= S_LOAD;
			end else begin
				msg_idx <= msg_idx + 1;
				state <= S_SEND;
			end
		end
	endcase
end

endmodule

`include "emitter_uart.v"
