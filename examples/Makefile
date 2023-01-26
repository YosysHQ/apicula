YOSYS ?= yosys
NEXTPNR ?= nextpnr-gowin

.DEFAULT_GOAL := all

all: attosoc-tec0117.fs nanolcd-tangnano.fs blinky-tec0117.fs blinky-runber.fs \
	blinky-tangnano.fs blinky-honeycomb.fs shift-tec0117.fs shift-runber.fs \
	shift-tangnano.fs shift-honeycomb.fs \
	tonegen-tec0117.fs blinky-tangnano9k.fs blinky-tangnano1k.fs blinky-tangnano4k.fs \
	shift-tangnano9k.fs shift-tangnano1k.fs shift-tangnano4k.fs \
	tlvds-tangnano4k.fs tlvds-tangnano9k.fs tlvds-tec0117.fs \
	tlvds-oddr-tangnano4k.fs tlvds-oddr-tangnano9k.fs tlvds-oddr-tec0117.fs \
	blinky-oddr-tec0117.fs blinky-oddr-runber.fs \
	blinky-oddr-tangnano.fs blinky-oddr-honeycomb.fs \
	blinky-oddr-tangnano4k.fs blinky-oddr-tangnano9k.fs \
	blinky-osc-tec0117.fs blinky-osc-runber.fs blinky-osc-tangnano.fs  \
	blinky-osc-honeycomb.fs \
	blinky-osc-tangnano9k.fs blinky-osc-tangnano1k.fs blinky-osc-tangnano4k.fs \
	pll-52-tangnano.fs pll-80-tangnano.fs \
	pll-54-tangnano1k.fs pll-81-tangnano1k.fs \
	pll-dyn-tangnano.fs pll-dyn-tangnano1k.fs \
	pll-tangnano4k.fs pll2-tangnano9k.fs \
	pll-nanolcd-tangnano.fs pll-nanolcd-tangnano9k.fs

unpacked: attosoc-tec0117-unpacked.v nanolcd-tangnano-unpacked.v blinky-tec0117-unpacked.v blinky-runber-unpacked.v \
	blinky-tangnano-unpacked.v blinky-honeycomb-unpacked.v shift-tec0117-unpacked.v shift-runber-unpacked.v \
	shift-tangnano-unpacked.v shift-honeycomb-unpacked.v \
	tonegen-tec0117-unpacked.v blinky-tangnano9k-unpacked.v blinky-tangnano1k-unpacked.v blinky-tangnano4k-unpacked.v \
	shift-tangnano9k-unpacked.v shift-tangnano1k-unpacked.v shift-tangnano4k-unpacked.v \
	tlvds-tangnano4k-unpacked.v tlvds-tangnano9k-unpacked.v tlvds-tec0117-unpacked.v \
	tlvds-oddr-tangnano4k-unpacked.v tlvds-oddr-tangnano9k-unpacked.v tlvds-oddr-tec0117-unpacked.v \
	blinky-oddr-tec0117-unpacked.v blinky-oddr-runber-unpacked.v \
	blinky-oddr-tangnano-unpacked.v blinky-oddr-honeycomb-unpacked.v \
	blinky-oddr-tangnano-unpacked.v blinky-oddr-honeycomb-unpacked.v \
	blinky-oddr-tangnano4k-unpacked.v blinky-oddr-tangnano9k-unpacked.v \
	blinky-osc-tec0117-unpacked.v blinky-osc-runber-unpacked.v blinky-osc-tangnano-unpacked.v \
	blinky-osc-honeycomb-unpacked.v \
	blinky-osc-tangnano9k-unpacked.v blinky-osc-tangnano1k-unpacked.v blinky-osc-tangnano4k-unpacked.v \
	pll-52-tangnano-unpacked.v pll-80-tangnano-unpacked.v \
	pll-54-tangnano1k-unpacked.v pll-81-tangnano1k-unpacked.v \
	pll-dyn-tangnano-unpacked.v pll-dyn-tangnano1k-unpacked.v \
	pll2-tangnano9k-unpacked.v \
	pll-nanolcd-tangnano-unpacked.v pll-nanolcd-tangnano9k-unpacked.v pll-tangnano4k-unpacked.v
	
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

