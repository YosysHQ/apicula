ifndef GOWINHOME
$(error GOWINHOME is not set. Must be location of Gowin EDA Tools)
endif

.SECONDARY:
.PHONY: all clean

all: apycula/GW1N-1.msgpack.xz apycula/GW1N-9.msgpack.xz apycula/GW1N-4.msgpack.xz \
	 apycula/GW1NS-4.msgpack.xz apycula/GW1N-9C.msgpack.xz apycula/GW1NZ-1.msgpack.xz \
	 apycula/GW2A-18.msgpack.xz apycula/GW2A-18C.msgpack.xz apycula/GW5A-25A.msgpack.xz \
	 apycula/GW5AST-138C.msgpack.xz

BUILDER_DEPS = apycula/chipdb_builder.py apycula/fse_parser.py apycula/dat_parser.py \
               apycula/tm_parser.py apycula/chipdb.py

apycula/%.msgpack.xz: $(BUILDER_DEPS)
	python3 -m apycula.chipdb_builder $*

clean:
	rm -f apycula/*.msgpack.xz
