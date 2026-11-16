#!/usr/bin/env python3
"""Compare Apicula with the vendor on randomly configured primitives.

    pip install -e .[fuzz]
    GOWINHOME=... python3 tools/tiled_fuzzer.py -d GW1N-9C [-n 20] [--prims LUT4 DFFRE]
    GOWINHOME=... python3 tools/tiled_fuzzer.py -d GW1N-9C --replay out/batch0/mismatch_inst3.json

Hypothesis (tools/primitive_strategies.py) draws single primitive instances
("cases") with parameters from the IDE's primitive.xml. As the old tiled fuzzer
did, many cases are placed on separate sites in one design, so one vendor run
checks many of them. Each design goes through:

- the vendor: gw_sh `run pnr` on the netlist, placement fixed with INS_LOC;
- Apicula: Yosys (no synthesis), nextpnr with the same placement given as BEL
  attributes, then gowin_pack.

Each case is then checked twice:

- Both bitstreams are unpacked with gowin_unpack (tools/unpacked_netlist.py),
  and the cell on the case's site is compared: type and parameters (LUT INIT
  included) and which inputs are tied to a constant. Nets are not traced.
  Vendor and Apicula must agree, and Apicula must agree with the generated
  case.
- The bitstreams are compared tile by tile on the bits that are not routing
  fuses, which catches fuses the unpacker does not decode. Differences also
  present in a design with no cases (the I/O harness) are subtracted.

Statuses: ok; mismatch (vendor and Apicula differ); decode (they agree with
each other but not with the generated case: an unpacker bug, or a mistake both
make); invalid (the vendor rejected the case: a rule the generator should
learn); unsupported (the Apicula flow failed on it: a failure to fix, like a
mismatch). The exit status is 1 if any case failed. A design that fails in either flow is split in half and rerun
until the failing case is alone. Failing cases are written out on
their own for `--replay`.

Tools: YOSYS and NEXTPNR environment variables, else yosys/nextpnr-himbaechel,
else their yowasp- versions.
"""
import argparse
import collections
import copy
import json
import os
import random
import re
import shutil
import subprocess
import sys

TOOLS = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(TOOLS)
sys.path[:0] = [REPO, TOOLS]  # this checkout's apycula, not an installed one
import primitive_strategies as ps  # noqa: E402
import unpacked_netlist  # noqa: E402
from apycula import attrids, bslib, chipdb, codegen, gowin_unpack  # noqa: E402

# device: (vendor device, part number, package). From legacy/tiled_fuzzer.py.
DEVICES = {
    'GW1N-1': ('GW1N-1', 'GW1N-LV1LQ144C6/I5', 'LQFP144'),
    'GW1NZ-1': ('GW1NZ-1', 'GW1NZ-LV1QN48C6/I5', 'QFN48'),
    'GW1N-4': ('GW1N-4', 'GW1N-LV4PG256C6/I5', 'PBGA256'),
    'GW1N-9': ('GW1N-9', 'GW1N-LV9PG256C6/I5', 'PBGA256'),
    'GW1N-9C': ('GW1NR-9C', 'GW1NR-LV9QN88PC6/I5', 'QFN88P'),
    'GW1NS-4': ('GW1NSR-4C', 'GW1NSR-LV4CQN48PC7/I6', 'QFN48P'),
    'GW2A-18': ('GW2A-18', 'GW2A-LV18PG256C8/I7', 'PBGA256'),
    'GW2A-18C': ('GW2A-18C', 'GW2A-LV18PG256SC8/I7', 'PBGA256S'),
    'GW5A-25A': ('GW5A-25A', 'GW5A-LV25MG121NC1/I0', 'MBGA121N'),
}

CONTROL_PORTS = {'CE', 'SET', 'RESET', 'PRESET', 'CLEAR', 'GE'}

# Ports the vendor and Yosys' cell library name differently. The Apicula side
# renames them before Yosys; the mismatch itself is recorded in
# doc/agent/primitive-params.md (a vendor-style netlist with latches does not
# go through Yosys).
YOSYS_PORTS = {re.compile(r'DLN?[CP]?E?$'): {'G': 'CLK', 'GE': 'CE'}}

# Vendor log codes that make a case invalid rather than a mismatch.
INVALID_CODES = {'PA1002': 'invalid parameter value', 'CT1094': 'not placed at its constraint'}


def tool(env, *names):
    path = os.environ.get(env) or next(filter(None, map(shutil.which, names)), None)
    if not path:
        sys.exit(f'none of {names} found; set {env}')
    return path


# ---------------------------------------------------------------- sites

