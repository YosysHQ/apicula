`default_nettype none

module top(input wire [7:0]a, input wire [7:0]b, output wire [7:0]led);
	assign led[3:0] = a[3:0] + {a[7:5], 1'b1};
endmodule

