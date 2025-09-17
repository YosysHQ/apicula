from collections import namedtuple
from itertools import chain
import os
import re
import subprocess
import tempfile
import shutil
from apycula import bslib


class Module:
    def __init__(self):
        self.inputs = set()
        self.outputs = set()
        self.inouts = set()
        self.wires = set()
        self.wire_aliases = dict()
        self.assigns = []
        self.primitives = {}

    def __add__(self, other):
        m = Module()
        m.inputs = self.inputs | other.inputs
        m.outputs = self.outputs | other.outputs
        m.inouts = self.inouts | other.inouts
        m.wires = self.wires | other.wires
        m.wire_aliases = self.wire_aliases | other.wire_aliases
        m.assigns = self.assigns + other.assigns
        m.primitives = {**self.primitives, **other.primitives}
        return m

    def write(self, f):
        f.write("module top(")
        first = True
        for port in chain(self.inputs, self.outputs, self.inouts):
            if not first:
                f.write(", ")
            first = False
            bare = re.sub(r" *\[.*\] *", "", port)
            f.write(bare)
        f.write(");\n")

        for port in self.inputs:
            f.write("input {};\n".format(port))
        for port in self.outputs:
            f.write("output {};\n".format(port))
        for port in self.inouts:
            f.write("inout {};\n".format(port))

        for wire in self.wires:
            if wire in self.wire_aliases:
                f.write("`define {} {}\n".format(wire, self.wire_aliases[wire]))
            else:
                f.write("wire {};\n".format(wire))

        # unique assignments or not
        #for dest, src in self.assigns:
        for dest, src in dict(self.assigns).items():
            dest_px = ''
            src_px = ''
            if dest in self.wire_aliases:
                dest_px = '`'
            if src in self.wire_aliases:
                src_px = '`'
            f.write("assign {}{} = {}{};\n".format(dest_px, dest, src_px, src))

        for module in self.primitives.values():
            module.write(f)

        f.write("endmodule\n")

class Primitive:
    def __init__(self, typ, inst):
        self.typ = typ
        self.inst = inst
        self.portmap = {}
        self.params = {}

    def write(self, f):
        f.write("{} {} (".format(self.typ, self.inst))
        first = True
        for port, wire in self.portmap.items():
            if not first:
                f.write(",")
            first = False
            if isinstance(wire, list):
                wire = "{" + ", ".join([x for x in wire]) + "}"
            f.write("\n.{}({})".format(port, wire))
        f.write("\n);\n")

        for key, val in self.params.items():
            f.write("defparam {}.{} = {};\n".format(self.inst, key, val))

class Constraints:
    def __init__(self):
        self.cells = {}
        self.ports = {}
        self.attrs = {}
        self.clocks = {}

    def __add__(self, other):
        cst = Constraints()
        cst.cells = {**self.cells, **other.cells}
        cst.ports = {**self.ports, **other.ports}
        cst.attrs = {**self.attrs, **other.attrs}
        cst.clocks = {**self.clocks, **other.clocks}
        return cst

    def write(self, f):
        for key, val in self.cells.items():
            row, col, side, lut = val
            f.write("INS_LOC \"{}\" R{}C{}[{}][{}];\n".format(key, row, col, side, lut))
        for key, val in self.ports.items():
            f.write("IO_LOC \"{}\" {};\n".format(key, val))
        for key, val in self.attrs.items():
            f.write("IO_PORT \"{}\" ".format(key))
            for attr, attr_value in val.items():
                f.write("{}={} ".format(attr, attr_value))
            f.write(";\n")
        for key, val in self.clocks.items():
            f.write("CLOCK_LOC \"{}\" {};\n".format(key, val))

class DeviceConfig:
    def __init__(self, settings=None):
        settings = settings or {}
        __default_pnr_config:dict = {
            "use_jtag_as_gpio"      : "1",
            "use_sspi_as_gpio"      : "1",
            "use_mspi_as_gpio"      : "1",
            "use_ready_as_gpio"     : "1",
            "use_done_as_gpio"      : "1",
            "use_reconfign_as_gpio" : "1",
            "use_mode_as_gpio"      : "1",
            "use_i2c_as_gpio"       : "1",
            "bit_crc_check"         : "1",
            "bit_compress"          : "0",
            "bit_encrypt"           : "0",
            "bit_security"          : "1",
            "bit_incl_bsram_init"   : "0",
            #"loading_rate"          : "250/100",
            "spi_flash_addr"        : "0x00FFF000",
            "bit_format"            : "txt",
            "bg_programming"        : "off",
            "secure_mode"           : "0"
        }
        self.settings = settings or __default_pnr_config

    def __repr__(self):
        return str(self.settings)

    @property
    def text(self):
        return "".join([' -' + name + ' ' + val for name, val in self.settings.items()])

class PnrOptions:
    def __init__(self, options=None):
        __default_opt = {
            "gen_posp"          : "1",
            "gen_io_cst"        : "1",
            #"gen_ibis"          : "1",
            "ireg_in_iob"       : "0",
            "oreg_in_iob"       : "0",
            "ioreg_in_iob"      : "0",
            "timing_driven"     : "0",
            "cst_warn_to_error" : "0",
            "top_module"        : "top",
            "output_base_name"  : "top"}


        self.options = options or __default_opt

    def __repr__(self):
        return str(self.options)

    @property
    def text(self):
        return "".join([' -' + name + ' ' + val for name, val in self.options.items()])

# Result of the vendor router-packer run
PnrResult = namedtuple('PnrResult', [
    'bitmap', 'hdr', 'ftr', 'extra_slots',
    'constrs',        # constraints
    'config',         # device config
    'attrs',          # port attributes
    'errs'            # parsed log file
    ])


class Pnr:
    def __init__(self, gowinhome=None):
        self.cst = None
        self.netlist = None
        self.device = None
        self.partnumber = None
        self.netlist_type = "netlist"
        self.gowinhome = gowinhome or os.getenv("GOWINHOME")
        self.cfg = DeviceConfig()
        self.opt = PnrOptions()
        # print(self.cfg)
        # print(self.opt)

    def write(self, f, *, cst=None, netlist=None):
        template = """
set_option -verilog_std sysv2017
add_file -type cst {cst}
add_file -type {netlist_type} {netlist}
set_device {device_desc}
set_option {opt}
run pnr
            """

        device_desc = f'-name {self.device} {self.partnumber}'
        if self.device in ['GW1N-9', 'GW1N-4', 'GW1N-9C', 'GW2A-18', 'GW2A-18C', 'GW2AR-18C', 'GW5A-25A']:
            device_desc = f'-name {self.device} {device_desc}'
        f.write(template.format(
            cst= cst or self.cst,
            netlist= netlist or self.netlist,
            netlist_type = self.netlist_type,
            device=self.device,
            device_desc=device_desc,
            opt=self.opt.text + self.cfg.text))


    # Read the packer vendor log to identify problem with primitives/attributes
    # returns dictionary {(primitive name, error code) : [full error text]}
    @staticmethod
    def read_err_log(fname):
        _err_parser = re.compile(r"(\w+) +\(([\w\d]+)\).*'(inst[^\']+)\'.*")
        errs = {}
        with open(fname, 'r') as f:
            for line in f:
                res = _err_parser.match(line)
                if res:
                    line_type, code, name = res.groups()
                    text = res.group(0)
                    if line_type in ["Warning", "Error"]:
                        errs.setdefault((name, code), []).append(text)
        return errs

    def run_pnr(self, *, device=None, constr=None, partnumber=None, opt=None):
        device = device or self.device
        constr = constr or self.cst
        partnumber = partnumber or self.partnumber
        self.opt = opt or self.opt


        with tempfile.TemporaryDirectory() as tmpdir:

            netlist = tmpdir + "/top.v"
            cst = tmpdir + "/top.cst"

            if isinstance(self.cst, Constraints):
                with open(cst, "w") as f:
                    self.cst.write(f)
            else:
                shutil.copy(str(self.cst), cst)

            if isinstance(self.netlist, Module):
                with open(netlist, "w") as f:
                    self.netlist.write(f)
            else:
                shutil.copy(str(self.netlist), netlist)


            # shutil.copy(str(self.cst), cst)
            with open(tmpdir+"/run.tcl", "w") as f:
                self.write(f, cst=cst, netlist=netlist)

            subprocess.run(["/usr/bin/env", "LD_PRELOAD=" + self.gowinhome + "/Programmer/bin/libfontconfig.so.1", self.gowinhome + "/IDE/bin/gw_sh", tmpdir+"/run.tcl"], cwd = tmpdir)
            #print(tmpdir); input()
            try:
                return PnrResult(
                        *bslib.read_bitstream(tmpdir+"/impl/pnr/top.fs"),
                        Constraints(),
                        DeviceConfig(),
                        None,
                        None)
            except FileNotFoundError:
                print(tmpdir)
                input()
                return None



