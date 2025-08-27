`default_nettype none
`define LEDS_NR 8

module top(input wire clk, input wire resetn, output wire [`LEDS_NR - 1:0]led);

wire tick_hz;
wire reset = resetn;

localparam HZ_PRESC = 24_000_000,
		HZ_SIZE = $clog2(HZ_PRESC);

reg [HZ_SIZE - 1:0]  hertz_cpt;
wire [HZ_SIZE - 1:0]  hertz_cpt_d = hertz_cpt - 1'b1;

always @(posedge clk) begin
	if (tick_hz) begin
		hertz_cpt <= HZ_PRESC;
	end else begin
		hertz_cpt <= hertz_cpt_d;
	end
end


reg [3:0]pc;
wire [`LEDS_NR - 1:0]out;

// primes :)
ROM16 mem0(
	.AD(pc),
	.DO(out[0])
);
ROM16 mem1(
	.AD(pc),
	.DO(out[1])
);
ROM16 mem2(
	.AD(pc),
	.DO(out[2])
);
ROM16 mem3(
	.AD(pc),
	.DO(out[3])
);
ROM16 mem4(
	.AD(pc),
	.DO(out[4])
);
ROM16 mem5(
	.AD(pc),
	.DO(out[5])
);
ROM16 mem6(
	.AD(pc),
	.DO(out[6])
);
ROM16 mem7(
	.AD(pc),
	.DO(out[7])
);
defparam mem0.INIT_0=16'b0000010000010000;
defparam mem1.INIT_0=16'b0000001000101000;
defparam mem2.INIT_0=16'b1000001101000100;
defparam mem3.INIT_0=16'b1100000110010010;
defparam mem4.INIT_0=16'b0110000010010010;
defparam mem5.INIT_0=16'b0011000001000100;
defparam mem6.INIT_0=16'b0001100000101000;
defparam mem7.INIT_0=16'b0000110000010000;

always @(posedge clk) begin
	if (reset) begin
		 pc <= 0;
	end else if (tick_hz) begin
		 pc <= pc + 1'b1;
	end
end

assign tick_hz = (hertz_cpt == 0);
assign led = ~out;
endmodule

