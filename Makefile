ifndef DEVICE
$(error DEVICE is not set. Must be either GW1NR-9 or GW1N-1)
endif
ifndef GOWINHOME
$(error GOWINHOME is not set. Must be location of Gowin EDA Tools)
endif

.PHONY: all clean
all: ${DEVICE}.pickle

${DEVICE}.json: dat19_h4x.py
	python3 dat19_h4x.py

${DEVICE}.pickle: tiled_fuzzer.py ${DEVICE}.json
	python3 tiled_fuzzer.py

clean:
	rm ${DEVICE}.json
	rm ${DEVICE}.pickle
