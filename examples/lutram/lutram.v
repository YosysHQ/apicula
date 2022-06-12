// Author: Niels A. Moseley, n.a.moseley@moseleyinstruments.com

`default_nettype none

/* 1-bit by 16 element SRAM */
module LUTRAM16S1(
    input wire clk, 
    input wire [3:0] ad,
    input wire wre,
    input wire di,
    output wire do);

reg memory[0:15];

always@(posedge clk)
begin
    if (wre == 1)
    begin
        memory[ad] <= di;
    end
end

assign do = memory[ad];

endmodule
