// N picorv32 cores fed from a shift register, outputs xor-reduced to one pin.
// yosys: read_verilog picorv32.v rvx.v; chparam -set N <n> top; synth_gowin -json out.json -family <fam>
module top #(parameter N = 3) (input clk, input din, output reg dout);
    reg [7:0] rst_cnt = 0;
    wire resetn = &rst_cnt;
    always @(posedge clk) if (!resetn) rst_cnt <= rst_cnt + 1;
    wire [N-1:0] red;
    genvar i;
    generate for (i = 0; i < N; i = i + 1) begin : core
        reg [64:0] sr;
        always @(posedge clk) sr <= {sr[63:0], i == 0 ? din : core[i-1].sr[64]};
        wire trap, mem_valid, mem_instr, mem_la_read, mem_la_write;
        wire [31:0] mem_addr, mem_wdata, mem_la_addr, mem_la_wdata, eoi;
        wire [3:0] mem_wstrb, mem_la_wstrb;
        picorv32 #(.ENABLE_IRQ(1), .ENABLE_MUL(0), .ENABLE_DIV(0)) cpu (
            .clk(clk), .resetn(resetn), .trap(trap),
            .mem_valid(mem_valid), .mem_instr(mem_instr), .mem_ready(sr[0]),
            .mem_addr(mem_addr), .mem_wdata(mem_wdata), .mem_wstrb(mem_wstrb), .mem_rdata(sr[32:1]),
            .mem_la_read(mem_la_read), .mem_la_write(mem_la_write), .mem_la_addr(mem_la_addr),
            .mem_la_wdata(mem_la_wdata), .mem_la_wstrb(mem_la_wstrb), .irq(sr[64:33]), .eoi(eoi));
        reg r;
        always @(posedge clk) r <= ^{trap, mem_valid, mem_instr, mem_la_read, mem_la_write, mem_addr, mem_wdata,
                                     mem_la_addr, mem_la_wdata, eoi, mem_wstrb, mem_la_wstrb};
        assign red[i] = r;
    end endgenerate
    always @(posedge clk) dout <= ^red;
endmodule
