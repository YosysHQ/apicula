ifndef GOWINHOME
$(error GOWINHOME is not set. Must be location of Gowin EDA Tools)
endif

.SECONDARY:
.PHONY: all clean

all: apycula/GW1N-1.msgpack.xz apycula/GW1N-9.msgpack.xz apycula/GW1N-4.msgpack.xz \
	 apycula/GW1NS-4.msgpack.xz apycula/GW1N-9C.msgpack.xz apycula/GW1NZ-1.msgpack.xz \
	 apycula/GW2A-18.msgpack.xz apycula/GW2A-18C.msgpack.xz apycula/GW5A-25A.msgpack.xz \
	 apycula/GW5AST-138C.msgpack.xz

%_stage1.msgpack.xz: apycula/tiled_fuzzer.py
	python3 -m apycula.tiled_fuzzer $*

%_stage2.msgpack.xz: apycula/find_sdram_pins.py %_stage1.msgpack.xz
	python3 -m apycula.find_sdram_pins $*

apycula/%.msgpack.xz: %_stage2.msgpack.xz
	cp $< $@

clean:
	rm -f *.json
	rm -f *.msgpack.xz
	rm -f apycula/*.msgpack.xz
