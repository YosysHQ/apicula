`default_nettype none

// DHCEN, gating clk into a CLKDIV2 and a CLKDIV (DIV_MODE 4) behind it, the
// connection the vendor documents (a CLKDIV2 may only drive HCLK loads, so
// only the CLKDIV is measured). CE is active low
// (UG286): the test turns the clock on and off in alternate measurement
// windows, and counts clk/8 edges in the on windows and none (up to the
// gating latency, one edge) in the off windows.
//
// pass[0]: the clock runs while CE=0; pass[1]: it stops while CE=1.

module dhcen_test (
	input wire clk,
	input wire rst,
	output wire [1:0] pass,
	output wire [15:0] raw
);

wire done;

// CE for the current window; it changes one cycle after done.
reg off;
always @(posedge clk)
	if (rst)
		off <= 1'b0;
	else if (done)
		off <= !off;

wire hclk;
DHCEN dhcen(
	.CLKIN(clk),
	.CE(off),
	.CLKOUT(hclk)
);

wire div2_out, div_out;
CLKDIV2 div2(
	.RESETN(1'b1),
	.HCLKIN(hclk),
	.CLKOUT(div2_out)
);

CLKDIV #(.DIV_MODE("4")) div(
	.RESETN(1'b1),
	.HCLKIN(div2_out),
	.CLKOUT(div_out)
);

hil_clock_meter #(.N(1), .PRE(4), .WIN(16)) meter(
	.clk(clk), .rst(rst), .mclk(div_out), .count(raw), .done(done)
);

// 2^(16-4) / 8 edges per window
hil_clock_check run(
	.clk(clk), .rst(rst), .done(done), .start(1'b1), .en(!off),
	.count(raw), .lo(16'd512 - 3), .hi(16'd512 + 3), .pass(pass[0])
);
hil_clock_check stop(
	.clk(clk), .rst(rst), .done(done), .start(1'b1), .en(off),
	.count(raw), .lo(16'd0), .hi(16'd1), .pass(pass[1])
);

endmodule
