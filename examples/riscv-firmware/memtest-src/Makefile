all: memtest16.hex memtest48.hex memtest88.hex

clean:
	rm -rf *.o *.hex *.elf

.PHONY: clean all

memtest16.hex: memtest16.bram.elf Makefile
	./firmware_words memtest16.bram.elf -ram 16384 -max_addr 16384 -out memtest16.hex

memtest48.hex: memtest48.bram.elf Makefile
	./firmware_words memtest48.bram.elf -ram 49152 -max_addr 49152 -out memtest48.hex

memtest88.hex: memtest88.bram.elf Makefile
	./firmware_words memtest88.bram.elf -ram 90112 -max_addr 90112 -out memtest88.hex

memtest16.bram.elf: memtest.o wait.o start.o bram16.ld Makefile
	riscv64-none-elf-ld memtest.o wait.o start.o -o memtest16.bram.elf -T bram16.ld -m elf32lriscv -nostdlib -Map=memtest.map

memtest48.bram.elf: memtest.o wait.o start.o bram48.ld Makefile
	riscv64-none-elf-ld memtest.o wait.o start.o -o memtest48.bram.elf -T bram48.ld -m elf32lriscv -nostdlib -Map=memtest.map

memtest88.bram.elf: memtest.o wait.o start.o bram88.ld Makefile
	riscv64-none-elf-ld memtest.o wait.o start.o -o memtest88.bram.elf -T bram88.ld -m elf32lriscv -nostdlib -Map=memtest.map
%.o: %.S
	riscv64-none-elf-as -a=$@.lst -march=rv32i -mabi=ilp32 -mno-relax $< -o $@
