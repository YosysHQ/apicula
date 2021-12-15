// Top level of signal generator
//
// Author: Niels A. Moseley, n.a.moseley@moseleyinstruments.com
//

module top(clk, rst, sd_out, led);

    // inputs
    input   clk;        // clock 12 MHz
    input   rst;      // synchronous reset, active low

    // outputs
    output  sd_out;     // noise shaper output
    output  [7:0] led;  // leds for debugging

    reg [23:0]  phase_accu;

    // ### BUGS BE HERE ###
    // frequency = 12e6 / 2^32 * phase_inc
    //reg [23:0]  phase_inc  = 24'd70; // (works) approximately 50 Hz at 12MHz system clock
    //reg [23:0]  phase_inc  = 24'd349;  // (works) approximately 250 Hz at 12MHz system clock
    reg [23:0]  phase_inc  = 24'd350;  // (fails?) approximately 250 Hz at 12MHz system clock
    //reg [23:0]  phase_inc  = 24'd351;  // (works) approximately 250 Hz at 12MHz system clock
    //reg [23:0]  phase_inc  = 24'd1398; // (works) approximately 1 kHz at 12MHz system clock
    //reg [23:0]  phase_inc  = 24'd6991; // (works) approximately 5 kHz at 12MHz system clock

    wire signed [15:0] sinusoid;

    // phase accumulator to drive the cordic
    always @(posedge clk)
    begin
        phase_accu <= phase_accu + phase_inc;
    end;

    cordic_10_16 cordic
    (
        .clk(clk),
        .rst_n(rst),
        .angle_in(phase_accu[23:8]),
        .cos_out(sinusoid)
    );

    sddac dac
    (
        .clk(clk),
        .rst_n(rst),
        .sig_in( {sinusoid[15], sinusoid[15:1]} ),
        .sd_out(sd_out)
    );

    assign led = phase_accu[7:0];

endmodule