blinky-oddr-runber.json: blinky-oddr-runber-synth.json runber-tlvds.cst
	$(NEXTPNR) --json $< --write $@ --device GW1N-UV4LQ144C6/I5 --cst runber-tlvds.cst

%-tangnano.fs: %-tangnano.json
	gowin_pack -d GW1N-1 -o $@ $^

%-tangnano.json: %-tangnano-synth.json tangnano.cst
	$(NEXTPNR) --json $< --write $@ --device GW1N-LV1QN48C6/I5 --cst tangnano.cst

%-tangnano1k.fs: %-tangnano1k.json
	gowin_pack -d GW1NZ-1 -o $@ $^

%-tangnano1k.json: %-tangnano1k-synth.json tangnano1k.cst
	$(NEXTPNR) --json $< --write $@ --device GW1NZ-LV1QN48C6/I5 --family GW1NZ-1 --cst tangnano1k.cst

%-tangnano4k.fs: %-tangnano4k.json
	gowin_pack -d GW1NS-4 -o $@ $^

%-tangnano4k.json: %-tangnano4k-synth.json tangnano4k.cst
	$(NEXTPNR) --json $< --write $@ --device GW1NSR-LV4CQN48PC7/I6 --cst tangnano4k.cst

pll-tangnano4k.json: pll-tangnano4k-synth.json tangnano4k.cst
	$(NEXTPNR) --json $< --write $@ --device GW1NSR-LV4CQN48PC7/I6 --cst tangnano4k.cst

%-tangnano9k.fs: %-tangnano9k.json
	gowin_pack -d GW1N-9C -o $@ $^

pll-nanolcd-tangnano9k.fs: pll-nanolcd-tangnano9k.json
	gowin_pack -d GW1N-9C --sspi_as_gpio --mspi_as_gpio -o $@ $^

%-tangnano9k.json: %-tangnano9k-synth.json tangnano9k.cst
	$(NEXTPNR) --json $< --write $@ --device GW1NR-LV9QN88PC6/I5 --family GW1N-9C --cst tangnano9k.cst

%-honeycomb.fs: %-honeycomb.json
	gowin_pack -d GW1NS-2 -o $@ $<

%-honeycomb.json: %-honeycomb-synth.json honeycomb.cst
	$(NEXTPNR) --json $< --write $@ --device GW1NS-UX2CQN48C5/I4 --cst honeycomb.cst

attosoc-tec0117-synth.json: attosoc/attosoc.v attosoc/picorv32.v
	$(YOSYS) -p "read_verilog $^; synth_gowin -json $@"

lutram-tec0117-synth.json: lutram/lutram.v lutram/prbs.v lutram/top.v
	$(YOSYS) -p "read_verilog $^; synth_gowin -nolutram -json $@"

attosoc-tangnano9k-synth.json: attosoc/attosoc.v attosoc/picorv32.v
	$(YOSYS) -p "read_verilog $^; synth_gowin -json $@"

tonegen-tec0117-synth.json: tonegen/top.v tonegen/sddac.v tonegen/cordic.v
	$(YOSYS) -p "read_verilog $^; synth_gowin -json $@"

nanolcd-tangnano-synth.json: nanolcd/TOP.v nanolcd/VGAMod.v
	$(YOSYS) -p "read_verilog $^; synth_gowin -json $@"

pll-nanolcd-tangnano-synth.json: pll/GW1N-1-dyn.vh pll-nanolcd/TOP.v pll-nanolcd/VGAMod.v
	$(YOSYS) -p "read_verilog $^; synth_gowin -noalu -json $@"

pll-nanolcd-tangnano9k-synth.json: pll/GW1N-9C-dyn.vh pll-nanolcd/TOP.v pll-nanolcd/VGAMod.v
	$(YOSYS) -p "read_verilog $^; synth_gowin -noalu -json $@"

