module top (
	input clk,
	input key_i,
	output [`LEDS_NR-1:0] led
);

/* Expected Result: 
    - 1 or 2 LEDs blinking, depending on your board.
    - The `faster` LED is associated with the input clock.
    - The `slower` LED is associated with a divided clock.
    - On boards with multiple CLKDIVs, the slower LED's blink rate changes as it cycles through CLKDIVs
      configured with different DIV_MODES.
    - If your board has only one LED, it should blink with the divided clock.
    - Holding the appropriate button should stop the blinking.
*/

localparam /*string*/ DIV_MODE_2 = "2";
localparam /*string*/ DIV_MODE_35 = "3.5";
localparam /*string*/ DIV_MODE_4 = "4";
localparam /*string*/ DIV_MODE_5 = "5";


wire key = key_i ^ `INV_BTN;

reg [25:0] ctr_q;
wire [25:0] ctr_d;
// localparam NUM_HCLKi=NUM_HCLK;

wire [`NUM_HCLK-1:0] hclk_counts;
reg [$clog2(`NUM_HCLK)-1:0] curr_hclk_idx; 
wire curr_hclk; 
reg [30:0] sup_count; 

genvar i;
generate 
    for (i=0; i < `NUM_HCLK; i=i+1) begin:hcount
        localparam /*string*/ div_mode =(i % 4 == 0) ? DIV_MODE_2 :
                                        (i % 4 == 1) ? DIV_MODE_35 :
                                        (i % 4 == 2) ? DIV_MODE_4 :
                                                       DIV_MODE_5;

        wire div2_out; 
        wire o_clk;

        CLKDIV2 my_div2 (
            .RESETN(key),
            .HCLKIN(clk),
            .CLKOUT(div2_out)
        );

        CLKDIV #(.DIV_MODE(div_mode)) my_div (
            .RESETN(1'b1),
            .HCLKIN(div2_out),
            .CLKOUT(o_clk) 
        );

        reg [23:0] count;
        always @(posedge o_clk)begin
            count <= count + 1'b1;
        end
        assign hclk_counts[i] = count[23]; 
    end
endgenerate

reg old_bit;
always @(posedge clk) begin
    sup_count <= sup_count + 1'b1;

    curr_hclk_idx <= curr_hclk_idx;
	old_bit <= old_bit;
	if (old_bit != sup_count[29]) begin
		old_bit <= sup_count[29];
		if (curr_hclk_idx + 1 == `NUM_HCLK) begin
			curr_hclk_idx <= 0;
		end else begin
			curr_hclk_idx <= curr_hclk_idx + 1;
		end
	end
end

assign curr_hclk = hclk_counts[curr_hclk_idx];
assign led = {curr_hclk, sup_count[23]}; 

endmodule
