# Device grouping

You may notice that in Apicula some devices that appear to be part of the same series have a seperate chipdb,
while others use the exact same chipdb, while having different modifiers.
Why is that?

Gowin produces a lot of "system in package" devices. An FPGA die with some wirebonded peripherals such as SDRAM or ARM cores.
The FPGA die in these devices is the same as in their more spartan counterparts, so we only consider the pinout different.
In a few cases the vendor files do appear to be different for unknown reasons.

The guiding principle has been, until proven wrong, to go by the `md5sum` of the vendor files.
For example, it appears that the `GW1NS-2` is different from the `GW1N-2`, but `GW1N-9` and `GW1NR-9` are the same.

```
$ md5sum bin/gowin1.9.8/IDE/share/device/*/*.fse | sort
1577ac9e268488ef0d13e545e4e1bbfa  bin/gowin1.9.8/IDE/share/device/GW1NS-4C/GW1NS-4C.fse
1577ac9e268488ef0d13e545e4e1bbfa  bin/gowin1.9.8/IDE/share/device/GW1NS-4/GW1NS-4.fse
1577ac9e268488ef0d13e545e4e1bbfa  bin/gowin1.9.8/IDE/share/device/GW1NSER-4C/GW1NSER-4C.fse
1577ac9e268488ef0d13e545e4e1bbfa  bin/gowin1.9.8/IDE/share/device/GW1NSR-4C/GW1NSR-4C.fse
1577ac9e268488ef0d13e545e4e1bbfa  bin/gowin1.9.8/IDE/share/device/GW1NSR-4/GW1NSR-4.fse
1bbc0c22a6ad6a8537b5e62e7f38dc55  bin/gowin1.9.8/IDE/share/device/GW1N-9C/GW1N-9C.fse
1bbc0c22a6ad6a8537b5e62e7f38dc55  bin/gowin1.9.8/IDE/share/device/GW1NR-9C/GW1NR-9C.fse
23e8cbadbed5245d4591000a39e8a714  bin/gowin1.9.8/IDE/share/device/GW1N-4B/GW1N-4B.fse
23e8cbadbed5245d4591000a39e8a714  bin/gowin1.9.8/IDE/share/device/GW1N-4D/GW1N-4D.fse
23e8cbadbed5245d4591000a39e8a714  bin/gowin1.9.8/IDE/share/device/GW1N-4/GW1N-4.fse
23e8cbadbed5245d4591000a39e8a714  bin/gowin1.9.8/IDE/share/device/GW1NR-4B/GW1NR-4B.fse
23e8cbadbed5245d4591000a39e8a714  bin/gowin1.9.8/IDE/share/device/GW1NR-4D/GW1NR-4D.fse
23e8cbadbed5245d4591000a39e8a714  bin/gowin1.9.8/IDE/share/device/GW1NR-4/GW1NR-4.fse
23e8cbadbed5245d4591000a39e8a714  bin/gowin1.9.8/IDE/share/device/GW1NRF-4B/GW1NRF-4B.fse
367aacd3777db1ae2f82d3d244ef9b46  bin/gowin1.9.8/IDE/share/device/GW1N-1/GW1N-1.fse
367aacd3777db1ae2f82d3d244ef9b46  bin/gowin1.9.8/IDE/share/device/GW1NR-1/GW1NR-1.fse
4416a5e0226fba7036d1a4a47bd4e3ef  bin/gowin1.9.8/IDE/share/device/GW2AN-18X/GW2AN-18X.fse
4416a5e0226fba7036d1a4a47bd4e3ef  bin/gowin1.9.8/IDE/share/device/GW2AN-4X/GW2AN-4X.fse
4416a5e0226fba7036d1a4a47bd4e3ef  bin/gowin1.9.8/IDE/share/device/GW2AN-9X/GW2AN-9X.fse
4e23e1797693721610674e964cd550f1  bin/gowin1.9.8/IDE/share/device/GW1N-1P5B/GW1N-1P5B.fse
4e23e1797693721610674e964cd550f1  bin/gowin1.9.8/IDE/share/device/GW1N-1P5/GW1N-1P5.fse
4e23e1797693721610674e964cd550f1  bin/gowin1.9.8/IDE/share/device/GW1N-2B/GW1N-2B.fse
4e23e1797693721610674e964cd550f1  bin/gowin1.9.8/IDE/share/device/GW1N-2/GW1N-2.fse
4e23e1797693721610674e964cd550f1  bin/gowin1.9.8/IDE/share/device/GW1NR-2B/GW1NR-2B.fse
4e23e1797693721610674e964cd550f1  bin/gowin1.9.8/IDE/share/device/GW1NR-2/GW1NR-2.fse
4e23e1797693721610674e964cd550f1  bin/gowin1.9.8/IDE/share/device/GW1NZR-2/GW1NZR-2.fse
55cfc48170a50c08f30b0b46e773669d  bin/gowin1.9.8/IDE/share/device/GW2A-18C/GW2A-18C.fse
55cfc48170a50c08f30b0b46e773669d  bin/gowin1.9.8/IDE/share/device/GW2ANR-18C/GW2ANR-18C.fse
55cfc48170a50c08f30b0b46e773669d  bin/gowin1.9.8/IDE/share/device/GW2AR-18C/GW2AR-18C.fse
5e1dcd76d79c23e800834c38aba9c018  bin/gowin1.9.8/IDE/share/device/GW1NS-2C/GW1NS-2C.fse
5e1dcd76d79c23e800834c38aba9c018  bin/gowin1.9.8/IDE/share/device/GW1NS-2/GW1NS-2.fse
5e1dcd76d79c23e800834c38aba9c018  bin/gowin1.9.8/IDE/share/device/GW1NSE-2C/GW1NSE-2C.fse
5e1dcd76d79c23e800834c38aba9c018  bin/gowin1.9.8/IDE/share/device/GW1NSR-2C/GW1NSR-2C.fse
5e1dcd76d79c23e800834c38aba9c018  bin/gowin1.9.8/IDE/share/device/GW1NSR-2/GW1NSR-2.fse
80cc685196264afd8358274228e3a0a3  bin/gowin1.9.8/IDE/share/device/GW2A-55C/GW2A-55C.fse
80cc685196264afd8358274228e3a0a3  bin/gowin1.9.8/IDE/share/device/GW2A-55/GW2A-55.fse
80cc685196264afd8358274228e3a0a3  bin/gowin1.9.8/IDE/share/device/GW2AN-55C/GW2AN-55C.fse
9f5ef5e4a8530ea5bbda62cd746e675a  bin/gowin1.9.8/IDE/share/device/GW2A-18/GW2A-18.fse
9f5ef5e4a8530ea5bbda62cd746e675a  bin/gowin1.9.8/IDE/share/device/GW2AR-18/GW2AR-18.fse
a55729d464a7d4c19b05be15768a9936  bin/gowin1.9.8/IDE/share/device/GW1N-1S/GW1N-1S.fse
aa903125ff6270dc8a4315c91b6f2dac  bin/gowin1.9.8/IDE/share/device/GW1N-9/GW1N-9.fse
aa903125ff6270dc8a4315c91b6f2dac  bin/gowin1.9.8/IDE/share/device/GW1NR-9/GW1NR-9.fse
b8ee256646453c2f203707fdd7a6b6b7  bin/gowin1.9.8/IDE/share/device/GW1NZ-1C/GW1NZ-1C.fse
b8ee256646453c2f203707fdd7a6b6b7  bin/gowin1.9.8/IDE/share/device/GW1NZ-1/GW1NZ-1.fse
```
