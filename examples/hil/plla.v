`default_nettype none

// GW5A PLLA, all seven outputs, as the old pll7 example: from the 50 MHz clk
// with IDIV 1, FBDIV 1 and MDIV 18 the VCO runs at 900 MHz, and the outputs at
// 900 MHz / ODIVn (UG306, 5.1: Fvco = Fclkin / IDIV * FBDIV * MDIV with internal
// feedback, Fclkoutx = Fvco / ODIVx). After LOCK, each output is measured
// against clk; the outputs are locked to it, so the counts are exact up to the
// edge at the window boundary. The window is 2^18 cycles of clk, long enough
// that ODIV6 = 117 (1260.3 edges) cannot pass for 116 (1271.2) or 118
// (1249.6).
//
// Each test measures some of the outputs: with all seven and the system clock
// on global wires, nextpnr routed the system clock partly through the fabric
// in about one placement of six, garbling the reporter. plla measures CLKOUT0-3,
// plla2 CLKOUT4-6, each with all seven outputs enabled.
//
// pass[0]: LOCK went high and stayed high; pass[n+1]: CLKOUT(FIRST + n) in range.

module hil_plla #(
	parameter integer MDIV = 18,
	parameter integer ODIV0 = 8, ODIV1 = 8, ODIV2 = 8, ODIV3 = 8,
	parameter integer ODIV4 = 8, ODIV5 = 8, ODIV6 = 8
) (
	input wire clk,
	output wire [6:0] clkout,
	output wire lock
);
	wire gnd = 1'b0;
	PLLA #(
		.FCLKIN("50"),
		.IDIV_SEL(1),
		.FBDIV_SEL(1),
		.MDIV_SEL(MDIV),
		.MDIV_FRAC_SEL(0),
		.ODIV0_SEL(ODIV0),
		.ODIV0_FRAC_SEL(0),
		.ODIV1_SEL(ODIV1),
		.ODIV2_SEL(ODIV2),
		.ODIV3_SEL(ODIV3),
		.ODIV4_SEL(ODIV4),
		.ODIV5_SEL(ODIV5),
		.ODIV6_SEL(ODIV6),
		.CLKOUT0_EN("TRUE"),
		.CLKOUT1_EN("TRUE"),
		.CLKOUT2_EN("TRUE"),
		.CLKOUT3_EN("TRUE"),
		.CLKOUT4_EN("TRUE"),
		.CLKOUT5_EN("TRUE"),
		.CLKOUT6_EN("TRUE"),
		.CLKFB_SEL("INTERNAL"),
		.DYN_DPA_EN("FALSE"),
		.RESET_I_EN("FALSE"),
		.RESET_O_EN("FALSE"),
		.SSC_EN("FALSE")
	) pll (
		.CLKIN(clk),
		.CLKFB(gnd),
		.RESET(gnd),
		.PLLPWD(gnd),
		.RESET_I(gnd),
		.RESET_O(gnd),
		.PSSEL(3'b0),
		.PSDIR(gnd),
		.PSPULSE(gnd),
		.SSCPOL(gnd),
		.SSCON(gnd),
		.SSCMDSEL(7'b0),
		.SSCMDSEL_FRAC(3'b0),
		.MDCLK(gnd),
		.MDOPC(2'b0),
		.MDAINC(gnd),
		.MDWDI(8'b0),
		.MDRDO(),  // two of the GW5AT-60B's three PLL sites have no MDRDO0-3
		.LOCK(lock),
		.CLKOUT0(clkout[0]),
		.CLKOUT1(clkout[1]),
		.CLKOUT2(clkout[2]),
		.CLKOUT3(clkout[3]),
		.CLKOUT4(clkout[4]),
		.CLKOUT5(clkout[5]),
		.CLKOUT6(clkout[6]),
		.CLKFBOUT()
	);
endmodule

// LOCK went high and stayed high, checked every cycle: the meter only
// samples start once per window.
module hil_lock_monitor (
	input wire clk,
	input wire rst,
	input wire lock,
	output wire held
);
	reg [1:0] sync;
	reg locked, lost;
	always @(posedge clk) begin
		sync <= {sync[0], lock};
		if (rst) begin
			locked <= 1'b0;
			lost <= 1'b0;
		end else begin
			locked <= locked | sync[1];
			lost <= lost | (locked & !sync[1]);
		end
	end
	assign held = sync[1] & !lost;
endmodule

module plla_test #(
	parameter integer FIRST = 0,  // measured outputs: CLKOUT[FIRST +: N]
	parameter integer N = 4
) (
	input wire clk,
	input wire rst,
	output wire [N:0] pass,
	output wire [N*16-1:0] raw
);
	localparam integer MDIV = 18;
	localparam [7*8-1:0] ODIV = {8'd117, 8'd100, 8'd90, 8'd60, 8'd45, 8'd41, 8'd36};

	wire [6:0] clks;
	wire lock, lock_held;
	hil_plla #(.MDIV(MDIV),
		.ODIV0(ODIV[0+:8]), .ODIV1(ODIV[8+:8]), .ODIV2(ODIV[16+:8]), .ODIV3(ODIV[24+:8]),
		.ODIV4(ODIV[32+:8]), .ODIV5(ODIV[40+:8]), .ODIV6(ODIV[48+:8])
	) pll(.clk(clk), .clkout(clks), .lock(lock));
	hil_lock_monitor mon(.clk(clk), .rst(rst), .lock(lock), .held(lock_held));

	wire done;
	hil_clock_meter #(.N(N), .PRE(5), .WIN(18)) meter(
		.clk(clk), .rst(rst), .mclk(clks[FIRST +: N]), .count(raw), .done(done)
	);

	hil_clock_check check_lock(
		.clk(clk), .rst(rst), .done(done), .start(lock_held), .en(1'b1),
		.count(16'd0), .lo(16'd0), .hi(16'd0), .pass(pass[0])
	);

	// 2^(18-5) * f / f_clk edges per window, f / f_clk = MDIV / ODIV
	genvar i;
	generate
		for (i = 0; i < N; i = i + 1) begin : chk
			localparam integer EXP = 8192 * MDIV / ODIV[8 * (FIRST + i) +: 8];
			hil_clock_check check(
				.clk(clk), .rst(rst), .done(done), .start(lock_held), .en(1'b1),
				.count(raw[16 * i +: 16]), .lo(EXP - 2), .hi(EXP + 3), .pass(pass[i + 1])
			);
		end
	endgenerate
endmodule
