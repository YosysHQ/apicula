# gw_sh run.tcl
add_file -cst iob.cst
add_file -sdc iob.sdc
add_file -vm iob.v
add_file -cfg device.cfg
set_option -device GW1NR-9-QFN88-6
set_option -pn GW1NR-LV9QN88C6/I5
run_pnr -opt pnr.cfg
