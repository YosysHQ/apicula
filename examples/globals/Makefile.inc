GLOBALS_DIR = globals

.PHONY: globals_clean globals_all globals_unpacked

globals_clean:
	rm -f $(GLOBALS_DIR)/*.json $(GLOBALS_DIR)/*.fs $(GLOBALS_DIR)/*-unpacked.v

globals_all: $(GLOBALS_DIR)/attosoc-tec0117.fs $(GLOBALS_DIR)/nanolcd-tangnano.fs \
	$(GLOBALS_DIR)/blinky-tec0117.fs $(GLOBALS_DIR)/blinky-runber.fs \
	$(GLOBALS_DIR)/blinky-tangnano.fs $(GLOBALS_DIR)/blinky-honeycomb.fs \
	$(GLOBALS_DIR)/shift-tec0117.fs $(GLOBALS_DIR)/shift-runber.fs \
	$(GLOBALS_DIR)/shift-tangnano.fs $(GLOBALS_DIR)/shift-honeycomb.fs \
	$(GLOBALS_DIR)/tonegen-tec0117.fs $(GLOBALS_DIR)/blinky-tangnano9k.fs \
	$(GLOBALS_DIR)/blinky-tangnano1k.fs $(GLOBALS_DIR)/blinky-tangnano4k.fs \
	$(GLOBALS_DIR)/shift-tangnano9k.fs $(GLOBALS_DIR)/shift-tangnano1k.fs \
	$(GLOBALS_DIR)/shift-tangnano4k.fs $(GLOBALS_DIR)/tlvds-tangnano4k.fs \
	$(GLOBALS_DIR)/tlvds-tangnano9k.fs $(GLOBALS_DIR)/tlvds-tec0117.fs \
	$(GLOBALS_DIR)/tlvds-oddr-tangnano4k.fs $(GLOBALS_DIR)/tlvds-oddr-tangnano9k.fs \
	$(GLOBALS_DIR)/tlvds-oddr-tec0117.fs $(GLOBALS_DIR)/blinky-oddr-tec0117.fs \
	$(GLOBALS_DIR)/blinky-oddr-runber.fs $(GLOBALS_DIR)/blinky-oddr-tangnano.fs \
	$(GLOBALS_DIR)/blinky-oddr-honeycomb.fs $(GLOBALS_DIR)/blinky-oddr-tangnano4k.fs \
	$(GLOBALS_DIR)/blinky-oddr-tangnano9k.fs $(GLOBALS_DIR)/blinky-osc-tec0117.fs \
	$(GLOBALS_DIR)/blinky-osc-runber.fs $(GLOBALS_DIR)/blinky-osc-tangnano.fs \
	$(GLOBALS_DIR)/blinky-osc-honeycomb.fs $(GLOBALS_DIR)/blinky-osc-tangnano9k.fs \
	$(GLOBALS_DIR)/blinky-osc-tangnano1k.fs $(GLOBALS_DIR)/blinky-osc-tangnano4k.fs 

globals_unpacked: $(GLOBALS_DIR)/attosoc-tec0117-unpacked.v \
	$(GLOBALS_DIR)/nanolcd-tangnano-unpacked.v $(GLOBALS_DIR)/blinky-tec0117-unpacked.v \
	$(GLOBALS_DIR)/blinky-runber-unpacked.v $(GLOBALS_DIR)/blinky-tangnano-unpacked.v \
	$(GLOBALS_DIR)/blinky-honeycomb-unpacked.v $(GLOBALS_DIR)/shift-tec0117-unpacked.v \
	$(GLOBALS_DIR)/shift-runber-unpacked.v $(GLOBALS_DIR)/shift-tangnano-unpacked.v \
	$(GLOBALS_DIR)/shift-honeycomb-unpacked.v $(GLOBALS_DIR)/tonegen-tec0117-unpacked.v \
	$(GLOBALS_DIR)/blinky-tangnano9k-unpacked.v $(GLOBALS_DIR)/blinky-tangnano1k-unpacked.v \
	$(GLOBALS_DIR)/blinky-tangnano4k-unpacked.v $(GLOBALS_DIR)/shift-tangnano9k-unpacked.v \
	$(GLOBALS_DIR)/shift-tangnano1k-unpacked.v $(GLOBALS_DIR)/shift-tangnano4k-unpacked.v \
	$(GLOBALS_DIR)/tlvds-tangnano4k-unpacked.v $(GLOBALS_DIR)/tlvds-tangnano9k-unpacked.v \
	$(GLOBALS_DIR)/tlvds-tec0117-unpacked.v $(GLOBALS_DIR)/tlvds-oddr-tangnano4k-unpacked.v \
	$(GLOBALS_DIR)/tlvds-oddr-tangnano9k-unpacked.v $(GLOBALS_DIR)/tlvds-oddr-tec0117-unpacked.v \
	$(GLOBALS_DIR)/blinky-oddr-tec0117-unpacked.v $(GLOBALS_DIR)/blinky-oddr-runber-unpacked.v \
	$(GLOBALS_DIR)/blinky-oddr-tangnano-unpacked.v $(GLOBALS_DIR)/blinky-oddr-honeycomb-unpacked.v \
	$(GLOBALS_DIR)/blinky-oddr-tangnano-unpacked.v $(GLOBALS_DIR)/blinky-oddr-honeycomb-unpacked.v \
	$(GLOBALS_DIR)/blinky-oddr-tangnano4k-unpacked.v \
	$(GLOBALS_DIR)/blinky-oddr-tangnano9k-unpacked.v \
	$(GLOBALS_DIR)/blinky-osc-tec0117-unpacked.v $(GLOBALS_DIR)/blinky-osc-runber-unpacked.v \
	$(GLOBALS_DIR)/blinky-osc-tangnano-unpacked.v $(GLOBALS_DIR)/blinky-osc-honeycomb-unpacked.v \
	$(GLOBALS_DIR)/blinky-osc-tangnano9k-unpacked.v $(GLOBALS_DIR)/blinky-osc-tangnano1k-unpacked.v \
	$(GLOBALS_DIR)/blinky-osc-tangnano4k-unpacked.v

$(GLOBALS_DIR)/%-tec0117.fs: $(GLOBALS_DIR)/%-tec0117.json
	gowin_pack -d GW1N-9 -o $@ $<

$(GLOBALS_DIR)/%-tec0117.json: %-tec0117-synth.json tec0117.cst
	$(NEXTPNR) --enable-globals --json $< --write $@ --device GW1NR-LV9QN88C6/I5 --cst tec0117.cst

$(GLOBALS_DIR)/%-runber.fs: $(GLOBALS_DIR)/%-runber.json
	gowin_pack -d GW1N-4 -o $@ $<

$(GLOBALS_DIR)/%-runber.json: %-runber-synth.json runber.cst
	$(NEXTPNR) --enable-globals --json $< --write $@ --device GW1N-UV4LQ144C6/I5 --cst runber.cst

$(GLOBALS_DIR)/blinky-oddr-runber.json: blinky-oddr-runber-synth.json runber-tlvds.cst
	$(NEXTPNR) --enable-globals --json $< --write $@ --device GW1N-UV4LQ144C6/I5 --cst runber-tlvds.cst

$(GLOBALS_DIR)/%-tangnano.fs: $(GLOBALS_DIR)/%-tangnano.json
	gowin_pack -d GW1N-1 -o $@ $^

$(GLOBALS_DIR)/%-tangnano.json: %-tangnano-synth.json tangnano.cst
	$(NEXTPNR) --enable-globals --json $< --write $@ --device GW1N-LV1QN48C6/I5 --cst tangnano.cst

$(GLOBALS_DIR)/%-tangnano1k.fs: $(GLOBALS_DIR)/%-tangnano1k.json
	gowin_pack -d GW1NZ-1 -o $@ $^

$(GLOBALS_DIR)/%-tangnano1k.json: %-tangnano1k-synth.json tangnano1k.cst
	$(NEXTPNR) --enable-globals --json $< --write $@ --device GW1NZ-LV1QN48C6/I5 --family GW1NZ-1 --cst tangnano1k.cst

$(GLOBALS_DIR)/%-tangnano4k.fs: $(GLOBALS_DIR)/%-tangnano4k.json
	gowin_pack -d GW1NS-4 -o $@ $^

$(GLOBALS_DIR)/%-tangnano4k.json: %-tangnano4k-synth.json tangnano4k.cst
	$(NEXTPNR) --enable-globals --json $< --write $@ --device GW1NSR-LV4CQN48PC7/I6 --cst tangnano4k.cst

$(GLOBALS_DIR)/%-tangnano9k.fs: $(GLOBALS_DIR)/%-tangnano9k.json
	gowin_pack -d GW1N-9C -o $@ $^

$(GLOBALS_DIR)/%-tangnano9k.json: %-tangnano9k-synth.json tangnano9k.cst
	$(NEXTPNR) --enable-globals --json $< --write $@ --device GW1NR-LV9QN88PC6/I5 --family GW1N-9C --cst tangnano9k.cst

$(GLOBALS_DIR)/%-honeycomb.fs: $(GLOBALS_DIR)/%-honeycomb.json
	gowin_pack -d GW1NS-2 -o $@ $<

$(GLOBALS_DIR)/%-honeycomb.json: %-honeycomb-synth.json honeycomb.cst
	$(NEXTPNR) --enable-globals --json $< --write $@ --device GW1NS-UX2CQN48C5/I4 --cst honeycomb.cst

$(GLOBALS_DIR)/%-tangnano-unpacked.v: $(GLOBALS_DIR)/%-tangnano.fs
	gowin_unpack -d GW1N-1 -o $@ $^

$(GLOBALS_DIR)/%-tangnano1k-unpacked.v: $(GLOBALS_DIR)/%-tangnano1k.fs
	gowin_unpack -d GW1NZ-1 -o $@ $^

$(GLOBALS_DIR)/%-tangnano4k-unpacked.v: $(GLOBALS_DIR)/%-tangnano4k.fs
	gowin_unpack -d GW1NS-4 -o $@ $^

$(GLOBALS_DIR)/%-tangnano9k-unpacked.v: $(GLOBALS_DIR)/%-tangnano9k.fs
	gowin_unpack -d GW1N-9C -o $@ $^

$(GLOBALS_DIR)/%-runber-unpacked.v: $(GLOBALS_DIR)/%-runber.fs
	gowin_unpack -d GW1N-4 -o $@ $^

$(GLOBALS_DIR)/%-tec0117-unpacked.v: $(GLOBALS_DIR)/%-tec0117.fs
	gowin_unpack -d GW1N-9 -o $@ $^

$(GLOBALS_DIR)/%-honeycomb-unpacked.v: $(GLOBALS_DIR)/%-honeycomb.fs
	gowin_unpack -d GW1NS-2 -o $@ $<

