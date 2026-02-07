ifndef GOWINHOME
$(error GOWINHOME is not set. Must be location of Gowin EDA Tools)
endif

.SECONDARY:
.PHONY: all clean

all: apycula/GW1N-1.msgpack.gz apycula/GW1N-9.msgpack.gz apycula/GW1N-4.msgpack.gz \
	 apycula/GW1NS-4.msgpack.gz apycula/GW1N-9C.msgpack.gz apycula/GW1NZ-1.msgpack.gz \
	 apycula/GW2A-18.msgpack.gz apycula/GW2A-18C.msgpack.gz apycula/GW5A-25A.msgpack.gz \
	 apycula/GW5AST-138C.msgpack.gz

%_stage1.msgpack.gz: apycula/tiled_fuzzer.py
	python3 -m apycula.tiled_fuzzer $*

%_stage2.msgpack.gz: apycula/find_sdram_pins.py %_stage1.msgpack.gz
	python3 -m apycula.find_sdram_pins $*

apycula/%.msgpack.gz: %_stage2.msgpack.gz
	cp $< $@

clean:
	rm -f *.json
	rm -f *.msgpack.gz
	rm -f apycula/*.msgpack.gz
