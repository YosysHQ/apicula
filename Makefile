ifndef GOWINHOME
$(error GOWINHOME is not set. Must be location of Gowin EDA Tools)
endif

.SECONDARY:
.PHONY: all clean

all: apycula/GW1N-1.pickle apycula/GW1N-9.pickle apycula/GW1N-4.pickle \
	 apycula/GW1NS-4.pickle apycula/GW1N-9C.pickle apycula/GW1NZ-1.pickle \
	 apycula/GW2A-18.pickle apycula/GW2A-18C.pickle apycula/GW5A-25A.pickle

%_stage1.pickle: apycula/tiled_fuzzer.py
	python3 -m apycula.tiled_fuzzer $*

%_stage2.pickle: apycula/find_sdram_pins.py %_stage1.pickle
	python3 -m apycula.find_sdram_pins $*

apycula/%.pickle: %_stage2.pickle
	gzip -c $< > $@

clean:
	rm -f *.json
	rm -f *.pickle
	rm -f apycula/*.pickle
