`default_nettype none

module top(input wire resetn, input wire key, output wire [7:0]led);
	assign led[4] = !(resetn | key);
endmodule

