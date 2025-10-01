`default_nettype none
module clock_pll(input wire clk, input wire rst, output wire write_clk, output wire pixel_clk);
    wire lock;
    wire clkout1;
    wire clkout2;
    wire clkout3;
    wire clkout4;
    wire clkout5;
    wire clkout6;
    wire clkfbout;
    wire [7:0] mdrdo;
    wire gw_gnd;

    assign gw_gnd = 1'b0;

    PLLA PLLA_inst (
        .LOCK(lock),
        .CLKOUT0(pixel_clk),
        .CLKOUT1(clkout1),
        .CLKOUT2(clkout2),
        .CLKOUT3(clkout3),
        .CLKOUT4(clkout4),
        .CLKOUT5(clkout5),
        .CLKOUT6(clkout6),
        .CLKFBOUT(clkfbout),
        .MDRDO(mdrdo),
        .CLKIN(clk),
        .CLKFB(gw_gnd),
        .RESET(!rst),
        .PLLPWD(gw_gnd),
        .RESET_I(gw_gnd),
        .RESET_O(gw_gnd),
        .PSSEL({gw_gnd,gw_gnd,gw_gnd}),
        .PSDIR(gw_gnd),
        .PSPULSE(gw_gnd),
        .SSCPOL(gw_gnd),
        .SSCON(gw_gnd),
        .SSCMDSEL({gw_gnd,gw_gnd,gw_gnd,gw_gnd,gw_gnd,gw_gnd,gw_gnd}),
        .SSCMDSEL_FRAC({gw_gnd,gw_gnd,gw_gnd}),
        .MDCLK(gw_gnd),
        .MDOPC({gw_gnd,gw_gnd}),
        .MDAINC(gw_gnd),
        .MDWDI({gw_gnd,gw_gnd,gw_gnd,gw_gnd,gw_gnd,gw_gnd,gw_gnd,gw_gnd})
    );

    defparam PLLA_inst.FCLKIN = `PLL_FCLKIN;
    defparam PLLA_inst.IDIV_SEL = `PLL_IDIV_SEL_LCD;
    defparam PLLA_inst.FBDIV_SEL = `PLL_FBDIV_SEL_LCD;
    defparam PLLA_inst.ODIV0_SEL = `PLL_ODIV0_SEL;
    defparam PLLA_inst.ODIV1_SEL = 8;
    defparam PLLA_inst.ODIV2_SEL = 8;
    defparam PLLA_inst.ODIV3_SEL = 8;
    defparam PLLA_inst.ODIV4_SEL = 8;
    defparam PLLA_inst.ODIV5_SEL = 8;
    defparam PLLA_inst.ODIV6_SEL = 8;
    defparam PLLA_inst.MDIV_SEL = 16;
    defparam PLLA_inst.MDIV_FRAC_SEL = 0;
    defparam PLLA_inst.ODIV0_FRAC_SEL = 0;
    defparam PLLA_inst.CLKOUT0_EN = "TRUE";
    defparam PLLA_inst.CLKOUT1_EN = "FALSE";
    defparam PLLA_inst.CLKOUT2_EN = "FALSE";
    defparam PLLA_inst.CLKOUT3_EN = "FALSE";
    defparam PLLA_inst.CLKOUT4_EN = "FALSE";
    defparam PLLA_inst.CLKOUT5_EN = "FALSE";
    defparam PLLA_inst.CLKOUT6_EN = "FALSE";
    defparam PLLA_inst.CLKFB_SEL = "INTERNAL";
    defparam PLLA_inst.CLKOUT0_DT_DIR = 1'b1;
    defparam PLLA_inst.CLKOUT1_DT_DIR = 1'b1;
    defparam PLLA_inst.CLKOUT2_DT_DIR = 1'b1;
    defparam PLLA_inst.CLKOUT3_DT_DIR = 1'b1;
    defparam PLLA_inst.CLKOUT0_DT_STEP = 0;
    defparam PLLA_inst.CLKOUT1_DT_STEP = 0;
    defparam PLLA_inst.CLKOUT2_DT_STEP = 0;
    defparam PLLA_inst.CLKOUT3_DT_STEP = 0;
    defparam PLLA_inst.CLK0_IN_SEL = 1'b0;
    defparam PLLA_inst.CLK0_OUT_SEL = 1'b0;
    defparam PLLA_inst.CLK1_IN_SEL = 1'b0;
    defparam PLLA_inst.CLK1_OUT_SEL = 1'b0;
    defparam PLLA_inst.CLK2_IN_SEL = 1'b0;
    defparam PLLA_inst.CLK2_OUT_SEL = 1'b0;
    defparam PLLA_inst.CLK3_IN_SEL = 1'b0;
    defparam PLLA_inst.CLK3_OUT_SEL = 1'b0;
    defparam PLLA_inst.CLK4_IN_SEL = 2'b00;
    defparam PLLA_inst.CLK4_OUT_SEL = 1'b0;
    defparam PLLA_inst.CLK5_IN_SEL = 1'b0;
    defparam PLLA_inst.CLK5_OUT_SEL = 1'b0;
    defparam PLLA_inst.CLK6_IN_SEL = 1'b0;
    defparam PLLA_inst.CLK6_OUT_SEL = 1'b0;
    defparam PLLA_inst.DYN_DPA_EN = "FALSE";
    defparam PLLA_inst.CLKOUT0_PE_COARSE = 0;
    defparam PLLA_inst.CLKOUT0_PE_FINE = 0;
    defparam PLLA_inst.CLKOUT1_PE_COARSE = 0;
    defparam PLLA_inst.CLKOUT1_PE_FINE = 0;
    defparam PLLA_inst.CLKOUT2_PE_COARSE = 0;
    defparam PLLA_inst.CLKOUT2_PE_FINE = 0;
    defparam PLLA_inst.CLKOUT3_PE_COARSE = 0;
    defparam PLLA_inst.CLKOUT3_PE_FINE = 0;
    defparam PLLA_inst.CLKOUT4_PE_COARSE = 0;
    defparam PLLA_inst.CLKOUT4_PE_FINE = 0;
    defparam PLLA_inst.CLKOUT5_PE_COARSE = 0;
    defparam PLLA_inst.CLKOUT5_PE_FINE = 0;
    defparam PLLA_inst.CLKOUT6_PE_COARSE = 0;
    defparam PLLA_inst.CLKOUT6_PE_FINE = 0;
    defparam PLLA_inst.DYN_PE0_SEL = "FALSE";
    defparam PLLA_inst.DYN_PE1_SEL = "FALSE";
    defparam PLLA_inst.DYN_PE2_SEL = "FALSE";
    defparam PLLA_inst.DYN_PE3_SEL = "FALSE";
    defparam PLLA_inst.DYN_PE4_SEL = "FALSE";
    defparam PLLA_inst.DYN_PE5_SEL = "FALSE";
    defparam PLLA_inst.DYN_PE6_SEL = "FALSE";
    defparam PLLA_inst.DE0_EN = "FALSE";
    defparam PLLA_inst.DE1_EN = "FALSE";
    defparam PLLA_inst.DE2_EN = "FALSE";
    defparam PLLA_inst.DE3_EN = "FALSE";
    defparam PLLA_inst.DE4_EN = "FALSE";
    defparam PLLA_inst.DE5_EN = "FALSE";
    defparam PLLA_inst.DE6_EN = "FALSE";
    defparam PLLA_inst.RESET_I_EN = "FALSE";
    defparam PLLA_inst.RESET_O_EN = "FALSE";
    defparam PLLA_inst.ICP_SEL = 6'bXXXXXX;
    defparam PLLA_inst.LPF_RES = 3'bXXX;
    defparam PLLA_inst.LPF_CAP = 2'b00;
    defparam PLLA_inst.SSC_EN = "FALSE";

    // ~70kHz for memory write
    // temporary solution
    localparam DIVIDER = 455;
    reg [8:0] counter;
    reg clk_div;
    assign write_clk = |counter;

    always @(negedge clk) begin
        clk_div <= counter == 0;
    end

    always @(posedge clk or negedge rst) begin
        if (!rst) begin
            counter <= 0;
            clk_div <= 0;
        end else begin
            if (counter == DIVIDER - 1) begin
                counter <= 0;
            end else begin
                counter <= counter + 1;
            end
        end
    end
endmodule
// vim: set et sw=4 ts=4:
