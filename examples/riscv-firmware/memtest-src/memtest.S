.equ IO_BASE, 0x400000  
.equ IO_LEDS,           4
.equ IO_UART_DAT,       8
.equ IO_UART_CTRL,     16

.extern _freeram_start
.extern _ram_size

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
	la s2, _freeram_start		# start addr for testing
	la s7, _ram_size			# free mem size
	sub s7, s7, s2
	andi s7, s7, 0xffffffc0     # mod 64 bytes
	mv s10, zero                # flag if there were errors

	la a0, hello_str
	call puts
	call put_eol

	la a0, start_addr_str
	call puts
	mv a0, s2
	call print_4_bytes
	call put_eol

	la a0, size_str
	call puts
	mv a0, s7
	call print_4_bytes
	call put_eol

	# Write
	la a0, write_title
	call puts
	call put_eol
	li s11, 0xcafe # init rnd
	
	mv s3, zero		# s3 - addr index
	mv s4, s7       # s4 - bytes count
	add s6, s3, s2
.L22:
	call rnd
	sw a0, (s6)
	add s3, s3, 4
	add s6, s3, s2
	bne s3, s4, .L22

	call put_eol

	# Read back
	la a0, read_title
	call puts
	call put_eol
	li s11, 0xcafe		# init rnd
	mv s3, zero			# s3 - addr index
	srli s4, s7, 6      # s4 - 64-chank count
.L1:
	slli a0, s3, 6      # print addr
	add a0, a0, s2
	call print_4_bytes
	la a0, colon_space
	call puts

	mv s5, zero
	li s6, 64
.L0:	
	call rnd
	mv t1, a0
	slli t0, s3, 6
	add t0, t0, s5
	add t0, t0, s2
	lw t0, (t0)
    li a0, '.'
	beq t0, t1, .L2
	li a0, 'X'
	li s10, 1
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
	
	la a0, error_str
	bne s10, zero, .L3
	la a0, no_error_str
.L3:
	call puts
	call put_eol
.L10:
	j .L10

hello_str:		.asciz "Apicula. Simple memory test: write a pseudo-random number to each address, and then read it back."
start_addr_str: .asciz "Free memory start:"
size_str:		.asciz "Free memory size:"
write_title:	.asciz "Write random numbers..."
read_title:		.asciz "Read back, each '.' represents a match with the 4 bytes written, each 'X' represents a failure."
colon_space:	.asciz ": "
no_error_str:	.asciz "Memory is OK."
error_str:		.asciz "Memory is bad."
