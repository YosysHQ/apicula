from itertools import chain

class Module:
    def __init__(self):
        self.inputs = set()
        self.outputs = set()
        self.inouts = set()
        self.wires = set()
        self.assigns = []
        self.primitives = {}

    def __add__(self, other):
        m = Module()
        m.inputs = self.inputs | other.inputs
        m.outputs = self.outputs | other.outputs
        m.inouts = self.inouts | other.inouts
        m.wires = self.wires | other.wires
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
            f.write(port)
        f.write(");\n")

        for port in self.inputs:
            f.write("input {};\n".format(port))
        for port in self.outputs:
            f.write("output {};\n".format(port))
        for port in self.inouts:
            f.write("inout {};\n".format(port))

        for wire in self.wires:
            f.write("wire {};\n".format(wire))

        # unique assignments or not
        #for dest, src in self.assigns:
        for dest, src in dict(self.assigns).items():
            f.write("assign {} = {};\n".format(dest, src))

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
            f.write("\n.{}({})".format(port, wire))
        f.write("\n);\n")

        for key, val in self.params.items():
            f.write("defparam {}.{} = {};\n".format(self.inst, key, val))

class Constraints:
    def __init__(self):
        self.cells = {}
        self.ports = {}

    def __add__(self, other):
        cst = Constraints()
        cst.cells = {**self.cells, **other.cells}
        cst.ports = {**self.ports, **other.ports}
        return cst

    def write(self, f):
        for key, val in self.cells.items():
            f.write("INS_LOC \"{}\" {};\n".format(key, val))
        for key, val in self.ports.items():
            f.write("IO_LOC \"{}\" {};\n".format(key, val))

class DeviceConfig:
    def __init__(self, settings):
        self.settings = settings

    def write(self, f):
        for key, val in self.settings.items():
            f.write("set {} = {}\n".format(key, val))

class PnrOptions:
    def __init__(self, options):
        self.options = options

    def write(self, f):
        for opt in self.options:
            f.write("-{}\n".format(opt))

class Pnr:
    def __init__(self):
        self.cst = None
        self.netlist = None
        self.cfg = None
        self.device = None
        self.partnumber = None
        self.opt = None
        self.outdir = None

    def write(self, f):
        template = """
            add_file -cst {cst}
            add_file -vm {netlist}
            add_file -cfg {cfg}
            set_option -device {device}
            set_option -pn {partnumber}
            set_option -out_dir {outdir}
            run_pnr -opt {opt}
            """
        f.write(template.format(
            cst=self.cst,
            netlist=self.netlist,
            cfg=self.cfg,
            device=self.device,
            partnumber=self.partnumber,
            opt=self.opt,
            outdir=self.outdir))
