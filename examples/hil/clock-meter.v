`default_nettype none

// Shared by the clock tests: frequency measurement against clk.
//
// Each of the N clocks under test runs a PRE-bit counter. Its top bit crosses
// into clk through two flip-flops, and its rising edges are counted over a
// window of 2^WIN cycles of clk, so a clock at f gives
//   2^(WIN-PRE) * f / f_clk
// edges per window, give or take one. The top bit has to toggle at less than
// half the rate of clk, i.e. f < 2^(PRE-1) * f_clk.
//
// At the end of each window, count holds the edges of that window, 16 bits
// per clock, and done pulses for one cycle.
module hil_clock_meter #(
	parameter N = 1,
	parameter PRE = 4,
	parameter WIN = 16
) (
	input wire clk,
	input wire rst,
	input wire [N-1:0] mclk,
	output reg [N*16-1:0] count,
	output reg done
);

reg [WIN-1:0] t;
wire last = &t;
always @(posedge clk) begin
	done <= !rst && last;
	if (rst)
		t <= 0;
	else
		t <= t + 1'b1;
end

genvar i;
generate
	for (i = 0; i < N; i = i + 1) begin : ch
		reg [PRE-1:0] pre = 0;
		always @(posedge mclk[i])
			pre <= pre + 1'b1;

		reg [2:0] sync = 0;
		wire rise = sync[1] && !sync[2];
		reg [15:0] acc = 0;
		always @(posedge clk) begin
			sync <= {sync[1:0], pre[PRE-1]};
			if (last) begin
				count[16*i +: 16] <= acc + rise;
				acc <= 0;
			end else begin
				acc <= acc + rise;
			end
		end
	end
endgenerate

endmodule

// Checks the counts of one clock against [lo, hi]. The first window after
// start goes high is skipped (power-up, PLL lock), and so are windows with en
// low. pass goes high after the first checked window and drops for good on
// the first count out of range, or when start drops.
module hil_clock_check (
	input wire clk,
	input wire rst,
	input wire done,
	input wire start,
	input wire en,
	input wire [15:0] count,
	input wire [15:0] lo,
	input wire [15:0] hi,
	output wire pass
);

reg armed, seen, fail;
always @(posedge clk)
	if (rst) begin
		armed <= 1'b0;
		seen <= 1'b0;
		fail <= 1'b0;
	end else if (done) begin
		if (!start) begin
			armed <= 1'b0;
			if (seen) fail <= 1'b1;
		end else if (!armed) begin
			armed <= 1'b1;
		end else if (en) begin
			seen <= 1'b1;
			if (count < lo || count > hi)
				fail <= 1'b1;
		end
	end

assign pass = seen && !fail;

endmodule
