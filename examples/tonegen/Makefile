YOSYS ?= yosys
NEXTPNR ?= nextpnr-gowin

all: tonegen-tec0117.fs

unpacked: tonegen-tec0117-unpacked.v
	
clean:
	rm -f *.json *.fs *-unpacked.v
	
.PHONY: all clean

%-tec0117.fs: %-tec0117.json
	gowin_pack -d GW1N-9 -o $@ $<

%-tec0117.json: %-tec0117-synth.json tec0117.cst
	$(NEXTPNR) --json $< --write $@ --device GW1NR-LV9QN88C6/I5 --cst tec0117.cst

%-tec0117-synth.json: %.v
	$(YOSYS) -D LEDS_NR=8 -p "read_verilog $^; synth_gowin -json $@"

%-tec0117-prog: %-tec0117.fs
	openFPGALoader -b tec0117 $^

%-tec0117-unpacked.v: %-tec0117.fs
	gowin_unpack -d GW1N-9 -o $@ $^
