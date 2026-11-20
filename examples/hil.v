`default_nettype none

// Hardware-in-the-loop test bench: one bitstream runs every test enabled with
// `define HIL_<name> (dashes become underscores), so a batch of tests costs a
// single place-and-route and upload. When one test poisons the design, run
// the tests one at a time to find it: see the HIL section of the Makefile.
//
// Each tick prints a line per row of every enabled test,
//   <test> <row> = 0x<72-bit value>
// then "--- tick ---", and then gives the DSPs one clock pulse, so the block
// after the n-th tick shows the DSPs after n clocks.

`include "emitter_uart.v"
`include "hil/latch.v"
`include "hil/dsp-mult9x9.v"
`include "hil/dsp-mult18x18.v"
`include "hil/dsp-mult36x36.v"
`include "hil/dsp-padd9.v"
`include "hil/dsp-padd18.v"
`include "hil/dsp-multalu18x18.v"
`include "hil/dsp-multalu36x18.v"
`include "hil/dsp-multaddalu18x18.v"
`include "hil/dsp-alu54d.v"
`include "hil/clock-meter.v"
`include "hil/osc.v"
`include "hil/clkdiv.v"
`include "hil/dhcen.v"
`include "hil/dqce.v"
`include "hil/dcs.v"
`include "hil/rpll.v"
`include "hil/bsram.v"

// The DSP tests have five 64-bit outputs; w is a 5*64-bit wire.
`define DSP_PORTS(w) \
	.product(w[0+:64]), .product1(w[64+:64]), .product2(w[128+:64]), \
	.product3(w[192+:64]), .product4(w[256+:64])
