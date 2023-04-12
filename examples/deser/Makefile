YOSYS ?= yosys
NEXTPNR ?= nextpnr-gowin

WRK_PATH = deser

all_deser: deser-oser4-tangnano.fs deser-oser8-tangnano.fs \
	deser-ovideo-tangnano.fs deser-oser10-tangnano.fs \
	deser-oser4-tangnano4k.fs deser-ovideo-tangnano4k.fs deser-oser8-tangnano4k.fs \
	deser-oser10-tangnano4k.fs deser-oser4-tangnano9k.fs deser-ovideo-tangnano9k.fs \
	deser-oser8-tangnano9k.fs deser-oser10-tangnano9k.fs \
	deser-oser4-szfpga.fs deser-ovideo-szfpga.fs deser-oser8-szfpga.fs \
	deser-oser10-szfpga.fs \
	deser-oser8-tlvds-tangnano4k.fs deser-ovideo-tlvds-tangnano4k.fs \
	deser-oser10-tlvds-tangnano4k.fs deser-oser4-tlvds-tangnano4k.fs \
	deser-oser8-tlvds-tangnano9k.fs deser-ovideo-tlvds-tangnano9k.fs \
	deser-oser10-tlvds-tangnano9k.fs deser-oser4-tlvds-tangnano9k.fs \
	deser-oser8-tlvds-tec0117.fs deser-ovideo-tlvds-tec0117.fs \
	deser-oser10-tlvds-tec0117.fs deser-oser4-tlvds-tec0117.fs \
	deser-ides4-tangnano.fs deser-ivideo-tangnano.fs deser-ides10-tangnano.fs \
	deser-ides8-tangnano.fs \
	deser-ides4-tangnano1k.fs deser-ivideo-tangnano1k.fs deser-ides10-tangnano1k.fs \
	deser-ides8-tangnano1k.fs \
	deser-ides4-tangnano4k.fs deser-ivideo-tangnano4k.fs deser-ides10-tangnano4k.fs \
	deser-ides8-tangnano4k.fs \
	deser-ides4-tangnano9k.fs deser-ivideo-tangnano9k.fs deser-ides10-tangnano9k.fs \
	deser-ides8-tangnano9k.fs \
	deser-ides4-szfpga.fs deser-ivideo-szfpga.fs deser-ides10-szfpga.fs \
	deser-ides8-szfpga.fs \
	deser-iddr-tangnano.fs deser-iddrc-tangnano.fs \
	deser-iddr-tangnano1k.fs deser-iddrc-tangnano1k.fs \
	deser-iddr-tangnano4k.fs deser-iddrc-tangnano4k.fs \
	deser-iddr-tangnano9k.fs deser-iddrc-tangnano9k.fs \
	deser-iddr-szfpga.fs deser-iddrc-szfpga.fs \
	deser-oser16-tangnano4k.fs deser-oser16-tangnano9k.fs deser-oser16-szfpga.fs \
	deser-ides16-tangnano4k.fs deser-ides16-tangnano9k.fs deser-ides16-szfpga.fs

unpacked_deser:	deser-oser4-tangnano-unpacked.v deser-oser8-tangnano-unpacked.v \
	deser-ovideo-tangnano-unpacked.v deser-oser10-tangnano-unpacked.v \
	deser-oser4-tangnano4k-unpacked.v deser-ovideo-tangnano4k-unpacked.v \
	deser-oser8-tangnano4k-unpacked.v deser-oser10-tangnano4k-unpacked.v \
	deser-oser4-tangnano9k-unpacked.v deser-ovideo-tangnano9k-unpacked.v \
	deser-oser8-tangnano9k-unpacked.v deser-oser10-tangnano9k-unpacked.v \
	deser-oser4-szfpga-unpacked.v deser-ovideo-szfpga-unpacked.v \
	deser-oser8-szfpga-unpacked.v deser-oser10-szfpga-unpacked.v \
	deser-oser8-tlvds-tangnano4k-unpacked.v deser-ovideo-tlvds-tangnano4k-unpacked.v \
	deser-oser10-tlvds-tangnano4k-unpacked.v deser-oser4-tlvds-tangnano4k-unpacked.v \
	deser-oser8-tlvds-tangnano9k-unpacked.v deser-ovideo-tlvds-tangnano9k-unpacked.v \
	deser-oser10-tlvds-tangnano9k-unpacked.v deser-oser4-tlvds-tangnano9k-unpacked.v \
	deser-oser8-tlvds-tec0117-unpacked.v deser-ovideo-tlvds-tec0117-unpacked.v \
	deser-oser10-tlvds-tec0117-unpacked.v deser-oser4-tlvds-tec0117-unpacked.v \
	deser-ides4-tangnano-unpacked.v deser-ivideo-tangnano-unpacked.v \
	deser-ides10-tangnano-unpacked.v deser-ides8-tangnano-unpacked.v \
	deser-ides4-tangnano1k-unpacked.v deser-ivideo-tangnano1k-unpacked.v \
	deser-ides10-tangnano1k-unpacked.v deser-ides8-tangnano1k-unpacked.v \
	deser-ides4-tangnano4k-unpacked.v deser-ivideo-tangnano4k-unpacked.v \
	deser-ides10-tangnano4k-unpacked.v deser-ides8-tangnano4k-unpacked.v \
	deser-ides4-tangnano9k-unpacked.v deser-ivideo-tangnano9k-unpacked.v \
	deser-ides10-tangnano9k-unpacked.v deser-ides8-tangnano9k-unpacked.v \
	deser-ides4-szfpga-unpacked.v deser-ivideo-szfpga-unpacked.v \
	deser-ides10-szfpga-unpacked.v deser-ides8-szfpga-unpacked.v \
	deser-iddr-tangnano-unpacked.v deser-iddrc-tangnano-unpacked.v \
	deser-iddr-tangnano1k-unpacked.v deser-iddrc-tangnano1k-unpacked.v \
	deser-iddr-tangnano4k-unpacked.v deser-iddrc-tangnano4k-unpacked.v \
	deser-iddr-tangnano9k-unpacked.v deser-iddrc-tangnano9k-unpacked.v \
	deser-iddr-szfpga-unpacked.v deser-iddrc-szfpga-unpacked.v \
	deser-oser16-tangnano4k-unpacked.v deser-oser16-tangnano9k-unpacked.v \
	deser-oser16-tangnano4k-unpacked.v \
	deser-ides16-tangnano4k-unpacked.v deser-ides16-tangnano9k-unpacked.v deser-ides16-szfpga-unpacked.v

