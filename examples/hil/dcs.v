`default_nettype none

// DCS in RISING (glitchless) mode, switching between four clocks: clk, and
// three CLKDIV2 + CLKDIV pairs at clk/4, clk/8 and clk/7. The test selects one
// input per measurement window in turn and checks the frequency of the
// output. nextpnr takes DCS_MODE from an attribute, not a parameter.
//
// pass[i]: windows with CLKSEL[i] set run at the frequency of CLKi.

module dcs_test (
	input wire clk,
	input wire rst,
	output wire [3:0] pass,
	output wire [15:0] raw
);

wire done;

// Window number; CLKSEL changes one cycle after done.
reg [1:0] phase;
always @(posedge clk)
	if (rst)
		phase <= 0;
	else if (done)
		phase <= phase + 1'b1;

wire [3:0] sel = 4'b1 << phase;

wire clk2, clk4, clk2a, clk2b, clk8, clk7;
CLKDIV2 div2(.RESETN(1'b1), .HCLKIN(clk), .CLKOUT(clk2));
CLKDIV #(.DIV_MODE("2")) div4(.RESETN(1'b1), .HCLKIN(clk2), .CLKOUT(clk4));
CLKDIV2 div2a(.RESETN(1'b1), .HCLKIN(clk), .CLKOUT(clk2a));
CLKDIV #(.DIV_MODE("4")) div8(.RESETN(1'b1), .HCLKIN(clk2a), .CLKOUT(clk8));
CLKDIV2 div2b(.RESETN(1'b1), .HCLKIN(clk), .CLKOUT(clk2b));
CLKDIV #(.DIV_MODE("3.5")) div7(.RESETN(1'b1), .HCLKIN(clk2b), .CLKOUT(clk7));

wire dcs_out;
(* DCS_MODE = "RISING" *)
DCS dcs(
	.CLK0(clk),
	.CLK1(clk4),
	.CLK2(clk8),
	.CLK3(clk7),
	.CLKSEL(sel),
	.SELFORCE(1'b0),
	.CLKOUT(dcs_out)
);

hil_clock_meter #(.N(1), .PRE(4), .WIN(16)) meter(
	.clk(clk), .rst(rst), .mclk(dcs_out), .count(raw), .done(done)
);

// 2^(16-4) / divider edges per window; the switch costs a few cycles
genvar i;
generate
	for (i = 0; i < 4; i = i + 1) begin : chk
		localparam integer EXP = i == 0 ? 4096 : i == 1 ? 1024 : i == 2 ? 512 : 585;
		hil_clock_check check(
			.clk(clk), .rst(rst), .done(done), .start(1'b1), .en(phase == i),
			.count(raw), .lo(EXP - 3), .hi(EXP + 3), .pass(pass[i])
		);
	end
endgenerate

endmodule
