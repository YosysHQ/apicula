/********************************************
Two PMODs will be required - seven-segment indicators and pushbuttons with switches. 
Connect them as shown in the photo: apuicula/doc/fig/tangprimer25-lut-test.jpeg
********************************************/
`default_nettype none

(* top *)
module top(input wire resetn, input wire key_i, input wire [7:0]pmod_keys, output wire [7:0]led);
	wire key = key_i ^ `INV_BTN;

	wire [7:0]w;
	assign led = {~w[5], ~w[6], ~w[4:3], ~w[1:0], ~w[2], w[7]};

	llut8 l8(
		.cnst0(resetn),
		.cnst1(key),
		.inp(pmod_keys),
		.out(w)
	);

endmodule

module llut8(input wire cnst0, input wire cnst1, input wire [7:0]inp, output wire [7:0]out);
	wire [15:0]w;

	llut7a l7a(
		.cnst0(cnst0),
		.cnst1(cnst1),
		.inp(inp),
		.out(w[7:0])
	);

	llut7a l7b(
		.cnst0(cnst0),
		.cnst1(cnst1),
		.inp({inp[7:4], inp[2:0], inp[3]}),
		.out(w[15:8])
	);

	MUX2_LUT8 m2l7A(
		.I0(w[0]),
		.I1(w[8]),
		.S0(~inp[7]),
		.O(out[0])
	);

	MUX2_LUT8 m2l6B(
		.I0(w[1]),
		.I1(w[9]),
		.S0(~inp[7]),
		.O(out[1])
	);

	MUX2_LUT8 m2l6C(
		.I0(w[2]),
		.I1(w[10]),
		.S0(~inp[7]),
		.O(out[2])
	);

	MUX2_LUT8 m2l6D(
		.I0(w[3]),
		.I1(w[11]),
		.S0(~inp[7]),
		.O(out[3])
	);

	MUX2_LUT8 m2l6E(
		.I0(w[4]),
		.I1(w[12]),
		.S0(~inp[7]),
		.O(out[4])
	);

	MUX2_LUT8 m2l6F(
		.I0(w[5]),
		.I1(w[13]),
		.S0(~inp[7]),
		.O(out[5])
	);

	MUX2_LUT8 m2l6G(
		.I0(w[6]),
		.I1(w[14]),
		.S0(~inp[7]),
		.O(out[6])
	);

	MUX2_LUT8 m2l6SEL(
		.I0(w[7]),
		.I1(w[15]),
		.S0(~inp[7]),
		.O(out[7])
	);
endmodule

module llut7a(input wire cnst0, input wire cnst1, input wire [7:0]inp, output wire [7:0]out);
	wire [15:0]w;

	llut6a l6a(
		.cnst0(cnst0),
		.cnst1(cnst1),
		.inp(inp),
		.out(w[7:0])
	);

	llut6a l6b(
		.cnst0(cnst0),
		.cnst1(cnst1),
		.inp(~inp),
		.out(w[15:8])
	);

	MUX2_LUT7 m2l7A(
		.I0(w[0]),
		.I1(w[8]),
		.S0(~inp[6]),
		.O(out[0])
	);

	MUX2_LUT7 m2l7B(
		.I0(w[1]),
		.I1(w[9]),
		.S0(~inp[6]),
		.O(out[1])
	);

	MUX2_LUT7 m2l7C(
		.I0(w[2]),
		.I1(w[10]),
		.S0(~inp[6]),
		.O(out[2])
	);

	MUX2_LUT7 m2l7D(
		.I0(w[3]),
		.I1(w[11]),
		.S0(~inp[6]),
		.O(out[3])
	);

	MUX2_LUT7 m2l7E(
		.I0(w[4]),
		.I1(w[12]),
		.S0(~inp[6]),
		.O(out[4])
	);

	MUX2_LUT7 m2l7F(
		.I0(w[5]),
		.I1(w[13]),
		.S0(~inp[6]),
		.O(out[5])
	);

	MUX2_LUT7 m2l7G(
		.I0(w[6]),
		.I1(w[14]),
		.S0(~inp[6]),
		.O(out[6])
	);

	MUX2_LUT7 m2l7SEL(
		.I0(w[7]),
		.I1(w[15]),
		.S0(~inp[6]),
		.O(out[7])
	);
endmodule

