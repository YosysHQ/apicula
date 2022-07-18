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
            f.write(";\n");
        for key, val in self.clocks.items():
            f.write("CLOCK_LOC \"{}\" {};\n".format(key, val))

class DeviceConfig:
    def __init__(self, settings):
        self.settings = settings

    @property
    def text(self):
        return "".join([' -' + name + ' ' + val for name, val in self.settings.items()])

class PnrOptions:
    def __init__(self, options):
        self.options = options

    @property
    def text(self):
        return "".join([' -' + name + ' ' + val for name, val in self.options.items()])

class Pnr:
    def __init__(self):
        self.cst = None
        self.netlist = None
        self.cfg = None
        self.device = None
        self.partnumber = None
        self.opt = None

    def write(self, f):
        template = """
add_file -type cst {cst}
add_file -type netlist {netlist}
set_device {device_desc}
set_option {opt}
run pnr
            """

        device_desc = self.partnumber
        if self.device in ['GW1N-9', 'GW1N-4', 'GW1N-9C']:
            device_desc = f'-name {self.device} {device_desc}'

        f.write(template.format(
            cst=self.cst,
            netlist=self.netlist,
            device=self.device,
            device_desc=device_desc,
            opt=self.opt.text + self.cfg.text))

