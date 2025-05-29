.equ IO_BASE, 0x400000  
.extern _ram_size
.section .text
.globl start
start:
    li   gp, IO_BASE
	la   sp, _ram_size
	call main
	ebreak
	
