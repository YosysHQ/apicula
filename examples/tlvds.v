/* Using an oscilloscope you can see on pins tlvds_p and tlvds_n the signal with changing polarity.
* You can also use a 100 Ohm resistor and two LEDs connected in opposite directions between these pins.
*/
`define LEDS_NR 3
`define INV_BTN 0
module top (
    input clk,
    input tlvds_p,
    input tlvds_n,
	output [2:0] led
);

reg [24:0] ctr_q;
wire [24:0] ctr_d;
wire i_tick;

// Sequential code (flip-flop)
always @(posedge clk)
    ctr_q <= ctr_d;

// Combinational code (boolean logic)
assign ctr_d = ctr_q + 1'b1;
assign i_tick = |ctr_q[24:23];

TLVDS_IBUF diff_buf(
        .I(tlvds_p),
        .IB(tlvds_n),
        .O(led[0])
    );

endmodule

