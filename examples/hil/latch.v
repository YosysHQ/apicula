`default_nettype none

// Transparent latches with runtime-generated data. Each of the four tests:
//   1. loads a counter-derived value with the gate open (transparent),
//   2. closes the gate, then drives the complement into the input,
//   3. checks that the held value still equals the transparent value.
// pass has one bit per test and drops for good on the first mismatch.

module latch_test (
	input wire clk,
	input wire rst,
	output wire [3:0] pass
);

// Runtime counter, prevents constant folding
reg [7:0] data_cnt;
always @(posedge clk)
	data_cnt <= data_cnt + 8'd1;

// ---- Latch under test ----
reg [7:0] latch_in;
reg gate;
reg [7:0] latch_q;

always @*
	if (gate) latch_q = latch_in;

reg [3:0] fail;
assign pass = ~fail;
reg [7:0] transparent_val;

localparam S_LOAD      = 0;  // Load counter value, open gate
localparam S_CAPTURE_T = 1;  // Capture transparent value, close gate
localparam S_HOLD      = 2;  // Change input while gate is closed
localparam S_COMPARE   = 3;  // Compare held value with transparent

reg [1:0] state;
reg [1:0] test_idx;

always @(posedge clk) begin
	if (rst) begin
		state <= S_LOAD;
		test_idx <= 0;
		gate <= 1'b0;
		fail <= 0;
	end else case (state)
		S_LOAD: begin
			latch_in <= data_cnt;
			gate <= 1'b1;
			state <= S_CAPTURE_T;
		end

		S_CAPTURE_T: begin
			transparent_val <= latch_q;
			gate <= 1'b0;
			state <= S_HOLD;
		end

		S_HOLD: begin
			// The gate is already closed
			latch_in <= ~data_cnt;
			state <= S_COMPARE;
		end

		S_COMPARE: begin
			if (latch_q != transparent_val)
				fail[test_idx] <= 1'b1;
			test_idx <= test_idx + 1;
			state <= S_LOAD;
		end
	endcase
end

endmodule
