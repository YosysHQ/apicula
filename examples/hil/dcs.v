`default_nettype none

// DCS in RISING (glitchless) mode, switching between four clocks. The test
// selects one input per measurement window in turn and checks the frequency
// of the output. nextpnr takes DCS_MODE from an attribute, not a parameter.
//
// GW1N/GW2A: clk, and three CLKDIV2 + CLKDIV pairs at clk/4, clk/8 and clk/7.
// GW5A (FAMILY_GW5A): its DCS inputs are CLKIN0-3, and nextpnr cannot route
// them from a pin, so they come from a PLLA as in the old gw5a dcs example:
// VCO 800 MHz (MDIV 16), CLKOUT0-3 at /32, /40, /64 and /100, i.e. 25, 20,
// 12.5 and 8 MHz (UG306, 5.1); the checks start once the PLL has locked.
//
// pass[i]: windows with CLKSEL[i] set run at the frequency of input i.

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

wire dcs_out;
wire start;
`ifdef FAMILY_GW5A
localparam integer MDIV = 16;
localparam [4*8-1:0] ODIV = {8'd100, 8'd64, 8'd40, 8'd32};
wire [6:0] pclk;
wire lock;
hil_plla #(.MDIV(MDIV), .ODIV0(ODIV[0+:8]), .ODIV1(ODIV[8+:8]), .ODIV2(ODIV[16+:8]), .ODIV3(ODIV[24+:8]))
	pll(.clk(clk), .clkout(pclk), .lock(lock));
hil_lock_monitor mon(.clk(clk), .rst(rst), .lock(lock), .held(start));

(* DCS_MODE = "RISING" *)
DCS dcs(
	.CLKIN0(pclk[0]),
	.CLKIN1(pclk[1]),
	.CLKIN2(pclk[2]),
	.CLKIN3(pclk[3]),
	.CLKSEL(sel),
	.SELFORCE(1'b0),
	.CLKOUT(dcs_out)
);
`else
wire clk2, clk4, clk2a, clk2b, clk8, clk7;
CLKDIV2 div2(.RESETN(1'b1), .HCLKIN(clk), .CLKOUT(clk2));
CLKDIV #(.DIV_MODE("2")) div4(.RESETN(1'b1), .HCLKIN(clk2), .CLKOUT(clk4));
CLKDIV2 div2a(.RESETN(1'b1), .HCLKIN(clk), .CLKOUT(clk2a));
CLKDIV #(.DIV_MODE("4")) div8(.RESETN(1'b1), .HCLKIN(clk2a), .CLKOUT(clk8));
CLKDIV2 div2b(.RESETN(1'b1), .HCLKIN(clk), .CLKOUT(clk2b));
CLKDIV #(.DIV_MODE("3.5")) div7(.RESETN(1'b1), .HCLKIN(clk2b), .CLKOUT(clk7));
assign start = 1'b1;

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
`endif

hil_clock_meter #(.N(1), .PRE(4), .WIN(16)) meter(
	.clk(clk), .rst(rst), .mclk(dcs_out), .count(raw), .done(done)
);

// 2^(16-4) * f / f_clk edges per window; the switch costs a few cycles
genvar i;
generate
	for (i = 0; i < 4; i = i + 1) begin : chk
`ifdef FAMILY_GW5A
		localparam integer EXP = 4096 * MDIV / ODIV[8 * i +: 8];
`else
		localparam integer EXP = i == 0 ? 4096 : i == 1 ? 1024 : i == 2 ? 512 : 585;
`endif
		hil_clock_check check(
			.clk(clk), .rst(rst), .done(done), .start(start), .en(phase == i),
			.count(raw), .lo(EXP - 3), .hi(EXP + 3), .pass(pass[i])
		);
	end
endgenerate

endmodule
