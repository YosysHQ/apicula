`default_nettype none

// BSRAM self-test: every primitive of a family (pROM/pROMX9, SP/SPX9,
// SDPB/SDPX9B, DPB/DPX9B) in up to four configurations, all driven in
// lockstep by one sequencer on the system clock.
//
// The memory contents follow pat(word index) ^ C, with C a constant per phase,
// so the expected value of every read is computed in the fabric from the
// address alone; the INIT_RAM parameters are generated from the same pat()
// at synthesis time. The phases:
//   init   read every word (all read ports), expect the INIT contents
//   write  write every word through port A (DP: then port B) and check
//          the write port's output during the write (WRITE_MODE 0/1/2)
//   read   read every word back
//   be     write with one byte enable per word (BEDYN configurations only;
//          the others must keep their contents), read back
//   script CE=0 holds the output, OCE=0 holds the pipeline register
//          (READ_MODE 1) or is ignored (READ_MODE 0), RESET clears it
// pass[15:0] per configuration: [7:0] port A, [15:8] port B; per port
//   bit 0 init, 1 read-during-write, 2 write/read back, 3 byte enables,
//   4 CE, 5 OCE, 6 RESET (each: checked at least once and never wrong),
//   bit 7 the sequence finished.
// Expected masks: pROM 0x80f1, SP 0x80ff, SDP 0xfd80, DP 0xffff, without
// bits 4 and 5 (and 12, 13) for the noce configurations.

// A configuration, see bsram_dut. w: BIT_WIDTH; rma/rmb, wma/wmb: READ_MODE
// and WRITE_MODE of port A/B (SDP: rmb is READ_MODE, SP/pROM: rma/wma);
// bedyn: byte enables driven by the fabric instead of tied high; oce0: OCE
// tied low (only with READ_MODE 0, as the old DPB16 example did); noce: skip
// the CE=0 and OCE=0 hold checks (pass bits 4 and 5 stay 0), for the
// configurations that fail them, see the *-bugs tests in hil.v.
`define BSRAM_CFG(w, rma, rmb, wma, wmb, bedyn, oce0, noce) \
	(((oce0) << 15) | ((bedyn) << 14) | ((wmb) << 12) | ((wma) << 10) | ((rmb) << 9) | ((rma) << 8) | \
	 ((noce) << 7) | (w))

`define BSRAM_FAM_ROM 0
`define BSRAM_FAM_SP  1
`define BSRAM_FAM_SDP 2
`define BSRAM_FAM_DP  3

