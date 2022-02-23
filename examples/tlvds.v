/* Using an oscilloscope you can see on pins 27, 28 the signal with changing polarity.
*/
module top (
    input clk,
    output [1:0]led
);

reg [25:0] ctr_q;
wire [25:0] ctr_d;
wire i_tick;

// Sequential code (flip-flop)
always @(posedge clk)
    ctr_q <= ctr_d;

// Combinational code (boolean logic)
assign ctr_d = ctr_q + 1'b1;
assign i_tick = ctr_q[25:25];

TLVDS_OBUF diff_buf(
        .O(led[1]),
        .OB(led[0]),
        .I(i_tick)
    );

endmodule

