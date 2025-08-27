YOSYS ?= yosys
NEXTPNR ?= nextpnr-himbaechel
DEBUG = -v --debug
#DEBUG =

.DEFAULT_GOAL := all
all: \
	in-out-primer25k.fs in-inv-out-primer25k.fs in-or-inv-out-primer25k.fs \
	lut8-primer25k.fs big-shift-primer25k.fs alu-simple-primer25k.fs lutram-primer25k.fs


clean: 
	rm -f *.json *.fs *-unpacked.v
	
.PHONY: unpacked clean

# ============================================================
# TangPrimer25k
%-primer25k.fs: %-primer25k.json
	gowin_pack --sspi_as_gpio --cpu_as_gpio -d GW5A-25A -o $@ $<

%-primer25k.json: %-primer25k-synth.json primer25k.cst
	$(NEXTPNR) $(DEBUG) --top top --json $< --write $@ --device GW5A-LV25MG121NES --vopt cst=primer25k.cst --vopt cpu_as_gpio --vopt sspi_as_gpio

big-shift-primer25k.json: big-shift-primer25k-synth.json big-shift-primer25k.cst
	$(NEXTPNR) $(DEBUG) --top top --json $< --write $@ --device GW5A-LV25MG121NES --vopt cst=big-shift-primer25k.cst --vopt cpu_as_gpio --vopt sspi_as_gpio

alu-%-primer25k.json: alu-%-primer25k-synth.json alu-%-primer25k.cst
	$(NEXTPNR) $(DEBUG) --top top --json $< --write $@ --device GW5A-LV25MG121NES --vopt cst=$(basename $@).cst --vopt cpu_as_gpio --vopt sspi_as_gpio

%-primer25k-synth.json: %.v
	$(YOSYS) -p "read_verilog $^; synth_gowin -json $@ -family gw5a"

