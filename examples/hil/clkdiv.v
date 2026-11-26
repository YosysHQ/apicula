`default_nettype none

// CLKDIV2 and CLKDIV, measured against clk.
//
// Every HCLK (NUM_HCLK from the board's yosys rule) gets a CLKDIV2 from clk
// and a CLKDIV behind it, with DIV_MODE 2, 3.5, 4, 5, 2, ... in turn, so the
// CLKDIV outputs run at clk/4, clk/7, clk/8, clk/10. Only the CLKDIV outputs
// are measured: a CLKDIV2 may only drive HCLK loads (the vendor's rule, see
// doc/agent/tiled-fuzzer.md), and nextpnr finds no route from one to the
// fabric. All come from clk, so the counts are exact up to the edge at the
// window boundary.
//
// pass[i]: the CLKDIV of HCLK i in range.

module clkdiv_test (
	input wire clk,
	input wire rst,
	output wire [`NUM_HCLK-1:0] pass,
	output wire [`NUM_HCLK*16-1:0] raw
);

wire [`NUM_HCLK-1:0] clks;

genvar i;
generate
	for (i = 0; i < `NUM_HCLK; i = i + 1) begin : hclk
		localparam DIV_MODE = i % 4 == 0 ? "2" : i % 4 == 1 ? "3.5" : i % 4 == 2 ? "4" : "5";

		wire div2_out;
		CLKDIV2 div2(
			.RESETN(1'b1),
			.HCLKIN(clk),
			.CLKOUT(div2_out)
		);

		CLKDIV #(.DIV_MODE(DIV_MODE)) div(
			.RESETN(1'b1),
			.HCLKIN(div2_out),
			.CLKOUT(clks[i])
		);
	end
endgenerate

wire done;
hil_clock_meter #(.N(`NUM_HCLK), .PRE(4), .WIN(16)) meter(
	.clk(clk), .rst(rst), .mclk(clks), .count(raw), .done(done)
);

// 2^(16-4) / M edges per window, M the total division
generate
	for (i = 0; i < `NUM_HCLK; i = i + 1) begin : chk
		localparam integer M = i % 4 == 0 ? 4 : i % 4 == 1 ? 7 : i % 4 == 2 ? 8 : 10;
		localparam [15:0] LO = 4096 / M - 2;
		localparam [15:0] HI = 4096 / M + 3;

		hil_clock_check check(
			.clk(clk), .rst(rst), .done(done), .start(1'b1), .en(1'b1),
			.count(raw[16*i +: 16]), .lo(LO), .hi(HI), .pass(pass[i])
		);
	end
endgenerate

endmodule
