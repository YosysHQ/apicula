`default_nettype none

// The on-chip oscillator, at FREQ_DIV=8, measured against clk.
//
// The boards use OSC, OSCZ, OSCH or OSCA (OSC_TYPE_* from the board's yosys
// rule). Its nominal frequency is OSC_MHZ / FREQ_DIV, with OSC_MHZ from Gowin's
// UG286: 250 MHz for OSC and OSCZ, 240 MHz for OSCH, and 210 MHz for GW1N-4,
// whose board rule overrides it; GW5A's OSCA runs at 210 MHz (DS1103, 2.13).
// The datasheets give a tolerance of 5%, but the bench boards measured +5%
// (tangnano9k) and -6% (tangnano20k); the check
// allows TOL percent, which still tells FREQ_DIV from its neighbours (6 and
// 10 are 33% and 20% away).
//
// pass[0]: every window in range.

`ifndef OSC_MHZ
`ifdef OSC_TYPE_OSCH
`define OSC_MHZ 240
`elsif OSC_TYPE_OSCA
`define OSC_MHZ 210
`else
`define OSC_MHZ 250
`endif
`endif

module osc_test (
	input wire clk,
	input wire rst,
	output wire [0:0] pass,
	output wire [15:0] raw
);

localparam FREQ_DIV = 8;
localparam TOL = 10;

wire oscout;
`ifdef OSC_TYPE_OSC
OSC #(.FREQ_DIV(FREQ_DIV)) osc(
	.OSCOUT(oscout)
);
`elsif OSC_TYPE_OSCZ
OSCZ #(.FREQ_DIV(FREQ_DIV)) osc(
	.OSCEN(1'b1),
	.OSCOUT(oscout)
);
`elsif OSC_TYPE_OSCF
OSCF #(.FREQ_DIV(FREQ_DIV)) osc(
	.OSCEN(1'b1),
	.OSCOUT(oscout),
	.OSCOUT30M()
);
`elsif OSC_TYPE_OSCH
OSCH #(.FREQ_DIV(FREQ_DIV)) osc(
	.OSCOUT(oscout)
);
`elsif OSC_TYPE_OSCA
OSCA #(.FREQ_DIV(FREQ_DIV)) osc(
	.OSCEN(1'b1),
	.OSCOUT(oscout)
);
`endif

// 2^(16-4) * f_osc / f_clk edges per window
localparam integer EXP = 4096 * `OSC_MHZ / (FREQ_DIV * `CPU_FREQ);
localparam integer LO = EXP * (100 - TOL) / 100;
localparam integer HI = EXP * (100 + TOL) / 100;

wire done;
hil_clock_meter #(.N(1), .PRE(4), .WIN(16)) meter(
	.clk(clk), .rst(rst), .mclk(oscout), .count(raw), .done(done)
);

hil_clock_check check(
	.clk(clk), .rst(rst), .done(done), .start(1'b1), .en(1'b1),
	.count(raw), .lo(LO[15:0]), .hi(HI[15:0]), .pass(pass[0])
);

endmodule
