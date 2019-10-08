# gw_sh run.tcl
add_file -vm empty.v
add_file -cfg device.cfg
set_option -device GW1NR-9-QFN88-6
set_option -pn GW1NR-LV9QN88C6/I5
run_pnr -opt pnr.cfg