// Sequencer to DUT bus
`define BS_A      13:0   // address (word index), shared by both ports
`define BS_CEA    14
`define BS_OCEA   15
`define BS_WREA   16
`define BS_RSTA   17
`define BS_CEB    18
`define BS_OCEB   19
`define BS_WREB   20
`define BS_RSTB   21
`define BS_WDSEL  23:22  // write data: 1 C1, 2 C2, 3 ~Cprev
`define BS_BEPH   24     // byte enable phase
`define BS_DONE   25
`define BS_DA0    45:26  // check descriptors {cat, sel, addr}: port A, READ_MODE 0
`define BS_DA1    65:46  //   port A, READ_MODE 1
`define BS_DB0    85:66  //   port B, READ_MODE 0
`define BS_DB1    105:86 //   port B, READ_MODE 1
`define BS_W      106

// Descriptor {cat[2:0], sel[2:0], addr[13:0]}: cat is the pass bit + 1
// (0 = no check), sel the expected data: 0 C0 (INIT), 1 C1, 2 C2, 3 contents
// after the byte-enable phase, 4 zero, 5 read-during-write of the C1 write
// (old C0), 6 of the C2 write (old C1)

`define BSRAM_INIT_ROWS \
	.INIT_RAM_00(init_row(0)), \
	.INIT_RAM_01(init_row(1)), \
	.INIT_RAM_02(init_row(2)), \
	.INIT_RAM_03(init_row(3)), \
	.INIT_RAM_04(init_row(4)), \
	.INIT_RAM_05(init_row(5)), \
	.INIT_RAM_06(init_row(6)), \
	.INIT_RAM_07(init_row(7)), \
	.INIT_RAM_08(init_row(8)), \
	.INIT_RAM_09(init_row(9)), \
	.INIT_RAM_0A(init_row(10)), \
	.INIT_RAM_0B(init_row(11)), \
	.INIT_RAM_0C(init_row(12)), \
	.INIT_RAM_0D(init_row(13)), \
	.INIT_RAM_0E(init_row(14)), \
	.INIT_RAM_0F(init_row(15)), \
	.INIT_RAM_10(init_row(16)), \
	.INIT_RAM_11(init_row(17)), \
	.INIT_RAM_12(init_row(18)), \
	.INIT_RAM_13(init_row(19)), \
	.INIT_RAM_14(init_row(20)), \
	.INIT_RAM_15(init_row(21)), \
	.INIT_RAM_16(init_row(22)), \
	.INIT_RAM_17(init_row(23)), \
	.INIT_RAM_18(init_row(24)), \
	.INIT_RAM_19(init_row(25)), \
	.INIT_RAM_1A(init_row(26)), \
	.INIT_RAM_1B(init_row(27)), \
	.INIT_RAM_1C(init_row(28)), \
	.INIT_RAM_1D(init_row(29)), \
	.INIT_RAM_1E(init_row(30)), \
	.INIT_RAM_1F(init_row(31)), \
	.INIT_RAM_20(init_row(32)), \
	.INIT_RAM_21(init_row(33)), \
	.INIT_RAM_22(init_row(34)), \
	.INIT_RAM_23(init_row(35)), \
	.INIT_RAM_24(init_row(36)), \
	.INIT_RAM_25(init_row(37)), \
	.INIT_RAM_26(init_row(38)), \
	.INIT_RAM_27(init_row(39)), \
	.INIT_RAM_28(init_row(40)), \
	.INIT_RAM_29(init_row(41)), \
	.INIT_RAM_2A(init_row(42)), \
	.INIT_RAM_2B(init_row(43)), \
	.INIT_RAM_2C(init_row(44)), \
	.INIT_RAM_2D(init_row(45)), \
	.INIT_RAM_2E(init_row(46)), \
	.INIT_RAM_2F(init_row(47)), \
	.INIT_RAM_30(init_row(48)), \
	.INIT_RAM_31(init_row(49)), \
	.INIT_RAM_32(init_row(50)), \
	.INIT_RAM_33(init_row(51)), \
	.INIT_RAM_34(init_row(52)), \
	.INIT_RAM_35(init_row(53)), \
	.INIT_RAM_36(init_row(54)), \
	.INIT_RAM_37(init_row(55)), \
	.INIT_RAM_38(init_row(56)), \
	.INIT_RAM_39(init_row(57)), \
	.INIT_RAM_3A(init_row(58)), \
	.INIT_RAM_3B(init_row(59)), \
	.INIT_RAM_3C(init_row(60)), \
	.INIT_RAM_3D(init_row(61)), \
	.INIT_RAM_3E(init_row(62)), \
	.INIT_RAM_3F(init_row(63))

`define BSRAM_C1 36'ha5a3cc369
`define BSRAM_C2 (~`BSRAM_C1)

module bsram_test #(
	parameter FAM = `BSRAM_FAM_SP,
	parameter [15:0] CFG0 = 0,
	parameter [15:0] CFG1 = 0,
	parameter [15:0] CFG2 = 0,
	parameter [15:0] CFG3 = 0
) (
	input wire clk,
	input wire rst,
	output wire [63:0] pass,
	output wire [255:0] dbg
);
	// The boards with 1152 LUTs (GW1N-1, GW1NZ-1, build only) get the first
	// two configurations, the old examples'.
`ifdef HIL_SMALL
	localparam SMALL = 1;
`else
	localparam SMALL = 0;
