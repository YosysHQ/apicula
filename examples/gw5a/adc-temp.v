`default_nettype none
// ----------------------------------------------------------
// -- We use two PMOD-LEDx8 to show the operation of the ADC with an internal
// -- thermometer as the signal source. The result is displayed on the LEDs.
// -- According to the documentation, the number should be divided by 4.
// -- We do not do this automatically because the chip temperature changes
// -- slowly and without fluctuations in the lower bits, it is not interesting to
// -- observe the operation of the ADC.
// -- The two most significant bits are reserved for displaying the FSM state.
// ----------------------------------------------------------

module top(
    input clk,
    input rst_i,
    output [7:0] rled,  // right LED PMOD
    output [7:0] mled   // middle LED PMOD
);

    reg adcen;
    wire adcrdy;
    reg adcreqi;
    wire [13:0] adcvalue;
    reg [13:0] read_value;

    assign {mled, rled} = ~{state[2:1], read_value};


    // **********************************************************
    // **  RESET
    // **********************************************************
    reg init_reset_cnt = 1;
    reg [7:0] reset_cnt = 0;
    wire reset_n = &reset_cnt;
    wire need_reset;
    assign need_reset = !(rst_i ^ `INV_BTN);

    always @(posedge clk) begin
        if (need_reset) begin 
            reset_cnt <= 0;
        end else begin
            reset_cnt <= reset_cnt + !reset_n;
        end
    end

    ADC adc(
        .ADCRDY(adcrdy), //output adcrdy
        .ADCVALUE(adcvalue), //output [13:0] adcvalue
        .MDRP_RDATA(), //output [7:0] mdrp_rdata
        .VSENCTL(3'b000), //input [2:0] vsenctl
        .ADCEN(adcen), //input adcen
        .CLK(1'b0), //input clk
        .DRSTN(reset_n), //input drstn
        .ADCREQI(adcreqi), //input adcreqi
        .ADCMODE(1'b0), //input adcmode
        .MDRP_CLK(1'b0), //input mdrp_clk
        .MDRP_WDATA(8'h0), //input [7:0] mdrp_wdata
        .MDRP_A_INC(1'b0), //input mdrp_a_inc
        .MDRP_OPCODE(2'b00) //input [1:0] mdrp_opcode
    );    
    defparam adc.CLK_SEL = 1'b0;
    defparam adc.DIV_CTL = 2'd0;
    defparam adc.BUF_EN = 12'b000000000000;
    defparam adc.BUF_BK0_VREF_EN = 1'b0;
    defparam adc.BUF_BK1_VREF_EN = 1'b0;
    defparam adc.BUF_BK2_VREF_EN = 1'b0;
    defparam adc.BUF_BK3_VREF_EN = 1'b0;
    defparam adc.BUF_BK4_VREF_EN = 1'b0;
    defparam adc.BUF_BK5_VREF_EN = 1'b0;
    defparam adc.BUF_BK6_VREF_EN = 1'b0;
    defparam adc.BUF_BK7_VREF_EN = 1'b0;
    defparam adc.CSR_ADC_MODE = 1'b0;
    defparam adc.CSR_VSEN_CTRL = 3'd0;
    defparam adc.CSR_SAMPLE_CNT_SEL = 3'd4;
    defparam adc.CSR_RATE_CHANGE_CTRL = 3'd4;
    defparam adc.CSR_FSCAL = 10'd730;
    defparam adc.CSR_OFFSET = -12'd1180;


    // pause between measurements
    localparam PAUSE = 50_000_000 / 2;
    localparam PAUSE_HIGH = $clog2(PAUSE) - 1;
    reg [PAUSE_HIGH:0] measure_pause;

    // request pusle 10 ADC cycles
    localparam REQ_PULSE = 10 * 50_000_000 / 2_500_000;
    localparam REQ_PULSE_HIGH = $clog2(REQ_PULSE) - 1;
    reg [REQ_PULSE_HIGH:0] req_pulse;

    // states
    reg [2:0] state;
    localparam s_idle     = 0;
    localparam s_enable   = 1;
    localparam s_enable_0 = 2;
    localparam s_req      = 3;
    localparam s_read     = 4;

    always @(posedge clk) begin
        if (!reset_n) begin
            adcen <= 1'b1;
            adcreqi <= 1'b0;
            
            // pause between measurements
            measure_pause <= PAUSE;
            state <= s_idle;
        end else begin
            case(state)
                // periodic measurement
                s_idle: begin
                    if (measure_pause) begin
                        measure_pause <= measure_pause - 1'b1;
                    end else begin
                        measure_pause <= PAUSE;
                        state <= s_enable;
                    end
                end
                // pause before send request
                s_enable: begin 
                    state <= s_enable_0;
                end
                s_enable_0: begin 
                    adcreqi <= 1'b1;
                    req_pulse <= REQ_PULSE;
                    state <= s_req; 
                end
                
                // pause after request
                s_req: begin
                    if (req_pulse) begin
                        req_pulse <= req_pulse - 1'b1;
                    end else begin
                        if (!adcrdy) begin
                            adcreqi <= 1'b0;
                            state <= s_read;
                        end
                    end
                end
                // read data
                s_read: begin
                    if (adcrdy) begin
                        read_value <= adcvalue;
                        state <= s_idle;
                    end
                end
                default:
                    state <= s_idle;
            endcase
        end
    end

endmodule
// vim: set et sw=4 ts=4:
