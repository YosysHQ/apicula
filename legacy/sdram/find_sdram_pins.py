#!/usr/bin/python3

import os
import re
import subprocess

def run_script(port : str, pinName : str):
    with open('template.vhd', 'rt') as f:
        template = f.read()

    f.close()

    template = template.replace("##PORT##", port)
    template = template.replace("##PORTNAME##", pinName)
    with open('findpin.vhd', 'wt') as f2:
        f2.write(template)

    f2.close()

    GowinHome = os.getenv('GOWINHOME')

    result = subprocess.run(["rm", "unpack.v"])
    result = subprocess.run([GowinHome+"/IDE/bin/gw_sh", "findpin.tcl"], check=True)
    result = subprocess.run(["gowin_unpack", "-d", "GW1N-9", "impl/pnr/project.fs"], check=True)

    with open('unpack.v', 'rt') as f3:
        unpackv = f3.readline()

    iobre = re.compile("\(([a-zA-Z0-9_]*)\)")

    matches = iobre.findall(unpackv)

    print("Found IOB: ", matches[0])

    with open('pin_report.txt', 'a+') as f:
        f.write(pinName + " -> " + matches[0] + "\n")

    f.close()


######################################################
## MAIN                                             ##
######################################################

result = subprocess.run(["rm", "pin_report.txt"])

# pin name, bus width, bus offset
pins = [
    ["IO_sdram_dq", 16, 0],
    ["O_sdram_clk", 0, 0],
    ["O_sdram_cke", 0, 0],
    ["O_sdram_cs_n", 0, 0],
    ["O_sdram_cas_n", 0, 0],
    ["O_sdram_ras_n", 0, 0],
    ["O_sdram_wen_n", 0, 0],
    ["O_sdram_addr", 12, 0],
    ["O_sdram_dqm", 2, 0],
    ["O_sdram_ba", 2, 0]
]



for pin in pins:
    pinName = pin[0]
    pinBuswidth = pin[1]
    pinOffset = pin[2]

    if (pinBuswidth == 0):
        port = pinName
        if (pinName.startswith("O")):
            port = port + " : out std_logic"
        else:
            port = port + " : inout std_logic"

        run_script(port, pinName)
    else:
        for pinIdx in range(0, pinBuswidth):
            port = pinName
            if (pinName.startswith("O")):
                port = port + " : out "
            else:
                port = port + " : inout "

            actualIdx = pinIdx + pinOffset

            port = port + "std_logic_vector(" + str(actualIdx) + " downto " + str(actualIdx) + ")"

            run_script(port, pinName+"("+str(actualIdx)+")")
