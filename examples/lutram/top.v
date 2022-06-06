// Top level of lutram test 
//
// A PRBS generator is used to write random bits into the RAM
// and checks if the resulting data out is the same.
// 
// For each error, a counter is incremented. The counter is displayed
// on the LEDs of the TEC0117 board.
//
// Author: Niels A. Moseley, n.a.moseley@moseleyinstruments.com
//

`default_nettype none

module top(clk, led, rst);

    // inputs
    input wire  clk;        // clock 12 MHz
    input wire  rst;

    wire dout;
    reg  wre = 0;
    wire din;
    wire random_bit;
    
    reg next_bit        = 0;
    reg [3:0] address   = 0;
    reg [1:0] state     = 0;
    reg [23:0] blinkCounter = 0;

    // outputs
    output reg [7:0] led = 0;  // leds for debugging

    // test state machine
    always @(posedge clk)
    begin
        next_bit <= 0;
        wre <= 0;
        if (rst == 0)
        begin
            blinkCounter <= 0;
            led[6:0]     <= 0;
        end
        else
        begin
            blinkCounter <= blinkCounter + 1;
            case(state)
                2'b00:  begin next_bit <= 1; address <= address + 1; end    /* setup for next test */
                2'b01:  begin wre <= 1; end                                 /* write bit */
                2'b10:  begin ; end
                2'b11:  
                    begin 
                        if (random_bit != dout)
                            led[6:0] <= led[6:0] + 1;
                    end                
            endcase
            state  <= state + 1;

        end

        led[7] <= blinkCounter[23];
    end

    PRBS7 prbs
    (
        .clk(clk),
        .next(next_bit),
        .out(random_bit)
    );

    LUTRAM16S1 ram
    (
        .clk(clk),
        .wre(wre),
        .ad(address),
        .di(random_bit),
        .do(dout)
    );

endmodule
