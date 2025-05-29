/*
* I tested performance by programming SRAM, programming in flash is left at your own risk.
* At startup, the UserFlash page is cleared, then the number 0xc001cafe is
* written, then this number is read back and displayed on the dual segment
* indicator (https://wiki.sipeed.com/hardware/en/tang/tang-PMOD/FPGA_PMOD.html#PMOD_DTx2)
* pinout:
*  A - 9           A
*  B - 10        F   B
*  C - 11          G
*  D - 15        E   C
*  E - 16          D
*  F - 17
*  G - 18
*  sel - 28
*/
`include "uflash_controller.v"
`default_nettype none
module top (
    input wire clk,
	input wire rst_i,
	input wire key_i,
	output wire [2:0] led,
	output wire [5:0] LCD_G
);

	wire [7:0] out;
	assign led[2:0] =   out[2:0];
	assign LCD_G[5:2] = out[7:3];

	reg sel;
	reg [3:0] w_strb;
	wire [31:0] data_i;
	wire ready;
    wire [31:0] data_o;

	assign data_i = 32'hc001cafe;

	
	uflash flash_ctl(
	 rst_i,
	 clk,
	 sel,
	 w_strb,
	 {9'h0, 6'h0},  //addr,
	 data_i,
	 ready,
	 data_o
	);
	defparam flash_ctl.CLK_FREQ=27000000;
	
	reg [25:0] ctr_q;
	wire [25:0] ctr_d;

	// ========= clock =============
	// Sequential code (flip-flop)
	always @(posedge clk) begin
			ctr_q <= ctr_d;
	end

	// Combinational code (boolean logic)
	assign ctr_d = ctr_q + 1'b1;
	wire led_tick = ctr_q[10];
	// ============================

    localparam ERASE           = 3'h0;
    localparam WAIT_ERASE_DONE = 3'h1;
    localparam WRITE           = 3'h2;
    localparam WAIT_WRITE_DONE = 3'h3;
    localparam READ            = 3'h4;
    localparam WAIT_READ_DONE  = 3'h5;
    localparam IDLE            = 3'h6;

	// rotate bytes
	reg [31:0] shift32; 
	reg [2:0] state;
	always @(posedge clk or negedge rst_i) begin
		if (!rst_i) begin
		   state <= ERASE;
		   sel <= 1'b1;
	       w_strb <= 4'b0001;	   
		   shift32 <= 32'h0;
		end else begin
			case (state)
				ERASE: begin
					state <= WAIT_ERASE_DONE;
					sel <= 1'b0;
				end
				WAIT_ERASE_DONE: begin
					if (ready) begin
						state <= WRITE;
						w_strb <= 4'b1111;
						sel <= 1'b1;
					end
				end
				WRITE: begin
					state <= WAIT_WRITE_DONE;
					sel <= 1'b0;
				end
				WAIT_WRITE_DONE: begin
					if (ready) begin
						state <= READ;
						w_strb <= 4'b0000;
						sel <= 1'b1;
					end
				end
				READ: begin
					state <= WAIT_READ_DONE;
					sel <= 1'b0;
				end
				WAIT_READ_DONE: begin
					if (ready) begin
						state <= IDLE;
						w_strb <= 4'b0000;
						sel <= 1'b0;
						shift32 <= data_o;
					end
				end
				IDLE: begin
					if (&ctr_q[24:0]) begin
						shift32 <= {shift32[23:0], shift32[31:24]};
					end
				end
			endcase
		end
	end


    // output
	assign LCD_G[0] = led_tick;

	wire [6:0] seg[1:0];
	bin2segments left(
		.halfbyte(shift32[31:28]),
		.segments(seg[0])
	);

	bin2segments right(
		.halfbyte(shift32[27:24]),
		.segments(seg[1])
	);
	assign out = ~seg[led_tick];

endmodule

module bin2segments(
	input wire [3:0] halfbyte,
	output wire [6:0] segments
);
  assign segments = halfbyte == 4'hf ? 7'b1110001 : 
	                halfbyte == 4'he ? 7'b1111001 :
					halfbyte == 4'hd ? 7'b1011111 :
					halfbyte == 4'hc ? 7'b0111001 :
					halfbyte == 4'hb ? 7'b1111100 :
					halfbyte == 4'ha ? 7'b1110111 :
					halfbyte == 4'h9 ? 7'b1101111 :
					halfbyte == 4'h8 ? 7'b1111111 :
					halfbyte == 4'h7 ? 7'b0000111 :
					halfbyte == 4'h6 ? 7'b1111100 :
					halfbyte == 4'h5 ? 7'b1101101 :
					halfbyte == 4'h4 ? 7'b1100110 :
					halfbyte == 4'h3 ? 7'b1001111 :
					halfbyte == 4'h2 ? 7'b1011011 :
					halfbyte == 4'h1 ? 7'b0000110 : 7'b0111111;
endmodule

