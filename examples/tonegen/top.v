// Top level of signal generator
//
// Author: Niels A. Moseley, n.a.moseley@moseleyinstruments.com
//

module top(clk, rst_n, sd_out, led);

    // inputs
    input   clk;        // clock 12 MHz
    input   rst_n;      // synchronous reset, active low

    // outputs
    output  sd_out;     // noise shaper output
    output  [7:0] led;  // leds for debugging

    reg [23:0]  phase_accu = 24'd0;

    // frequency = 12e6 / 2^32 * phase_inc

    reg [23:0]  phase_inc  = 24'd5592; // approximately 1kHz at 12MHz system clock
    wire signed [15:0] sinusoid;

    // phase accumulator to drive the cordic
    always @(posedge clk)
    begin
        phase_inc  <= phase_inc + 24'd1;
        phase_accu <= phase_accu + phase_inc[23:14];
    end;

    cordic_10_16 cordic
    (
        .clk(clk),
        .rst_n(rst_n),
        .angle_in(phase_accu[23:8]),
        .cos_out(sinusoid)
    );

    sddac dac
    (
        .clk(clk),
        .rst_n(rst_n),
        .sig_in( {sinusoid[15], sinusoid[15:1]} ),
        .sd_out(sd_out)
    );

    assign led = phase_accu[7:0];

endmodule
