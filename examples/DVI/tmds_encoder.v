// TMDS encoding as described in Digital Visual Interface (DVI) Revision 1.0
// 3.2.2 Encode algorithm Figure 3-5. T.M.D.S. Encode Algorithm

`default_nettype none

module tmds_encoder (
    input  wire       clk,
    input  wire       rst,
    input  wire       C0,
    input  wire       C1,
    input  wire       DE,
    input  wire [7:0] D,
    output reg  [9:0] q_out
);

localparam W_CNT = 8;

integer i;

reg signed [W_CNT-1:0] cnt;
reg signed [W_CNT-1:0] cnt_next;
reg [8:0]              q_m;
reg [9:0]              q_next;
reg [3:0]              N1D;
reg [3:0]              N1_qm;
reg [3:0]              N0_qm;

always @* begin

    N1D    = D[0] + D[1] + D[2] + D[3] + D[4] + D[5] + D[6] + D[7];
    q_m[0] = D[0];

    if ((N1D > 4) || (N1D == 4 && ~D[0])) begin
        q_m[8] = 1'b0;

        for (i = 0; i < 7; i = i + 1) begin
            q_m[i + 1] = q_m[i] ~^ D[i + 1];
        end

    end else begin
        q_m[8] = 1'b1;

        for (i = 0; i < 7; i = i + 1) begin
            q_m[i + 1] = q_m[i] ^ D[i + 1];
        end
    end

    N1_qm = q_m[0] + q_m[1] + q_m[2] + q_m[3] + q_m[4] + q_m[5] + q_m[6] + q_m[7];

    N0_qm = !q_m[0] + !q_m[1] + !q_m[2] + !q_m[3] + !q_m[4] + !q_m[5] + !q_m[6] + !q_m[7];

    if (DE) begin
        if ((cnt == 0) || (N1_qm == N0_qm)) begin
            q_next[9]   = ~q_m[8];
            q_next[8]   =  q_m[8];
            q_next[7:0] =  q_m[8] ? q_m[7:0] : ~q_m[7:0];

            if (~q_m[8]) begin
                cnt_next = cnt + $signed({{4{N0_qm[3]}}, N0_qm}) - $signed({{4{N1_qm[3]}},N1_qm});
            end else begin
                cnt_next = cnt + $signed({{4{N1_qm[3]}}, N1_qm}) - $signed({{4{N0_qm[3]}}, N0_qm});
            end

        end else begin
            if (((cnt > 0) && (N1_qm > N0_qm)) ||
                ((cnt < 0) && (N0_qm > N1_qm))) begin

                q_next[9]   = 1'b1;
                q_next[8]   = q_m[8];
                q_next[7:0] = ~q_m[7:0];
                cnt_next    = cnt + ($signed( {8{q_m  [8]}}) << 1)   +
                                     $signed({{4{N0_qm[3]}}, N0_qm}) -
                                     $signed({{4{N1_qm[3]}}, N1_qm});

            end else begin
                q_next[9]   = 1'b0;
                q_next[8]   = q_m[8];
                q_next[7:0] = q_m[7:0];
                cnt_next    = cnt - ($signed( {8{~q_m [8]}}) << 1)   +
                                     $signed({{4{N1_qm[3]}}, N1_qm}) -
                                     $signed({{4{N0_qm[3]}}, N0_qm});
            end
        end

    end else begin
        cnt_next = 0;

        case ({C1, C0})
            2'b00: q_next = 10'b1101010100;
            2'b01: q_next = 10'b0010101011;
            2'b10: q_next = 10'b0101010100;
            2'b11: q_next = 10'b1010101011;
        endcase
    end
end

always @(posedge clk) begin
    if (rst) begin
        cnt <= 0;
    end else begin
        cnt <= cnt_next;
    end
end

always @(posedge clk) begin
    q_out <= q_next;
end

endmodule

`resetall
