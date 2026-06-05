/* Using an oscilloscope you can see on pins tlvds_p and tlvds_n the signal with changing polarity.
* You can also use a 100 Ohm resistor and two LEDs connected in opposite directions between these pins.
*/
module top (
    input clk,
    output tlvds_p,
    output tlvds_n,
	input key_i
);

wire key = key_i ^ `INV_BTN;
reg [24:0] ctr_q;
wire [24:0] ctr_d;
wire i_tick;

// Sequential code (flip-flop)
always @(posedge clk)
    ctr_q <= ctr_d;

// Combinational code (boolean logic)
assign ctr_d = ctr_q + 1'b1;
assign i_tick = |ctr_q[24:23];

TLVDS_TBUF diff_buf(
		.OEN(~key),
        .O(tlvds_p),
        .OB(tlvds_n),
        .I(i_tick)
    );

endmodule