module llut6a(input wire cnst0, input wire cnst1, input wire [7:0]inp, output wire [7:0]out);
	wire [17:0]w;

	llut5a l5a(
		.cnst0(cnst0),
		.cnst1(cnst1),
		.inp(inp),
		.out(w[7:0])
	);
	
	llut5m l5b(
		.cnst0(cnst0),
		.cnst1(cnst1),
		.inp(inp),
		.out(w[15:8])
	);

	// straight <-> mirror
	MUX2_LUT6 m2l6A(
		.I0(w[0]),
		.I1(w[8]),
		.S0(~inp[5]),
		.O(out[0])
	);

	MUX2_LUT6 m2l6B(
		.I0(w[1]),
		.I1(w[9]),
		.S0(~inp[5]),
		.O(out[1])
	);

	MUX2_LUT6 m2l6C(
		.I0(w[2]),
		.I1(w[10]),
		.S0(~inp[5]),
		.O(out[2])
	);

	MUX2_LUT6 m2l6D(
		.I0(w[3]),
		.I1(w[11]),
		.S0(~inp[5]),
		.O(out[3])
	);

	MUX2_LUT6 m2l6E(
		.I0(w[4]),
		.I1(w[12]),
		.S0(~inp[5]),
		.O(out[4])
	);

	MUX2_LUT6 m2l6F(
		.I0(w[5]),
		.I1(w[13]),
		.S0(~inp[5]),
		.O(out[5])
	);

	MUX2_LUT6 m2l6G(
		.I0(w[6]),
		.I1(w[14]),
		.S0(~inp[5]),
		.O(out[6])
	);

	MUX2_LUT6 m2l6SEL(
		.I0(w[7]),
		.I1(w[15]),
		.S0(~inp[5]),
		.O(out[7])
	);
endmodule

module llut5a(input wire cnst0, input wire cnst1, input wire [7:0]inp, output wire [7:0]out);
	wire [17:0]w;

	llut4a l4a0(
		.inp(inp),
		.out(w[7:0]),
	);
	llut4a l4a1(
		.inp(inp),
		.out(w[15:8]),
	);

	MUX2_LUT5 m2l5A(
		.I0(w[0]),
		.I1(w[8]),
		.S0(~inp[4]),
		.O(out[0])
	);
	MUX2_LUT5 m2l5B(
		.I0(w[1]),
		.I1(w[9]),
		.S0(~inp[4]),
		.O(out[1])
	);
	MUX2_LUT5 m2l5C(
		.I0(w[2]),
		.I1(w[10]),
		.S0(~inp[4]),
		.O(out[2])
	);
	MUX2_LUT5 m2l5D(
		.I0(w[3]),
		.I1(w[11]),
		.S0(~inp[4]),
		.O(out[3])
	);
	MUX2_LUT5 m2l5E(
		.I0(w[4]),
		.I1(w[12]),
		.S0(~inp[4]),
		.O(out[4])
	);
	MUX2_LUT5 m2l5F(
		.I0(w[5]),
		.I1(w[13]),
		.S0(~inp[4]),
		.O(out[5])
	);
	MUX2_LUT5 m2l5G(
		.I0(w[6]),
		.I1(w[14]),
		.S0(~inp[4]),
		.O(out[6])
	);
	MUX2_LUT5 m2l5S0EL(
		.I0(w[16]),
		.I1(w[17]),
		.S0(~inp[4]),
		.O(out[7])
	);

	LUT1 vcc_lut(
		.I0(cnst1),
		.F(w[16])
	);
	defparam vcc_lut.INIT=2'b01;

	LUT1 vss_lut(
		.I0(cnst0),
		.F(w[17])
	);
	defparam vss_lut.INIT=2'b10;
endmodule

module llut5m(input wire cnst0, input wire cnst1, input wire [7:0]inp, output wire [7:0]out);
	wire [17:0]w;

	llut4m l4a0(
		.inp(inp),
		.out(w[7:0]),
	);
	llut4m l4a1(
		.inp(inp),
		.out(w[15:8]),
	);

	MUX2_LUT5 m2l5A(
		.I0(w[0]),
		.I1(w[8]),
		.S0(~inp[4]),
		.O(out[0])
	);
	MUX2_LUT5 m2l5B(
		.I0(w[1]),
		.I1(w[9]),
		.S0(~inp[4]),
		.O(out[1])
	);
	MUX2_LUT5 m2l5C(
		.I0(w[2]),
		.I1(w[10]),
		.S0(~inp[4]),
		.O(out[2])
	);
	MUX2_LUT5 m2l5D(
		.I0(w[3]),
		.I1(w[11]),
		.S0(~inp[4]),
		.O(out[3])
	);
	MUX2_LUT5 m2l5E(
		.I0(w[4]),
		.I1(w[12]),
		.S0(~inp[4]),
		.O(out[4])
	);
	MUX2_LUT5 m2l5F(
		.I0(w[5]),
		.I1(w[13]),
		.S0(~inp[4]),
		.O(out[5])
	);
	MUX2_LUT5 m2l5G(
		.I0(w[6]),
		.I1(w[14]),
		.S0(~inp[4]),
		.O(out[6])
	);
	MUX2_LUT5 m2l5S0EL(
		.I0(w[16]),
		.I1(w[17]),
		.S0(~inp[4]),
		.O(out[7])
	);

	LUT1 vcc_lut(
		.I0(cnst1),
		.F(w[16])
	);
	defparam vcc_lut.INIT=2'b01;

	LUT1 vss_lut(
		.I0(cnst0),
		.F(w[17])
	);
	defparam vss_lut.INIT=2'b10;
