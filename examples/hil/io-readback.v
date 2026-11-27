`default_nettype none

// I/O on a pad that reads itself back, with no loopback wire: a pad's input
// buffer sees the pad while its own output drives it. The pads are free pins
// with nothing attached (see the board CSTs), so every expected value comes
// from what the test drives or from the pad's pull, never from a capture.
// Design and measurements: doc/agent/hil-carry-pad.md, "Same-pin I/O".
//
// Read-back is compared only where the pad has been driven to the same value
// for two clocks, which leaves room for the round trip through the pad.

// ---- io-readback: IOBUF read-back, and the pull of a tristated pad ----
//
// One pad per pull mode (UP, DOWN, KEEPER), a nibble each, pad 0 lowest:
// [0] the pad never read wrong while driven, [1] it read a 1, [2] it read a 0,
// [3] its tristate windows read what the pull gives.
// The checks start 2^16 clocks after reset: the Primer 25K misreads for its
// first ~10k clocks (YosysHQ/apicula#681, tested by io-startup).
module io_readback_test (
	input wire clk,
	input wire rst,
	inout wire [2:0] pad,
	output wire [11:0] pass
);
	io_pull_pad #(.PULL("UP"))     up(.clk(clk), .rst(rst), .pad(pad[0]), .pass(pass[3:0]));
	io_pull_pad #(.PULL("DOWN"))   down(.clk(clk), .rst(rst), .pad(pad[1]), .pass(pass[7:4]));
	io_pull_pad #(.PULL("KEEPER")) keeper(.clk(clk), .rst(rst), .pad(pad[2]), .pass(pass[11:8]));
endmodule

// Eight phases of 2^20 clocks:
//   0, 5, 6, 7: drive a value that toggles every 8 clocks
//   1: drive 0    2: tristate, the "after 0" window
//   3: drive 1    4: tristate, the "after 1" window
// A window is the second half of its phase, 2^19 clocks (19 ms at 27 MHz)
// after release, so a pull has settled and a keeper has held that long.
// UP reads 1 in both windows, DOWN 0, KEEPER the value driven before. The pull
// bit needs one whole sequence, so that every window was seen.
// PULL must match the pad's PULL_MODE in the board CST.
module io_pull_pad #(
	parameter PULL = "UP"
) (
	input wire clk,
	input wire rst,
	inout wire pad,
	output wire [3:0] pass
);
	reg [22:0] t;
	wire [2:0] ph = t[22:20];

	// I keeps its value while the pad is released: if it changed together
	// with OEN, the pad could see the new I for a moment before OEN, and the
	// keeper would hold that instead.
	reg drv, oen;
	always @(posedge clk) begin
		t <= rst ? 23'd0 : t + 1'b1;
		oen <= ph == 2 || ph == 4;
		drv <= ph == 1 || ph == 2 ? 1'b0 : ph == 3 || ph == 4 ? 1'b1 : t[3];
	end

	wire in;
	IOBUF iob (.I(drv), .OEN(oen), .O(in), .IO(pad));

	// q, drv1, oen1 and the windows line up: all one clock after drv, oen
	reg q, drv1, drv2, oen1, oen2, win0, win1;
	reg warm, bad, one, zero, w0_1, w0_0, w1_1, w1_0, seq;
	always @(posedge clk) begin
		q <= in;
		drv1 <= drv;
		drv2 <= drv1;
		oen1 <= oen;
		oen2 <= oen1;
		win0 <= ph == 2 && t[19];
		win1 <= ph == 4 && t[19];
		if (rst)
			{warm, bad, one, zero, w0_1, w0_0, w1_1, w1_0, seq} <= 0;
		else begin
			if (t[16]) warm <= 1;
			if (warm && !oen1 && !oen2 && drv1 == drv2) begin
				if (q != drv1) bad <= 1;
				if (q) one <= 1; else zero <= 1;
			end
			if (warm && win0) begin
				if (q) w0_1 <= 1; else w0_0 <= 1;
			end
			if (warm && win1) begin
				if (q) w1_1 <= 1; else w1_0 <= 1;
			end
			if (&t) seq <= 1;
		end
	end

	// what the after-0 and after-1 windows read
	localparam E0 = PULL == "UP";
	localparam E1 = PULL == "UP" || PULL == "KEEPER";
	wire pull_ok = seq &&
		(E0 ? w0_1 && !w0_0 : w0_0 && !w0_1) &&
		(E1 ? w1_1 && !w1_0 : w1_0 && !w1_1);
	assign pass = {pull_ok, zero, one, !bad};
endmodule

// ---- io-startup: read-back from the first clock after reset ----
//
// The read-back check of io-readback on one driven pad, without the warm-up,
// so that YosysHQ/apicula#681 (wrong reads on the Primer 25K for ~10k clocks
// after start-up) has a test of its own.
// pass[0] the pad never read wrong, [1] it read a 1, [2] it read a 0.
module io_startup_test (
	input wire clk,
	input wire rst,
	inout wire pad,
	output wire [2:0] pass
);
	reg [3:0] t;
	always @(posedge clk)
		t <= rst ? 4'd0 : t + 1'b1;
	wire drv = t[3];

	wire in;
	IOBUF iob (.I(drv), .OEN(1'b0), .O(in), .IO(pad));

	reg q, drv1, drv2, bad, one, zero;
	always @(posedge clk) begin
		q <= in;
		drv1 <= drv;
		drv2 <= drv1;
		if (rst)
			{bad, one, zero} <= 0;
		else if (drv1 == drv2) begin
			if (q != drv1) bad <= 1;
			if (q) one <= 1; else zero <= 1;
		end
	end
	assign pass = {zero, one, !bad};
endmodule

// ---- io-ddr and io-ser4: a serialiser and a deserialiser on one pad ----
//
// N = 2: ODDR -> IOBUF -> IDDR, all on clk.
// N = 4: OSER4 -> IOBUF -> IDES4, FCLK = clk, PCLK = clk/2 from a fabric
// flip-flop (no CLKDIV: the clock-divider test keeps that to itself).
// Each PCLK the sender takes N fresh bits from an LFSR. The receiver does not
// know the latency or the bit order, so it tries every hypothesis: send order
// (D0 or D(N-1) first on the wire), receive order (Q0 or Q(N-1) holds the
// oldest bit) and the offset into the last 16*N bits sent. A hypothesis
// survives while the received word always matched. With a random stream only
// the true one survives; none means the pad lost the data.
// pass[0] the checks ran, [1] a hypothesis survived, [2] one with D0 sent
// first and Q0 the oldest bit survived: the order that vendor bitstreams of
// this test give on the Tang Nano 9K, 20K and Primer 25K.
// The checks start 2^16 clocks after reset.
module io_serdes_test #(
	parameter N = 2
) (
	input wire clk,
	input wire rst,
	inout wire pad,
	output wire [2:0] pass
);
	localparam W = 16 * N;         // history of the wire, in bits
	localparam OFFS = W - N + 1;   // offsets of an N-bit window into it

	// The fabric runs on clk alone, which is on a global clock wire: with
	// registers on the fabric PCLK, nextpnr reported hold violations from its
	// clock skew, and a 20K build lost its data once in three loads. PCLK
	// clocks only the I/O logic, and the fabric works one clk after each PCLK
	// rise: it sends the next word then, half a PCLK from the rise that loads
	// it (OSER4 loads D on PCLK's rising edge in the vendor's simulation
	// models), and reads the word IDES4 put out on that rise.
	wire pclk, take;
	generate if (N == 2) begin : one_clk
		assign pclk = clk;
		assign take = 1'b1;
	end else begin : div2
		reg pclk_r = 0;
		always @(posedge clk) pclk_r <= !pclk_r;
		assign pclk = pclk_r;
		assign take = pclk_r;
	end endgenerate

	reg [31:0] lfsr = 32'h1;
	always @(posedge clk)
		if (take) lfsr <= {lfsr[30:0], lfsr[31] ^ lfsr[21] ^ lfsr[1] ^ lfsr[0]};
	wire [N-1:0] d = lfsr[N-1:0];

	wire out_q, out_t, in;
	wire [N-1:0] q;
	generate if (N == 2) begin : ddr
		ODDR oddr (.D0(d[0]), .D1(d[1]), .TX(1'b0), .CLK(clk), .Q0(out_q), .Q1(out_t));
		IDDR iddr (.D(in), .CLK(clk), .Q0(q[0]), .Q1(q[1]));
	end else begin : ser4
		OSER4 oser (.D0(d[0]), .D1(d[1]), .D2(d[2]), .D3(d[3]), .TX0(1'b0), .TX1(1'b0),
			.FCLK(clk), .PCLK(pclk), .RESET(1'b0), .Q0(out_q), .Q1(out_t));
		IDES4 ides (.D(in), .FCLK(clk), .PCLK(pclk), .CALIB(1'b0), .RESET(1'b0),
			.Q0(q[0]), .Q1(q[1]), .Q2(q[2]), .Q3(q[3]));
	end endgenerate

	IOBUF iob (.I(out_q), .OEN(out_t), .O(in), .IO(pad));

	function [N-1:0] rev(input [N-1:0] v);
		integer k;
		for (k = 0; k < N; k = k + 1) rev[k] = v[N-1-k];
	endfunction

	// bit 0 of a history is the newest bit on the wire, so the bit at a
	// window's top is the oldest
	reg [W-1:0] hist_d0first, hist_dnfirst;
	reg [N-1:0] rx;
	always @(posedge clk)
		if (take) begin
			hist_d0first <= {hist_d0first[W-N-1:0], rev(d)};
			hist_dnfirst <= {hist_dnfirst[W-N-1:0], d};
			rx <= q;
		end

	reg [16:0] warm;
	always @(posedge clk)
		warm <= rst ? 17'd0 : warm[16] ? warm : warm + 1'b1;

	// hyp[k*OFFS + o]: k = 2*(D(N-1) first) + (Q(N-1) oldest), o = offset
	reg [4*OFFS-1:0] hyp;
	genvar o;
	generate for (o = 0; o < OFFS; o = o + 1) begin : off
		wire [N-1:0] w0 = hist_d0first[o +: N];
		wire [N-1:0] w1 = hist_dnfirst[o +: N];
		always @(posedge clk)
			if (rst) begin
				hyp[0*OFFS + o] <= 1'b1;
				hyp[1*OFFS + o] <= 1'b1;
				hyp[2*OFFS + o] <= 1'b1;
				hyp[3*OFFS + o] <= 1'b1;
			end else if (warm[16] && take) begin
				if (rev(rx) != w0) hyp[0*OFFS + o] <= 1'b0;
				if (rx != w0)      hyp[1*OFFS + o] <= 1'b0;
				if (rev(rx) != w1) hyp[2*OFFS + o] <= 1'b0;
				if (rx != w1)      hyp[3*OFFS + o] <= 1'b0;
			end
	end endgenerate

	assign pass = {|hyp[0 +: OFFS], |hyp, warm[16]};
endmodule