`define DSP_OUT(w, i) {8'b0, w[(i)*64 +: 64]}

// The modules of the disabled tests are top-level candidates too
(* top *)
module top (
	input wire clk,
	output wire TXD
);

// Power-on reset
reg [3:0] por_cnt = 0;
wire rst = !por_cnt[3];
always @(posedge clk)
	if (rst) por_cnt <= por_cnt + 1;

// DSP clock: one registered pulse per tick
reg dsp_clk;

// ---- Tests ----

`ifdef HIL_latch
wire [3:0] latch_pass;
latch_test latch(.clk(clk), .rst(rst), .pass(latch_pass));
`endif
`ifdef HIL_dsp_mult9x9
wire [5*64-1:0] mult9x9;
dsp_mult9x9 mult9x9_i(.clk(dsp_clk), .reset(rst), `DSP_PORTS(mult9x9));
`endif
`ifdef HIL_dsp_mult18x18
wire [5*64-1:0] mult18x18;
dsp_mult18x18 mult18x18_i(.clk(dsp_clk), .reset(rst), `DSP_PORTS(mult18x18));
`endif
`ifdef HIL_dsp_mult36x36
wire [5*64-1:0] mult36x36;
dsp_mult36x36 mult36x36_i(.clk(dsp_clk), .reset(rst), `DSP_PORTS(mult36x36));
`endif
`ifdef HIL_dsp_padd9
wire [5*64-1:0] padd9;
dsp_padd9 padd9_i(.clk(dsp_clk), .reset(rst), `DSP_PORTS(padd9));
`endif
`ifdef HIL_dsp_padd18
wire [5*64-1:0] padd18;
dsp_padd18 padd18_i(.clk(dsp_clk), .reset(rst), `DSP_PORTS(padd18));
`endif
`ifdef HIL_dsp_multalu18x18
wire [5*64-1:0] multalu18x18;
dsp_multalu18x18 multalu18x18_i(.clk(dsp_clk), .reset(rst), `DSP_PORTS(multalu18x18));
`endif
`ifdef HIL_dsp_multalu36x18
wire [5*64-1:0] multalu36x18;
dsp_multalu36x18 multalu36x18_i(.clk(dsp_clk), .reset(rst), `DSP_PORTS(multalu36x18));
`endif
`ifdef HIL_dsp_multaddalu18x18
wire [5*64-1:0] multaddalu18x18;
dsp_multaddalu18x18 multaddalu18x18_i(.clk(dsp_clk), .reset(rst), `DSP_PORTS(multaddalu18x18));
`endif
`ifdef HIL_dsp_alu54d
wire [5*64-1:0] alu54d;
dsp_alu54d alu54d_i(.clk(dsp_clk), .reset(rst), `DSP_PORTS(alu54d));
`endif
// The clock tests also give their raw counts (16 bits each, four to a row),
// which vary from run to run and so are not in the references. To print them,
// add `define HIL_RAW to the generated hil-<test>.v and build it by hand.
`ifdef HIL_osc
wire [0:0] osc_pass;
wire [15:0] osc_raw;
osc_test osc(.clk(clk), .rst(rst), .pass(osc_pass), .raw(osc_raw));
`endif
`ifdef HIL_clkdiv
wire [`NUM_HCLK-1:0] clkdiv_pass;
wire [`NUM_HCLK*16-1:0] clkdiv_raw;
wire [2*64-1:0] clkdiv_raw_rows = clkdiv_raw;
clkdiv_test clkdiv(.clk(clk), .rst(rst), .pass(clkdiv_pass), .raw(clkdiv_raw));
`endif
`ifdef HIL_dhcen
wire [1:0] dhcen_pass;
wire [15:0] dhcen_raw;
dhcen_test dhcen(.clk(clk), .rst(rst), .pass(dhcen_pass), .raw(dhcen_raw));
`endif
`ifdef HIL_dqce
wire [3:0] dqce_pass;
wire [31:0] dqce_raw;
dqce_test dqce(.clk(clk), .rst(rst), .pass(dqce_pass), .raw(dqce_raw));
`endif
`ifdef HIL_dcs
wire [3:0] dcs_pass;
wire [15:0] dcs_raw;
dcs_test dcs(.clk(clk), .rst(rst), .pass(dcs_pass), .raw(dcs_raw));
`endif
`ifdef HIL_rpll
wire [4:0] rpll_pass;
wire [63:0] rpll_raw;
rpll_test rpll(.clk(clk), .rst(rst), .pass(rpll_pass), .raw(rpll_raw));
`endif
// BSRAM tests: pass masks, see hil/bsram.v. BSRAM_CFG: width, READ_MODE A/B,
// WRITE_MODE A/B, byte enables from the fabric, OCE tied low, skip the CE/OCE
// hold checks.
`ifdef HIL_bsram_rom
// pROM/pROMX9 as the old bsram-pROM, -pROMX9 and DPB16/DPX9B18 image ROMs
wire [63:0] bsram_rom_pass;
wire [255:0] bsram_rom_dbg;
bsram_test #(.FAM(`BSRAM_FAM_ROM),
	.CFG0(`BSRAM_CFG(8, 1, 0, 0, 0, 0, 0, 1)),
	.CFG1(`BSRAM_CFG(9, 1, 0, 0, 0, 0, 0, 1)),
	.CFG2(`BSRAM_CFG(16, 1, 0, 0, 0, 0, 0, 0)),
	.CFG3(`BSRAM_CFG(18, 1, 0, 0, 0, 0, 0, 0))
) bsram_rom(.clk(clk), .rst(rst), .pass(bsram_rom_pass), .dbg(bsram_rom_dbg));
`endif
`ifdef HIL_bsram_rom2
// pROM/pROMX9, other widths and READ_MODE
wire [63:0] bsram_rom2_pass;
wire [255:0] bsram_rom2_dbg;
bsram_test #(.FAM(`BSRAM_FAM_ROM),
	.CFG0(`BSRAM_CFG(16, 0, 0, 0, 0, 0, 0, 0)),
	.CFG1(`BSRAM_CFG(18, 0, 0, 0, 0, 0, 0, 0)),
	.CFG2(`BSRAM_CFG(4, 0, 0, 0, 0, 0, 0, 1)),
	.CFG3(`BSRAM_CFG(1, 1, 0, 0, 0, 0, 0, 1))
) bsram_rom2(.clk(clk), .rst(rst), .pass(bsram_rom2_pass), .dbg(bsram_rom2_dbg));
`endif
`ifdef HIL_bsram_sp
// SP/SPX9 as the old bsram-SP and -SPX9, then 16/18 bit with byte enables
wire [63:0] bsram_sp_pass;
wire [255:0] bsram_sp_dbg;
bsram_test #(.FAM(`BSRAM_FAM_SP),
	.CFG0(`BSRAM_CFG(8, 1, 0, 1, 0, 0, 0, 0)),
	.CFG1(`BSRAM_CFG(9, 1, 0, 1, 0, 0, 0, 0)),
	.CFG2(`BSRAM_CFG(16, 0, 0, 0, 0, 1, 0, 0)),
	.CFG3(`BSRAM_CFG(18, 1, 0, 2, 0, 1, 0, 0))
) bsram_sp(.clk(clk), .rst(rst), .pass(bsram_sp_pass), .dbg(bsram_sp_dbg));
`endif
`ifdef HIL_bsram_sp2
// SP/SPX9, other widths and modes
wire [63:0] bsram_sp2_pass;
wire [255:0] bsram_sp2_dbg;
bsram_test #(.FAM(`BSRAM_FAM_SP),
	.CFG0(`BSRAM_CFG(32, 1, 0, 1, 0, 0, 0, 0)),
	.CFG1(`BSRAM_CFG(36, 0, 0, 0, 0, 0, 0, 0)),
	.CFG2(`BSRAM_CFG(8, 0, 0, 2, 0, 0, 0, 1)),
	.CFG3(`BSRAM_CFG(4, 1, 0, 0, 0, 0, 0, 0))
) bsram_sp2(.clk(clk), .rst(rst), .pass(bsram_sp2_pass), .dbg(bsram_sp2_dbg));
`endif
`ifdef HIL_bsram_sdp
// SDPB/SDPX9B as the old bsram-SDPB and -SDPX9B, then 16/18 bit
wire [63:0] bsram_sdp_pass;
wire [255:0] bsram_sdp_dbg;
bsram_test #(.FAM(`BSRAM_FAM_SDP),
	.CFG0(`BSRAM_CFG(8, 0, 1, 0, 0, 0, 0, 1)),
	.CFG1(`BSRAM_CFG(9, 0, 1, 0, 0, 0, 0, 1)),
	.CFG2(`BSRAM_CFG(16, 0, 0, 0, 0, 0, 0, 0)),
	.CFG3(`BSRAM_CFG(18, 0, 1, 0, 0, 1, 0, 0))
) bsram_sdp(.clk(clk), .rst(rst), .pass(bsram_sdp_pass), .dbg(bsram_sdp_dbg));
`endif
`ifdef HIL_bsram_sdp2
// SDPB/SDPX9B, other widths and modes
wire [63:0] bsram_sdp2_pass;
wire [255:0] bsram_sdp2_dbg;
bsram_test #(.FAM(`BSRAM_FAM_SDP),
	.CFG0(`BSRAM_CFG(32, 0, 0, 0, 0, 0, 0, 0)),
	.CFG1(`BSRAM_CFG(36, 0, 1, 0, 0, 0, 0, 0)),
	.CFG2(`BSRAM_CFG(8, 0, 0, 0, 0, 0, 0, 1)),
	.CFG3(`BSRAM_CFG(2, 0, 1, 0, 0, 0, 0, 1))
) bsram_sdp2(.clk(clk), .rst(rst), .pass(bsram_sdp2_pass), .dbg(bsram_sdp2_dbg));
`endif
`ifdef HIL_bsram_dp
// DPB/DPX9B as the old bsram-DPB and -DPX9B (whose port A output was unused), then other modes
wire [63:0] bsram_dp_pass;
wire [255:0] bsram_dp_dbg;
bsram_test #(.FAM(`BSRAM_FAM_DP),
	.CFG0(`BSRAM_CFG(8, 0, 1, 1, 1, 0, 0, 0)),
	.CFG1(`BSRAM_CFG(9, 0, 1, 1, 1, 0, 0, 0)),
	.CFG2(`BSRAM_CFG(8, 1, 0, 2, 0, 0, 0, 0)),
	.CFG3(`BSRAM_CFG(9, 1, 0, 0, 2, 0, 0, 0))
) bsram_dp(.clk(clk), .rst(rst), .pass(bsram_dp_pass), .dbg(bsram_dp_dbg));
`endif
`ifdef HIL_bsram_dp16
// DPB/DPX9B 16/18 bit as the old bsram-DPB16 and -DPX9B18, then byte enables and other modes
wire [63:0] bsram_dp16_pass;
wire [255:0] bsram_dp16_dbg;
bsram_test #(.FAM(`BSRAM_FAM_DP),
	.CFG0(`BSRAM_CFG(16, 0, 0, 1, 1, 0, 1, 0)),
	.CFG1(`BSRAM_CFG(18, 0, 0, 1, 1, 0, 1, 0)),
	.CFG2(`BSRAM_CFG(16, 1, 0, 2, 0, 1, 0, 0)),
	.CFG3(`BSRAM_CFG(18, 0, 1, 0, 2, 1, 0, 0))
) bsram_dp16(.clk(clk), .rst(rst), .pass(bsram_dp16_pass), .dbg(bsram_dp16_dbg));
`endif
`ifdef HIL_bsram_rom_bugs
// Known failures, in no batch: narrow pROM output does not hold with CE=0;
// 32/36-bit pROM reads part of word 0 wrong after some designs (e.g. after loading
// bsram-sp-bugs)
wire [63:0] bsram_rom_bugs_pass;
wire [255:0] bsram_rom_bugs_dbg;
bsram_test #(.FAM(`BSRAM_FAM_ROM),
	.CFG0(`BSRAM_CFG(8, 1, 0, 0, 0, 0, 0, 0)),
	.CFG1(`BSRAM_CFG(9, 0, 0, 0, 0, 0, 0, 0)),
	.CFG2(`BSRAM_CFG(32, 0, 0, 0, 0, 0, 0, 0)),
	.CFG3(`BSRAM_CFG(36, 1, 0, 0, 0, 0, 0, 0))
) bsram_rom_bugs(.clk(clk), .rst(rst), .pass(bsram_rom_bugs_pass), .dbg(bsram_rom_bugs_dbg));
`endif
`ifdef HIL_bsram_sp_bugs
// Known failures, in no batch: narrow SP READ_MODE 0 output with CE=0,
// 32-bit WRITE_MODE 2, 32-bit byte enables
wire [63:0] bsram_sp_bugs_pass;
wire [255:0] bsram_sp_bugs_dbg;
bsram_test #(.FAM(`BSRAM_FAM_SP),
	.CFG0(`BSRAM_CFG(8, 0, 0, 2, 0, 0, 0, 0)),
	.CFG1(`BSRAM_CFG(32, 1, 0, 2, 0, 0, 0, 0)),
	.CFG2(`BSRAM_CFG(32, 0, 0, 0, 0, 1, 0, 0))
) bsram_sp_bugs(.clk(clk), .rst(rst), .pass(bsram_sp_bugs_pass), .dbg(bsram_sp_bugs_dbg));
`endif
`ifdef HIL_bsram_sdp_bugs
// Known failures, in no batch: narrow SDP output with CE=0, 32-bit byte enables
wire [63:0] bsram_sdp_bugs_pass;
wire [255:0] bsram_sdp_bugs_dbg;
bsram_test #(.FAM(`BSRAM_FAM_SDP),
	.CFG0(`BSRAM_CFG(8, 0, 1, 0, 0, 0, 0, 0)),
	.CFG1(`BSRAM_CFG(9, 0, 0, 0, 0, 0, 0, 0)),
	.CFG2(`BSRAM_CFG(32, 0, 0, 0, 0, 1, 0, 0))
) bsram_sdp_bugs(.clk(clk), .rst(rst), .pass(bsram_sdp_bugs_pass), .dbg(bsram_sdp_bugs_dbg));
`endif
`ifdef HIL_bsram_dp_bugs
// Known failures, in no batch: nextpnr aborts on a narrow DP with READ_MODE 1 on both used ports
wire [63:0] bsram_dp_bugs_pass;
wire [255:0] bsram_dp_bugs_dbg;
bsram_test #(.FAM(`BSRAM_FAM_DP),
	.CFG0(`BSRAM_CFG(8, 1, 1, 1, 1, 0, 0, 0))
) bsram_dp_bugs(.clk(clk), .rst(rst), .pass(bsram_dp_bugs_pass), .dbg(bsram_dp_bugs_dbg));
`endif

// ---- Report rows ----
// Row (slot, i) of the report. A test owns a slot of 8 rows; the slot number
// only sets the print order, give a new test the next free one, up to 31.

`define ROW(slot, name, i, val) \
	(slot)*8 + (i): begin row_on = 1; row_name = name; row_num = i; row_val = val; end

reg [8:0] row;  // row[8]: all rows done, print the tick line
reg row_on;
reg [8*20-1:0] row_name;
reg [2:0] row_num;
reg [71:0] row_val;

always @* begin
	row_on = 0;
	row_name = 0;
	row_num = 0;
	row_val = 0;
	case (row)
`ifdef HIL_latch
	`ROW(0, "latch", 0, latch_pass)
`endif
`ifdef HIL_dsp_mult9x9
	`ROW(1, "dsp-mult9x9", 0, `DSP_OUT(mult9x9, 0))
	`ROW(1, "dsp-mult9x9", 1, `DSP_OUT(mult9x9, 1))
	`ROW(1, "dsp-mult9x9", 2, `DSP_OUT(mult9x9, 2))
	`ROW(1, "dsp-mult9x9", 3, `DSP_OUT(mult9x9, 3))
	`ROW(1, "dsp-mult9x9", 4, `DSP_OUT(mult9x9, 4))
`endif
`ifdef HIL_dsp_mult18x18
	`ROW(2, "dsp-mult18x18", 0, `DSP_OUT(mult18x18, 0))
	`ROW(2, "dsp-mult18x18", 1, `DSP_OUT(mult18x18, 1))
	`ROW(2, "dsp-mult18x18", 2, `DSP_OUT(mult18x18, 2))
	`ROW(2, "dsp-mult18x18", 3, `DSP_OUT(mult18x18, 3))
	`ROW(2, "dsp-mult18x18", 4, `DSP_OUT(mult18x18, 4))
`endif
`ifdef HIL_dsp_mult36x36
	// 72-bit products, the top byte in the next output
	`ROW(3, "dsp-mult36x36", 0, {mult36x36[64+:8], mult36x36[0+:64]})
	`ROW(3, "dsp-mult36x36", 1, {mult36x36[192+:8], mult36x36[128+:64]})
`endif
`ifdef HIL_dsp_padd9
	`ROW(4, "dsp-padd9", 0, `DSP_OUT(padd9, 0))
	`ROW(4, "dsp-padd9", 1, `DSP_OUT(padd9, 1))
	`ROW(4, "dsp-padd9", 2, `DSP_OUT(padd9, 2))
	`ROW(4, "dsp-padd9", 3, `DSP_OUT(padd9, 3))
	`ROW(4, "dsp-padd9", 4, `DSP_OUT(padd9, 4))
`endif
`ifdef HIL_dsp_padd18
	`ROW(5, "dsp-padd18", 0, `DSP_OUT(padd18, 0))
	`ROW(5, "dsp-padd18", 1, `DSP_OUT(padd18, 1))
	`ROW(5, "dsp-padd18", 2, `DSP_OUT(padd18, 2))
	`ROW(5, "dsp-padd18", 3, `DSP_OUT(padd18, 3))
	`ROW(5, "dsp-padd18", 4, `DSP_OUT(padd18, 4))
`endif
`ifdef HIL_dsp_multalu18x18
	`ROW(6, "dsp-multalu18x18", 0, `DSP_OUT(multalu18x18, 0))
	`ROW(6, "dsp-multalu18x18", 1, `DSP_OUT(multalu18x18, 1))
	`ROW(6, "dsp-multalu18x18", 2, `DSP_OUT(multalu18x18, 2))
	`ROW(6, "dsp-multalu18x18", 3, `DSP_OUT(multalu18x18, 3))
	`ROW(6, "dsp-multalu18x18", 4, `DSP_OUT(multalu18x18, 4))
`endif
`ifdef HIL_dsp_multalu36x18
	`ROW(7, "dsp-multalu36x18", 0, `DSP_OUT(multalu36x18, 0))
	`ROW(7, "dsp-multalu36x18", 1, `DSP_OUT(multalu36x18, 1))
	`ROW(7, "dsp-multalu36x18", 2, `DSP_OUT(multalu36x18, 2))
	`ROW(7, "dsp-multalu36x18", 3, `DSP_OUT(multalu36x18, 3))
	`ROW(7, "dsp-multalu36x18", 4, `DSP_OUT(multalu36x18, 4))
`endif
`ifdef HIL_dsp_multaddalu18x18
	`ROW(8, "dsp-multaddalu18x18", 0, `DSP_OUT(multaddalu18x18, 0))
	`ROW(8, "dsp-multaddalu18x18", 1, `DSP_OUT(multaddalu18x18, 1))
	`ROW(8, "dsp-multaddalu18x18", 2, `DSP_OUT(multaddalu18x18, 2))
	`ROW(8, "dsp-multaddalu18x18", 3, `DSP_OUT(multaddalu18x18, 3))
`endif
`ifdef HIL_dsp_alu54d
	`ROW(9, "dsp-alu54d", 0, `DSP_OUT(alu54d, 0))
	`ROW(9, "dsp-alu54d", 1, `DSP_OUT(alu54d, 1))
	`ROW(9, "dsp-alu54d", 2, `DSP_OUT(alu54d, 2))
`endif
`ifdef HIL_osc
	`ROW(10, "osc", 0, osc_pass)
`ifdef HIL_RAW
	`ROW(10, "osc", 1, osc_raw)
`endif
`endif
`ifdef HIL_clkdiv
	`ROW(11, "clkdiv", 0, clkdiv_pass)
`ifdef HIL_RAW
	`ROW(11, "clkdiv", 1, clkdiv_raw_rows[0+:64])
	`ROW(11, "clkdiv", 2, clkdiv_raw_rows[64+:64])
`endif
`endif
`ifdef HIL_dhcen
	`ROW(12, "dhcen", 0, dhcen_pass)
`ifdef HIL_RAW
	`ROW(12, "dhcen", 1, dhcen_raw)
`endif
`endif
`ifdef HIL_dqce
	`ROW(13, "dqce", 0, dqce_pass)
`ifdef HIL_RAW
	`ROW(13, "dqce", 1, dqce_raw)
`endif
`endif
`ifdef HIL_dcs
	`ROW(14, "dcs", 0, dcs_pass)
`ifdef HIL_RAW
	`ROW(14, "dcs", 1, dcs_raw)
`endif
`endif
`ifdef HIL_rpll
	`ROW(15, "rpll", 0, rpll_pass)
`ifdef HIL_RAW
	`ROW(15, "rpll", 1, rpll_raw)
`endif
`endif
`ifdef HIL_bsram_rom
	`ROW(16, "bsram-rom", 0, bsram_rom_pass)
`ifdef BSRAM_DEBUG
	`ROW(16, "bsram-rom", 1, bsram_rom_dbg[0+:64])
	`ROW(16, "bsram-rom", 2, bsram_rom_dbg[64+:64])
	`ROW(16, "bsram-rom", 3, bsram_rom_dbg[128+:64])
	`ROW(16, "bsram-rom", 4, bsram_rom_dbg[192+:64])
`endif
`endif
`ifdef HIL_bsram_rom2
	`ROW(17, "bsram-rom2", 0, bsram_rom2_pass)
`ifdef BSRAM_DEBUG
	`ROW(17, "bsram-rom2", 1, bsram_rom2_dbg[0+:64])
	`ROW(17, "bsram-rom2", 2, bsram_rom2_dbg[64+:64])
	`ROW(17, "bsram-rom2", 3, bsram_rom2_dbg[128+:64])
	`ROW(17, "bsram-rom2", 4, bsram_rom2_dbg[192+:64])
`endif
`endif
`ifdef HIL_bsram_sp
	`ROW(18, "bsram-sp", 0, bsram_sp_pass)
`ifdef BSRAM_DEBUG
	`ROW(18, "bsram-sp", 1, bsram_sp_dbg[0+:64])
	`ROW(18, "bsram-sp", 2, bsram_sp_dbg[64+:64])
	`ROW(18, "bsram-sp", 3, bsram_sp_dbg[128+:64])
	`ROW(18, "bsram-sp", 4, bsram_sp_dbg[192+:64])
`endif
`endif
`ifdef HIL_bsram_sp2
	`ROW(19, "bsram-sp2", 0, bsram_sp2_pass)
`ifdef BSRAM_DEBUG
	`ROW(19, "bsram-sp2", 1, bsram_sp2_dbg[0+:64])
	`ROW(19, "bsram-sp2", 2, bsram_sp2_dbg[64+:64])
	`ROW(19, "bsram-sp2", 3, bsram_sp2_dbg[128+:64])
	`ROW(19, "bsram-sp2", 4, bsram_sp2_dbg[192+:64])
`endif
`endif
`ifdef HIL_bsram_sdp
	`ROW(20, "bsram-sdp", 0, bsram_sdp_pass)
`ifdef BSRAM_DEBUG
	`ROW(20, "bsram-sdp", 1, bsram_sdp_dbg[0+:64])
	`ROW(20, "bsram-sdp", 2, bsram_sdp_dbg[64+:64])
	`ROW(20, "bsram-sdp", 3, bsram_sdp_dbg[128+:64])
	`ROW(20, "bsram-sdp", 4, bsram_sdp_dbg[192+:64])
`endif
`endif
`ifdef HIL_bsram_sdp2
	`ROW(21, "bsram-sdp2", 0, bsram_sdp2_pass)
`ifdef BSRAM_DEBUG
	`ROW(21, "bsram-sdp2", 1, bsram_sdp2_dbg[0+:64])
	`ROW(21, "bsram-sdp2", 2, bsram_sdp2_dbg[64+:64])
	`ROW(21, "bsram-sdp2", 3, bsram_sdp2_dbg[128+:64])
	`ROW(21, "bsram-sdp2", 4, bsram_sdp2_dbg[192+:64])
`endif
`endif
`ifdef HIL_bsram_dp
	`ROW(22, "bsram-dp", 0, bsram_dp_pass)
`ifdef BSRAM_DEBUG
	`ROW(22, "bsram-dp", 1, bsram_dp_dbg[0+:64])
	`ROW(22, "bsram-dp", 2, bsram_dp_dbg[64+:64])
	`ROW(22, "bsram-dp", 3, bsram_dp_dbg[128+:64])
	`ROW(22, "bsram-dp", 4, bsram_dp_dbg[192+:64])
`endif
`endif
`ifdef HIL_bsram_dp16
	`ROW(23, "bsram-dp16", 0, bsram_dp16_pass)
`ifdef BSRAM_DEBUG
	`ROW(23, "bsram-dp16", 1, bsram_dp16_dbg[0+:64])
	`ROW(23, "bsram-dp16", 2, bsram_dp16_dbg[64+:64])
	`ROW(23, "bsram-dp16", 3, bsram_dp16_dbg[128+:64])
	`ROW(23, "bsram-dp16", 4, bsram_dp16_dbg[192+:64])
`endif
`endif
`ifdef HIL_bsram_rom_bugs
	`ROW(24, "bsram-rom-bugs", 0, bsram_rom_bugs_pass)
`ifdef BSRAM_DEBUG
	`ROW(24, "bsram-rom-bugs", 1, bsram_rom_bugs_dbg[0+:64])
	`ROW(24, "bsram-rom-bugs", 2, bsram_rom_bugs_dbg[64+:64])
	`ROW(24, "bsram-rom-bugs", 3, bsram_rom_bugs_dbg[128+:64])
	`ROW(24, "bsram-rom-bugs", 4, bsram_rom_bugs_dbg[192+:64])
`endif
`endif
`ifdef HIL_bsram_sp_bugs
	`ROW(25, "bsram-sp-bugs", 0, bsram_sp_bugs_pass)
`ifdef BSRAM_DEBUG
	`ROW(25, "bsram-sp-bugs", 1, bsram_sp_bugs_dbg[0+:64])
	`ROW(25, "bsram-sp-bugs", 2, bsram_sp_bugs_dbg[64+:64])
	`ROW(25, "bsram-sp-bugs", 3, bsram_sp_bugs_dbg[128+:64])
`endif
`endif
`ifdef HIL_bsram_sdp_bugs
	`ROW(26, "bsram-sdp-bugs", 0, bsram_sdp_bugs_pass)
`ifdef BSRAM_DEBUG
	`ROW(26, "bsram-sdp-bugs", 1, bsram_sdp_bugs_dbg[0+:64])
	`ROW(26, "bsram-sdp-bugs", 2, bsram_sdp_bugs_dbg[64+:64])
	`ROW(26, "bsram-sdp-bugs", 3, bsram_sdp_bugs_dbg[128+:64])
`endif
`endif
`ifdef HIL_bsram_dp_bugs
	`ROW(27, "bsram-dp-bugs", 0, bsram_dp_bugs_pass)
`ifdef BSRAM_DEBUG
	`ROW(27, "bsram-dp-bugs", 1, bsram_dp_bugs_dbg[0+:64])
`endif
`endif
	default: ;
	endcase
end

// ---- Reporter ----

`ifdef HIL_SMALL
// Boards that only build the tests (no UART, too small for the reporter):
// fold the rows into TXD so that nothing is optimised away.
reg tx_fold;
always @(posedge clk) begin
	row <= rst ? 9'd0 : row + 1;
	dsp_clk <= row[8];
	tx_fold <= ^{row_on, row_val};
end
assign TXD = tx_fold;
`else
wire uart_ready;
reg uart_valid;
reg [7:0] uart_data;

corescore_emitter_uart #(
	.clk_freq_hz(`CPU_FREQ * 1000000),
	.baud_rate(115200)
) uart (
	.i_clk(clk),
	.i_rst(rst),
	.i_data(uart_data),
	.i_valid(uart_valid),
	.o_ready(uart_ready),
	.o_uart_tx(TXD)
);

function [7:0] hex(input [3:0] v);
	hex = v < 10 ? "0" + v : "a" - 10 + v;
endfunction

reg [8*18-1:0] row_hex;
integer k;
always @*
	for (k = 0; k < 18; k = k + 1)
		row_hex[8*k +: 8] = hex(row_val[4*k +: 4]);

// The line being sent, first character in the top byte. Strings are padded
// with leading NULs, which are skipped.
localparam LINE = 46;
reg [8*LINE-1:0] line;
reg [5:0] left;
wire [7:0] head = line[8*LINE-1 -: 8];

// A quarter second before each tick line, so that a capture started just
// after the upload cannot miss the first tick and miscount the accumulators.
localparam PAUSE = `CPU_FREQ * 250000;
reg [23:0] pause;

always @(posedge clk) begin
	uart_valid <= 1'b0;
	dsp_clk <= 1'b0;

	if (rst) begin
		row <= 0;
		left <= 0;
		pause <= 0;
	end else if (left) begin
		if (head == 0 || (uart_ready && !uart_valid)) begin
			uart_data <= head;
			uart_valid <= head != 0;
			line <= line << 8;
			left <= left - 1;
		end
	end else if (row[8]) begin
		if (pause != PAUSE) begin
			pause <= pause + 1;
		end else begin
			pause <= 0;
			line <= "--- tick ---\n";
			left <= LINE;
			row <= 0;
			dsp_clk <= 1'b1;
		end
	end else begin
		if (row_on) begin
			line <= {row_name, " ", "0" + row_num, " = 0x", row_hex, "\n"};
			left <= LINE;
		end
		row <= row + 1;
	end
end

`endif

endmodule
