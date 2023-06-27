module Gowin_PLLVR (clkout, clkin, lock_o, reset, reset_p, clkfb, clkoutd_o, fdiv, idiv, odiv);

output wire clkout;
output wire lock_o;
input wire clkin;
input wire reset;
input wire reset_p;
input wire clkfb;
output wire clkoutd_o;
input wire [5:0] fdiv;
input wire [5:0] idiv;
input wire [5:0] odiv;

wire clkoutp_o;
wire clkoutd3_o;
wire gw_gnd;
wire gw_vcc;

assign gw_gnd = 1'b0;
assign gw_vcc = 1'b1;

PLLVR pllvr_inst (
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
    .ODSEL(odiv),
    .PSDA({gw_gnd,gw_gnd,gw_gnd,gw_gnd}),
    .DUTYDA({gw_gnd,gw_gnd,gw_gnd,gw_gnd}),
    .FDLY({gw_gnd,gw_gnd,gw_gnd,gw_gnd}),
	.VREN(gw_vcc)
);

defparam pllvr_inst.FCLKIN = "27";
defparam pllvr_inst.DYN_IDIV_SEL = "true";
defparam pllvr_inst.IDIV_SEL = 5;
defparam pllvr_inst.DYN_FBDIV_SEL = "true";
defparam pllvr_inst.FBDIV_SEL = 12;
defparam pllvr_inst.DYN_ODIV_SEL = "true";
defparam pllvr_inst.ODIV_SEL = 8;
defparam pllvr_inst.PSDA_SEL = "0000";
defparam pllvr_inst.DYN_DA_EN = "false";
defparam pllvr_inst.DUTYDA_SEL = "1000";
defparam pllvr_inst.CLKOUT_FT_DIR = 1'b1;
defparam pllvr_inst.CLKOUTP_FT_DIR = 1'b1;
defparam pllvr_inst.CLKOUT_DLY_STEP = 0;
defparam pllvr_inst.CLKOUTP_DLY_STEP = 0;
defparam pllvr_inst.CLKFB_SEL = "internal";
defparam pllvr_inst.CLKOUT_BYPASS = "false";
defparam pllvr_inst.CLKOUTP_BYPASS = "false";
defparam pllvr_inst.CLKOUTD_BYPASS = "false";
defparam pllvr_inst.DYN_SDIV_SEL = 126;
defparam pllvr_inst.CLKOUTD_SRC = "CLKOUTP";
defparam pllvr_inst.CLKOUTD3_SRC = "CLKOUTP";
defparam pllvr_inst.DEVICE = "GW1NSR-4C";

endmodule //Gowin_rPLL