`endif
	wire [`BS_W-1:0] bus;
	bsram_seq #(.FAM(FAM)) seq(.clk(clk), .rst(rst), .bus(bus));

	generate
		if (CFG0[5:0]) bsram_dut #(.FAM(FAM), .CFG(CFG0)) d0(.clk(clk), .rst(rst), .bus(bus), .pass(pass[0+:16]), .dbg(dbg[0+:64]));
		else assign pass[0+:16] = 0, dbg[0+:64] = 0;
		if (CFG1[5:0]) bsram_dut #(.FAM(FAM), .CFG(CFG1)) d1(.clk(clk), .rst(rst), .bus(bus), .pass(pass[16+:16]), .dbg(dbg[64+:64]));
		else assign pass[16+:16] = 0, dbg[64+:64] = 0;
		if (CFG2[5:0] && !SMALL) bsram_dut #(.FAM(FAM), .CFG(CFG2)) d2(.clk(clk), .rst(rst), .bus(bus), .pass(pass[32+:16]), .dbg(dbg[128+:64]));
		else assign pass[32+:16] = 0, dbg[128+:64] = 0;
		if (CFG3[5:0] && !SMALL) bsram_dut #(.FAM(FAM), .CFG(CFG3)) d3(.clk(clk), .rst(rst), .bus(bus), .pass(pass[48+:16]), .dbg(dbg[192+:64]));
		else assign pass[48+:16] = 0, dbg[192+:64] = 0;
	endgenerate
endmodule

