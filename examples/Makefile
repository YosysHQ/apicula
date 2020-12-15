all: attosoc.json blinky.json

attosoc.json: attosoc/attosoc.v attosoc/picorv32.v
	yosys -p "synth_gowin -json $@" $^

%.json: %.v
	yosys -p "synth_gowin -json $@" $^
