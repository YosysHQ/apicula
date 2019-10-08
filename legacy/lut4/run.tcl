# gw_sh run.tcl
add_file -cst lut4.cst
add_file -sdc lut4.sdc
add_file -vm lut4.v
add_file -cfg device.cfg
set_option -device GW1NR-9-QFN88-6
set_option -pn GW1NR-LV9QN88C6/I5
run_pnr -opt pnr.cfg
