`default_nettype none

module top(input wire resetn, input wire key_i, output wire [7:0]led);
	wire key = key_i ^ `INV_BTN;
	assign led[4] = !(resetn | key);
endmodule

