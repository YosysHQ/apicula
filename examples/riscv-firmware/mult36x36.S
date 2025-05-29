.equ IO_BASE, 0x400000  
.equ IO_LEDS,           4
.equ IO_UART_DAT,       8
.equ IO_UART_CTRL,     16
.equ IO_DSP_CLK,       32
.equ IO_DSP_OUT_L,     64
.equ IO_DSP_OUT_H,    128
.equ IO_DSP_OUT_L1,   256 
.equ IO_DSP_OUT_H1,   512
.equ IO_DSP_OUT_L2,  1024
.equ IO_DSP_OUT_H2,  2048
.equ IO_DSP_OUT_L3,  4096
.equ IO_DSP_OUT_H3,  8192
.equ IO_DSP_OUT_L4, 16384
.equ IO_DSP_OUT_H4, 32768

.section .text

putc:
	sw	a0, IO_UART_DAT(gp)
	li	t0, 512
0:
	lw	t1,	IO_UART_CTRL(gp)
	and	t1,	t1,	t0
	bnez t1, 0b
	ret

puts:
	addi sp, sp, -4
	sw	ra, 0(sp)
	mv  t2, a0
0:
	lbu	a0, 0(t2)
	beqz a0, 1f
	call putc
	addi t2, t2, 1
	j	0b
1:
	lw	ra, 0(sp)
	addi sp, sp, 4
	ret

put_eol:
	addi sp, sp, -4
	sw	ra, 0(sp)

	li a0, 0xa
	call putc

	lw	ra, 0(sp)
	addi sp, sp, 4
	ret

hex:		.ascii "0123456789abcdef"
print_byte_hex:
    addi sp, sp, -4
    sw  ra, 0(sp)

    la  t5, hex
    mv  t3, a0

    srli a0, a0, 4
    add t4, t5, a0
    lbu a0, 0(t4)
    call putc

    andi a0, t3, 0xf
    add t4, t5, a0
    lbu a0, 0(t4)
    call putc

    lw  ra, 0(sp)
    addi sp, sp, 4
    ret

print_2_bytes:
    addi sp, sp, -8
    sw  ra, 4(sp)
	sw  s1, 0(sp)
	
	mv  s1, a0
	srli a0, a0, 8
	call print_byte_hex

	andi a0, s1, 0xff
	call print_byte_hex

    lw  s1, 0(sp)
    lw  ra, 4(sp)
    addi sp, sp, 8
    ret

print_dsp_out_h:
    addi sp, sp, -4
    sw  ra, 0(sp)

	andi a0, a0, 0xff
	call print_byte_hex
	
    lw  ra, 0(sp)
    addi sp, sp, 4
    ret

print_dsp_out_l:
    addi sp, sp, -4
    sw  ra, 0(sp)

	mv t2, a0
	srli a0, t2, 24
	call print_byte_hex
	srli a0, t2, 16
	andi a0, a0, 0xff
	call print_byte_hex
	srli a0, t2, 8
	andi a0, a0, 0xff
	call print_byte_hex
	andi a0, t2, 0xff
	call print_byte_hex
	
    lw  ra, 0(sp)
    addi sp, sp, 4
    ret


.globl main
main:
.L0:
	la  a0, hello_str
	call puts

.L1:
	la  a0, m0_str
	call puts
	lw	a0, IO_DSP_OUT_L1(gp)
	call print_dsp_out_h
	lw	a0, IO_DSP_OUT_H(gp)
	call print_dsp_out_l
	lw	a0, IO_DSP_OUT_L(gp)
	call print_dsp_out_l
	la  a0, m0_end_str
	call puts

	la  a0, m1_str
	call puts
	li	a0, IO_DSP_OUT_L3
	add a0, a0, gp
	lw a0, 0(a0)
	call print_dsp_out_h
	li	a0, IO_DSP_OUT_H2
	add a0, a0, gp
	lw a0, 0(a0)
	call print_dsp_out_l
	lw	a0, IO_DSP_OUT_L2(gp)
	call print_dsp_out_l
	la  a0, m1_end_str
	call puts

	call wait
	call wait
	call wait
	call wait

	la a0, iter_str
	call puts

	# clk
	sw a0, IO_DSP_CLK(gp)

	j .L1

hello_str:	.asciz "Apicula. MULT36X36.\n"
iter_str:   .asciz "--- tick ---\n"
hex_str:    .asciz "0x"
m0_str:		.asciz "0x412345678 * 0x187654321 = 0x"
m0_end_str: .asciz " <- must be '0x6396a300170b88d78'\n"
m1_str:		.asciz "-0x514233241 * -0x234567 = 0x"
m1_end_str: .asciz " settle down to '0xb321487597bd27'\n"

