YOSYS ?= yosys
YOSYS_FLAGS = -setundef
NEXTPNR ?= nextpnr-himbaechel
DEBUG = -v --debug
DEBUG =

.DEFAULT_GOAL := all
all: \
	in-out-primer25k.fs in-inv-out-primer25k.fs in-or-inv-out-primer25k.fs \
	lut8-primer25k.fs big-shift-primer25k.fs alu-simple-primer25k.fs lutram-primer25k.fs \
	blinky-osc-primer25k.fs pll7-primer25k.fs dcs-primer25k.fs \
	bsram-DPB-primer25k.fs bsram-DPB16-primer25k.fs bsram-DPX9B-primer25k.fs bsram-DPX9B18-primer25k.fs \
	bsram-pROM-primer25k.fs bsram-pROMX9-primer25k.fs bsram-SP-primer25k.fs bsram-SPX9-primer25k.fs \
	bsram-SDPB-primer25k.fs bsram-SDPX9B-primer25k.fs bsram-SDPB32-primer25k.fs \
	femto-riscv-15-primer25k.fs femto-riscv-16-primer25k.fs femto-riscv-18-primer25k.fs \
	adc-temp-primer25k.fs adc-loc-left-primer25k.fs adc-glo-right-primer25k.fs

clean: 
	rm -f *.json *.fs *-unpacked.v
	
.PHONY: unpacked clean

# ============================================================
# TangPrimer25k
%-primer25k.fs: %-primer25k.json
	gowin_pack --sspi_as_gpio --cpu_as_gpio -d GW5A-25A -o $@ $<

%-primer25k.json: %-primer25k-synth.json primer25k.cst
	$(NEXTPNR) $(DEBUG) --top top --json $< --write $@ --device GW5A-LV25MG121NES --vopt cst=primer25k.cst --vopt sspi_as_gpio

big-shift-primer25k.json: big-shift-primer25k-synth.json big-shift-primer25k.cst
	$(NEXTPNR) $(DEBUG) --top top --json $< --write $@ --device GW5A-LV25MG121NES --vopt cst=big-shift-primer25k.cst --vopt sspi_as_gpio

alu-%-primer25k.json: alu-%-primer25k-synth.json alu-%-primer25k.cst
	$(NEXTPNR) $(DEBUG) --top top --json $< --write $@ --device GW5A-LV25MG121NES --vopt cst=$(basename $@).cst --vopt sspi_as_gpio

%-primer25k-synth.json: %.v
	$(YOSYS) -D INV_BTN=1 -D LEDS_NR=8 -D OSC_TYPE_OSCA -p "read_verilog $^; synth_gowin -json $@ -family gw5a ${YOSYS_FLAGS}"

bsram-%-primer25k-synth.json: pll/GW5A-25A.vh io444.vh display-640x480.v %-image-rom.v %-video-ram.v %.v clock-PLLA.v
	$(YOSYS) -D INV_BTN=1 -p "read_verilog $^; synth_gowin -json $@ -family gw5a ${YOSYS_FLAGS}"

femto-%-primer25k-synth.json: femto-%.v
	$(YOSYS) -D INV_BTN=1 -D LEDS_NR=8 -D OSC_TYPE_OSCA -D CPU_FREQ=50 -D BAUD_RATE=115200 -p "read_verilog $^; synth_gowin -json $@ -nolutram -family gw5a ${YOSYS_FLAGS}"

attosoc-primer25k.json: attosoc-primer25k-synth.json primer25k.cst
	$(NEXTPNR) $(DEBUG) --top attosoc --json $< --write $@ --device GW5A-LV25MG121NES --vopt cst=primer25k.cst --vopt sspi_as_gpio

attosoc-primer25k-synth.json: attosoc/attosoc.v attosoc/picorv32.v
	$(YOSYS) -D INV_BTN=1 -p "read_verilog $^; synth_gowin -json $@ -nolutram -strict-gw5a-dffs -family gw5a ${YOSYS_FLAGS}"

