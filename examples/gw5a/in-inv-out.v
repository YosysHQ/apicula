`default_nettype none

module top(input wire resetn, output wire led);
	assign led = !resetn;
endmodule

