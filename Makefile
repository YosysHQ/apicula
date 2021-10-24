ifndef GOWINHOME
$(error GOWINHOME is not set. Must be location of Gowin EDA Tools)
endif

.SECONDARY:
.PHONY: all clean
all: apycula/GW1N-1.pickle apycula/GW1N-9.pickle apycula/GW1N-4.pickle apycula/GW1NS-2.pickle

%.json: apycula/dat19_h4x.py
	python3 -m apycula.dat19_h4x $*

%_stage1.pickle: apycula/tiled_fuzzer.py %.json
	python3 -m apycula.tiled_fuzzer $*

%_stage2.pickle: apycula/clock_fuzzer.py %_stage1.pickle
	python3 -m apycula.clock_fuzzer $*

apycula/%.pickle: %_stage2.pickle
	cp $< $@

clean:
	rm *.json
	rm *.pickle
	rm apycula/*.pickle
