module Gowin_rPLL (clkout, clkin, lock_o, reset, reset_p, clkfb, clkoutd_o, fdiv, idiv);
output wire clkout;
output wire lock_o;
input wire clkin;
input wire reset;
input wire reset_p;
input wire clkfb;
output wire clkoutd_o;
input wire [5:0] fdiv;
input wire [5:0] idiv;

parameter DEVICE = "GW1N-1",
	      FCLKIN = "24",
	      FBDIV_SEL = 0,
		  IDIV_SEL =  0,
	      ODIV_SEL =  8,
	      DYN_ODIV_SEL="false",
          DYN_FBDIV_SEL="false",
          DYN_IDIV_SEL="false",
	      DYN_SDIV_SEL=2,
          PSDA_SEL="0000";

wire clkoutp_o;
wire clkoutd3_o;
wire gw_gnd;
wire gw_vcc;

assign gw_gnd = 1'b0;
assign gw_vcc = 1'b1;

rPLL rpll_inst (
    .CLKOUT(clkout),
    .LOCK(lock_o),
    .CLKOUTP(clkoutp_o),
    .CLKOUTD(clkoutd_o),
    .CLKOUTD3(clkoutd3_o),
    .RESET(reset),
    .RESET_P(reset_p),
    .CLKIN(clkin),
    .CLKFB(gw_gnd),
    .FBDSEL(fdiv),
    .IDSEL(idiv),
    .ODSEL({gw_gnd,gw_gnd,gw_gnd,gw_gnd,gw_gnd,gw_gnd}),
    .PSDA({gw_gnd,gw_gnd,gw_gnd,gw_gnd}),
    .DUTYDA({gw_gnd,gw_gnd,gw_gnd,gw_gnd}),
    .FDLY({gw_gnd,gw_gnd,gw_gnd,gw_gnd})
);

defparam rpll_inst.DEVICE = DEVICE;
defparam rpll_inst.FCLKIN = FCLKIN;
defparam rpll_inst.FBDIV_SEL = FBDIV_SEL;
defparam rpll_inst.DYN_IDIV_SEL = DYN_IDIV_SEL;
defparam rpll_inst.IDIV_SEL = IDIV_SEL;
defparam rpll_inst.DYN_FBDIV_SEL = DYN_FBDIV_SEL;
defparam rpll_inst.DYN_ODIV_SEL = DYN_ODIV_SEL;
defparam rpll_inst.ODIV_SEL = ODIV_SEL;
defparam rpll_inst.PSDA_SEL = PSDA_SEL;
defparam rpll_inst.DYN_DA_EN = "false";
defparam rpll_inst.DUTYDA_SEL = "1000";
defparam rpll_inst.CLKOUT_FT_DIR = 1'b1;
defparam rpll_inst.CLKOUTP_FT_DIR = 1'b1;
defparam rpll_inst.CLKOUT_DLY_STEP = 0;
defparam rpll_inst.CLKOUTP_DLY_STEP = 0;
defparam rpll_inst.CLKFB_SEL = "internal";
defparam rpll_inst.CLKOUT_BYPASS = "false";
defparam rpll_inst.CLKOUTP_BYPASS = "false";
defparam rpll_inst.CLKOUTD_BYPASS = "false";
defparam rpll_inst.DYN_SDIV_SEL = DYN_SDIV_SEL;
defparam rpll_inst.CLKOUTD_SRC = "CLKOUTP";
defparam rpll_inst.CLKOUTD3_SRC = "CLKOUTP";

endmodule //Gowin_rPLL
