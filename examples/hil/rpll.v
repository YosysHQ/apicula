`default_nettype none

// rPLL from clk to 90 MHz (VCO 720 MHz), with CLKOUTP phase shifted (the
// phase is not checked), CLKOUTD at CLKOUT/6 and CLKOUTD3 at CLKOUT/3. After
// LOCK, all four outputs are measured against clk; they are locked to it, so
// the counts are exact up to the edge at the window boundary.
//
// pass[0]: LOCK went high and stayed high; pass[1]: CLKOUT, pass[2]:
// CLKOUTP, pass[3]: CLKOUTD, pass[4]: CLKOUTD3 in range.
//
// VR=1 is the pllvr test: the same with PLLVR (GW1NS-4), whose input and
// feedback dividers come from the dynamic IDSEL and FBDSEL inputs instead,
// as the old blinky-pll-vr example did. Those inputs take the inverted
// divider setting (from the dual-pll-vr example, not checked on hardware).

module rpll_test #(
	parameter VR = 0
) (
	input wire clk,
	input wire rst,
	output wire [4:0] pass,
	output wire [63:0] raw
);

// FCLKIN * (FBDIV_SEL+1) / (IDIV_SEL+1) = 90 MHz for the boards' clocks
localparam FCLKIN = `CPU_FREQ == 27 ? "27" : `CPU_FREQ == 50 ? "50" :
                    `CPU_FREQ == 24 ? "24" : "12";
localparam integer IDIV = `CPU_FREQ == 27 ? 3 : `CPU_FREQ == 50 ? 5 :
                          `CPU_FREQ == 24 ? 4 : 2;
localparam integer FBDIV = 90 * IDIV / `CPU_FREQ;
localparam integer SDIV = 6;
// PLLVR's dynamic divider inputs
localparam [5:0] IDSEL = ~(IDIV - 1);
localparam [5:0] FBDSEL = ~(FBDIV - 1);

generate
	if (`CPU_FREQ * FBDIV != 90 * IDIV)
		$error("rpll_test: no PLL setting for CPU_FREQ");
endgenerate

wire lock;
wire [3:0] clks;
generate
if (VR) begin : vr
	PLLVR #(
		.FCLKIN(FCLKIN),
		.DEVICE("GW1NSR-4C"),
		.IDIV_SEL(0),
		.FBDIV_SEL(0),
		.ODIV_SEL(8),
		.DYN_IDIV_SEL("true"),
		.DYN_FBDIV_SEL("true"),
		.DYN_ODIV_SEL("false"),
		.DYN_SDIV_SEL(SDIV),
		.CLKFB_SEL("internal"),
		.CLKOUT_BYPASS("false"),
		.CLKOUTP_BYPASS("false"),
		.CLKOUTD_BYPASS("false"),
		.CLKOUTD_SRC("CLKOUT"),
		.CLKOUTD3_SRC("CLKOUT"),
		.DYN_DA_EN("false"),
		.PSDA_SEL("0100"),
		.DUTYDA_SEL("1000")
	) pll(
		.CLKIN(clk),
		.CLKFB(1'b0),
		.RESET(1'b0),
		.RESET_P(1'b0),
		.FBDSEL(FBDSEL),
		.IDSEL(IDSEL),
		.ODSEL(6'b0),
		.PSDA(4'b0),
		.DUTYDA(4'b0),
		.FDLY(4'b0),
		.VREN(1'b1),
		.CLKOUT(clks[0]),
		.CLKOUTP(clks[1]),
		.CLKOUTD(clks[2]),
		.CLKOUTD3(clks[3]),
		.LOCK(lock)
	);
end else begin : r
	rPLL #(
		.FCLKIN(FCLKIN),
		.IDIV_SEL(IDIV - 1),
		.FBDIV_SEL(FBDIV - 1),
		.ODIV_SEL(8),
		.DYN_IDIV_SEL("false"),
		.DYN_FBDIV_SEL("false"),
		.DYN_ODIV_SEL("false"),
		.DYN_SDIV_SEL(SDIV),
		.CLKFB_SEL("internal"),
		.CLKOUT_BYPASS("false"),
		.CLKOUTP_BYPASS("false"),
		.CLKOUTD_BYPASS("false"),
		.CLKOUTD_SRC("CLKOUT"),
		.CLKOUTD3_SRC("CLKOUT"),
		.DYN_DA_EN("false"),
		.PSDA_SEL("0100"),
		.DUTYDA_SEL("1000")
	) pll(
		.CLKIN(clk),
		.CLKFB(1'b0),
		.RESET(1'b0),
		.RESET_P(1'b0),
		.FBDSEL(6'b0),
		.IDSEL(6'b0),
		.ODSEL(6'b0),
		.PSDA(4'b0),
		.DUTYDA(4'b0),
		.FDLY(4'b0),
		.CLKOUT(clks[0]),
		.CLKOUTP(clks[1]),
		.CLKOUTD(clks[2]),
		.CLKOUTD3(clks[3]),
		.LOCK(lock)
	);
end
endgenerate

reg [1:0] lock_sync;
always @(posedge clk)
	lock_sync <= {lock_sync[0], lock};

// Checked every cycle: the meter only samples start once per window.
reg locked, lost;
always @(posedge clk)
	if (rst) begin
		locked <= 1'b0;
		lost <= 1'b0;
	end else begin
		locked <= locked | lock_sync[1];
		lost <= lost | (locked & !lock_sync[1]);
	end
wire lock_held = lock_sync[1] & !lost;

wire done;
hil_clock_meter #(.N(4), .PRE(5), .WIN(16)) meter(
	.clk(clk), .rst(rst), .mclk(clks), .count(raw), .done(done)
);

// 2^(16-5) * f / f_clk edges per window
localparam integer EXP = 2048 * FBDIV / IDIV;
localparam integer EXPD = 2048 * FBDIV / (IDIV * SDIV);
localparam integer EXPD3 = 2048 * FBDIV / (IDIV * 3);

hil_clock_check check_lock(
	.clk(clk), .rst(rst), .done(done), .start(lock_held), .en(1'b1),
	.count(16'd0), .lo(16'd0), .hi(16'd0), .pass(pass[0])
);
hil_clock_check check_out(
	.clk(clk), .rst(rst), .done(done), .start(lock_held), .en(1'b1),
	.count(raw[0 +: 16]), .lo(EXP - 2), .hi(EXP + 2), .pass(pass[1])
);
hil_clock_check check_outp(
	.clk(clk), .rst(rst), .done(done), .start(lock_held), .en(1'b1),
	.count(raw[16 +: 16]), .lo(EXP - 2), .hi(EXP + 2), .pass(pass[2])
);
hil_clock_check check_outd(
	.clk(clk), .rst(rst), .done(done), .start(lock_held), .en(1'b1),
	.count(raw[32 +: 16]), .lo(EXPD - 2), .hi(EXPD + 2), .pass(pass[3])
);
hil_clock_check check_outd3(
	.clk(clk), .rst(rst), .done(done), .start(lock_held), .en(1'b1),
	.count(raw[48 +: 16]), .lo(EXPD3 - 2), .hi(EXPD3 + 2), .pass(pass[4])
);

endmodule
