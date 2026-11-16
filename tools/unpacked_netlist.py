"""Read gowin_unpack output as a netlist: cells, parameters and resolved nets.

gowin_unpack writes routing as `assign` statements and `` `define `` aliases.
Every wire joined by them is one net. Each net has a root name, and `driver`
gives the cell output on it.
"""
import os
import re
import subprocess
import sys

_define = re.compile(r'`define (\S+) (\S+)')
_assign = re.compile(r'assign `?(\S+) = `?(\S+);')
_cell = re.compile(r'([A-Za-z_][\w]*) ([\w]+) \($')
_port = re.compile(r'\.(\w+)\(`?([^)]*)\),?$')
_defparam = re.compile(r'defparam (\w+)\.(\w+) = (.*);')


class Netlist:
    def __init__(self, path):
        self.parent = {}
        self.cells = {}  # name -> {'type', 'ports': {port: wire}, 'params'}
        cell = None
        with open(path) as f:
            for line in f:
                line = line.strip()
                if cell is not None:
                    m = _port.match(line)
                    if m:
                        cell['ports'][m.group(1)] = m.group(2).strip()
                    elif line.startswith(');'):
                        cell = None
                    continue
                m = _assign.match(line) or _define.match(line)
                if m:
                    self.union(m.group(1), m.group(2))
                    continue
                m = _defparam.match(line)
                if m:
                    self.cells[m.group(1)]['params'][m.group(2)] = m.group(3).strip()
                    continue
                m = _cell.match(line)
                if m and m.group(1) not in ('module', 'input', 'output', 'inout', 'wire'):
                    cell = {'type': m.group(1), 'ports': {}, 'params': {}}
                    self.cells[m.group(2)] = cell
        self.driver = {}

    def find(self, w):
        root = w
        while self.parent.get(root, root) != root:
            root = self.parent[root]
        while self.parent.get(w, w) != root:  # path compression
            self.parent[w], w = root, self.parent[w]
        return root

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            # keep the constants as roots so they are recognisable
            if ra in ('VCC', 'VSS'):
                ra, rb = rb, ra
            self.parent[ra] = rb

    def set_outputs(self, outputs):
        """outputs: cell type -> set of output port names (from primitive.xml)."""
        for name, cell in self.cells.items():
            for port, wire in cell['ports'].items():
                if port in outputs.get(cell['type'], ()):
                    self.driver[self.find(wire)] = (name, port)


def unpack(device, fs, out, repo):
    subprocess.run([sys.executable, '-m', 'apycula.gowin_unpack', '-d', device, '-o', out, fs],
                   check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                   env={**os.environ, 'PYTHONPATH': repo})
    return Netlist(out)
