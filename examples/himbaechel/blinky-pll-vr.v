(* top *)
module top (
	input key_i,
	input clk,
	output [`LEDS_NR-1:0] led
);

wire clk_w;
wire GND = 1'b0;
wire VCC = 1'b1;

PLLVR pllvr_inst (
    .CLKOUT(clk_w),
	.CLKIN(clk),
	.CLKFB(GND),
	.RESET(GND),
	.RESET_P(GND),
	.FBDSEL({GND,GND,GND,GND,GND,GND}),
	.IDSEL({GND,GND,GND,GND,GND,GND}),
	.ODSEL({GND,GND,GND,GND,GND,GND}),
	.DUTYDA({GND,GND,GND,GND}),
	.PSDA({GND,GND,GND,GND}),
	.FDLY({GND,GND,GND,GND}),
	.VREN(VCC)
);
defparam pllvr_inst.FCLKIN = "27";
defparam pllvr_inst.DYN_IDIV_SEL = "true";
defparam pllvr_inst.IDIV_SEL = 2;
defparam pllvr_inst.DYN_FBDIV_SEL = "true";
defparam pllvr_inst.FBDIV_SEL = 0;
defparam pllvr_inst.DYN_ODIV_SEL = "false";
defparam pllvr_inst.ODIV_SEL = 48;
defparam pllvr_inst.PSDA_SEL = "0000";
defparam pllvr_inst.DYN_DA_EN = "false";
defparam pllvr_inst.DUTYDA_SEL = "0100";
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

wire key = key_i ^ `INV_BTN;

reg [25:0] ctr_q;
wire [25:0] ctr_d;

// Sequential code (flip-flop)
always @(posedge clk_w) begin
	if (key) begin
		ctr_q <= ctr_d;
	end
end

// Combinational code (boolean logic)
assign ctr_d = ctr_q + 1'b1;
assign led = {ctr_q[25:25-(`LEDS_NR - 2)], |ctr_q[25-(`LEDS_NR - 1):25-(`LEDS_NR)] };

endmodule