endmodule

module llut4a(input wire [7:0]inp, output wire [7:0]out);
	// *********************
	// normal 0
	LUT4 l4A(
		.I0(!inp[0]),
		.I1(!inp[1]),
		.I2(!inp[2]),
		.I3(!inp[3]),
		.F(out[0])
	);
	defparam l4A.INIT=16'b1101_0111_1110_1101;

	LUT4 l4B(
		.I0(!inp[0]),
		.I1(!inp[1]),
		.I2(!inp[2]),
		.I3(!inp[3]),
		.F(out[1])
	);
	defparam l4B.INIT=16'b0010_0111_1001_1111;

	LUT4 l4C(
		.I0(!inp[0]),
		.I1(!inp[1]),
		.I2(!inp[2]),
		.I3(!inp[3]),
		.F(out[2])
	);
	defparam l4C.INIT=16'b0010_1111_1111_1011;

	LUT4 l4D(
		.I0(!inp[0]),
		.I1(!inp[1]),
		.I2(!inp[2]),
		.I3(!inp[3]),
		.F(out[3])
	);
	defparam l4D.INIT=16'b0111_1001_0110_1101;

	LUT4 l4E(
		.I0(!inp[0]),
		.I1(!inp[1]),
		.I2(!inp[2]),
		.I3(!inp[3]),
		.F(out[4])
	);
	defparam l4E.INIT=16'b1111_1101_0100_0101;

	LUT4 l4F(
		.I0(!inp[0]),
		.I1(!inp[1]),
		.I2(!inp[2]),
		.I3(!inp[3]),
		.F(out[5])
	);
	defparam l4F.INIT=16'b1101_1111_0111_0001;

	LUT4 l4G(
		.I0(!inp[0]),
		.I1(!inp[1]),
		.I2(!inp[2]),
		.I3(!inp[3]),
		.F(out[6])
	);
	defparam l4G.INIT=16'b1110_1111_0111_1100;
endmodule		

module llut4m(input wire [7:0]inp, output wire [7:0]out);		
	// *********************************
	// upside down 0
	LUT4 l4AU(
		.I0(!inp[0]),
		.I1(!inp[1]),
		.I2(!inp[2]),
		.I3(!inp[3]),
		.F(out[0])
	);
	defparam l4AU.INIT=16'b0111_1001_0110_1101;

	LUT4 l4BU(
		.I0(!inp[0]),
		.I1(!inp[1]),
		.I2(!inp[2]),
		.I3(!inp[3]),
		.F(out[1])
	);
	defparam l4BU.INIT=16'b1111_1101_0100_0101;

	LUT4 l4CU(
		.I0(!inp[0]),
		.I1(!inp[1]),
		.I2(!inp[2]),
		.I3(!inp[3]),
		.F(out[2])
	);
	defparam l4CU.INIT=16'b1101_1111_0111_0001;

	LUT4 l4DU(
		.I0(!inp[0]),
		.I1(!inp[1]),
		.I2(!inp[2]),
		.I3(!inp[3]),
		.F(out[3])
	);
	defparam l4DU.INIT=16'b1101_0111_1110_1101;

	LUT4 l4EU(
		.I0(!inp[0]),
		.I1(!inp[1]),
		.I2(!inp[2]),
		.I3(!inp[3]),
		.F(out[4])
	);
	defparam l4EU.INIT=16'b0010_0111_1001_1111;

	LUT4 l4FU(
		.I0(!inp[0]),
		.I1(!inp[1]),
		.I2(!inp[2]),
		.I3(!inp[3]),
		.F(out[5])
	);
	defparam l4FU.INIT=16'b0010_1111_1111_1011;

	LUT4 l4GU(
		.I0(!inp[0]),
		.I1(!inp[1]),
		.I2(!inp[2]),
		.I3(!inp[3]),
		.F(out[6])
	);
	defparam l4GU.INIT=16'b1110_1111_0111_1100;
endmodule

