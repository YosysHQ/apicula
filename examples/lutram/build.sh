#!/bin/sh

yosys -p "read_verilog lutram.v; read_verilog prbs.v; read_verilog top.v; synth_gowin -json lutram.json"
nextpnr-gowin --json lutram.json --write lutram-tec0117-synth.json --device GW1NR-LV9QN88C6/I5 --cst ../tec0117.cst
gowin_pack -d GW1N-9 -o lutram-tec0117.fs lutram-tec0117-synth.json
