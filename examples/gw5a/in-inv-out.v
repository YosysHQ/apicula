`default_nettype none

module top(input wire resetn, output wire [7:0]led);
	assign led[3] = !resetn;
endmodule

