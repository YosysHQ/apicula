module top(input clk, input din, output dout);
    reg [127:0] sr;
    always @(posedge clk) sr <= {sr[126:0], din};

    wire [23:0] p_comb, p_reg, p_pipe, p_oreg;
    wire [47:0] p_alu, p_addalu;
    wire [62:0] p_27x36;

    // all registers bypassed
    MULT12X12 m_comb (.A(sr[11:0]), .B(sr[23:12]), .CLK({1'b0, clk}), .CE(2'b11), .RESET(2'b00), .DOUT(p_comb));
    defparam m_comb.AREG_CLK = "BYPASS"; defparam m_comb.BREG_CLK = "BYPASS";
    defparam m_comb.PREG_CLK = "BYPASS"; defparam m_comb.OREG_CLK = "BYPASS";

    // input and output registers, pipeline bypassed
    MULT12X12 m_reg (.A(sr[23:12]), .B(sr[35:24]), .CLK({1'b0, clk}), .CE(2'b11), .RESET(2'b00), .DOUT(p_reg));
    defparam m_reg.AREG_CLK = "CLK0"; defparam m_reg.BREG_CLK = "CLK0";
    defparam m_reg.PREG_CLK = "BYPASS"; defparam m_reg.OREG_CLK = "CLK0";

    // only the pipeline register
    MULT12X12 m_pipe (.A(sr[35:24]), .B(sr[47:36]), .CLK({1'b0, clk}), .CE(2'b11), .RESET(2'b00), .DOUT(p_pipe));
    defparam m_pipe.AREG_CLK = "BYPASS"; defparam m_pipe.BREG_CLK = "BYPASS";
    defparam m_pipe.PREG_CLK = "CLK0"; defparam m_pipe.OREG_CLK = "BYPASS";

    // only the output register
    MULT12X12 m_oreg (.A(sr[47:36]), .B(sr[59:48]), .CLK({1'b0, clk}), .CE(2'b11), .RESET(2'b00), .DOUT(p_oreg));
    defparam m_oreg.AREG_CLK = "BYPASS"; defparam m_oreg.BREG_CLK = "BYPASS";
    defparam m_oreg.PREG_CLK = "BYPASS"; defparam m_oreg.OREG_CLK = "CLK0";

    MULTALU27X18 m_alu (.A(sr[26:0]), .B(sr[44:27]), .C(48'b0), .D(26'b0), .SIA(27'b0), .CASI(48'b0),
        .ACCSEL(1'b0), .CASISEL(1'b0), .ADDSUB(2'b00), .PADDSUB(1'b0), .ASEL(1'b0), .PSEL(1'b0), .CSEL(1'b0),
        .CLK({1'b0, clk}), .CE(2'b11), .RESET(2'b00), .DOUT(p_alu), .CASO(), .SOA());

    MULTADDALU12X12 m_addalu (.A0(sr[11:0]), .B0(sr[23:12]), .A1(sr[35:24]), .B1(sr[47:36]), .CASI(48'b0),
        .ACCSEL(1'b0), .CASISEL(1'b0), .ADDSUB(2'b00),
        .CLK({1'b0, clk}), .CE(2'b11), .RESET(2'b00), .DOUT(p_addalu), .CASO());

    MULT27X36 m_27x36 (.A(sr[86:60]), .B(sr[122:87]), .D(26'b0), .PSEL(1'b0), .PADDSUB(1'b0),
        .CLK({1'b0, clk}), .CE(2'b11), .RESET(2'b00), .DOUT(p_27x36));

    reg [62:0] q;
    always @(posedge clk) q <= {39'b0, p_comb ^ p_reg ^ p_pipe ^ p_oreg} ^ p_alu ^ p_addalu ^ p_27x36;
    assign dout = ^q;
endmodule