module bsram_seq #(
	parameter FAM = `BSRAM_FAM_SP
) (
	input wire clk,
	input wire rst,
	output reg [`BS_W-1:0] bus
);
	// Steps: R(sel, cat) read all, WA/WB write through port A/B, BE byte
	// enable write, S script, D done.
	localparam R = 0, WA = 1, WB = 2, BE = 3, S = 4, D = 5;
	localparam GAP = 8;    // idle cycles before each step, reading word 0
	localparam N = 16384;  // words swept: the deepest configuration (1 bit)

	reg [3:0] step;
	reg [14:0] cnt;
	reg [2:0] kind;
	reg [2:0] rsel, rcat, wsel;

	always @* begin
		kind = D; rsel = 0; rcat = 0; wsel = 0;
		if (FAM == `BSRAM_FAM_ROM)
			case (step)
			0: begin kind = R; rsel = 0; rcat = 1; end
			1: kind = S;
			default: ;
			endcase
		else if (FAM == `BSRAM_FAM_DP)
			case (step)
			0: begin kind = R; rsel = 0; rcat = 1; end
			1: begin kind = WA; wsel = 1; rsel = 5; end
			2: begin kind = R; rsel = 1; rcat = 3; end
			3: begin kind = WB; wsel = 2; rsel = 6; end
			4: begin kind = R; rsel = 2; rcat = 3; end
			5: begin kind = BE; wsel = 3; end
			6: begin kind = R; rsel = 3; rcat = 4; end
			7: kind = S;
			default: ;
			endcase
		else
			case (step)
			0: begin kind = R; rsel = 0; rcat = 1; end
			1: begin kind = WA; wsel = 1; rsel = 5; end
			2: begin kind = R; rsel = 1; rcat = 3; end
			3: begin kind = BE; wsel = 3; end
			4: begin kind = R; rsel = 3; rcat = 4; end
			5: kind = S;
			default: ;
			endcase
	end

	// Script for the read ports, after the sweeps. Entry c: controls of
	// cycle c and the expected output during cycle c (after edge c-1) for
	// READ_MODE 0 and 1. X, Y, Z, W differ in their low 9 bits; at width 1 the
	// data of X and Y (and of Z and W) is equal, so the hold checks prove nothing.
	localparam [13:0] X = 14'h0005, Y = 14'h00a3, Z = 14'h015a, W = 14'h01f0;
	wire [2:0] ssel = FAM == `BSRAM_FAM_ROM ? 3'd0 : 3'd3;
	reg [13:0] s_a;
	reg s_ce, s_oce, s_rst;
	reg [19:0] s_e0, s_e1;
	always @* begin
		s_a = W; s_ce = 0; s_oce = 1; s_rst = 0;
		s_e0 = 0; s_e1 = 0;
		case (cnt)
		GAP + 0: begin s_a = X; s_ce = 1; end
		GAP + 1: begin s_a = Y; s_ce = 1;            s_e0 = {3'd5, ssel, X}; end
		GAP + 2: begin s_a = Z; s_ce = 1; s_oce = 0; s_e0 = {3'd5, ssel, Y}; s_e1 = {3'd5, ssel, X}; end
		GAP + 3: begin          s_oce = 0;           s_e0 = {3'd6, ssel, Z}; s_e1 = {3'd6, ssel, X}; end
		GAP + 4: begin                               s_e0 = {3'd5, ssel, Z}; s_e1 = {3'd6, ssel, X}; end
		GAP + 5: begin                               s_e0 = {3'd5, ssel, Z}; s_e1 = {3'd5, ssel, Z}; end
		GAP + 6: begin s_ce = 1; s_rst = 1;          s_e0 = {3'd5, ssel, Z}; s_e1 = {3'd5, ssel, Z}; end
		GAP + 7: begin                               s_e0 = {3'd7, 3'd4, W}; s_e1 = {3'd7, 3'd4, W}; end
		default: ;
		endcase
	end

	wire last = kind == S ? cnt == GAP + 15 : cnt == GAP + N - 1;
	wire active = cnt >= GAP;
	wire [13:0] a = active ? cnt - GAP : 14'd0;

	wire rd_a = FAM != `BSRAM_FAM_SDP;  // ports with an output
	wire rd_b = FAM == `BSRAM_FAM_SDP || FAM == `BSRAM_FAM_DP;
	wire sp_b = FAM == `BSRAM_FAM_SDP;  // the script runs on port B only

	// Next cycle's operation
	reg [13:0] n_a;
	reg n_cea, n_wrea, n_ceb, n_wreb, n_ocea, n_oceb, n_rsta, n_rstb;
	reg [19:0] n_opa, n_opb;  // descriptor of this cycle's read
	reg [19:0] n_sa0, n_sa1, n_sb0, n_sb1;
	always @* begin
		n_a = a; n_cea = rd_a; n_ceb = rd_b; n_wrea = 0; n_wreb = 0;
		n_ocea = 1; n_oceb = 1; n_rsta = 0; n_rstb = 0;
		n_opa = 0; n_opb = 0;
		n_sa0 = 0; n_sa1 = 0; n_sb0 = 0; n_sb1 = 0;
		case (kind)
		R: if (active) begin
			if (rd_a) n_opa = {rcat, rsel, a};
			if (rd_b) n_opb = {rcat, rsel, a};
		end
		WA, BE: if (active) begin
			n_cea = 1; n_wrea = 1; n_ceb = 0;
			if (kind == WA && FAM != `BSRAM_FAM_SDP) n_opa = {3'd2, rsel, a};
		end
		WB: if (active) begin
			n_ceb = 1; n_wreb = 1; n_cea = 0;
			n_opb = {3'd2, rsel, a};
		end
		S: begin
			n_a = s_a;
			n_cea = rd_a && !sp_b && s_ce; n_ocea = s_oce; n_rsta = rd_a && !sp_b && s_rst;
			n_ceb = rd_b && s_ce; n_oceb = s_oce; n_rstb = rd_b && s_rst;
			if (rd_a && !sp_b) begin n_sa0 = s_e0; n_sa1 = s_e1; end
			if (rd_b) begin n_sb0 = s_e0; n_sb1 = s_e1; end
		end
		default: begin n_cea = 0; n_ceb = 0; end
		endcase
	end

	// The op of the current cycle, delayed into the descriptors
	reg [19:0] opa, opb;
	always @(posedge clk) begin
		if (rst) begin
			step <= 0;
			cnt <= 0;
			bus <= 0;
			opa <= 0;
			opb <= 0;
		end else begin
			if (kind != D) begin
				cnt <= last ? 0 : cnt + 1;
				if (last) step <= step + 1;
			end
			bus[`BS_A] <= n_a;
			bus[`BS_CEA] <= n_cea;
			bus[`BS_OCEA] <= n_ocea;
			bus[`BS_WREA] <= n_wrea;
			bus[`BS_RSTA] <= n_rsta;
			bus[`BS_CEB] <= n_ceb;
			bus[`BS_OCEB] <= n_oceb;
			bus[`BS_WREB] <= n_wreb;
			bus[`BS_RSTB] <= n_rstb;
			bus[`BS_WDSEL] <= wsel[1:0];
			bus[`BS_BEPH] <= kind == BE;
			bus[`BS_DONE] <= kind == D;
			opa <= n_opa;
			opb <= n_opb;
			if (kind == S) begin
				bus[`BS_DA0] <= n_sa0;
				bus[`BS_DA1] <= n_sa1;
				bus[`BS_DB0] <= n_sb0;
				bus[`BS_DB1] <= n_sb1;
			end else begin
				bus[`BS_DA0] <= opa;
				bus[`BS_DA1] <= bus[`BS_DA0];
				bus[`BS_DB0] <= opb;
				bus[`BS_DB1] <= bus[`BS_DB0];
			end
		end
	end
endmodule

module bsram_dut #(
	parameter FAM = `BSRAM_FAM_SP,
	parameter [15:0] CFG = 8
) (
	input wire clk,
	input wire rst,
	input wire [`BS_W-1:0] bus,
	output wire [15:0] pass,
	// with BSRAM_DEBUG, the first failure: {port B, cat, sel, addr, data read}
	output reg [63:0] dbg
);
	localparam W = CFG[5:0];
	localparam NOCE = CFG[7];
	localparam RMA = CFG[8];
	localparam RMB = CFG[9];
	localparam [1:0] WMA = CFG[11:10];
	localparam [1:0] WMB = CFG[13:12];
	localparam BEDYN = CFG[14];
	localparam OCE0 = CFG[15];

	localparam X9 = W == 9 || W == 18 || W == 36;
	localparam RB = X9 ? 288 : 256;          // bits per INIT_RAM row
	localparam S = W >= 32 ? 5 : W >= 16 ? 4 : W >= 8 ? 3 : W >= 4 ? 2 : W >= 2 ? 1 : 0;
	localparam AW = 14 - S;                  // word address bits
	localparam WPR = 256 >> S;               // words per row
	localparam LANES = W >= 32 ? 4 : W >= 16 ? 2 : 1;
	localparam LW = W / LANES;

	localparam [35:0] C1 = `BSRAM_C1;
	localparam [35:0] C2 = `BSRAM_C2;
	localparam [35:0] CPREV = FAM == `BSRAM_FAM_DP ? C2 : C1;

	// Test pattern of word k: each bit the XOR of three address bits, bit 0
	// the parity of the whole address, so that every address bit shows.
	function [35:0] pat(input [13:0] k);
		integer j;
		begin
			for (j = 0; j < 36; j = j + 1)
				pat[j] = k[(j * 5) % 14] ^ k[(j * 5 + 3) % 14] ^ k[(j * 3 + 8) % 14] ^ (j % 2);
			pat[0] = ^k;
		end
	endfunction

	function [RB-1:0] init_row(input integer r);
		integer j;
		reg [35:0] p;
		begin
			init_row = 0;
			for (j = 0; j < WPR; j = j + 1) begin
				p = pat(r * WPR + j);
				init_row[j * W +: W] = p[W-1:0];
			end
		end
	endfunction

	// Mask of the byte lane written in the byte-enable phase
	function [35:0] lane_mask(input [13:0] k);
		begin
			lane_mask = 0;
			if (BEDYN) begin
				if (LANES == 2) lane_mask = {LW{1'b1}} << (k[0] * LW);
				if (LANES == 4) lane_mask = {LW{1'b1}} << (k[1:0] * LW);
			end
		end
	endfunction

	function [35:0] expected(input [5:0] sel, input [13:0] addr, input [1:0] wm);
		reg [13:0] k;
		reg first;
		begin
			k = addr & ((1 << AW) - 1);
			first = (addr >> AW) == 0;
			// read-during-write: WRITE_MODE 0 keeps the word read before
			// the write step (word 0), 1 shows the new data, 2 the old
			if ((sel == 5 || sel == 6) && wm == 0) k = 0;
			case (sel)
			0: expected = pat(k);
			1: expected = pat(k) ^ C1;
			2: expected = pat(k) ^ C2;
			3: expected = pat(k) ^ CPREV ^ lane_mask(k);
			4: expected = 0;
			5: expected = pat(k) ^ (wm == 1 || (wm == 2 && !first) ? C1 : 0);
			6: expected = pat(k) ^ (wm == 1 || (wm == 2 && !first) ? C2 : C1);
			default: expected = 0;
			endcase
		end
	endfunction

	wire [13:0] k = bus[`BS_A] & ((1 << AW) - 1);
	wire [35:0] wd = pat(k) ^ (bus[`BS_WDSEL] == 1 ? C1 : bus[`BS_WDSEL] == 2 ? C2 : ~CPREV);
	wire [W-1:0] di = wd[W-1:0];
	wire beph = bus[`BS_BEPH];
	wire [3:0] be = !BEDYN ? 4'b1111 : !beph ? 4'b1111 : LANES == 4 ? 4'b0001 << k[1:0] : 4'b0001 << k[0];
	// Configurations with constant byte enables do not write in that phase
	wire wr_ok = !beph || BEDYN;
	wire [13:0] ad = W >= 32 ? {k[8:0], 1'b0, be[3:0]} :
	                 W >= 16 ? {k[9:0], 2'b00, be[1:0]} :
	                 k << S;
	// pROM: the byte enable bits low, as the old examples did. On GW2A-18C a
	// 32/36-bit pROM read word 0 as 0 in every build with them high; with them
	// low part of word 0 can still be wrong, see bsram-rom-bugs.
	wire [13:0] ad_rom = k << S;
	wire [13:0] ad_rd = W >= 32 ? {k[8:0], 5'b01111} : W >= 16 ? {k[9:0], 4'b0011} : k << S;

	wire cea = bus[`BS_CEA], ceb = bus[`BS_CEB];
	wire ocea = OCE0 ? 1'b0 : bus[`BS_OCEA];
	wire oceb = OCE0 ? 1'b0 : bus[`BS_OCEB];
	wire wrea = bus[`BS_WREA] && wr_ok;
	wire wreb = bus[`BS_WREB];
	wire rsta = bus[`BS_RSTA], rstb = bus[`BS_RSTB];

	wire [35:0] doa, dob;

	generate
	if (FAM == `BSRAM_FAM_ROM) begin
		wire [35:0] dout;
		if (X9) begin
			pROMX9 #(.READ_MODE(RMA), .BIT_WIDTH(W), .RESET_MODE("SYNC"), `BSRAM_INIT_ROWS)
			mem(.CLK(clk), .CE(cea), .OCE(ocea), .RESET(rsta), .AD(ad_rom), .DO(dout));
		end else begin
			pROM #(.READ_MODE(RMA), .BIT_WIDTH(W), .RESET_MODE("SYNC"), `BSRAM_INIT_ROWS)
			mem(.CLK(clk), .CE(cea), .OCE(ocea), .RESET(rsta), .AD(ad_rom), .DO(dout[31:0]));
		end
		assign doa = dout;
		assign dob = 0;
	end else if (FAM == `BSRAM_FAM_SP) begin
		wire [35:0] dout;
		wire [35:0] din = di;
		if (X9) begin
			SPX9 #(.READ_MODE(RMA), .WRITE_MODE(WMA), .BIT_WIDTH(W), .BLK_SEL(3'b000), .RESET_MODE("SYNC"), `BSRAM_INIT_ROWS)
			mem(.CLK(clk), .CE(cea), .OCE(ocea), .RESET(rsta), .WRE(wrea), .AD(ad), .BLKSEL(3'b000),
			    .DI(din), .DO(dout));
		end else begin
			SP #(.READ_MODE(RMA), .WRITE_MODE(WMA), .BIT_WIDTH(W), .BLK_SEL(3'b000), .RESET_MODE("SYNC"), `BSRAM_INIT_ROWS)
			mem(.CLK(clk), .CE(cea), .OCE(ocea), .RESET(rsta), .WRE(wrea), .AD(ad), .BLKSEL(3'b000),
			    .DI(din[31:0]), .DO(dout[31:0]));
		end
		assign doa = dout;
		assign dob = 0;
	end else if (FAM == `BSRAM_FAM_SDP) begin
		wire [35:0] dout;
		wire [35:0] din = di;
		// port A writes when CEA is high
		wire cew = cea && wrea;
		if (X9) begin
			SDPX9B #(.READ_MODE(RMB), .BIT_WIDTH_0(W), .BIT_WIDTH_1(W), .BLK_SEL_0(3'b000), .BLK_SEL_1(3'b000),
			         .RESET_MODE("SYNC"), `BSRAM_INIT_ROWS)
			mem(.CLKA(clk), .CEA(cew), .RESETA(1'b0), .ADA(ad), .DI(din), .BLKSELA(3'b000),
			    .CLKB(clk), .CEB(ceb), .RESETB(rstb), .OCE(oceb), .ADB(ad_rd), .DO(dout), .BLKSELB(3'b000));
		end else begin
			SDPB #(.READ_MODE(RMB), .BIT_WIDTH_0(W), .BIT_WIDTH_1(W), .BLK_SEL_0(3'b000), .BLK_SEL_1(3'b000),
			       .RESET_MODE("SYNC"), `BSRAM_INIT_ROWS)
			mem(.CLKA(clk), .CEA(cew), .RESETA(1'b0), .ADA(ad), .DI(din[31:0]), .BLKSELA(3'b000),
			    .CLKB(clk), .CEB(ceb), .RESETB(rstb), .OCE(oceb), .ADB(ad_rd), .DO(dout[31:0]), .BLKSELB(3'b000));
		end
		assign doa = 0;
		assign dob = dout;
	end else begin
		wire [17:0] douta, doutb;
		wire [17:0] din = di;
		// port B writes whole words only
		if (X9) begin
			DPX9B #(.READ_MODE0(RMA), .READ_MODE1(RMB), .WRITE_MODE0(WMA), .WRITE_MODE1(WMB),
			        .BIT_WIDTH_0(W), .BIT_WIDTH_1(W), .BLK_SEL_0(3'b000), .BLK_SEL_1(3'b000),
			        .RESET_MODE("SYNC"), `BSRAM_INIT_ROWS)
			mem(.CLKA(clk), .CEA(cea), .OCEA(ocea), .RESETA(rsta), .WREA(wrea), .ADA(ad), .DIA(din), .DOA(douta),
			    .BLKSELA(3'b000),
			    .CLKB(clk), .CEB(ceb), .OCEB(oceb), .RESETB(rstb), .WREB(wreb), .ADB(ad_rd), .DIB(din), .DOB(doutb),
			    .BLKSELB(3'b000));
		end else begin
			DPB #(.READ_MODE0(RMA), .READ_MODE1(RMB), .WRITE_MODE0(WMA), .WRITE_MODE1(WMB),
			      .BIT_WIDTH_0(W), .BIT_WIDTH_1(W), .BLK_SEL_0(3'b000), .BLK_SEL_1(3'b000),
			      .RESET_MODE("SYNC"), `BSRAM_INIT_ROWS)
			mem(.CLKA(clk), .CEA(cea), .OCEA(ocea), .RESETA(rsta), .WREA(wrea), .ADA(ad), .DIA(din[15:0]),
			    .DOA(douta[15:0]), .BLKSELA(3'b000),
			    .CLKB(clk), .CEB(ceb), .OCEB(oceb), .RESETB(rstb), .WREB(wreb), .ADB(ad_rd), .DIB(din[15:0]),
			    .DOB(doutb[15:0]), .BLKSELB(3'b000));
		end
		assign doa = douta;
		assign dob = doutb;
	end
	endgenerate

	// Checks: one per port
	wire [19:0] da = RMA ? bus[`BS_DA1] : bus[`BS_DA0];
	wire [19:0] db = RMB ? bus[`BS_DB1] : bus[`BS_DB0];
	wire [35:0] ea = expected(da[16:14], da[13:0], WMA);
	wire [35:0] eb = expected(db[16:14], db[13:0], WMB);
	// cat 5 and 6: the CE/OCE hold checks
	wire [2:0] cata = NOCE && (da[19:17] == 5 || da[19:17] == 6) ? 3'd0 : da[19:17];
	wire [2:0] catb = NOCE && (db[19:17] == 5 || db[19:17] == 6) ? 3'd0 : db[19:17];
	wire oka = doa[W-1:0] == ea[W-1:0];
	wire okb = dob[W-1:0] == eb[W-1:0];

	reg [6:0] seen_a, fail_a, seen_b, fail_b;
	always @(posedge clk) begin
		if (rst) begin
			seen_a <= 0; fail_a <= 0; seen_b <= 0; fail_b <= 0;
			dbg <= 0;
		end else begin
`ifdef BSRAM_DEBUG
			if (!dbg[63:60]) begin
				if (cata && !oka) dbg <= {1'b0, da, 7'b0, doa};
				else if (catb && !okb) dbg <= {1'b1, db, 7'b0, dob};
			end
`endif
			if (cata) begin
				seen_a[cata - 1] <= 1;
				if (!oka) fail_a[cata - 1] <= 1;
			end
			if (catb) begin
				seen_b[catb - 1] <= 1;
				if (!okb) fail_b[catb - 1] <= 1;
			end
		end
	end
	wire done = bus[`BS_DONE];
	assign pass = {done, seen_b & ~fail_b, done, seen_a & ~fail_a};
endmodule
