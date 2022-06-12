// Author: Niels A. Moseley, n.a.moseley@moseleyinstruments.com

`default_nettype none

/* 1-bit random bit generator */
module PRBS7(
    input wire clk, 
    input wire next,
    output wire out);

reg [6:0] d;

always @(posedge clk) 
begin
    if (next == 1)
        d <= { d[5:0], d[6] ^ d[5] };
    
    if (d == 0)
        d <= 1;
end

assign out = d[0];

endmodule
