add_file -type vhdl "findpin.vhd"
set_device GW1NR-UV9QN88C6/I5 -name GW1NR-9
set_option -synthesis_tool gowinsynthesis
set_option -top_module top
run all
exit