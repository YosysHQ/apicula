
Here are both compiled and source codes for the tiny riscv, which are intended to test the functioning of various DSP ascetics.

Compilation itself is not provided because this imposes too strong requirements on the client environment.
Those interested can read [lesson 20](https://github.com/BrunoLevy/learn-fpga/tree/master/FemtoRV/TUTORIALS/FROM_BLINKER_TO_RISCV#step-20-using-the-gnu-toolchain-to-compile-programs---assembly)


This is an example Makefile that was used to create these .hex files

``` Makefile
mult36x36.hex: mult36x36.bram.elf
    ./firmware_words mult36x36.bram.elf -ram 6144 -max_addr 6144 -out mult36x36.hex

mult36x36.bram.elf: mult36x36.o wait.o start.o
    riscv64-none-elf-ld mult36x36.o wait.o start.o -o mult36x36.bram.elf -T bram.ld -m elf32lriscv -nostdlib

%.o: %.S
    riscv64-none-elf-as -march=rv32i -mabi=ilp32 -mno-relax $< -o $@
```

