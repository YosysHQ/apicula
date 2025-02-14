.equ IO_BASE, 0x400000  
.equ IO_LEDS,           4
.equ IO_UART_DAT,       8
.equ IO_UART_CTRL,     16
.equ USERFLASH_BASE, 0x800000

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

print_4_bytes:
    addi sp, sp, -8
    sw  ra, 4(sp)
	sw  s1, 0(sp)
	
	mv  s1, a0
	srli a0, a0, 16
	call print_2_bytes

	li t0, 0xffff
	and a0, s1, t0
	call print_2_bytes

    lw  s1, 0(sp)
    lw  ra, 4(sp)
    addi sp, sp, 8
    ret

.globl main
rnd:	# xorshift rnd generator
	slli a0, s11, 13
	xor s11, s11, a0
	srli a0, s11, 17
	xor s11, s11, a0
	slli a0, s11, 5
	xor s11, s11, a0
	mv a0, s11
	ret
main:
	li s2, USERFLASH_BASE
	la a0, hello_str
	call puts
	call put_eol

	# Erase/Write
	la a0, erase_write_title
	call puts
	call put_eol
	li s11, 0xcafe # init rnd
	
	mv s3, zero
	li s4, 304*64*4
	add s6, s3, s2
.L20:
	andi t1, s3, 2047 # 2048 bytes per page
	bnez t1, .L21
	sb a0, (s6) # writing byte erases page
	li a0, '.'
	call putc
.L21:
	li s5, 512 # 2048/4
.L22:
	call rnd
	sw a0, (s6)
	add s3, s3, 4
	add s5, s5, -1
	add s6, s3, s2
	bnez s5, .L22
	bne s3, s4, .L20

	call put_eol

	# Read back
	la a0, read_title
	call puts
	call put_eol
	li s11, 0xcafe # init rnd
	mv s3, zero
	li s4, 304
.L1:
	slli a0, s3, 6
	call print_4_bytes
	la a0, colon_space
	call puts

	mv s5, zero
	li s6, 64
.L0:	
	# read flash
	call rnd
	mv t1, a0
	slli t0, s3, 6
	add t0, t0, s5
	add t0, t0, s2
	lw t0, (t0)
    li a0, '.'
	beq t0, t1, .L2
	li a0, 'X'
.L2:
	call putc
	call putc
	call putc
	call putc

    add s5, s5, 4
	bne s5, s6, .L0

	call put_eol

	add s3, s3, 1
	bne s3, s4, .L1
	

.L10:
	j .L10

hello_str:	.asciz "Apicula. Simple UserFlash test: Erase everything, write a pseudo-random number to each address, and then read it back."
erase_write_title: .asciz "Erase page by page and write random numbers..."
read_title: .asciz "Read the entire UserFlash, each '.' represents a match with the 4 bytes written, each 'X' represents a failure."
colon_space: .asciz ": "
