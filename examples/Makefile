honeycomb_leds=3
runber_leds=8
tangnano_leds=3
tec0117_leds=8

all: attosoc-tec0117.fs blinky-tec0117.fs blinky-runber.fs blinky-tangnano.fs blinky-honeycomb.fs

%-tec0117.fs: %-tec0117.json
	gowin_pack -d GW1N-9 -o $@ $^

%-tec0117.json: %-tec0117-synth.json
	nextpnr-gowin --json $^ --write $@ --device GW1NR-UV9QN881C6/I5 --cst tec0117.cst

%-runber.fs: %-runber.json
	gowin_pack -d GW1N-4 -o $@ $^

%-runber.json: %-runber-synth.json
	nextpnr-gowin --json $^ --write $@ --device GW1N-UV4LQ144C6/I5 --cst runber.cst

%-tangnano.fs: %-tangnano.json
	gowin_pack -d GW1N-1 -o $@ $^

%-tangnano.json: %-tangnano-synth.json
	nextpnr-gowin --json $^ --write $@ --device GW1N-LV1QN48C6/I5 --cst tangnano.cst

%-honeycomb.fs: %-honeycomb.json
	gowin_pack -d GW1NS-2 -o $@ $^

%-honeycomb.json: %-honeycomb-synth.json
	nextpnr-gowin --json $^ --write $@ --device GW1NS-UX2CQN48C5/I4 --cst honeycomb.cst

attosoc-tec0117-synth.json: attosoc/attosoc.v attosoc/picorv32.v
	yosys -p "synth_gowin -json $@" $^

nanolcd-tangano-synth.json: nanolcd/TOP.v nanolcd/VGAMod.v
	yosys -p "synth_gowin -json $@" $^

%-synth.json: blinky.v
	yosys -D LEDS_NR=$($(shell echo $(@) | cut -d\- -f 2)_leds) \
		-p "synth_gowin -json $@" $^

%-honeycomb-prog: %-honeycomb.fs
	openFPGALoader -b honeycomb $^

%-tec0117-prog: %-tec0117.fs
	openFPGALoader -b tec0117 $^

%-runber-prog: %-runber.fs
	openFPGALoader -b runber $^

%-tangnano-prog: %-tangnano.fs
	openFPGALoader -b tangnano $^

clean:
	rm -f *.json *.fs

.PHONY: %-tangnano-prog clean all
