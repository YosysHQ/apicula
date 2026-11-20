`default_nettype none

// Two DQCEs gating clk, each with its own CE pattern: over four measurement
// windows dqce0 runs, stops, runs, stops and dqce1 runs, runs, stops, stops.
// A running clock gives clk/16 edges per window, a stopped one none (up to
// the gating latency, one edge).
//
// pass[0]: dqce0 runs while CE=1; pass[1]: dqce0 stops while CE=0;
// pass[2], pass[3]: the same for dqce1.

module dqce_test (
	input wire clk,
	input wire rst,
	output wire [3:0] pass,
	output wire [31:0] raw
);

wire done;

// Window number; CE changes one cycle after done.
reg [1:0] phase;
always @(posedge clk)
	if (rst)
		phase <= 0;
	else if (done)
		phase <= phase + 1'b1;

wire [1:0] ce = ~phase;  // dqce0 runs in even windows, dqce1 in windows 0 and 1

wire [1:0] clks;
DQCE dqce0(
	.CLKIN(clk),
	.CE(ce[0]),
	.CLKOUT(clks[0])
);

DQCE dqce1(
	.CLKIN(clk),
	.CE(ce[1]),
	.CLKOUT(clks[1])
);

hil_clock_meter #(.N(2), .PRE(4), .WIN(16)) meter(
	.clk(clk), .rst(rst), .mclk(clks), .count(raw), .done(done)
);

// 2^(16-4) edges per window
genvar i;
generate
	for (i = 0; i < 2; i = i + 1) begin : chk
		hil_clock_check run(
			.clk(clk), .rst(rst), .done(done), .start(1'b1), .en(ce[i]),
			.count(raw[16*i +: 16]), .lo(16'd4096 - 3), .hi(16'd4096 + 3), .pass(pass[2*i])
		);
		hil_clock_check stop(
			.clk(clk), .rst(rst), .done(done), .start(1'b1), .en(!ce[i]),
			.count(raw[16*i +: 16]), .lo(16'd0), .hi(16'd1), .pass(pass[2*i+1])
		);
	end
endgenerate

endmodule
