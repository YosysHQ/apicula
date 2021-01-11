DEVICE ?= GW1N-9
PN ?= GW1NR-UV9QN881C6/I5
BOARD ?= tec0117

all: attosoc.fs blinky.fs

%.fs: %.pnr.json
	gowin_pack -d ${DEVICE} -o $@ $^
	cp $@ ${BOARD}-$@

%.pnr.json: %.json
	nextpnr-gowin --json $^ --write $@ --device ${PN} --cst ${BOARD}.cst

attosoc.json: attosoc/attosoc.v attosoc/picorv32.v
	yosys -p "synth_gowin -json $@" $^

%.json: %.v
	yosys -p "synth_gowin -json $@" $^

prog:
	openFPGALoader -b littleBee -r -f blinky.fs

clean:
	rm -f *.json *.fs

.PHONY: prog clean
