`default_nettype none
/*
* GW5AT-60B has interesting clock structure:
*  . - unused space
*  f - fpga fabric (usual cells)
*  = - clock spine rows
*                        73
*                        V
*        ................fffffffffffffffff      -+
*        ................fffffffffffffffff       |
*        ................fffffffffffffffff       |
*        ................================= <9    |
*        ................fffffffffffffffff       |  TOP
*        ................fffffffffffffffff       |
*        ................fffffffffffffffff       |
*        ................fffffffffffffffff       |
*    28> ================................. <28   |
*        ffffffffffffffff.================ <29   |
*        ffffffffffffffff.ffffffffffffffff      -+ <37
*        ffffffffffffffff.ffffffffffffffff       |
*    47> ================.================       |
*        ffffffffffffffff.ffffffffffffffff       |  BOTTOM
*        ffffffffffffffff.ffffffffffffffff       |
*    65> ================.================       |
*        ffffffffffffffff.ffffffffffffffff      -+
*
* We have 16 LEDs on the PMOD, so we place a pair of DFFREs in each area of
* interest. We don't care where the counter flip-flops are located.
* LED 16 is used as clock tick indicator.

* DFFRE, because UG303-1.0E states that only four types of flip-flops are
* supported — and a simple DFF isn't one of them; the last thing we need in a test
* example is surprises like that.
*/

module top(input wire clk, input wire resetn, output wire [15:0]led);
wire spec_tick_hz;
wire rst = !(`INV_BTN ^ resetn);

localparam HZ_PRESC = 16_000_000,
		HZ_SIZE = $clog2(HZ_PRESC);

reg [HZ_SIZE-1:0]  hertz_cpt;
wire [HZ_SIZE-1:0]  hertz_cpt_d = hertz_cpt - 1'b1;

always @(posedge clk) begin
	if (spec_tick_hz) begin
		hertz_cpt <= HZ_PRESC;
	end else begin
		hertz_cpt <= hertz_cpt_d;
	end
end

assign spec_tick_hz = (hertz_cpt == 0);

wire [15:0] ctr_q;

// bottom left 0
(* BEL="X1Y71/DFF0" *)
DFFSE r0(
	.D(ctr_q[14]),
	.Q(ctr_q[0]),
	.CE(1'b1),
	.SET(rst),
	.CLK(spec_tick_hz)
);

(* BEL="X72Y71/DFF0" *)
DFFRE r1(
	.D(ctr_q[0]),
	.Q(ctr_q[1]),
	.CE(1'b1),
	.RESET(rst),
	.CLK(spec_tick_hz)
);

// bottom left 1
(* BEL="X2Y48/DFF1" *)
DFFRE r2(
	.D(ctr_q[1]),
	.Q(ctr_q[2]),
	.CE(1'b1),
	.RESET(rst),
	.CLK(spec_tick_hz)
);

(* BEL="X72Y48/DFF2" *)
DFFRE r3(
	.D(ctr_q[2]),
	.Q(ctr_q[3]),
	.CE(1'b1),
	.RESET(rst),
	.CLK(spec_tick_hz)
);

// bottom right 0
(* BEL="X74Y71/DFF3" *)
DFFRE r4(
	.D(ctr_q[3]),
	.Q(ctr_q[4]),
	.CE(1'b1),
	.RESET(rst),
	.CLK(spec_tick_hz)
);

(* BEL="X145Y71/DFF4" *)
DFFRE r5(
	.D(ctr_q[4]),
	.Q(ctr_q[5]),
	.CE(1'b1),
	.RESET(rst),
	.CLK(spec_tick_hz)
);

// bottom right 0
(* BEL="X74Y40/DFF5" *)
DFFRE r6(
	.D(ctr_q[5]),
	.Q(ctr_q[6]),
	.CE(1'b1),
	.RESET(rst),
	.CLK(spec_tick_hz)
);

(* BEL="X145Y40/DFF0" *)
DFFRE r7(
	.D(ctr_q[6]),
	.Q(ctr_q[7]),
	.CE(1'b1),
	.RESET(rst),
	.CLK(spec_tick_hz)
);

// top left
(* BEL="X3Y36/DFF7" *)
DFFRE r8(
	.D(ctr_q[7]),
	.Q(ctr_q[8]),
	.CE(1'b1),
	.RESET(rst),
	.CLK(spec_tick_hz)
);

(* BEL="X72Y36/DFF2" *)
DFFRE r9(
	.D(ctr_q[8]),
	.Q(ctr_q[9]),
	.CE(1'b1),
	.RESET(rst),
	.CLK(spec_tick_hz)
);

// top upper right 
(* BEL="X74Y11/DFF3" *)
DFFRE r10(
	.D(ctr_q[9]),
	.Q(ctr_q[10]),
	.CE(1'b1),
	.RESET(rst),
	.CLK(spec_tick_hz)
);

(* BEL="X95Y17/DFF4" *)
DFFRE r11(
	.D(ctr_q[10]),
	.Q(ctr_q[11]),
	.CE(1'b1),
	.RESET(rst),
	.CLK(spec_tick_hz)
);

(* BEL="X74Y21/DFF5" *)
DFFRE r12(
	.D(ctr_q[11]),
	.Q(ctr_q[12]),
	.CE(1'b1),
	.RESET(rst),
	.CLK(spec_tick_hz)
);

// top lower right
(* BEL="X130Y26/DFF6" *)
DFFRE r13(
	.D(ctr_q[12]),
	.Q(ctr_q[13]),
	.CE(1'b1),
	.RESET(rst),
	.CLK(spec_tick_hz)
);

(* BEL="X74Y30/DFF7" *)
DFFRE r14(
	.D(ctr_q[13]),
	.Q(ctr_q[14]),
	.CE(1'b1),
	.RESET(rst),
	.CLK(spec_tick_hz)
);

assign led = ~{|hertz_cpt[HZ_SIZE - 1: HZ_SIZE - 2], ctr_q[14:0]};
endmodule

