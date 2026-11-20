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
	default: ;
	endcase
end

// ---- Reporter ----

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

endmodule