pll2-tangnano9k-synth.json: pll/GW1N-9C-dyn.vh pll2.v pll/rpll.v
	$(YOSYS) -p "read_verilog $^; synth_gowin -noalu -json $@"

%-tec0117-synth.json: %.v
	$(YOSYS) -D LEDS_NR=8 -D OSC_TYPE_OSC -p "read_verilog $^; synth_gowin -json $@"

%-runber-synth.json: %.v
	$(YOSYS) -D LEDS_NR=8 -D OSC_TYPE_OSC -p "read_verilog $^; synth_gowin -json $@"

pll-%-tangnano-synth.json: pll/GW1N-1-%.vh pll.v pll/rpll.v
	$(YOSYS) -D LEDS_NR=3 -p "read_verilog $^; synth_gowin -json $@"

pll-%-tangnano1k-synth.json: pll/GW1NZ-1-%.vh pll.v pll/rpll.v
	$(YOSYS) -D LEDS_NR=3 -p "read_verilog $^; synth_gowin -json $@"

%-tangnano-synth.json: %.v
	$(YOSYS) -D LEDS_NR=3 -D OSC_TYPE_OSCH -p "read_verilog $^; synth_gowin -json $@"

%-tangnano1k-synth.json: %.v
	$(YOSYS) -D LEDS_NR=3 -D OSC_TYPE_OSCZ -p "read_verilog $^; synth_gowin -json $@"

%-tangnano4k-synth.json: %.v
	$(YOSYS) -D LEDS_NR=6 -D OSC_TYPE_OSCZ -p "read_verilog $^; synth_gowin -json $@"

pll-tangnano4k-synth.json: pll-tangnano4k.v pll/pllvr.v
	$(YOSYS) -D LEDS_NR=6 -D OSC_TYPE_OSCZ -p "read_verilog $^; synth_gowin -json $@"

%-tangnano9k-synth.json: %.v
	$(YOSYS) -D LEDS_NR=6 -D OSC_TYPE_OSC -p "read_verilog $^; synth_gowin -json $@"

%-honeycomb-synth.json: %.v
	$(YOSYS) -D LEDS_NR=3 -D OSC_TYPE_OSCF -p "read_verilog $^; synth_gowin -json $@"

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

%-tangnano1k-unpacked.v: %-tangnano1k.fs
	gowin_unpack -d GW1NZ-1 -o $@ $^
	
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

#############
# long wires
%-lw-tangnano.json: %-tangnano-synth.json longwires/tangnano.cst
	$(NEXTPNR) --json $< --write $@ --device GW1N-LV1QN48C6/I5 --cst longwires/tangnano.cst

%-lw-tangnano1k.json: %-tangnano1k-synth.json longwires/tangnano1k.cst
	$(NEXTPNR) --json $< --write $@ --device GW1NZ-LV1QN48C6/I5 --family GW1NZ-1 --cst longwires/tangnano1k.cst

%-lw-tangnano4k.json: %-tangnano4k-synth.json longwires/tangnano4k.cst
	$(NEXTPNR) --json $< --write $@ --device GW1NSR-LV4CQN48PC7/I6 --cst longwires/tangnano4k.cst

%-lw-tangnano9k.json: %-tangnano9k-synth.json longwires/tangnano9k.cst
	$(NEXTPNR) --json $< --write $@ --device GW1NR-LV9QN88PC6/I5 --family GW1N-9C --cst longwires/tangnano9k.cst

%-lw-runber.json: %-runber-synth.json longwires/runber.cst
	$(NEXTPNR) --json $< --write $@ --device GW1N-UV4LQ144C6/I5 --cst longwires/runber.cst

%-lw-tec0117.json: %-tec0117-synth.json longwires/tec0117.cst
	$(NEXTPNR) --json $< --write $@ --device GW1NR-LV9QN88C6/I5 --cst longwires/tec0117.cst

%-lw-honeycomb.json: %-honeycomb-synth.json longwires/honeycomb.cst
	$(NEXTPNR) --json $< --write $@ --device GW1NS-UX2CQN48C5/I4 --cst longwires/honeycomb.cst

