# longval tables
The table entries are divided into two parts: key and fuses. The key is an ascending ordered list of non-repeating feature codes, padded with zeros to the right up to a length of 16 elements. Fuzes is an ascending ordered list of non-repeating numbers of fuzes, extended to the right by -1 to a length of 12 elements.

The feature codes change from board to board and no common recoding table has been found yet. So all codes below are correct for GW1N-1, for other boards empirical recoding is used (see beginning of file tiled_fuzzer.py). 

In some cases, the key uses an as yet unknown feature that seems to be responsible for configuring the I/O logic. Voltage levels and I/O attributes do not depend on it, so this code is ignored when searching for a entry.

*The GW1N-4 boards stand out --- everything is different for them!*

## IOB tables
Correspondence of table numbers to pin names:

|  A  |  B  |  C  |  D  |  E  |  F  |  G  |  H  |  I  |  J  |
|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| 23  |  24 |  40 |  41 |  42 |  43 |  44 |  45 |  46 |  47 |


Simple IO attributes and their detected features codes, if empty, no fuses are set.

`SLEW_RATE`
| Value | Code |
|:-----:|:----:|
| SLOW  |      |
| FAST  |  42  |

example: `SLEW_RATE=FAST`:
[42, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 3377, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1]


`PULL_MODE`
| Value  | Code |
|:------:|:----:|
| UP     |      |
| NONE   |  45  |
| KEEPER |  44  |
| DOWN   |  43  |

example: `PULL_MODE=DOWN`:
[43, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 3342, 3357, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1]

`HYSTERESIS`
| Value  | Code       |
|:------:|:----------:|
| NONE   |            |
| HIGH   |  {57, 85}  |
| H2L    |  {58, 85}  |
| L2H    |  {59, 85}  |

example: `HYSTERESIS=HIGH`:
[37, 57, 85, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 3352, 3374, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1]

See this *37*? This is the ignored part of the key.

Complex attributes take into account the current I/O standard. But the standard code is only in addition to the attribute code, and does not work as a separate single switch.

IO standard codes
| Value     | Code  |
|:---------:|:-----:|
| LVCMOS33  |  68   |
| LVCMOS25  |  67   |
| LVCMOS18  |  66   |
| LVCMOS15  |  65   |
| LVCMOS12  |  64   |
| SSTL25_I  |  71   |
| SSTL25_II |  71   |
| SSTL33_I  |       |
| SSTL33_II |       |
| SSTL18_I  |  72   |
| SSTL18_II |  72   |
| SSTL15    |  74   |
| HSTL18_I  |  72   |
| HSTL18_II |  72   |
| HSTL15_I  |  74   |
| PCI33     |  69   |

`DRIVE`
| Value | Code  |
|:-----:|:-----:|
|   4   |  48   |
|   8   |  50   |
|  12   |  51   |
|  16   |  52   |
|  24   |  54   |

The code for `DRIVE` is made up of the value from the above table plus {56} plus the standard code.

example: 'IO_TYPE=LVCMOS18, DRIVE=8':
[12, 50, 56, 66, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 3356, 3372, 3375, 3379, 3394, 3397, -1, -1, -1, -1, -1, -1]

`OPEN_DRAIN`
Perhaps the most difficult attribute at the moment. It uses the same fuses as `DRIVE`, setting one of them and clearing the other two. The procedure for determining the fuzes is epirical and is best seen in the tiled_fuzzer.py code.

| Value | Code        |
|:-----:|:-----------:|
|   ON  |  {55, 70}   |

NOISE fuse: {55, 72}

example: 'OPEN_DRAIN=ON':

16mA LVCMOS33 fuse: 

[12, 52, 56, 68, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 3210, 3238, 3245, 3263, 3273, 3281, -1, -1, -1, -1, -1, -1]

ON fuse:

[10, 55, 70, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 3273, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1]

NOISE fuse:

[7, 55, 72, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 3238, 3263, 3273, 3281, -1, -1, -1, -1, -1, -1, -1, -1]

Thus we clear {3210, 3245} and set {3273}.


## Tables of corner tiles
Corner tiles enable I/O banks and set logical levels.

Table 37.

The key includes the bank number, usually unchanged, but there are strange numbers like 10 or 30. which still need to be investigated.

Simple modes are found simply by the standard code:

| Value     | Code  |
|:---------:|:-----:|
| LVCMOS33  |  68   |
| LVCMOS25  |  67   |
| LVCMOS18  |  66   |
| LVCMOS15  |  65   |
| LVCMOS12  |  64   |

example: 'IO_TYPE=LVCMOS15'

[2, 65, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 2797, 2813, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1]


Complex modes are obtained by adding fuse 79:

| Mode      | Fuses  |
|:---------:|:-----------------------:|
| SSTL15    |  fuses(65) + fuses(79)  |
| HSTL18_I  |  fuses(66) + fuses(79)  |
| SSTL25_I  |  fuses(67) + fuses(79)  |
| SSTL33_I  |  fuses(68) + fuses(79)  |

example: 'IO_TYPE=SSTL15'

Fuse 79: 

[3, 79, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 2229, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1]

Fuse 65:

[3, 65, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 2181, 2197, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1]

Thus we set {2181, 2197, 2229}

TODO: Describe the situation when all pins in the bank are working as input
