/*
*  Nothing meaningful is tested here other than compilation.
*/
module top (
	input clk,
	input key_i,
	input rst_i,
	output [`LEDS_NR-1:0] led,
	inout [1:0] mipi_in
);

  wire rst = rst_i ^ `INV_BTN;
  wire key = key_i ^ `INV_BTN;

  wire term, ol, ob, hs_clk;

  MIPI_IBUF mipi_ibuf_clk (
    .OH(hs_clk),
    .OL(ol),
    .OB(ob),
    .IO(mipi_in[0]),
    .IOB(mipi_in[1]),
    .I(1'b0),
    .IB(1'b1),
    .OEN(1'b1),
    .OENB(1'b1),
    .HSREN(term)
  );

    CLKDIV cd (
    .CLKOUT(led[0]),
    .CALIB(1'b0),
    .HCLKIN(hs_clk),
    .RESETN(!rst)
  );
  defparam cd.DIV_MODE="4";

  assign term = (!(ol && ob)) ? 1'b1 : 1'b0;

endmodule
