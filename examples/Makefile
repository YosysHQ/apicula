all: attosoc-tec0117.fs blinky-tec0117.fs blinky-runber.fs blinky-tangnano.fs

%-tec0117.fs: %-tec0117.json
	gowin_pack -d GW1N-9 -o $@ $^

%-tec0117.json: %.json
	nextpnr-gowin --json $^ --write $@ --device GW1NR-UV9QN881C6/I5 --cst tec0117.cst

%-runber.fs: %-runber.json
	gowin_pack -d GW1N-4 -o $@ $^

%-runber.json: %.json
	nextpnr-gowin --json $^ --write $@ --device GW1N-UV4LQ144C6/I5 --cst runber.cst

%-tangnano.fs: %-tangnano.json
	gowin_pack -d GW1N-1 -o $@ $^

%-tangnano.json: %.json
	nextpnr-gowin --json $^ --write $@ --device GW1N-LV1QN48C6/I5 --cst tangnano.cst

attosoc.json: attosoc/attosoc.v attosoc/picorv32.v
	yosys -p "synth_gowin -json $@" $^

%.json: %.v
	yosys -p "synth_gowin -json $@" $^

%-tec0117-prog: %-tec0117.fs
	openFPGALoader -b tec0117 $^

%-runber-prog: %-runber.fs
	openFPGALoader -b runber $^

%-tangnano-prog: %-tangnano.fs
	openFPGALoader -b tangnano $^

clean:
	rm -f *.json *.fs

.PHONY: %-tangnano-prog clean all
