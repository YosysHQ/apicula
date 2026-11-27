`default_nettype none

// Carry chains (ALUs) checked by arithmetic. Only the arithmetic says what
// the answer is, so synthesis can not fold the checks away.
//
// CRT: YosysHQ/apicula#514's rad_min.v datapath. A counter sweeps 0..N-1 once,
// N = 2*3*5*7*11*13*17 = 510510; its residues cnt % p are rebuilt into
// sum(r_p * E_p) mod N, which the Chinese remainder theorem says is cnt
// again. Built with synth_gowin -nodsp (see the Makefile): with DSPs for the
// products it no longer exercised the ALUs #514 broke.
//
// Chunked add (YosysHQ/apicula#541): A + B in 2-bit chunks, the carry between
// chunks through a flip-flop, so that nothing merges them into one chain. Each
// chunk is a chain of its own, started by a carry-from-logic head; #541 broke
// such heads, and short chunks give many of them.
//
// Every register moves once in STEP clocks: the CRT paths are longer than a
// 27 MHz clock, and a slow path must not pass for a wrong carry.
//
// pass[0] CRT never mismatched, [1] chunked add never mismatched, [2] the
// sweep finished.
module carry_crt_test (
	input wire clk,
	input wire rst,
	output wire [2:0] pass
);
	localparam STEP = 16;
	reg [3:0] ph;
	always @(posedge clk)
		ph <= rst ? 4'd0 : ph + 1'b1;
	wire ce = rst || ph == STEP - 1;

	// ---- CRT ----
	localparam [18:0] E2 = 19'd255255, E3 = 19'd170170, E5 = 19'd306306,
		E7 = 19'd145860, E11 = 19'd46410, E13 = 19'd157080, E17 = 19'd450450;

	reg [18:0] cnt;
	reg done;
	always @(posedge clk)
		if (ce) begin
			if (rst) begin
				cnt <= 0;
				done <= 0;
			end else if (!done) begin
				if (cnt == 19'd510509) done <= 1;
				else cnt <= cnt + 1'b1;
			end
		end

	reg [0:0] r2;
	reg [1:0] r3;
	reg [2:0] r5, r7;
	reg [3:0] r11, r13;
	reg [4:0] r17;
	reg [18:0] cnt1;
	always @(posedge clk)
		if (ce) begin
			r2 <= cnt[0];
			r3 <= cnt % 3;
			r5 <= cnt % 5;
			r7 <= cnt % 7;
			r11 <= cnt % 11;
			r13 <= cnt % 13;
			r17 <= cnt % 17;
			cnt1 <= cnt;
		end

	wire [23:0] wsum = r2 * E2 + r3 * E3 + r5 * E5 + r7 * E7 + r11 * E11 +
		r13 * E13 + r17 * E17;
	// wsum < 16 * 510510: reduce by 16, 8, 4, 2 and 1 times N
	wire [23:0] q4 = wsum >= 24'd8168160 ? wsum - 24'd8168160 : wsum;
	wire [23:0] q3 = q4 >= 24'd4084080 ? q4 - 24'd4084080 : q4;
	wire [23:0] q2 = q3 >= 24'd2042040 ? q3 - 24'd2042040 : q3;
	wire [23:0] q1 = q2 >= 24'd1021020 ? q2 - 24'd1021020 : q2;
	wire [18:0] recon = q1 >= 24'd510510 ? q1[18:0] - 19'd510510 : q1[18:0];

	reg [18:0] recon2, cnt2;
	always @(posedge clk)
		if (ce) begin
			recon2 <= recon;
			cnt2 <= cnt1;
		end

	// ---- Chunked add ----
	reg [23:0] la, lb;
	always @(posedge clk)
		if (ce) begin
			if (rst) begin
				la <= 24'h123456;
				lb <= 24'hfedcba;
			end else begin
				// Galois LFSRs, x^24 + x^23 + x^22 + x^17 + 1
				la <= {1'b0, la[23:1]} ^ (la[0] ? 24'he10000 : 24'h0);
				lb <= {1'b0, lb[23:1]} ^ (lb[0] ? 24'he10000 : 24'h0);
			end
		end

	localparam W = 48, K = 2;
	wire [W-1:0] a = {la, lb}, b = {lb ^ 24'h5a5a5a, la};
	wire [W:0] sum = a + b;
	// The carries ripple through these, a chunk per clock. Over the LFSRs'
	// whole period no carry crosses more than 13 chunks, within a STEP.
	reg [W/K:1] c;
	wire [W/K:0] cin = {c, 1'b0};
	wire [W-1:0] csum;
	genvar j;
	generate
		for (j = 0; j < W / K; j = j + 1) begin : chunk
			wire [K:0] part = a[j*K +: K] + b[j*K +: K] + cin[j];
			always @(posedge clk) c[j+1] <= part[K];
			assign csum[j*K +: K] = part[K-1:0];
		end
	endgenerate

	// ---- Checks, two steps after reset so that the pipeline is full ----
	reg [1:0] warm;
	reg crt_bad, add_bad;
	always @(posedge clk)
		if (ce) begin
			if (rst) begin
				warm <= 0;
				crt_bad <= 0;
				add_bad <= 0;
			end else if (warm != 2) begin
				warm <= warm + 1'b1;
			end else begin
				if (recon2 != cnt2) crt_bad <= 1;
				if ({c[W/K], csum} != sum) add_bad <= 1;
			end
		end

	assign pass = {done, {2{warm == 2}} & ~{add_bad, crt_bad}};
endmodule
