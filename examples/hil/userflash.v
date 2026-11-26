`default_nettype none

// User flash (FLASH608K on GW1N-9/9C, FLASH64KZ on GW1NZ-1) through the uflash
// controller in uflash_controller.v, which follows the timing of UG295: page
// erase 120 ms, program 16 us, and the setup and recovery times around them.
// Once after power-up, with no CPU:
//   1. read word 0 (raw only: what the previous run left there),
//   2. erase page 1 (rows 8-15, the same rows on both flash sizes),
//   3. read six words of the page and check they are erased,
//   4. program four of them with a pattern that holds the address,
//   5. read the six words again: the four hold the pattern, the two others
//      (the neighbours of word 0 in its row and its column) are still erased.
// Every load erases the page once, so the test is in no batch (flash wear).
//
// Erased words read as zeros and programming sets ones: UG295 says so for
// FLASH96K, and the tangnano9k (GW1N-9C) reads FLASH608K the same way.
//
// pass[5:0]: word i erased; pass[9:6]: words 0-3 read back the pattern;
// pass[11:10]: words 4 and 5 still erased after programming; pass[12]: done.
// raw: word 0 before the erase, word 0 at the end.

module userflash_test (
	input wire clk,
	input wire rst,
	output reg [12:0] pass,
	output reg [63:0] raw
);

// Word address: {row (XADR), column (YADR)}
function [14:0] word_addr(input [2:0] i);
	case (i)
	0: word_addr = {9'd8, 6'd0};
	1: word_addr = {9'd8, 6'd63};
	2: word_addr = {9'd13, 6'd21};
	3: word_addr = {9'd15, 6'd42};
	4: word_addr = {9'd8, 6'd1};   // next to word 0 in its row
	default: word_addr = {9'd9, 6'd0};  // next to word 0 in its column
	endcase
endfunction

function [31:0] pattern(input [2:0] i);
	pattern = {1'b0, word_addr(i), 16'hcafe ^ {13'd0, i}};
endfunction

// The sequence, one controller access per step
localparam S_OLD = 0;          // read word 0
localparam S_ERASE = 1;
localparam S_ERASED = 2;       // 2-7: read words 0-5, expect them erased
localparam S_PROG = 8;         // 8-11: program words 0-3
localparam S_CHECK = 12;       // 12-17: read words 0-5
localparam S_DONE = 18;

reg [4:0] step;
reg [2:0] idx;
reg [3:0] wstrb;
always @* begin
	idx = 0;
	wstrb = 4'b0000;          // read
	if (step == S_ERASE)
		wstrb = 4'b0001;      // erase the page of addr
	else if (step >= S_PROG && step < S_CHECK) begin
		idx = step - S_PROG;
		wstrb = 4'b1111;      // program
	end else if (step >= S_CHECK)
		idx = step - S_CHECK;
	else if (step >= S_ERASED)
		idx = step - S_ERASED;
end

localparam [31:0] ERASED = 32'h00000000;
wire [31:0] want = step >= S_CHECK && idx < 4 ? pattern(idx) : ERASED;

reg sel;
wire ready;
wire [31:0] dout;
uflash #(.CLK_FREQ(`CPU_FREQ * 1000000)) ctrl(
	.reset_n(!rst),
	.clk(clk),
	.sel(sel),
	.wstrb(wstrb),
	.addr(word_addr(idx)),
	.data_i(pattern(idx)),
	.ready(ready),
	.data_o(dout)
);

// About 1 ms before the first access
reg [15:0] wait_cnt;
reg busy;

always @(posedge clk) begin
	sel <= 1'b0;
	if (rst) begin
		step <= S_OLD;
		wait_cnt <= 0;
		busy <= 1'b0;
		pass <= 0;
		raw <= 0;
	end else if (!(&wait_cnt)) begin
		wait_cnt <= wait_cnt + 1'b1;
	end else if (step != S_DONE) begin
		if (!busy) begin
			sel <= 1'b1;
			busy <= 1'b1;
		end else if (ready) begin
			busy <= 1'b0;
			step <= step + 1'b1;
			if (step == S_OLD)
				raw[63:32] <= dout;
			if (step >= S_ERASED && step < S_PROG)
				pass[idx] <= dout == ERASED;
			if (step >= S_CHECK) begin
				pass[6 + idx] <= dout == want;
				if (idx == 0)
					raw[31:0] <= dout;
			end
		end
	end else begin
		pass[12] <= 1'b1;
	end
end

endmodule
