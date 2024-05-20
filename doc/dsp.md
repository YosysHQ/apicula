# DSP
## Accumulator in ALU and modes

The diagram in the Gowin documentation shows many things that are not described anywhere and which are not clear how to use (see, for example, RND_INIT and RND_INIT-1 - there must be some very funny signals). But it will definitely shed light on some interesting details.

![DSP ALU54D diagram](fig/dsp-alu.png)
ALU can operate in three modes:

 - 0: accumulator value +/- A +/- B
 - 1: accumulator value +/- B + CASI
 - 2: A +/- B + CASI

Why exactly such modes is connected with the organization of the accumulator itself - it is formed from the REGOUT register and one of the MUXs: C_MUX or A_MUX, which can receive a signal from the ALU output.
B_MUX does not have this feature and is therefore used in all three modes.

If we use A as an operand, then the accumulator is formed using C_MUX, and if we need CASI, then using A_MUX, but then we can no longer use A.

And another interesting point follows from the diagram: REGOUT must function as a register, that is, the parameter of the OUT_REG primitive must be set to 1'b1. If this is not done, the accumulator simply will not function properly.

