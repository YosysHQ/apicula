`default_nettype none

module top(input wire resetn, input wire key, output wire led);
	assign led = !(resetn | key);
endmodule

