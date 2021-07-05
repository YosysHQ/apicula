# gw_sh run.tcl
add_file -vm empty.v
add_file -cfg device.cfg
set_option -device GW1N-1-QFN48-6
set_option -pn GW1N-LV1QN48C6/I5
run_pnr -opt pnr.cfg
