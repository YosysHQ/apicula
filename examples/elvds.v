/* Using an oscilloscope you can see on pins elvds_p and elvds_n the signal with changing polarity.
* You can also use a 100 Ohm resistor and two LEDs connected in opposite directions between these pins.
*/
module top (
    input clk,
    output elvds_p,
    output elvds_n,
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

ELVDS_OBUF diff_buf(
        .O(elvds_p),
        .OB(elvds_n),
        .I(i_tick)
    );

endmodule
