//Copyright (C)2014-2019 GOWIN Semiconductor Corporation.
//All rights reserved.
//File Title: Timing Constraints file
//GOWIN Version: 1.9.1.01 Beta
//Created Time: 2019-08-06 14:29:38
create_clock -name clock -period 10 -waveform {0 5} [get_ports {clk}]
