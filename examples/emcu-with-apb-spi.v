`default_nettype none

/*
* The apprate SPI is implemented with the following limitations:
* - master only,
* - SPI3 mode,
* - write only,
* - LSB/MSB format switching is performed by a bit in the control/status register,
* - the status register contains one bit - BUSY.
* - speed is fixed = 0.5 clk (~13MHz)
*
* Attention: flashing is performed with firmware as follows:
* openFPGALoader -f -b tangnano4k --mcufw=emcu-firmware/apb-spi.bin emcu-apb-spi-tangnano4k.fs
*
*/

module top (
  input wire clk_i,
  output wire mode_led,
  input wire RXD,
  output wire TXD,
  input wire rst_i,
  // gpio
  inout wire [1:0] gpio,
  // SPI
  output wire spi_OUT,
  output reg spi_SCL,
  output [5:0] led
  );

  // dummy sinks
  wire dummy_uart1_txd;
  wire dummy_uart0_baudtick;
  wire dummy_uart1_baudtick;
  wire dummy_intmonitor;
  wire dummy_targexp0_hsel;
  wire [31:0] dummy_targexp0_haddr;
  wire [1:0] dummy_targexp0_htrans;
  wire dummy_targexp0_hwrite;
  wire [2:0] dummy_targexp0_hsize;
  wire [2:0] dummy_targexp0_hburst;
  wire [3:0] dummy_targexp0_hprot;
  wire [1:0] dummy_targexp0_memattr;
  wire dummy_targexp0_exreq;
  wire [3:0] dummy_targexp0_hmaster;
  wire [31:0] dummy_targexp0_hwdata;
  wire dummy_targexp0_hmastlock;
  wire dummy_targexp0_hauser;
  wire [3:0] dummy_targexp0_hwuser;
  wire [31:0] dummy_initexp0_hrdata;
  wire dummy_initexp0_hready;
  wire dummy_initexp0_hresp;
  wire dummy_initexp0_exresp;
  wire [2:0] dummy_initexp0_hruser;
  wire dummy_daptdo;
  wire dummy_dapjtagnsw;
  wire [3:0] dummy_tpiutracedata;
  wire dummy_targexp0_hreadymux;
  wire dummy_dapntdoen;

  // Periphery bus
  wire apbtargexp2_psel;
  wire [11:0] apbtargexp2_paddr;
  wire apbtargexp2_pready;
  wire apbtargexp2_penable;
  wire apbtargexp2_pwrite;
  wire [31:0] apbtargexp2_pwdata;
  wire [31:0] apbtargexp2_prdata;
  wire [3:0] apbtargexp2_pstrb;
  wire [2:0] apbtargexp2_pprot;

  // ROM 32k
  wire [12:0] rom_addr;
  wire [15:0] dummy_rom_addr; // flash is addressed by 4 bytes each, and there are also unused high bits of the address
  wire targflash0_hsel;
  wire [1:0] targflash0_htrans;
  wire [2:0] dummy_targflash0_hsize;
  wire [2:0] dummy_targflash0_hburst;
  wire dummy_targflash0_hreadymux;
  wire [31:0] rom_out;
  wire targflash0_readyout;

  // SRAM 8k
  wire [10:0] sram0_addr;
  wire [1:0] dummy_sram0_addr; // high address bits
  wire sram0_cs;
  wire [3:0] sram0_wren; // byte write mask
  wire [31:0] sram0_wdata;
  wire [31:0] sram0_rdata; // all 32bit
  wire [23:0] dummy_sram0_rdata_0; // for unused bits
  wire [23:0] dummy_sram0_rdata_1; 
  wire [23:0] dummy_sram0_rdata_2; 
  wire [23:0] dummy_sram0_rdata_3; 

  wire mtx_hreset_n;

  // The processor reset inputs are not explicitly brought out - Global Set Reset is used. 
  GSR gsr (
    .GSRI(rst_i) 
  );

  wire GND = 1'b0;
  wire VCC = 1'b1;

  wire dummy_lock;
  wire clk;
  PLLVR #(
	.FCLKIN("27.0"),
	.IDIV_SEL(4), // -> PFD = 5.4 MHz (range: 3-400 MHz)
	.FBDIV_SEL(12), // -> CLKOUT = 70.2 MHz (range: 400-600 MHz)
	.ODIV_SEL(8) // -> VCO = 561.6 MHz (range: 600-1200 MHz)
)
	pll (.CLKOUTP(), .CLKOUTD(), .CLKOUTD3(), .RESET(1'b0), .RESET_P(1'b0), .CLKFB(1'b0), .FBDSEL(6'b0), .IDSEL(6'b0), .ODSEL(6'b0), .PSDA(4'b0), .DUTYDA(4'b0), .FDLY(4'b0), .VREN(1'b1),
	.CLKIN(clk_i), // 27.0 MHz
	.CLKOUT(clk), // 70.2 MHz
	.LOCK(dummy_lock)
  );

  // dummy GPIO inout ports, unused
  wire [15:0] gpio_out;
  wire [15:0] gpio_oen;
  wire [15:0] gpio_in;

  // GPIO inout ports, 16 total but we need only two
  wire [15:0] gpio_out;
  wire [15:0] gpio_oen; // active low
  wire [15:0] gpio_in;
  
  IOBUF gpio0(
	  .O(gpio_in[0]),
	  .IO(gpio[0]),
	  .I(gpio_out[0]),
	  .OEN(~gpio_oen[0])
	  );

  IOBUF gpio1(
	  .O(gpio_in[1]),
	  .IO(gpio[1]),
	  .I(gpio_out[1]),
	  .OEN(~gpio_oen[1])
	  );

  
  EMCU cpu (
    .FCLK(clk),
    .PORESETN(GND),  // doesn't matter 
    .SYSRESETN(GND), // doesn't matter
    .RTCSRCCLK(GND), // this is normal port but we haven't RTC in this example
    .MTXHRESETN(mtx_hreset_n),

    .IOEXPOUTPUTO(gpio_out),
    .IOEXPOUTPUTENO(gpio_oen),
    .IOEXPINPUTI(gpio_in),

    .UART0RXDI(RXD),
    .UART1RXDI(GND),
    .UART0TXDO(TXD),
    .UART1TXDO(dummy_uart1_txd),
    .UART0BAUDTICK(dummy_uart0_baudtick),
    .UART1BAUDTICK(dummy_uart1_baudtick),

    .INTMONITOR(dummy_intmonitor),

    .SRAM0ADDR({dummy_sram0_addr, sram0_addr}),
    .SRAM0CS(sram0_cs),
    .SRAM0WREN(sram0_wren),
    .SRAM0WDATA(sram0_wdata),
    .SRAM0RDATA(sram0_rdata),

    .TARGFLASH0HSEL(targflash0_hsel),
    .TARGFLASH0HADDR({dummy_rom_addr[15:2], rom_addr, dummy_rom_addr[1:0]}),
    .TARGFLASH0HTRANS(targflash0_htrans),
    .TARGFLASH0HSIZE(dummy_targflash0_hsize),
    .TARGFLASH0HBURST(dummy_targflash0_hburst),
    .TARGFLASH0HREADYMUX(dummy_targflash0_hreadymux),
    .TARGFLASH0HRDATA(rom_out),
    .TARGFLASH0HRUSER({GND,GND,GND}),
    .TARGFLASH0HRESP(GND),
    .TARGFLASH0EXRESP(GND),
    .TARGFLASH0HREADYOUT(targflash0_readyout),

    .TARGEXP0HSEL(dummy_targexp0_hsel),
    .TARGEXP0HADDR(dummy_targexp0_haddr),
    .TARGEXP0HTRANS(dummy_targexp0_htrans),
    .TARGEXP0HWRITE(dummy_targexp0_hwrite),
    .TARGEXP0HSIZE(dummy_targexp0_hsize),
    .TARGEXP0HBURST(dummy_targexp0_hburst[2:0]),
    .TARGEXP0HPROT(dummy_targexp0_hprot[3:0]),
    .TARGEXP0MEMATTR(dummy_targexp0_memattr),
    .TARGEXP0EXREQ(dummy_targexp0_exreq),
    .TARGEXP0HMASTER(dummy_targexp0_hmaster),
    .TARGEXP0HWDATA(dummy_targexp0_hwdata),
    .TARGEXP0HMASTLOCK(dummy_targexp0_hmastlock),
    .TARGEXP0HREADYMUX(dummy_targexp0_hreadymux),
    .TARGEXP0HAUSER(dummy_targexp0_hauser),
    .TARGEXP0HWUSER(dummy_targexp0_hwuser),
    .INITEXP0HRDATA(dummy_initexp0_hrdata),
    .INITEXP0HREADY(dummy_initexp0_hready),
    .INITEXP0HRESP(dummy_initexp0_hresp),
    .INITEXP0EXRESP(dummy_initexp0_exresp),
    .INITEXP0HRUSER(dummy_initexp0_hruser),
    .DAPTDO(dummy_daptdo),
    .DAPJTAGNSW(dummy_dapjtagnsw),
    .DAPNTDOEN(dummy_dapntdoen),
    .TPIUTRACEDATA(dummy_tpiutracedata),
    .TARGEXP0HRDATA({32{GND}}),
    .TARGEXP0HREADYOUT(GND),
    .TARGEXP0HRESP(VCC), // XXX 
    .TARGEXP0EXRESP(GND),
    .TARGEXP0HRUSER({GND,GND,GND}),
    .INITEXP0HSEL(GND),
    .INITEXP0HADDR({32{GND}}),
    .INITEXP0HTRANS({GND,GND}),
    .INITEXP0HWRITE(GND),
    .INITEXP0HSIZE({GND,GND,GND}),
    .INITEXP0HBURST({GND,GND,GND}),
    .INITEXP0HPROT({GND,GND,GND,GND}),
    .INITEXP0MEMATTR({GND,GND}),
    .INITEXP0EXREQ(GND),
    .INITEXP0HMASTER({GND,GND,GND,GND}),
    .INITEXP0HWDATA({32{GND}}),
    .INITEXP0HMASTLOCK(GND),
    .INITEXP0HAUSER(GND),
    .INITEXP0HWUSER({GND,GND,GND,GND}),

    .APBTARGEXP2PSEL(apbtargexp2_psel),
    .APBTARGEXP2PADDR(apbtargexp2_paddr),
    .APBTARGEXP2PSTRB(apbtargexp2_pstrb),
    .APBTARGEXP2PPROT(apbtargexp2_pprot),
    .APBTARGEXP2PENABLE(apbtargexp2_penable),
    .APBTARGEXP2PWRITE(apbtargexp2_pwrite),
    .APBTARGEXP2PWDATA(apbtargexp2_pwdata),

    .APBTARGEXP2PRDATA(apbtargexp2_prdata),
    .APBTARGEXP2PREADY(apbtargexp2_pready),
    .APBTARGEXP2PSLVERR(GND),

    .DAPSWDITMS(GND),
    .FLASHERR(GND),
    .FLASHINT(GND)
  );

  // ROM 
  // To understand what the entrances and outputs of this primitive, I followed the description of the AMBA protocol.
  // https://developer.arm.com/documentation/ihi0011/a/ or search for IHI0011a.pdf
  // It was from there and by the names of the ports of the primitive that it
  // became clear that RAM is connected directly without tricks, but for Flash
  // it would be necessary to implement a whole client of this AHB Bus.
  localparam ROM_IDLE = 2'b00;
  localparam ROM_READ = 2'b01;
  localparam ROM_OKEY = 2'b10;
  reg [1:0] rom_state;
  reg rom_sel;
  reg [12:0] flash_in_addr; 

  // AHB slave
  always @(posedge clk) begin
	  if (!(rst_i & mtx_hreset_n)) begin
		  rom_state <= ROM_IDLE;
		  rom_sel <= 1'b0;
	  end else begin
		case (rom_state) 
			ROM_IDLE: begin
				if (targflash0_hsel & targflash0_htrans[1]) begin // NONSEQ/SEQ transfer
					rom_state <= ROM_READ;
					flash_in_addr <= rom_addr;
					rom_sel <= 1'b1;
				end
			end
			ROM_READ: begin
				if (targflash0_hsel & targflash0_htrans[1]) begin // NONSEQ/SEQ transfer
					rom_state <= ROM_OKEY;
					rom_sel <= 1'b0;
				end else begin
				  rom_state <= ROM_IDLE;
				  rom_sel <= 1'b0;
				end
			end
			ROM_OKEY: begin
				if (targflash0_hsel & targflash0_htrans[1]) begin // NONSEQ/SEQ transfer
				  rom_state <= ROM_IDLE;
				  rom_sel <= 1'b0;
				end
			end
		endcase
	end
  end
  assign targflash0_readyout = rom_state == ROM_IDLE;

  // very simple APB bridge: decode only second APB address 0x4000250
  wire psel2;
  assign psel2 = apbtargexp2_psel && (apbtargexp2_paddr[11:8] == 4'h5); // 0x40002 >5< 00


  // SPI device
  wire spi_status;
  reg spi_msb;
  reg spi_start;
  reg [7:0] spi_WDATA;
  reg [9:0] spi_tmp_wdata;
  assign spi_OUT = spi_msb ? spi_tmp_wdata[9] : spi_tmp_wdata[0];
  reg spi_clk;
  assign spi_SCL = spi_clk;

  assign led[0] = spi_start;
  assign led[1] = spi_status;
  assign led[2] = psel2;

  // spi clock
  reg [4:0] spi_clk_cnt;
  always @(posedge clk or negedge rst_i) begin
	  spi_clk <= 1'b1;
	  spi_status <= 1'b0;
	  if (!rst_i) begin
		  spi_clk <= 1'b1;
		  spi_clk_cnt <= 5'd0;
	  end else begin
		  if (spi_start) begin
			spi_clk_cnt <= 5'd16;
			spi_status <= 1'b1;
		  end else begin
			  if (spi_clk_cnt != 5'd0) begin
				spi_status <= 1'b1;
				spi_clk_cnt <= spi_clk_cnt - 1'b1;
				spi_clk <= ~spi_clk;
			end
		  end
	  end
  end

  // spi data
  always @(posedge clk or negedge rst_i) begin
	  if (!rst_i) begin
		spi_tmp_wdata <= 8'b0;
	  end else begin
		  if (spi_start) begin
			  spi_tmp_wdata[8:1] <= spi_WDATA;
		  end else begin
			  if (spi_status && (spi_clk)) begin
				  spi_tmp_wdata <= spi_msb ? {spi_tmp_wdata[8:0], 1'b0} : {1'b0, spi_tmp_wdata[9:1]};
			  end
		  end
	  end
  end

  // APB slave device
  // One can use apbtargexp2_paddr[7:0] for master 1 registers.
  localparam APB_IDLE  = 2'b00;
  localparam APB_WRITE = 2'b01;
  localparam APB_READ  = 2'b10;
  reg [1:0] apb_slave_state;
  always @(posedge clk or negedge rst_i) begin
	  spi_start <= 1'b0;
	  if (!rst_i) begin
		  apb_slave_state <= APB_IDLE;
		  apbtargexp2_pready <= 1'b0;
		  apbtargexp2_prdata <= {32{1'b0}};
      end else begin
		  case (apb_slave_state)
			  APB_IDLE: begin
				apbtargexp2_pready <= 1'b0;
				apbtargexp2_prdata <= {32{1'b0}};
				if (psel2) begin
					if (apbtargexp2_pwrite) begin
						apb_slave_state <= APB_WRITE;
					end else begin
						apb_slave_state <= APB_READ;
					end
				end
			  end
			  APB_WRITE: begin
				  if (psel2 && apbtargexp2_pwrite) begin 
					  apbtargexp2_pready <= 1'b1;
					  if (|apbtargexp2_paddr[7:0]) begin  // any addr != 0 
						  spi_WDATA <= apbtargexp2_pwdata[7:0];
						  spi_start <= 1'b1;
					  end else begin
						  spi_msb <= apbtargexp2_pwdata[0];
					  end
				  end
		          apb_slave_state <= APB_IDLE;
			  end
			  APB_READ: begin
				  if (psel2 && !apbtargexp2_pwrite) begin // return the spi status
					  apbtargexp2_pready <= 1'b1;
					  if (!(|apbtargexp2_paddr[7:0])) begin 
				          apbtargexp2_prdata[0] <= spi_status;
				      end
				  end
		          apb_slave_state <= APB_IDLE;
			  end
			  default: begin
				  apb_slave_state <= APB_IDLE;
			  end
		  endcase
	  end
  end

  assign mode_led = spi_status;

  FLASH256K rom(
    .DOUT(rom_out[31:0]),
    .XADR(flash_in_addr[12:6]),
    .YADR(flash_in_addr[5:0]),
    .XE(rst_i),
    .YE(rst_i),
    .SE(rom_sel),
    .ERASE(GND),
    .PROG(GND),
    .NVSTR(GND),
    .DIN({32{GND}}) 
  );

  // RAM 4 block of 2K
  // Inferring will probably also work, but with primitives it is somehow easier for me.
  SDPB ram_0 (
    .DO({dummy_sram0_rdata_0, sram0_rdata[7:0]}),
    .DI({{24{GND}}, sram0_wdata[7:0]}),
    .BLKSELA({GND, GND, sram0_cs}),
    .BLKSELB({GND, GND, sram0_cs}),
    .ADA({sram0_addr, GND,GND,GND}),
    .ADB({sram0_addr, GND,GND,GND}),
    .CLKA(clk),
    .CLKB(clk),
    .CEA(sram0_wren[0]),
    .CEB(!sram0_wren[0]),
    .OCE(VCC),
    .RESETA(GND),
    .RESETB(!rst_i) 
  );
  defparam ram_0.BIT_WIDTH_0=8;
  defparam ram_0.BIT_WIDTH_1=8;
  defparam ram_0.BLK_SEL_0=3'b001;
  defparam ram_0.BLK_SEL_1=3'b001;
  defparam ram_0.READ_MODE=1'b0;
  defparam ram_0.RESET_MODE="SYNC";

  SDPB ram_1 (
    .DO({dummy_sram0_rdata_1, sram0_rdata[15:8]}),
    .DI({{24{GND}}, sram0_wdata[15:8]}),
    .BLKSELA({GND, GND, sram0_cs}),
    .BLKSELB({GND, GND, sram0_cs}),
    .ADA({sram0_addr, GND,GND,GND}),
    .ADB({sram0_addr, GND,GND,GND}),
    .CLKA(clk),
    .CLKB(clk),
    .CEA(sram0_wren[1]),
    .CEB(!sram0_wren[1]),
    .OCE(VCC),
    .RESETA(GND),
    .RESETB(!rst_i) 
  );
  defparam ram_1.BIT_WIDTH_0=8;
  defparam ram_1.BIT_WIDTH_1=8;
  defparam ram_1.BLK_SEL_0=3'b001;
  defparam ram_1.BLK_SEL_1=3'b001;
  defparam ram_1.READ_MODE=1'b0;
  defparam ram_1.RESET_MODE="SYNC";

  SDPB ram_2 (
    .DO({dummy_sram0_rdata_2, sram0_rdata[23:16]}),
    .DI({{24{GND}}, sram0_wdata[23:16]}),
    .BLKSELA({GND, GND, sram0_cs}),
    .BLKSELB({GND, GND, sram0_cs}),
    .ADA({sram0_addr, GND,GND,GND}),
    .ADB({sram0_addr, GND,GND,GND}),
    .CLKA(clk),
    .CLKB(clk),
    .CEA(sram0_wren[2]),
    .CEB(!sram0_wren[2]),
    .OCE(VCC),
    .RESETA(GND),
    .RESETB(!rst_i) 
  );
  defparam ram_2.BIT_WIDTH_0=8;
  defparam ram_2.BIT_WIDTH_1=8;
  defparam ram_2.BLK_SEL_0=3'b001;
  defparam ram_2.BLK_SEL_1=3'b001;
  defparam ram_2.READ_MODE=1'b0;
  defparam ram_2.RESET_MODE="SYNC";

  SDPB ram_3 (
    .DO({dummy_sram0_rdata_3, sram0_rdata[31:24]}),
    .DI({{24{GND}}, sram0_wdata[31:24]}),
    .BLKSELA({GND, GND, sram0_cs}),
    .BLKSELB({GND, GND, sram0_cs}),
    .ADA({sram0_addr, GND,GND,GND}),
    .ADB({sram0_addr, GND,GND,GND}),
    .CLKA(clk),
    .CLKB(clk),
    .CEA(sram0_wren[3]),
    .CEB(!sram0_wren[3]),
    .OCE(VCC),
    .RESETA(GND),
    .RESETB(!rst_i) 
  );
  defparam ram_3.BIT_WIDTH_0=8;
  defparam ram_3.BIT_WIDTH_1=8;
  defparam ram_3.BLK_SEL_0=3'b001;
  defparam ram_3.BLK_SEL_1=3'b001;
  defparam ram_3.READ_MODE=1'b0;
  defparam ram_3.RESET_MODE="SYNC";

endmodule
