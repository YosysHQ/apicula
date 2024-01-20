ifndef GOWINHOME
$(error GOWINHOME is not set. Must be location of Gowin EDA Tools)
endif

.SECONDARY:
.PHONY: all clean
all: apycula/GW1N-1.pickle apycula/GW1N-9.pickle apycula/GW1N-4.pickle \
	 apycula/GW1NS-2.pickle apycula/GW1NS-4.pickle apycula/GW1N-9C.pickle \
	 apycula/GW1NZ-1.pickle apycula/GW2A-18.pickle apycula/GW2A-18C.pickle

%_stage1.pickle: apycula/tiled_fuzzer.py
	python3 -m apycula.tiled_fuzzer $*

%_stage2.pickle: apycula/clock_fuzzer.py %_stage1.pickle
	python3 -m apycula.clock_fuzzer $*

apycula/%.pickle: %_stage2.pickle
	gzip -c $< > $@

clean:
	rm -f *.json
	rm -f *.pickle
	rm -f apycula/*.pickle
