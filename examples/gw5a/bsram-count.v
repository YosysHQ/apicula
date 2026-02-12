/* Simple BSRAM test: SP primitive with init data, counter-driven read to LEDs */
module top (
	input clk,
	output [`LEDS_NR-1:0] led
);

wire gnd = 1'b0;
wire vcc = 1'b1;

reg [13:0] counter;
always @(posedge clk)
	counter <= counter + 1;

// Use upper counter bits as BSRAM read address
wire [13:0] addr = {counter[13:3], gnd, gnd, gnd};

wire [31:0] dout;

SP sp_inst (
	.DO(dout),
	.DI(32'h00000000),
	.AD(addr),
	.CLK(clk),
	.CE(vcc),
	.WRE(gnd),
	.OCE(vcc),
	.BLKSEL(3'b000),
	.RESET(gnd)
);
defparam sp_inst.READ_MODE = 1'b0;
defparam sp_inst.WRITE_MODE = 2'b00;
defparam sp_inst.BIT_WIDTH = 1;
defparam sp_inst.BLK_SEL = 3'b000;
defparam sp_inst.RESET_MODE = "SYNC";
defparam sp_inst.INIT_RAM_00 = 256'hA5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5;
defparam sp_inst.INIT_RAM_01 = 256'h5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A;
defparam sp_inst.INIT_RAM_02 = 256'hFFFF0000FFFF0000FFFF0000FFFF0000FFFF0000FFFF0000FFFF0000FFFF0000;
defparam sp_inst.INIT_RAM_03 = 256'h0123456789ABCDEF0123456789ABCDEF0123456789ABCDEF0123456789ABCDEF;

assign led = dout[`LEDS_NR-1:0];

endmodule
