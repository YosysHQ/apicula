YOSYS ?= yosys
NEXTPNR ?= nextpnr-himbaechel

.DEFAULT_GOAL := all

all: \
	in-out-primer25k.fs in-inv-out-primer25k.fs in-or-inv-out-primer25k.fs


clean: 
	rm -f *.json *.fs *-unpacked.v
	
.PHONY: unpacked clean

# ============================================================
# TangPrimer25k
%-primer25k.fs: %-primer25k.json
	gowin_pack -d GW5A-25A -o $@ $<

%-primer25k.json: %-primer25k-synth.json primer25k.cst
	$(NEXTPNR) -v --debug --json $< --write $@ --device GW5A-LV25MG121NES --vopt cst=primer25k.cst

%-primer25k-synth.json: %.v
	$(YOSYS) -p "read_verilog $^; synth_gowin -json $@ -family gw5a"