clean_deser: 
	
.PHONY: all-deser unpacked-deser clean-deser

deser-%-tec0117.json: deser-%-tec0117-synth.json $(WRK_PATH)/%-tec0117.cst
	$(NEXTPNR) --json $< --write $@ --device GW1NR-LV9QN88C6/I5 --cst $(WRK_PATH)/$*-tec0117.cst

deser-%-tec0117-synth.json: $(WRK_PATH)/%.v
	$(YOSYS) -p "read_verilog $^; synth_gowin -json $@"

deser-%-tangnano.json: deser-%-tangnano-synth.json $(WRK_PATH)/%-tangnano.cst
	$(NEXTPNR) --json $< --write $@ --device GW1N-LV1QN48C6/I5 --cst $(WRK_PATH)/$*-tangnano.cst

deser-%-tangnano-synth.json: $(WRK_PATH)/%.v
	$(YOSYS) -p "read_verilog $^; synth_gowin -json $@"

deser-%-tangnano1k.json: deser-%-tangnano1k-synth.json $(WRK_PATH)/%-tangnano1k.cst
	$(NEXTPNR) --json $< --write $@ --device GW1NZ-LV1QN48C6/I5 --family GW1NZ-1 --cst $(WRK_PATH)/$*-tangnano1k.cst

deser-%-tangnano1k-synth.json: $(WRK_PATH)/%.v
	$(YOSYS) -p "read_verilog $^; synth_gowin -json $@"

deser-%-tangnano4k.json: deser-%-tangnano4k-synth.json $(WRK_PATH)/%-tangnano4k.cst
	$(NEXTPNR) --json $< --write $@ --device GW1NSR-LV4CQN48PC7/I6 --cst $(WRK_PATH)/$*-tangnano4k.cst

deser-%-tangnano4k-synth.json: $(WRK_PATH)/%.v
	$(YOSYS) -p "read_verilog $^; synth_gowin -json $@"

deser-%-tangnano9k.json: deser-%-tangnano9k-synth.json $(WRK_PATH)/%-tangnano9k.cst
	$(NEXTPNR) --json $< --write $@ --device GW1NR-LV9QN88PC6/I5 --family GW1N-9C --cst $(WRK_PATH)/$*-tangnano9k.cst

deser-%-tangnano9k-synth.json: $(WRK_PATH)/%.v
	$(YOSYS) -p "read_verilog $^; synth_gowin -json $@"

######################################################
%-szfpga-unpacked.v: %-szfpga.fs
	gowin_unpack -d GW1N-9 -o $@ $^

deser-%-szfpga.json: deser-%-szfpga-synth.json $(WRK_PATH)/%-szfpga.cst
	$(NEXTPNR) --json $< --write $@ --device GW1NR-LV9LQ144PC6/I5 --cst $(WRK_PATH)/$*-szfpga.cst

deser-%-szfpga-synth.json: $(WRK_PATH)/%.v
	$(YOSYS) -p "read_verilog $^; synth_gowin -json $@"

%-szfpga.fs: %-szfpga.json
	gowin_pack -d GW1N-9 -o $@ $<