class Sites:
    """Free sites of each kind. A slice (CLS) holds two LUT cases or one DFF case,
    because the two flip-flops of a slice share clock, CE and set/reset modes.
    Sites are (row, col, cls, 'A'|'B') for slices and (row, col, 'BSRAM', n) for
    the n-th BSRAM of a row, which is how the vendor numbers them in INS_LOC."""

    def __init__(self, db, rng, pins=None, pinout=None):
        self.cls = [(r, c, cls) for r in range(db.rows) for c in range(db.cols)
                    for cls in range(4)
                    if {f'LUT{2 * cls}', f'LUT{2 * cls + 1}', f'DFF{2 * cls}'} <= db[r, c].bels.keys()]
        rng.shuffle(self.cls)
        # an ALU case goes in ALU1 (CLS0, B): with CIN tied to GND, nextpnr puts a
        # carry-in head in ALU0 of the same chain
        self.alu = [(r, c, 0, 'B') for r in range(db.rows) for c in range(db.cols)
                    if {'ALU0', 'ALU1'} <= db[r, c].bels.keys()]
        rng.shuffle(self.alu)
        # DSP blocks: the main tile with a 'DSP' bel, numbered per row as the
        # vendor's DSP_R<row>[n]; its DSP_AUX tiles are to the right
        self.dsp = []
        for r in range(db.rows):
            cols = [c for c in range(db.cols) if 'DSP' in db[r, c].bels]
            self.dsp += [(r, c, 'DSP', n) for n, c in enumerate(cols)]
        rng.shuffle(self.dsp)
        # SSRAM takes a whole logic tile
        self.ssram = [(r, c, 'RAM16', '-') for r in range(db.rows) for c in range(db.cols)
                      if 'RAM16' in db[r, c].bels]
        rng.shuffle(self.ssram)
        self.bsram = []
        for r in range(db.rows):
            cols = [c for c in range(db.cols) if 'BSRAM' in db[r, c].bels]
            self.bsram += [(r, c, 'BSRAM', n) for n, c in enumerate(cols)]
        rng.shuffle(self.bsram)
        # rPLLs: the vendor names them PLL_L and PLL_R by side, and PLL_L[n] when a
        # side has several (n counted top to bottom). Skip PLLs the chipdb marks
        # disabled, which nextpnr does not offer (GW2A-18C rows 10).
        self.pll = []
        for side, cols in (('L', range(db.cols // 2)), ('R', range(db.cols // 2, db.cols))):
            plls = [(r, c) for r in range(db.rows) for c in cols if 'RPLLA' in db[r, c].bels]
            for n, (r, c) in enumerate(plls):
                if not db.extra_func.get((r, c), {}).get('disabled', {}).get('PLL'):
                    self.pll.append((r, c, 'PLL', side if len(plls) == 1 else f'{side}[{n}]'))
        self.singletons = {'osc'}
        # GW5A PLLs (extra_func 'pll'), configured through a bitstream slot. The
        # vendor names them by side and row order (checked on GW5A-25A: PLL_L[0]
        # is slot 5, PLL_L[1] slot 6, PLL_R[0] slot 3, PLL_R[1] slot 2, PLL_T
        # slot 4, PLL_B slot 8).
        by_side = collections.defaultdict(list)
        for (r, c), f in sorted(db.extra_func.items()):
            if 'pll' in f:
                side = 'L' if c == 0 else 'R' if c == db.cols - 1 else 'T' if r == 0 else 'B'
                by_side[side].append((r, c))
        self.plla = [(r, c, 'PLLA', side if len(locs) == 1 else f'{side}[{n}]')
                     for side, locs in by_side.items() for n, (r, c) in enumerate(locs)]
        # I/O: plain package pins (no special function) not used by the harness,
        # as (row, col, 'IOBA'|'IOBB', pin number)
        harness = {pins['clk'], pins['out'], *pins['in']} if pins else set()
        self.iob = []
        for pin, (name, funcs) in (pinout or {}).items():
            if not funcs and pin not in harness:
                r, c, ab = io_loc(db, name)
                self.iob.append((r, c, f'IOB{ab}', pin))
        rng.shuffle(self.iob)
        # IDES16/OSER16 need an "X16 location" (vendor PR2046): pin A of a tile
        # whose io16 role is MAIN; the AUX tile beside it is used as well
        self.iob16 = [s for s in self.iob if s[2] == 'IOBA'
                      and db.extra_func.get(s[:2], {}).get('io16', {}).get('role') == 'MAIN']
        if not any('io16' in f for f in db.extra_func.values()):
            self.iob16 = self.iob  # no X16 data in the chipdb (GW5A): let the vendor say
        # differential pairs: A is the positive pin; TLVDS needs true-LVDS pins
        self.tlvds, self.elvds = [], []
        names = {name: pin for pin, (name, funcs) in (pinout or {}).items() if not funcs and pin not in harness}
        for name, pin in names.items():
            if name.endswith('A') and name[:-1] + 'B' in names:
                r, c, _ = io_loc(db, name)
                bel = db[r, c].bels.get('IOBA')
                if bel and bel.is_diff:
                    site = (r, c, 'IOBA', [pin, names[name[:-1] + 'B']])
                    (self.tlvds if bel.is_true_lvds else self.elvds).append(site)
        rng.shuffle(self.tlvds)
        # emulated LVDS can use any differential pair
        self.elvds += self.tlvds
        rng.shuffle(self.elvds)


_io_name = re.compile(r'IO([TBLR])(\d+)([A-Z])')


def io_loc(db, name):
    """(row, col, 'A'|'B') of a pin name such as IOT2A or IOL16B."""
    side, num, ab = _io_name.fullmatch(name).groups()
    num = int(num) - 1
    r, c = {'T': (0, num), 'B': (db.rows - 1, num), 'L': (num, 0), 'R': (num, db.cols - 1)}[side]
    return r, c, ab


def io_name(db, r, c, ab):
    side = 'T' if r == 0 else 'B' if r == db.rows - 1 else 'L' if c == 0 else 'R'
    return f'IO{side}{c + 1 if side in "TB" else r + 1}{ab}'


HARNESS_IO_TYPE = {'3.3': 'LVCMOS33', '2.5': 'LVCMOS25', '1.8': 'LVCMOS18', '1.5': 'LVCMOS15', '1.2': 'LVCMOS12'}
IO_PAD = {'IBUF': 'I', 'OBUF': 'O', 'TBUF': 'O', 'IOBUF': 'IO'}
DIFF_PAD = {'IBUF': ['I', 'IB'], 'OBUF': ['O', 'OB'], 'TBUF': ['O', 'OB'], 'IOBUF': ['IO', 'IOB']}
IO_SITES = ('iob', 'diob')
PIN_SITES = {'iob', 'diob', 'iol'}  # placed by IO_LOC on a pin
IOL_INPUT = {'D', 'DI'}  # I/O logic port fed by the input buffer
IOL_OUTPUT = {'Q', 'Q0', 'DO'}  # port that feeds the output buffer


def io_pads(case, site):
    """[(port, pin)] of an I/O case: one pad, or the positive and negative pads
    of a differential buffer."""
    if case.site == 'diob':
        return list(zip(DIFF_PAD[case.prim.rpartition('_')[2]], site[3]))
    return [(IO_PAD[case.prim], site[3])]


def io_class(batch):
    """Bank voltage shared by the I/O cases of a batch, or None."""
    return next((ps.io_vccio(c) for c, _ in batch if c.site in PIN_SITES), None)


def allocate(cases, sites):
    """Split cases into batches and give each a site. Returns [[(case, site), ...]]."""
    queues = collections.defaultdict(list)
    for case in cases:
        queues[case.site].append(case)
    batches = []
    for kind in ('alu', 'ssram'):  # these use slices too, so in designs of their own
        group, free = queues.pop(kind, []), getattr(sites, kind)
        for i in range(0, len(group), len(free) or 1):
            batches.append(list(zip(group[i:i + len(free)], free)))
    # I/O cases: one bank voltage per design, since a bank has one VCCIO
    by_vccio = collections.defaultdict(list)
    for case in queues.pop('iob', []) + queues.pop('diob', []) + queues.pop('iol', []):
        pool = (case.prim.split('_')[0].lower() if case.site == 'diob'
                else 'iob16' if case.prim in ('IDES16', 'OSER16') else 'iob')
        by_vccio[(ps.io_vccio(case), pool)].append(case)
    for (_, pool), group in by_vccio.items():
        free = getattr(sites, pool)
        if not free:
            print(f'no {pool} sites for {sorted({c.prim for c in group})}; {len(group)} cases not run')
            continue
        for i in range(0, len(group), len(free)):
            batches.append(list(zip(group[i:i + len(free)], free)))
    while any(queues.values()):
        batch, free = [], iter(sites.cls)
        luts = queues['lut']
        dffs = queues['dff']
        for r, c, cls in free:
            if dffs and (not luts or len(dffs) * 2 >= len(luts)):
                batch.append((dffs.pop(), (r, c, cls, 'A')))
            elif luts:
                batch.append((luts.pop(), (r, c, cls, 'A')))
                if luts:
                    batch.append((luts.pop(), (r, c, cls, 'B')))
            else:
                break
        for kind, free in (('bsram', sites.bsram), ('pll', sites.pll), ('plla', sites.plla), ('dsp', sites.dsp)):
            for site in free:
                if queues[kind]:
                    batch.append((queues[kind].pop(), site))
        for kind in sites.singletons:
            if queues[kind]:
                batch.append((queues[kind].pop(), None))
        batches.append(batch)
    return batches


# ---------------------------------------------------------------- netlist

def pick_pins(db, vendor_device, device, package):
    pins = db.pinout.get(vendor_device, db.pinout[device])[package]
    plain = sorted((p for p, (_, funcs) in pins.items() if not funcs), key=lambda p: int(p) if p.isdigit() else p)
    clocks = [p for p, (_, funcs) in pins.items() if any(f.startswith('GCLK') for f in funcs)]
    return {'clk': clocks[0], 'out': plain[0], 'in': plain[1:6]}


def netlist(batch, spec, pins, harness_io_type=None):
    """One design: an I/O harness and the cases. I/O cases get a top-level pad
    with IO_LOC and their attributes as IO_PORT; the harness pins then use
    `harness_io_type`, so that banks agree on VCCIO."""
    mod, cst = codegen.Module(), codegen.Constraints()

    def inst(typ, name, conns, params=()):
        p = codegen.Primitive(typ, name)
        for port, (direction, width) in spec[typ]['ports'].items():
            if port in conns:
                p.portmap[port] = conns[port]
            elif direction == 'input':  # the vendor rejects unconnected or constant ports
                p.portmap[port] = ['gnd'] * width if width > 1 else 'gnd'
            else:
                # the vendor reads netlists per bit: a `wire [7:0]` on a port is
                # rejected with PA2060, a concatenation of 1-bit wires is not
                wires = [f'{name}_{port}' + (f'_{b}' if width > 1 else '') for b in range(width)]
                mod.wires.update(wires)
                p.portmap[port] = wires[0] if width == 1 else wires[::-1]
        p.params = dict(params)
        mod.primitives[name] = p
        return p

    mod.wires.add('gnd')
    inst('GND', 'harness_gnd', {'G': 'gnd'})
    data = []
    for i, pin in enumerate(['clk'] + [f'in{n}' for n in range(len(pins['in']))]):
        mod.inputs.add(f'{pin}_pad')
        mod.wires.add(pin)
        inst('IBUF', f'harness_ib_{pin}', {'I': f'{pin}_pad', 'O': pin})
        cst.ports[f'{pin}_pad'] = pins['clk'] if pin == 'clk' else pins['in'][i - 1]
        if harness_io_type:
            cst.attrs[f'{pin}_pad'] = {'IO_TYPE': harness_io_type}
        if pin != 'clk':
            data.append(pin)

    # As in the old tiled fuzzer, data inputs get their own undriven dummy wires
    # and outputs are left unconnected. Nothing is routed to a LUT, so neither
    # tool reorders its inputs, and no constant reaches a case. The vendor keeps
    # cells whose outputs are unused. Slice control inputs (clock, CE, set/reset)
    # come from input pins: left undriven they become constants, which hides the
    # flip-flop type. They use dedicated slice ports, so they cannot be reordered.
    names, wiring = {}, {}
    for i, (case, site) in enumerate(batch):
        name = f'inst{i}_{case.prim}'
        names[name] = (case, site)
        conns, sources = {}, data[i % len(data):] + data[:i % len(data)]
        if case.site in IO_SITES:
            for k, (pad, pin) in enumerate(io_pads(case, site)):
                conns[pad] = f'{name}_pad' + ('_n' if k else '')
                direction = spec[case.prim]['ports'][pad][0]
                getattr(mod, {'input': 'inputs', 'output': 'outputs', 'inout': 'inouts'}[direction]).add(conns[pad])
                cst.ports[conns[pad]] = pin
                cst.attrs[conns[pad]] = dict(case.params)
        if case.site == 'iol':
            # I/O logic must connect to an I/O buffer (vendor PR0018): an IBUF
            # feeding its data input, or an OBUF fed by its output
            ports = spec[case.prim]['ports']
            data_in = next((p for p in ports if p in IOL_INPUT), None)
            pad = f'{name}_pad'
            if data_in:
                conns[data_in] = f'{name}_in'
                mod.wires.add(conns[data_in])
                mod.inputs.add(pad)
                inst('IBUF', f'{name}_buf', {'I': pad, 'O': conns[data_in]})
            else:
                out = next(p for p in ports if p in IOL_OUTPUT)
                conns[out] = f'{name}_out'
                mod.wires.add(conns[out])
                mod.outputs.add(pad)
                inst('OBUF', f'{name}_buf', {'I': conns[out], 'O': pad})
            cst.ports[pad] = site[3]
            cst.attrs[pad] = {'IO_TYPE': ps.IOL_IO_TYPE}
        for port, (d, w) in spec[case.prim]['ports'].items():
            if d != 'input' or w != 1 or port in conns:
                continue
            if case.site == 'iol' and port in ('CLK', 'PCLK', 'FCLK'):
                conns[port] = 'clk'
                continue
            if case.site in IO_SITES and sources:
                conns[port] = sources.pop(0)  # buffer data and enable inputs
            elif port == 'CLKIN' and sources:
                # a plain pin: nextpnr moves a PLL fed from a dedicated PLL input
                # pin (the harness clock on GW2A-18C) before applying its BEL
                conns[port] = sources.pop(0)
            elif port in ('CLK', 'G'):
                conns[port] = 'clk'
            elif case.site == 'alu' and port == 'CIN':
                conns[port] = 'gnd'
            elif port in CONTROL_PORTS and sources:
                conns[port] = sources.pop(0)
            else:
                conns[port] = f'{name}_{port}'
                mod.wires.add(conns[port])
        inst(case.prim, name, conns, () if case.site in IO_SITES else case.params)
        wiring[name] = conns
        if case.site in PIN_SITES:
            pass  # placed by IO_LOC
        elif site and site[2] == 'BSRAM':
            cst.cells[name] = f'BSRAM_R{site[0] + 1}[{site[3]}]'
        elif site and site[2] in ('PLL', 'PLLA'):
            cst.cells[name] = f'PLL_{site[3]}'
        elif site and site[2] == 'DSP':
            cst.cells[name] = f'DSP_R{site[0] + 1}[{site[3]}][A]'
            dsp_bel(DB[0], site[0], site[1], case.prim)
        elif site and site[2] == 'RAM16':
            cst.cells[name] = f'R{site[0] + 1}C{site[1] + 1}'
        elif site:
            cst.cells[name] = (site[0] + 1, site[1] + 1, site[2], site[3])

    mod.outputs.add('out_pad')
    inst('OBUF', 'harness_ob', {'I': data[0], 'O': 'out_pad'})
    cst.ports['out_pad'] = pins['out']
    if harness_io_type:
        cst.attrs['out_pad'] = {'IO_TYPE': harness_io_type}
    return mod, cst, names, wiring


DSP_BEL = {}  # (row, col, primitive) -> bel
DB = [None]  # the device, for dsp_bel from netlist()


def dsp_bel(db, r, c, prim):
    """First bel of a DSP primitive in a block's main tile, e.g. MULT18X1800
    (macro 0, unit 0). Its fuses are compared over the whole block."""
    if (r, c, prim) not in DSP_BEL:
        DSP_BEL[(r, c, prim)] = min((b for b in db[r, c].bels if re.fullmatch(prim + r'\d*', b)), default=None)
    return DSP_BEL[(r, c, prim)]


def bel_name(case, site):
    r, c, cls, ab = site
    if cls == 'DSP':
        return f'X{c}Y{r}/{DSP_BEL.get((r, c, case.prim))}'
    if cls == 'BSRAM':
        return f'X{c}Y{r}/BSRAM'
    if cls in ('PLL', 'PLLA'):
        return f'X{c}Y{r}/PLL'
    if cls == 'RAM16':
        return f'X{c}Y{r}/RAM16SDP4'
    if str(cls).startswith('IOB'):
        return f'X{c}Y{r}/{cls}'
    kind = {'dff': 'DFF', 'alu': 'ALU'}.get(case.site, 'LUT')
    return f'X{c}Y{r}/{kind}{2 * cls + "AB".index(ab)}'


# ---------------------------------------------------------------- flows

def run_vendor(workdir, mod, cst, vendor_device, part):
    pnr = codegen.Pnr()
    pnr.device, pnr.partnumber, pnr.netlist, pnr.cst = vendor_device, part, mod, cst
    os.makedirs(workdir, exist_ok=True)
    with open(os.path.join(workdir, 'gw_sh.log'), 'w') as log:
        return pnr.run_pnr(workdir=workdir, stdout=log)


def run_apicula(workdir, mod, cst, names, device, part):
    os.makedirs(workdir, exist_ok=True)
    mod = copy.deepcopy(mod)
    for prim in mod.primitives.values():
        for pattern, rename in YOSYS_PORTS.items():
            if pattern.match(prim.typ):
                prim.portmap = {rename.get(k, k): v for k, v in prim.portmap.items()}
    with open(os.path.join(workdir, 'top.v'), 'w') as f:
        mod.write(f)
    with open(os.path.join(workdir, 'top.cst'), 'w') as f:
        cst.write(f)
    log = open(os.path.join(workdir, 'tools.log'), 'w')
    # yowasp tools only see the working directory, so use relative paths
    subprocess.run([tool('YOSYS', 'yosys', 'yowasp-yosys'), '-q', '-p',
                    f'read_verilog -lib +/gowin/cells_sim.v; read_verilog -lib +/gowin/cells_xtra_{ps.family(device)}.v; '
                    'read_verilog top.v; hierarchy -top top; '
                    # as synth_gowin does: differential buffers' pads get IBUF/OBUF cells,
                    # which nextpnr merges; pads that already have a buffer are skipped
                    # (enables not inverted: an inverter would need synthesis to map)
                    'iopadmap -bits -inpad IBUF O:I -outpad OBUF I:O -toutpad TBUF OEN:I:O '
                    '-tinoutpad IOBUF OEN:O:I:IO top; '
                    'blackbox =A:whitebox; write_json syn.json'],
                   cwd=workdir, check=True, stdout=log, stderr=subprocess.STDOUT)
    path = os.path.join(workdir, 'syn.json')
    with open(path) as f:
        syn = json.load(f)
    for name, cell in syn['modules']['top']['cells'].items():
        if name in names and names[name][1] and names[name][0].site not in PIN_SITES | FOLLOW_NEXTPNR:
            cell['attributes']['BEL'] = bel_name(*names[name])  # nextpnr ignores INS_LOC
    with open(path, 'w') as f:
        json.dump(syn, f)
    subprocess.run([tool('NEXTPNR', 'nextpnr-himbaechel', 'yowasp-nextpnr-himbaechel-gowin'),
                    '--json', 'syn.json', '--write', 'pnr.json', '--device', part,
                    '--vopt', f'family={device}', '--vopt', 'cst=top.cst'],
                   cwd=workdir, check=True, stdout=log, stderr=subprocess.STDOUT)
    subprocess.run([sys.executable, '-m', 'apycula.gowin_pack', '-d', device, '-o', 'top.fs', 'pnr.json'],
                   cwd=workdir, check=True, stdout=log, stderr=subprocess.STDOUT,
                   env={**os.environ, 'PYTHONPATH': REPO})
    with open(os.path.join(workdir, 'pnr.json')) as f:
        placed = {n: c['attributes'].get('NEXTPNR_BEL') for n, c in json.load(f)['modules']['top']['cells'].items()}
    bm, _, _, slots = bslib.read_bitstream(os.path.join(workdir, 'top.fs'))
    return bm, slots, placed


# ---------------------------------------------------------------- compare

_masks = {}


def route_mask(db, r, c):
    ttyp = db.grid[r][c]
    if ttyp not in _masks:
        bits = set(chipdb.get_route_bits(db, r, c))
        # alonenode_6 holds the fuses that isolate long-wire segments
        for table in (db[r, c].alonenode, db[r, c].alonenode_6):
            for srcs in table.values():
                for _, fuses in srcs:
                    bits |= fuses
        _masks[ttyp] = bits
    return _masks[ttyp]


def diff_bits(db, vt, at):
    """{(row, col): {(bit, vendor value)}} for non-routing bits that differ."""
    out = {}
    for (r, c), vtile in vt.items():
        atile, mask = at[(r, c)], route_mask(db, r, c)
        bits = {((y, x), v) for y, row in enumerate(vtile) for x, v in enumerate(row)
                if v != atile[y][x] and (y, x) not in mask}
        if bits:
            out[(r, c)] = bits
    return out


_owners = {}


def bit_owner(db, r, c, bit):
    """The bel a non-routing bit configures: LUTn for INIT fuses, CLSn for the
    slice table that holds the flip-flop modes, else None (tile level)."""
    ttyp = db.grid[r][c]
    if ttyp not in _owners:
        own = {}
        for name, rows in db.shortval.get(ttyp, {}).items():
            if name.startswith('CLS'):
                for bits in rows.values():
                    own.update(dict.fromkeys(bits, name))
        for bel, b in db[r, c].bels.items():
            if bel.startswith('LUT'):
                for bits in b.flags.values():
                    own.update(dict.fromkeys(bits, bel))
        for name, rows in db.shortval.get(ttyp, {}).items():
            if name in ('IOLOGICA', 'IOLOGICB'):
                for bits in rows.values():
                    own.update(dict.fromkeys(bits, name))
        # I/O: bits in only one of the IOBA and IOBB tables belong to that bel
        io = {name: set().union(*rows.values()) for name, rows in db.longval.get(ttyp, {}).items()
              if name in ('IOBA', 'IOBB') and rows}
        if len(io) == 2:
            own.update(dict.fromkeys(io['IOBA'] - io['IOBB'], 'IOBA'))
            own.update(dict.fromkeys(io['IOBB'] - io['IOBA'], 'IOBB'))
        _owners[ttyp] = own
    return _owners[ttyp].get(bit)


def case_bel(case, site):
    r, c, cls, ab = site
    if case.site == 'iol':
        return f'IOLOGIC{cls[-1]}'
    if cls in ('BSRAM', 'PLL', 'PLLA', 'RAM16', 'DSP') or str(cls).startswith('IOB'):
        return cls
    return f'LUT{2 * cls + "AB".index(ab)}' if case.site == 'lut' else f'CLS{cls}'


def fuse_tables(db, r, c, bit):
    ttyp = db.grid[r][c]
    owners = [f'{name}{key}' for name, rows in db.shortval.get(ttyp, {}).items()
              for key, bits in rows.items() if bit in bits]
    owners += [f'{bel}.{flag}' for bel, b in db[r, c].bels.items()
               for flag, bits in b.flags.items() if bit in bits]
    return owners[:4]


# ---------------------------------------------------------------- unpacked netlists
#
# Each case sits on a known bel, so only the configuration of that bel is
# compared. Nets are dummies and are not traced; the only nets that matter are
# constants, which the unpacker ties to VCC or VSS in the same tile.

def literal_value(text):
    text = str(text).strip().strip('"')
    if re.fullmatch(r'-?\d+\.0*', text):  # gowin_unpack writes some integers as floats
        text = text.split('.')[0]
    m = re.fullmatch(r"(\d+)'([bhd])([0-9a-fA-F_]+)", text)
    if m:
        return int(m.group(3).replace('_', ''), {'b': 2, 'h': 16, 'd': 10}[m.group(2)])
    return int(text) if re.fullmatch(r'-?\d+', text) else text.upper()


def lut_init(case):
    """16-bit INIT of a generated LUTn: unused inputs do not matter."""
    n = int(case.prim[3:])
    init = literal_value(dict(case.params)['INIT'])
    return sum(((init >> (i & ((1 << n) - 1))) & 1) << i for i in range(16))


_SR = {'S': 'SET', 'R': 'RESET', 'P': 'PRESET', 'C': 'CLEAR'}


def canonical(cell, params, inputs):
    """Flip-flops in one form: no E means CE=VCC, and a set/reset input tied to
    VSS means no set/reset. The unpacker emits e.g. DFFPE with CE=VCC for DFFP.
    `inputs` maps each input port to 'VCC', 'VSS' or 'sig'."""
    m = re.fullmatch(r'(DFF|DL)(N?)([SRPC]?)(E?)', cell or '')
    if not m:
        return {'cell': cell, 'params': params, 'inputs': inputs}
    kind, neg, sr, ce = m.groups()
    if sr and inputs.get(_SR[sr]) == 'VSS':
        sr = ''
    enable = inputs.get('CE', inputs.get('GE', 'sig')) if ce else 'VCC'
    return {'cell': kind, 'params': params, 'edge': 'neg' if neg else 'pos', 'sr': sr or None, 'ce': enable}


class Decoded:
    """Cells of an unpacked bitstream, looked up by the site a case was placed on."""

    def __init__(self, nl, spec):
        self.nl, self.spec = nl, spec

    def find(self, case, site):
        if site is None:
            return next((n for n, c in self.nl.cells.items() if c['type'].startswith(case.site.upper())), None)
        r, c, cls, ab = site
        if case.site == 'iol':
            # gowin_unpack names I/O logic R<r>C<c>_<MODE>_<A|B>
            prefix, suffix = f'R{r + 1}C{c + 1}_', f'_{cls[-1]}'
            return next((n for n, cell in self.nl.cells.items() if n.startswith(prefix) and n.endswith(suffix)
                         and cell['type'] in ps.SITES and ps.SITES[cell['type']] == 'iol'), None)
        if case.site in IO_SITES:
            # gowin_unpack names I/O buffers R<r>C<c>_<TYPE>_<A|B>
            prefix, suffix = f'R{r + 1}C{c + 1}_', f'_{cls[-1]}'
            return next((n for n, cell in self.nl.cells.items() if n.startswith(prefix) and n.endswith(suffix)
                         and cell['type'].endswith('BUF')), None)
        if case.site in ('bsram', 'pll'):
            # gowin_unpack names these by a counter; find the one on this tile
            prefix, typ = f'R{r + 1}C{c + 1}_', {'bsram': 'BSRAM', 'pll': 'rPLL'}[case.site]
            return next((n for n, cell in self.nl.cells.items() if cell['type'] == typ
                         and any(str(w).startswith(prefix) for w in cell['ports'].values())), None)
        if case.site == 'ssram':
            name = f'R{r + 1}C{c + 1}_RAM16'
            return name if name in self.nl.cells else None
        if case.site == 'alu':
            name = f'R{r + 1}C{c + 1}_ALU_{2 * cls + "AB".index(ab)}'
            return name if name in self.nl.cells else None
        if case.site == 'lut':
            name = f'R{r + 1}C{c + 1}_LUT4_{2 * cls + "AB".index(ab)}'
            return name if name in self.nl.cells else None
        prefix, suffix = f'R{r + 1}C{c + 1}_', f'_{2 * cls}'
        return next((n for n, cell in self.nl.cells.items() if n.startswith(prefix) and n.endswith(suffix)
                     and cell['type'].startswith(('DFF', 'DL'))), None)  # flip-flops and latches

    def describe(self, case, site):
        name = self.find(case, site)
        if case.site == 'iol':
            cell = self.nl.cells[name] if name else None
            return {'cell': cell['type'] if cell else None,
                    'params': {k: literal_value(v) for k, v in cell['params'].items()} if cell else {}}
        if case.site in IO_SITES:
            # attributes are compared on fuses; gowin_unpack writes them to a .cst
            return {'cell': self.nl.cells[name]['type'] if name else None}
        if case.site == 'plla':
            return {'cell': 'PLLA'}  # compared through its bitstream slot in run_batch
        if case.site == 'dsp':
            return {'cell': 'DSP'}  # gowin_unpack decodes fuse-level modes only; compared on fuses
        if case.site == 'ssram' and isinstance(site[2], int):
            # nextpnr implements ROM16 as a LUT; its INIT is the ROM contents
            cell = self.nl.cells.get(f'R{site[0] + 1}C{site[1] + 1}_LUT4_{2 * site[2] + "AB".index(site[3])}')
            return {'cell': 'SSRAM' if cell else None,
                    'params': {'INIT_0': literal_value(cell['params']['INIT'])} if cell else {}}
        if case.site == 'ssram':
            # gowin_unpack writes every SSRAM as RAM16SDP4; compare INIT
            cell = self.nl.cells.get(name) if name else None
            return {'cell': 'SSRAM' if cell else None,
                    'params': {k: literal_value(v) for k, v in cell['params'].items()} if cell else {}}
        if case.site == 'alu':
            cell = self.nl.cells.get(name) if name else None
            return {'cell': 'ALU', 'params': {'ALU_MODE': literal_value(cell['params'].get('ALU_MODE'))}
                    if cell else {}} if cell else {'cell': None}
        if case.site == 'bsram':
            # gowin_unpack does not decode BSRAM parameters; the fuse comparison covers them
            return {'cell': 'BSRAM' if name else None}
        if case.site == 'pll':
            if name is None:
                return {'cell': None, 'params': {}}
            return {'cell': 'rPLL', 'params': {k: literal_value(v) for k, v in self.nl.cells[name]['params'].items()
                                               if k != 'DEVICE'}}  # not a fuse; unpacked as the family name
        if case.site == 'lut':
            if name:
                return {'cell': 'LUT', 'init': literal_value(self.nl.cells[name]['params']['INIT'])}
            # constant LUTs are written as an assign of the F wire to VCC or VSS
            r, c, cls, ab = site
            const = self.nl.find(f'R{r + 1}C{c + 1}_F{2 * cls + "AB".index(ab)}')
            return {'cell': 'LUT', 'init': {'VCC': 0xffff, 'VSS': 0}.get(const)}
        if name is None:
            return {'cell': None}
        cell = self.nl.cells[name]
        ports = self.spec.get(cell['type'], {'ports': {}})['ports']
        inputs = {}
        for port, wire in cell['ports'].items():
            if ports.get(port, ('input',))[0] == 'input':
                root = self.nl.find(wire)
                inputs[port] = root if root in ('VCC', 'VSS') else 'sig'
        return canonical(cell['type'], {k: literal_value(v) for k, v in cell['params'].items()}, inputs)


def describe_generated(case, conns, spec):
    if case.site == 'dsp':
        return {'cell': 'DSP'}
    if case.site == 'ssram':
        return {'cell': 'SSRAM', 'params': {k: literal_value(v) for k, v in case.params}}
    if case.site == 'alu':
        return {'cell': 'ALU', 'params': {'ALU_MODE': literal_value(dict(case.params)['ALU_MODE'])}}
    if case.site == 'plla':
        return {'cell': 'PLLA'}
    if case.site == 'iol':
        return {'cell': case.prim, 'params': {k: literal_value(v) for k, v in case.params}}
    if case.site in IO_SITES:
        return {'cell': case.prim}
    if case.site == 'bsram':
        return {'cell': 'BSRAM'}
    if case.site == 'pll':
        return {'cell': 'rPLL', 'params': {k: literal_value(v) for k, v in case.params if k != 'DEVICE'}}
    if case.site == 'lut':
        return {'cell': 'LUT', 'init': lut_init(case)}
    inputs = {p: 'VSS' if conns.get(p, 'gnd') == 'gnd' else 'sig'
              for p, (d, _) in spec[case.prim]['ports'].items() if d == 'input'}
    return canonical(case.prim, {k: literal_value(v) for k, v in case.params}, inputs)


def same(a, b):
    """Compare descriptions. Parameters are compared where both sides have them,
    because the unpacker does not emit every parameter."""
    if a.keys() != b.keys():
        return False
    if any(a[k] != b[k] for k in a.keys() - {'params'}):
        return False
    x, y = a.get('params') or {}, b.get('params') or {}
    return all(x[k] == y[k] for k in x.keys() & y.keys())


# Placed by nextpnr, and the vendor constrained to where nextpnr put them: ALU
# clusters ignore BEL; SSRAM with a BEL makes nextpnr crash (RAM16SDP2/4) or
# leave its blocker cells unplaced (RAM16SDP1); ROM16 becomes a LUT.
# DSP clusters get DUMMY_CELLs that stay unplaced with a BEL.
FOLLOW_NEXTPNR = {'alu', 'ssram', 'dsp'}


def vendor_failed(workdir):
    log = os.path.join(workdir, 'vendor/impl/pnr/top.log')
    why = []
    if os.path.exists(log):
        with open(log, errors='replace') as f:
            why = [line.strip() for line in f if line.startswith('ERROR')]
    return {'error': 'vendor produced no bitstream', 'why': why}, None


def run_batch(args, db, spec, pins, batch, workdir, baseline, harness_io_type=None):
    vendor_device, part, _ = DEVICES[args.device]
    mod, cst, names, wiring = netlist(batch, spec, pins, harness_io_type)
    # Cases nextpnr places itself (FOLLOW_NEXTPNR) run through Apicula first;
    # the vendor then gets the location nextpnr chose.
    follow = any(case.site in FOLLOW_NEXTPNR for case, _ in names.values())
    vres = None if follow else run_vendor(os.path.join(workdir, 'vendor'), mod, cst, vendor_device, part)
    if not follow and vres is None:
        return vendor_failed(workdir)
    try:
        abm, aslots, placed = run_apicula(os.path.join(workdir, 'apicula'), mod, cst, names, args.device, part)
    except subprocess.CalledProcessError:
        with open(os.path.join(workdir, 'apicula/tools.log'), errors='replace') as f:
            why = [line.strip() for line in f
                   if 'ERROR' in line or re.match(r'\w*(Error|Exception): ', line)]
        return {'error': 'the Apicula flow failed', 'why': why}, None
    if follow:
        for name, (case, site) in list(names.items()):
            if case.site in FOLLOW_NEXTPNR:
                m = re.fullmatch(r'X(\d+)Y(\d+)/(\w+)', placed.get(name) or '')
                if m and case.site == 'dsp':
                    # DSP_R<row>[n][A|B]: n-th DSP block of the row, macro from the bel name
                    c, r, bel = int(m.group(1)), int(m.group(2)), m.group(3)
                    cols = [cc for cc in range(db.cols) if 'DSP' in db[r, cc].bels]
                    if c not in cols:
                        continue
                    macro = bel[len(case.prim):][:1]
                    names[name] = (case, (r, c, 'DSP', cols.index(c)))
                    cst.cells[name] = f'DSP_R{r + 1}[{cols.index(c)}]' + (f'[{"AB"[int(macro)]}]' if macro else '')
                    continue
                m = re.fullmatch(r'X(\d+)Y(\d+)/(ALU|LUT|RAM16SDP4)(\d?)', placed.get(name) or '')
                if not m:
                    continue
                c, r = int(m.group(1)), int(m.group(2))
                if m.group(3) == 'RAM16SDP4':
                    site = (r, c, 'RAM16', '-')
                    cst.cells[name] = f'R{r + 1}C{c + 1}'
                else:
                    n = int(m.group(4))
                    site = (r, c, n // 2, 'AB'[n % 2])
                    cst.cells[name] = (r + 1, c + 1, n // 2, 'AB'[n % 2])
                names[name] = (case, site)
        vres = run_vendor(os.path.join(workdir, 'vendor'), mod, cst, vendor_device, part)
        if vres is None:
            return vendor_failed(workdir)
    vt = chipdb.tile_bitmap(db, vres.bitmap, empty=True)
    at = chipdb.tile_bitmap(db, abm, empty=True)
    diffs = diff_bits(db, vt, at)
    decoded = {}
    if batch:
        for side, fs in (('vendor', os.path.join(workdir, 'vendor/impl/pnr/top.fs')),
                         ('apicula', os.path.join(workdir, 'apicula/top.fs'))):
            nl = unpacked_netlist.unpack(args.device, fs, os.path.join(workdir, f'{side}_unpack.v'), REPO)
            decoded[side] = Decoded(nl, spec)
    if baseline is not None:
        diffs = {k: v - baseline.get(k, set()) for k, v in diffs.items()}
        diffs = {k: v for k, v in diffs.items() if v}

    results = {}
    by_bel = {}  # (row, col, bel) -> case name
    by_tile = collections.defaultdict(list)
    for name, (case, site) in names.items():
        res = {'case': case.to_json(), 'site': site, 'status': 'ok'}
        problems = [msg for (n, code), msgs in vres.errs.items() if n == name
                    for msg in msgs if code in INVALID_CODES or msg.startswith('ERROR')]
        # I/O is placed by IO_LOC; nextpnr merges differential buffers into cells
        # of other names, so check placement for the rest only
        if site and case.site not in PIN_SITES | FOLLOW_NEXTPNR and placed.get(name) != bel_name(case, site):
            problems.append(f'nextpnr placed it at {placed.get(name)}')
        if problems:
            res['status'] = 'invalid'
            res['why'] = problems
        else:
            gen = describe_generated(case, wiring[name], spec)
            dv, da = decoded['vendor'].describe(case, site), decoded['apicula'].describe(case, site)
            if not same(dv, da):
                res['status'] = 'mismatch'
            elif not same(da, gen):
                res['status'] = 'decode'
            if res['status'] != 'ok':
                res['generated'], res['vendor'], res['apicula'] = gen, dv, da
        results[name] = res
        if site:
            loc = (site[0], site[1])
        else:
            # the bel is named after the primitive (OSCA) or the site kind (OSC)
            loc = SINGLETON_LOCS.setdefault(case.prim, find_bel(db, case.prim) or find_bel(db, case.site.upper()))
        by_tile[loc].append(name)
        if site and site[2] == 'BSRAM':
            # a BSRAM's fuses are in its tile and the two tiles to its right:
            # BSRAM_AUX bels on GW1N/GW2A, tiles with BSRAM tables but no bel on GW5A
            for dc in (1, 2):
                if loc[1] + dc < db.cols:
                    aux = db[loc[0], loc[1] + dc]
                    if 'BSRAM_AUX' in aux.bels or ('BSRAM' not in aux.bels
                                                    and 'BSRAM_SP' in db.shortval.get(aux.ttyp, {})):
                        by_tile[(loc[0], loc[1] + dc)].append(name)
        if case.site in PIN_SITES:
            # bank settings are shared by every I/O in the bank
            bank = db.pin_bank.get(io_name(db, site[0], site[1], site[2][-1]))
            if bank in db.bank_tiles:
                by_tile[db.bank_tiles[bank]].append(name)
        if site and site[2] == 'DSP':
            # a DSP block's fuses are in its main tile and the DSP_AUX tiles to its right
            dc = 1
            while loc[1] + dc < db.cols and any(b.startswith('DSP_AUX') for b in db[loc[0], loc[1] + dc].bels):
                by_tile[(loc[0], loc[1] + dc)].append(name)
                dc += 1
        if site and site[2] == 'PLL':
            # an rPLL's fuses are in its RPLLA tile and the adjacent RPLLB tiles
            for dc in (-3, -2, -1, 1, 2, 3):
                if 0 <= loc[1] + dc < db.cols and 'RPLLB' in db[loc[0], loc[1] + dc].bels:
                    by_tile[(loc[0], loc[1] + dc)].append(name)
        if site:
            by_bel[(*loc, case_bel(case, site))] = name

    # GW5A PLLs: compare the slot bits and the slot's decoded PLL attributes
    for name, (case, site) in names.items():
        if case.site != 'plla' or results[name]['status'] != 'ok':
            continue
        slot = db.extra_func[(site[0], site[1])]['pll']['slot_idx']
        vs, as_ = vres.extra_slots.get(slot), aslots.get(slot)
        if vs is None or as_ is None:
            results[name]['status'] = 'mismatch'
            results[name]['why'] = [f'slot {slot}: vendor {"has" if vs else "lacks"} it, '
                                    f'apicula {"has" if as_ else "lacks"} it']
            continue
        bits = [(y, x, v) for y, row in enumerate(vs) for x, v in enumerate(row) if v != as_[y][x]]
        if bits:
            dec = [gowin_unpack.parse_attrvals(b, db.rev_logicinfo('PLL'), db.shortval[1024]['PLL'],
                                               attrids.pll_attrids, 'PLL') for b in (vs, as_)]
            results[name]['status'] = 'mismatch'
            results[name]['why'] = [f'slot {slot}: {len(bits)} bits differ']
            results[name]['slot_attrs'] = {
                k: (dec[0].get(k), dec[1].get(k)) for k in dec[0].keys() | dec[1].keys()
                if dec[0].get(k) != dec[1].get(k)}

    # Unused I/Os are configured from their bank's settings, so differences in
    # an I/O tile with no case belong to the I/O cases of that bank.
    by_bank = collections.defaultdict(list)
    for name, (case, site) in names.items():
        if case.site in PIN_SITES:
            by_bank[db.pin_bank.get(io_name(db, site[0], site[1], site[2][-1]))].append(name)

    def bank_cases(r, c):
        if not any(b.startswith('IOB') for b in db[r, c].bels):
            return []
        banks = {db.pin_bank.get(io_name(db, r, c, ab)) for ab in 'AB'}
        return [n for b in banks for n in by_bank.get(b, [])]

    unattributed = {}
    for (r, c), bits in sorted(diffs.items()):
        for bit, v in sorted(bits):
            bel = bit_owner(db, r, c, bit)
            owners = [by_bel[(r, c, bel)]] if (r, c, bel) in by_bel else by_tile.get((r, c)) or bank_cases(r, c)
            detail = f'{bit} vendor={v} apicula={1 - v} {bel or ""} {fuse_tables(db, r, c, bit)}'
            if not owners:
                unattributed.setdefault(f'R{r + 1}C{c + 1}', []).append(detail)
            for name in owners:
                if results[name]['status'] == 'ok':
                    results[name]['status'] = 'mismatch'
                results[name].setdefault('diffs', {}).setdefault(f'R{r + 1}C{c + 1}', []).append(detail)
    report = {'cases': results, 'unattributed': unattributed}
    return report, diffs


SINGLETON_LOCS = {}


def find_bel(db, bel):
    return next(((r, c) for r in range(db.rows) for c in range(db.cols) if bel in db[r, c].bels), None)


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('-d', '--device', required=True, choices=sorted(DEVICES))
    ap.add_argument('-n', '--count', type=int, default=10, help='cases per primitive')
    ap.add_argument('--prims', nargs='*', help='primitives to fuzz (default: all supported)')
    ap.add_argument('--seed', type=int, default=0)
    ap.add_argument('--replay', nargs='*', help='case JSON files to run, one per design')
    ap.add_argument('-o', '--out', default='fuzz-out')
    args = ap.parse_args(argv)

    vendor_device, part, package = DEVICES[args.device]
    db = chipdb.load_chipdb(os.path.join(os.path.dirname(chipdb.__file__), f'{args.device}.msgpack.xz'))
    DB[0] = db
    prims = ps.Primitives(args.device, vendor_device)
    pins = pick_pins(db, vendor_device, args.device, package)
    rng = random.Random(args.seed)
    pinout = db.pinout.get(vendor_device, db.pinout[args.device])[package]
    sites = Sites(db, rng, pins, pinout)

    if args.replay:
        batches = []
        for path in args.replay:
            with open(path) as f:
                d = json.load(f)
            batches.append([(ps.Case.from_json(d['case']), tuple(d['site']) if d['site'] else None)])
    else:
        names = args.prims or [p for p in ps.SITES if p in prims.spec
                               and p not in ps.UNAVAILABLE.get(args.device, ())]
        cases = [c for p in names for c in set(ps.draw(prims.case(p), args.count, args.seed))]
        rng.shuffle(cases)
        batches = allocate(cases, sites)

    print(f'{sum(map(len, batches))} cases in {len(batches)} designs; pins {pins}')
    baselines = {}

    def baseline_for(batch):
        """Differences of the harness alone, with the harness I/O standard the
        batch needs. They are subtracted from the batch's differences."""
        vccio = io_class(batch)
        if vccio not in baselines:
            io_type = HARNESS_IO_TYPE.get(vccio)
            _, b = run_batch(args, db, prims.spec, pins, [], os.path.join(args.out, f'baseline_{io_type}'),
                             None, io_type)
            if b is None:
                sys.exit(f'the harness alone ({io_type}) failed in the vendor flow')
            print(f'harness ({io_type or "default I/O"}) differences, ignored: {sum(map(len, b.values()))} bits in '
                  f'{" ".join(f"R{r + 1}C{c + 1}" for r, c in sorted(b))}')
            baselines[vccio] = b
        return baselines[vccio]

    totals = collections.Counter()
    queue = [(f'batch{i}', b) for i, b in enumerate(batches)]
    while queue:
        i, batch = queue.pop(0)
        workdir = os.path.join(args.out, i)
        report, _ = run_batch(args, db, prims.spec, pins, batch, workdir, baseline_for(batch),
                              HARNESS_IO_TYPE.get(io_class(batch)))
        with open(os.path.join(workdir, 'report.json'), 'w') as f:
            json.dump(report, f, indent=1)
        if 'error' in report:
            if len(batch) > 1:
                # an error stops the whole design: split it to find the case. If
                # Apicula fails on a design the vendor accepts, that is a failure
                # in itself, even when every case passes alone.
                half = len(batch) // 2
                print(f'{i}: {report["error"]}; splitting')
                for line in dict.fromkeys(report.get('why', [])):
                    print('    ', line)
                if 'Apicula' in report['error']:
                    totals['unsupported combinations'] += 1
                    with open(os.path.join(workdir, 'unsupported_combination.json'), 'w') as f:
                        json.dump({'cases': [(c.to_json(), s) for c, s in batch], 'why': report.get('why', [])},
                                  f, indent=1)
                queue[:0] = [(f'{i}a', batch[:half]), (f'{i}b', batch[half:])]
                continue
            case, site = batch[0]
            # unsupported is a failure to fix in Apicula, not a case to drop
            status = 'unsupported' if 'Apicula' in report['error'] else 'invalid'
            res = {'case': case.to_json(), 'site': site, 'status': status, 'why': report.get('why', [])}
            path = os.path.join(workdir, f'{status}_{case.prim}.json')
            with open(path, 'w') as f:
                json.dump(res, f, indent=1)
            print(f'{i} {status}: {case.to_json()} at {site} -> {path}')
            for line in dict.fromkeys(res['why']):
                print('    ', line)
            totals[status] += 1
            continue
        for name, res in report['cases'].items():
            totals[res['status']] += 1
            if res['status'] != 'ok':
                path = os.path.join(workdir, f'{res["status"]}_{name}.json')
                with open(path, 'w') as f:
                    json.dump(res, f, indent=1)
                print(f'{i} {name} {res["status"]}: {res["case"]} at {res["site"]} -> {path}')
                for side in ('generated', 'vendor', 'apicula'):
                    if side in res:
                        print(f'     {side:9}', res[side])
                for line in res.get('why', []):
                    print('    ', line)
                for tile, bits in res.get('diffs', {}).items():
                    print(f'     {tile}:', *bits, sep='\n       ')
        for tile, bits in report['unattributed'].items():
            totals['unattributed tiles'] += 1
            print(f'{i} unattributed {tile}:', *bits, sep='\n       ')
    print('summary:', dict(totals))
    # invalid cases are generator problems (a vendor rule to learn); the rest are failures
    return 1 if totals.keys() & {'mismatch', 'decode', 'unsupported', 'unsupported combinations',
                                 'unattributed tiles'} else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
