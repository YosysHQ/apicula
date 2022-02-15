YOSYS ?= yosys
NEXTPNR ?= nextpnr-gowin

all: attosoc-tec0117.fs nanolcd-tangnano.fs blinky-tec0117.fs blinky-runber.fs \
	blinky-tangnano.fs blinky-honeycomb.fs shift-tec0117.fs shift-runber.fs \
	shift-tangnano.fs shift-honeycomb.fs iob-tangnano.fs iob-default-flags-tangnano.fs \
	tonegen-tec0117.fs blinky-tangnano9k.fs blinky-tangnano1k.fs

unpacked: attosoc-tec0117-unpacked.v nanolcd-tangnano-unpacked.v blinky-tec0117-unpacked.v blinky-runber-unpacked.v \
	blinky-tangnano-unpacked.v blinky-honeycomb-unpacked.v shift-tec0117-unpacked.v shift-runber-unpacked.v \
	shift-tangnano-unpacked.v shift-honeycomb-unpacked.v iob-tangnano-unpacked.v iob-default-flags-tangnano-unpacked.v \
	tonegen-tec0117-unpacked.v
	
clean:
	rm -f *.json *.fs *-unpacked.v
	
.PHONY: all clean

%-tec0117.fs: %-tec0117.json
	gowin_pack -d GW1N-9 -o $@ $<

%-tec0117.json: %-tec0117-synth.json tec0117.cst
	$(NEXTPNR) --json $< --write $@ --device GW1NR-LV9QN88C6/I5 --cst tec0117.cst

%-runber.fs: %-runber.json
	gowin_pack -d GW1N-4 -o $@ $<

%-runber.json: %-runber-synth.json runber.cst
	$(NEXTPNR) --json $< --write $@ --device GW1N-UV4LQ144C6/I5 --cst runber.cst

%-tangnano.fs: %-tangnano.json
	gowin_pack -d GW1N-1 -o $@ $^

%-tangnano.json: %-tangnano-synth.json tangnano.cst
	$(NEXTPNR) --json $< --write $@ --device GW1N-LV1QN48C6/I5 --cst tangnano.cst

%-default-flags-tangnano.json: %-tangnano-synth.json
	$(NEXTPNR) --json $^ --write $@ --device GW1N-LV1QN48C6/I5 \
		--cst iob/tangnano-default.cst

%-tangnano1k.fs: %-tangnano1k.json
	gowin_pack -d GW1NZ-1 -o $@ $^

%-tangnano1k.json: %-tangnano1k-synth.json tangnano1k.cst
	$(NEXTPNR) --json $< --write $@ --device GW1NZ-LV1QN48C6/I5 --family GW1NZ-1 --cst tangnano1k.cst

%-tangnano4k.fs: %-tangnano4k.json
	gowin_pack -d GW1NS-4 -o $@ $^

%-tangnano4k.json: %-tangnano4k-synth.json tangnano4k.cst
	$(NEXTPNR) --json $< --write $@ --device GW1NSR-LV4CQN48PC7/I6 --cst tangnano4k.cst

%-tangnano9k.fs: %-tangnano9k.json
	gowin_pack -d GW1N-9C -o $@ $^

%-tangnano9k.json: %-tangnano9k-synth.json tangnano9k.cst
	$(NEXTPNR) --json $< --write $@ --device GW1NR-LV9QN88PC6/I5 --family GW1N-9C --cst tangnano9k.cst

%-honeycomb.fs: %-honeycomb.json
	gowin_pack -d GW1NS-2 -o $@ $<

%-honeycomb.json: %-honeycomb-synth.json honeycomb.cst
	$(NEXTPNR) --json $< --write $@ --device GW1NS-UX2CQN48C5/I4 --cst honeycomb.cst

attosoc-tec0117-synth.json: attosoc/attosoc.v attosoc/picorv32.v
	$(YOSYS) -p "read_verilog $^; synth_gowin -json $@"

tonegen-tec0117-synth.json: tonegen/top.v tonegen/sddac.v tonegen/cordic.v
	$(YOSYS) -p "read_verilog $^; synth_gowin -json $@"

nanolcd-tangnano-synth.json: nanolcd/TOP.v nanolcd/VGAMod.v
	$(YOSYS) -p "read_verilog $^; synth_gowin -json $@"

%-tec0117-synth.json: %.v
	$(YOSYS) -D LEDS_NR=8 -p "read_verilog $^; synth_gowin -json $@"

%-runber-synth.json: %.v
	$(YOSYS) -D LEDS_NR=8 -p "read_verilog $^; synth_gowin -json $@"

%-tangnano-synth.json: %.v
	$(YOSYS) -D LEDS_NR=3 -p "read_verilog $^; synth_gowin -json $@"

%-tangnano1k-synth.json: %.v
	$(YOSYS) -D LEDS_NR=3 -p "read_verilog $^; synth_gowin -json $@"

%-tangnano4k-synth.json: %.v
	$(YOSYS) -D LEDS_NR=8 -p "read_verilog $^; synth_gowin -json $@"

%-tangnano9k-synth.json: %.v
	$(YOSYS) -D LEDS_NR=6 -p "read_verilog $^; synth_gowin -json $@"

%-honeycomb-synth.json: %.v
	$(YOSYS) -D LEDS_NR=3 -p "read_verilog $^; synth_gowin -json $@"

%-honeycomb-prog: %-honeycomb.fs
	openFPGALoader -b honeycomb $^

%-tec0117-prog: %-tec0117.fs
	openFPGALoader -b tec0117 $^

%-runber-prog: %-runber.fs
	openFPGALoader -b runber $^

%-tangnano-prog: %-tangnano.fs
	openFPGALoader -b tangnano $^
	
%-tangnano4k-prog: %-tangnano4k.fs
	openFPGALoader -b tangnano4k $^

%-tangnano-unpacked.v: %-tangnano.fs
	gowin_unpack -d GW1N-1 -o $@ $^

%-tangnano4k-unpacked.v: %-tangnano4k.fs
	gowin_unpack -d GW1NS-4 -o $@ $^

%-tangnano9k-unpacked.v: %-tangnano9k.fs
	gowin_unpack -d GW1N-9C -o $@ $^

%-runber-unpacked.v: %-runber.fs
	gowin_unpack -d GW1N-4 -o $@ $^

%-tec0117-unpacked.v: %-tec0117.fs
	gowin_unpack -d GW1N-9 -o $@ $^

%-honeycomb-unpacked.v: %-honeycomb.fs
	gowin_unpack -d GW1NS-2 -o $@ $<

