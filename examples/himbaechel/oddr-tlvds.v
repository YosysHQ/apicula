/* Using an oscilloscope you can see on pins tlvds_p and tlvds_n the signal with changing polarity.
* You can also use a 100 Ohm resistor and two LEDs connected in opposite directions between these pins.
* ODDR needs 4 clock cycles to start working, so be patient:)
*/
module top (
    input clk,
	input key_i,
    output tlvds_p,
    output tlvds_n
);

wire key = key_i ^ `INV_BTN;
reg [24:0] ctr_q;
wire [24:0] ctr_d;
wire i_tick;
wire w_ddr;

// Sequential code (flip-flop)
always @(posedge clk)
    ctr_q <= ctr_d;

// Combinational code (boolean logic)
assign ctr_d = ctr_q + 1'b1;
assign i_tick = |ctr_q[24:23];

wire w_oen;

ODDR oddr_0(
	.D0(1'b0),
	.D1(1'b1),
	.CLK(i_tick),
	.Q0(w_ddr),
	.Q1(w_oen),
	.TX(~key)
);

TLVDS_TBUF diff_buf(
		.OEN(w_oen),
        .O(tlvds_p),
        .OB(tlvds_n),
        .I(w_ddr)
    );

endmodule

