// pipelined CORDIC algorithm to calculate sin/cos pair from a given angle (0..1)
// Author: Niels A. Moseley
//


// one stage of the cordic iteration with registered outputs
module cordic_stage_16(clk, rst_n, x_in, y_in, angle_in, angle_adj, x_out, y_out, angle_out);
    parameter SHIFT = 1;

    // inputs
    input clk;
    input rst_n;
    input signed [16-1:0] x_in;
    input signed [16-1:0] y_in;
    input signed [16-1:0] angle_in;
    input signed [16-1:0] angle_adj;

    // outputs
    output reg signed [16-1:0] x_out;
    output reg signed [16-1:0] y_out;
    output reg signed [16-1:0] angle_out;

    // internal signal
    reg signed [16-1:0] new_x;
    reg signed [16-1:0] new_y;
    reg signed [16-1:0] new_angle;

    wire sign;
    wire signed [16-1:0] shifted_x;
    wire signed [16-1:0] shifted_y;

    assign sign = angle_in[16-1];  // angle sign bit
    assign shifted_x = x_in >>> SHIFT;
    assign shifted_y = y_in >>> SHIFT;

    always @(*)
    begin
        new_x = sign ? (x_in + shifted_y) : (x_in - shifted_y);
        new_y = sign ? (y_in - shifted_x) : (y_in + shifted_x);
        new_angle = sign ? (angle_in + angle_adj) : (angle_in - angle_adj);
    end

    always @(posedge clk)
    begin
        if (rst_n == 1'b0)
        begin
            x_out <= 0;
            y_out <= 0;
            angle_out <= 0;
        end
        else begin
            x_out <= new_x;
            y_out <= new_y;
            angle_out <= new_angle;        
        end
    end

endmodule


module cordic_10_16(clk, rst_n, angle_in, cos_out, sin_out);

    // inputs
    input clk;
    input rst_n;
    input signed [16-1:0] angle_in;

    // outputs
    output signed [16-1:0] cos_out;
    output signed [16-1:0] sin_out;

    // internal signals
    reg signed [16-1:0] x_in; 
    reg signed [16-1:0] y_in;
    reg signed [16-1:0] z_in;

    wire signed [16-1:0] xbus [0:10-1];
    wire signed [16-1:0] ybus [0:10-1];
    wire signed [16-1:0] zbus [0:10-1];

    assign cos_out = xbus[10-1];
    assign sin_out = ybus[10-1];

    always @(*)
    begin
        case($unsigned(angle_in[16-1:16-2]))
            2'b00:
                begin
                    x_in <= 16'd19896;
                    y_in <= 0;
                    z_in <= angle_in;
                end
            2'b11:
                begin
                    x_in <= 16'd19896;
                    y_in <= 0;
                    z_in <= angle_in;
                end
            2'b01:
                begin
                    x_in <= 0;
                    y_in <= 16'd19896;
                    z_in <= $signed({2'b00, angle_in[16-3:0]});
                end
            2'b10:
                begin
                    x_in <= 0;
                    y_in <= -16'd19896;
                    z_in <= $signed({2'b11, angle_in[16-3:0]});
                end
        endcase
    end

    // generate instances of cordic_stage
        cordic_stage_16 #(0) stage0(clk, rst_n, x_in, y_in, z_in, 16'sd8192, xbus[0], ybus[0], zbus[0]);
    cordic_stage_16 #(1) stage1(clk, rst_n, xbus[0], ybus[0], zbus[0], 16'sd4836, xbus[1], ybus[1], zbus[1]);
    cordic_stage_16 #(2) stage2(clk, rst_n, xbus[1], ybus[1], zbus[1], 16'sd2555, xbus[2], ybus[2], zbus[2]);
    cordic_stage_16 #(3) stage3(clk, rst_n, xbus[2], ybus[2], zbus[2], 16'sd1297, xbus[3], ybus[3], zbus[3]);
    cordic_stage_16 #(4) stage4(clk, rst_n, xbus[3], ybus[3], zbus[3], 16'sd651, xbus[4], ybus[4], zbus[4]);
    cordic_stage_16 #(5) stage5(clk, rst_n, xbus[4], ybus[4], zbus[4], 16'sd326, xbus[5], ybus[5], zbus[5]);
    cordic_stage_16 #(6) stage6(clk, rst_n, xbus[5], ybus[5], zbus[5], 16'sd163, xbus[6], ybus[6], zbus[6]);
    cordic_stage_16 #(7) stage7(clk, rst_n, xbus[6], ybus[6], zbus[6], 16'sd81, xbus[7], ybus[7], zbus[7]);
    cordic_stage_16 #(8) stage8(clk, rst_n, xbus[7], ybus[7], zbus[7], 16'sd41, xbus[8], ybus[8], zbus[8]);
    cordic_stage_16 #(9) stage9(clk, rst_n, xbus[8], ybus[8], zbus[8], 16'sd20, xbus[9], ybus[9], zbus[9]);


endmodule
