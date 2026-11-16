"""Hypothesis strategies for single primitive instances.

Parameter domains come from the IDE's primitive.xml, through
tools/gowin_primitives.py; see doc/agent/primitive-params.md. This module only
adds what the XML does not have: which primitives the fuzzer can place, and
values that depend on the device.

A Case is one primitive instance. tools/tiled_fuzzer.py places many cases in one
design.
"""
import dataclasses
import os
import re
import sys

from hypothesis import strategies as st

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gowin_primitives  # noqa: E402

# Which kind of site each supported primitive occupies. The tiled fuzzer knows
# how to place each site kind.
DFFS = ['DFF', 'DFFE', 'DFFS', 'DFFSE', 'DFFR', 'DFFRE', 'DFFP', 'DFFPE', 'DFFC', 'DFFCE',
        'DFFN', 'DFFNE', 'DFFNS', 'DFFNSE', 'DFFNR', 'DFFNRE', 'DFFNP', 'DFFNPE', 'DFFNC', 'DFFNCE']
SITES = {
    **{f'LUT{n}': 'lut' for n in range(1, 5)},
    **{name: 'dff' for name in DFFS},
    'OSC': 'osc',
    # the BSRAM types nextpnr packs (type_is_bsram in himbaechel/uarch/gowin/gowin.h)
    'rPLL': 'pll',
    'PLLA': 'plla',
    **{name: 'iob' for name in ['IBUF', 'OBUF', 'TBUF', 'IOBUF']},
    **{f'{kind}_{buf}': 'diob' for kind in ('TLVDS', 'ELVDS') for buf in ('IBUF', 'OBUF', 'TBUF', 'IOBUF')},
    # I/O logic: placed with an I/O buffer on a pin
    **{name: 'iol' for name in ['IDDR', 'IDDRC', 'ODDR', 'ODDRC', 'IDES4', 'IDES8', 'IDES10', 'IDES16',
                                'OSER4', 'OSER8', 'OSER10', 'OSER16', 'IODELAY', 'IVIDEO', 'OVIDEO']},
    **{name: 'bsram' for name in ['SP', 'SPX9', 'pROM', 'pROMX9', 'ROM', 'SDP', 'SDPB', 'SDPX9B',
                                  'DP', 'DPB', 'DPX9B']},
}

# Parameters held at their default. BSRAM contents are not in the vendor
# bitstream (bit_incl_bsram_init is off), so they cannot be compared yet.
KEEP_DEFAULT = re.compile(r'INIT_RAM_[0-9A-F]{2}$')

# PLL frequency limits in MHz, from the vendor's PA2078 message for GW1NR-9C
# ("suitable range is from 400MHz to 1200MHz"); PFD and output limits as in
# apycula/gowin_pll.py. Too few valid divider combinations survive a filter, so
# rPLL dividers are drawn to satisfy them (see pll_dividers).
PLL_LIMITS = {'pfd': (3, 400), 'vco': (400, 1200), 'clkout': (3.125, 600)}


@st.composite
def pll_dividers(draw, spec):
    """FCLKIN, IDIV_SEL, FBDIV_SEL and ODIV_SEL of an rPLL within PLL_LIMITS:
    PFD = FCLKIN/(IDIV+1), CLKOUT = PFD*(FBDIV+1), VCO = CLKOUT*ODIV."""
    lo, hi = PLL_LIMITS['pfd']
    fclkin = draw(st.sampled_from([f for f in REAL_VALUES if float(f) >= lo]))
    f = float(fclkin)
    idiv = draw(st.sampled_from([i for i in range(64) if lo <= f / (i + 1) <= hi]))
    pfd = f / (idiv + 1)
    choices = [(fb, od) for fb in range(64) for od in map(int, spec['ODIV_SEL']['values'])
               if PLL_LIMITS['clkout'][0] <= pfd * (fb + 1) <= PLL_LIMITS['clkout'][1]
               and PLL_LIMITS['vco'][0] <= pfd * (fb + 1) * od <= PLL_LIMITS['vco'][1]]
    if not choices:
        return {}
    fb, od = draw(st.sampled_from(choices))
    return {'FCLKIN': f'"{fclkin}"', 'IDIV_SEL': str(idiv), 'FBDIV_SEL': str(fb), 'ODIV_SEL': str(od)}


# I/O settings are constraint-file attributes (IO_PORT), not primitive
# parameters, so primitive.xml has no domain for them. Values are those the
# chipdb's IOB logicinfo knows; IO_TYPE maps to the bank voltage it needs.
# Single-ended standards only for now.
IO_STANDARDS = {
    'LVTTL33': '3.3', 'LVCMOS33': '3.3', 'PCI33': '3.3', 'SSTL33_I': '3.3', 'SSTL33_II': '3.3',
    'LVCMOS25': '2.5', 'SSTL25_I': '2.5', 'SSTL25_II': '2.5',
    'LVCMOS18': '1.8', 'SSTL18_I': '1.8', 'SSTL18_II': '1.8', 'HSTL18_I': '1.8', 'HSTL18_II': '1.8',
    'LVCMOS15': '1.5', 'SSTL15': '1.5', 'HSTL15_I': '1.5',
    'LVCMOS12': '1.2',
}
# Differential standards: true LVDS buffers (TLVDS_*) need true-LVDS pins,
# emulated ones (ELVDS_*) use a pair of single-ended drivers.
DIFF_STANDARDS = {
    'TLVDS': {'LVDS25': '2.5', 'RSDS': '2.5', 'MINILVDS': '2.5', 'PPLVDS': '2.5', 'LVPECL33': '3.3'},
    'ELVDS': {'LVDS25E': '2.5', 'BLVDS25E': '2.5', 'MLVDS25E': '2.5', 'RSDS25E': '2.5', 'LVPECL33E': '3.3',
              'SSTL15D': '1.5', 'SSTL18D_I': '1.8', 'SSTL25D_I': '2.5', 'SSTL33D_I': '3.3',
              'HSTL15D_I': '1.5', 'HSTL18D_I': '1.8',
              'LVCMOS33D': '3.3', 'LVCMOS25D': '2.5', 'LVCMOS18D': '1.8', 'LVCMOS15D': '1.5', 'LVCMOS12D': '1.2'},
}


IOL_IO_TYPE = 'LVCMOS33'  # standard of the buffer an I/O logic case is placed with


def io_vccio(case):
    """Bank voltage an I/O case needs."""
    if SITES.get(case.prim) == 'iol':
        return IO_STANDARDS[IOL_IO_TYPE]
    io_type = dict(case.params)['IO_TYPE']
    for table in (IO_STANDARDS, *DIFF_STANDARDS.values()):
        if io_type in table:
            return table[io_type]
    raise KeyError(io_type)


IO_INPUT_ATTRS = {'PULL_MODE': ['UP', 'DOWN', 'NONE', 'KEEPER'], 'HYSTERESIS': ['NONE', 'H2L', 'L2H', 'HIGH']}
IO_OUTPUT_ATTRS = {'PULL_MODE': ['UP', 'DOWN', 'NONE', 'KEEPER'], 'DRIVE': ['4', '8', '12', '16', '24'],
                   'SLEW_RATE': ['SLOW', 'FAST'], 'OPEN_DRAIN': ['ON', 'OFF']}


def io_case(prim):
    """An I/O buffer with IO_TYPE and a random subset of its attributes. The
    Case params are the IO_PORT attributes."""
    attrs = {}
    kind, _, buf = prim.rpartition('_')
    if kind:  # differential
        standards = DIFF_STANDARDS[kind]
        attrs['PULL_MODE'] = ['UP', 'DOWN', 'NONE']
        if buf in ('IBUF', 'IOBUF'):
            attrs['DIFF_RESISTOR'] = ['ON', 'OFF']
    else:
        standards = IO_STANDARDS
        if buf in ('IBUF', 'IOBUF'):
            attrs.update(IO_INPUT_ATTRS)
        if buf in ('OBUF', 'TBUF', 'IOBUF'):
            attrs.update(IO_OUTPUT_ATTRS)
    fields = {'IO_TYPE': st.sampled_from(sorted(standards))}
    fields.update({k: st.one_of(st.none(), st.sampled_from(v)) for k, v in attrs.items()})
    return st.fixed_dictionaries(fields).map(
        lambda d: Case(prim, tuple(sorted((k, v) for k, v in d.items() if v is not None))))


# GW5A PLLA limits, from the vendor's PA2078 messages on GW5A-25A: PFD
# (FCLKIN/IDIV_SEL) 19-400 MHz and VCO
# (FCLKIN*FBDIV_SEL*(MDIV_SEL+MDIV_FRAC_SEL/8)/IDIV_SEL) 800-1600 MHz.
PLLA_LIMITS = {'pfd': (19, 400), 'vco': (800, 1600)}


@st.composite
def plla_dividers(draw):
    lo, hi = PLLA_LIMITS['pfd']
    f = float(draw(st.sampled_from([v for v in REAL_VALUES if lo <= float(v) <= hi * 64])))
    idiv = draw(st.sampled_from([i for i in range(1, 65) if lo <= f / i <= hi]))
    fb = draw(st.integers(1, 64))
    frac = draw(st.integers(0, 7))
    vlo, vhi = PLLA_LIMITS['vco']
    mdivs = [m for m in range(2, 129) if vlo <= f * fb * (m + frac / 8) / idiv <= vhi]
    if not mdivs:
        fb, frac = 1, 0
        mdivs = [m for m in range(2, 129) if vlo <= f * (m + frac / 8) / idiv <= vhi] or [8]
    m = draw(st.sampled_from(mdivs))
    return {'FCLKIN': f'"{f:.1f}"', 'IDIV_SEL': str(idiv), 'FBDIV_SEL': str(fb),
            'MDIV_SEL': str(m), 'MDIV_FRAC_SEL': str(frac)}


def plla_fixup(p):
    """Rules between PLLA channel settings, from vendor messages on GW5A-25A:
    PA2096 CLKOUTn_PE_COARSE <= ODIVn_SEL; PA2115 channel n disabled when
    CLKn_OUT_SEL=1'b1; PA2093 CLKn_IN_SEL=1'b1 needs CLKn_OUT_SEL=1'b1 under
    some dynamic settings (avoided by not combining them)."""
    p = dict(p)
    for n in range(7):
        pe, od = f'CLKOUT{n}_PE_COARSE', f'ODIV{n}_SEL'
        if pe in p and od in p and int(p[pe]) > int(p[od]):
            p[pe] = p[od]
        if p.get(f'CLK{n}_OUT_SEL') == "1'b1":
            p[f'CLKOUT{n}_EN'] = '"FALSE"'
        elif p.get(f'CLK{n}_IN_SEL', "1'b0") not in ("1'b0", "2'b00"):
            p[f'CLK{n}_IN_SEL'] = "2'b00" if n == 4 else "1'b0"
    return p


# Rules across parameters, or values the XML allows but the vendor rejects.
# Found with tools/vendor_sweep.py; each is (primitive regex, predicate on the
# case's {name: literal}, vendor message it avoids).
RULES = [
    (r'DP', lambda p: "2'b10" not in (p.get('WRITE_MODE0'), p.get('WRITE_MODE1')),
     "PA2122: dual-port BSRAM does not support WRITE_MODE 2'b10"),
]

# Primitives in a family's primitive.xml that a device does not have: the
# vendor answers PA2085, "No '<primitive>' resource in current device"
# (doc/agent/vendor-sweep.md). Only those the fuzzer would otherwise generate.
UNAVAILABLE = {
    'GW1N-9C': {'TLVDS_IOBUF'},
    'GW2A-18C': {'IDES16', 'OSER16'},
    'GW5A-25A': {'DFF', 'DFFC', 'DFFE', 'DFFN', 'DFFNC', 'DFFNCE', 'DFFNE', 'DFFNP', 'DFFNPE', 'DFFNR',
                 'DFFNRE', 'DFFNS', 'DFFNSE', 'DFFP', 'DFFR', 'DFFS', 'OSC'},
}

# Real-valued parameters (the PLL and DCC input frequency FCLKIN) have no domain
# in primitive.xml; draw typical frequencies in MHz.
REAL_VALUES = ['3', '10', '24', '27', '50', '100', '200', '400']


def family(device):
    if device.startswith('GW5'):
        return 'gw5a'
    if device.startswith('GW2'):
        return 'gw2a'
    return 'gw1n'


@dataclasses.dataclass(frozen=True)
class Case:
    prim: str
    params: tuple  # ((name, verilog literal), ...), sorted

    @property
    def site(self):
        return SITES[self.prim]

    def to_json(self):
        return {'prim': self.prim, 'params': dict(self.params)}

    @staticmethod
    def from_json(d):
        return Case(d['prim'], tuple(sorted(d['params'].items())))


def literal(param, value):
    """Verilog literal for a value drawn from `param`'s domain."""
    if param['kind'] == 'bits':
        # in the radix of the default in primitive.xml: the vendor rejects LUT3
        # INIT 8'b10010101 and DFF INIT 1'h1 with PA1002 (invalid value), and
        # the XML has 8'h00 and 1'b0
        w = param['width']
        if "'b" in param['default']:
            return f"{w}'b{value:0{w}b}"
        return f"{w}'h{value:0{(w + 3) // 4}x}"
    if param['type'] == 'string':
        return f'"{value}"'
    return str(value)


def param_strategy(param):
    kind = param['kind']
    if kind == 'enum':
        return st.sampled_from(param['values'])
    if kind == 'range':
        lo, hi, step = param['min'], param['max'], param['step']
        return st.integers(0, (hi - lo) // step).map(lambda i: lo + i * step)
    if kind == 'bits':
        return st.integers(0, (1 << param['width']) - 1)
    if kind == 'real':
        return st.sampled_from(REAL_VALUES)
    raise ValueError(f'no strategy for {kind} parameters')


class Primitives:
    """Strategies for one device, from the XML of its family."""

    def __init__(self, device, vendor_device, gowinhome=None):
        gowinhome = gowinhome or os.environ['GOWINHOME']
        xml = os.path.join(gowinhome, gowin_primitives.XML_PATHS[family(device)])
        self.spec = gowin_primitives.load(xml)
        self.vendor_device = vendor_device

    def fixed(self, prim, name, param):
        """Literal for a parameter whose value depends on the device, else None.
        DEVICE parameters list the devices a primitive exists on; use this one."""
        if name == 'DEVICE' and param['kind'] == 'enum' and self.vendor_device in param['values']:
            return literal(param, self.vendor_device)
        if KEEP_DEFAULT.match(name):
            return f'"{param["default"]}"' if param['type'] == 'string' else param['default']
        return None

    def case(self, prim):
        if SITES.get(prim) in ('iob', 'diob'):
            return io_case(prim)
        fields = {}
        for name, param in self.spec[prim]['params'].items():
            fixed = self.fixed(prim, name, param)
            if fixed is not None:
                fields[name] = st.just(fixed)
            else:
                fields[name] = param_strategy(param).map(lambda v, p=param: literal(p, v))
        rules = [ok for pat, ok, _ in RULES if re.match(pat, prim)]
        if prim == 'rPLL':
            base = st.fixed_dictionaries(fields)
            return st.tuples(base, pll_dividers(self.spec[prim]['params'])).map(
                lambda t: Case(prim, tuple(sorted({**t[0], **t[1]}.items()))))
        if prim == 'PLLA':
            base = st.fixed_dictionaries(fields)
            return st.tuples(base, plla_dividers()).map(
                lambda t: Case(prim, tuple(sorted(plla_fixup({**t[0], **t[1]}).items()))))
        return (st.fixed_dictionaries(fields).filter(lambda d: all(ok(d) for ok in rules))
                .map(lambda d: Case(prim, tuple(sorted(d.items())))))

    def cases(self, prims=None):
        prims = sorted(prims or (p for p in SITES if p in self.spec))
        return st.sampled_from(prims).flatmap(self.case)


def draw(strategy, n, seed=0):
    """Draw up to `n` examples from `strategy`, outside a test."""
    from hypothesis import given, settings, seed as hseed, Phase, HealthCheck
    out = []

    @hseed(seed)
    @settings(max_examples=n, phases=[Phase.generate], database=None, deadline=None,
              suppress_health_check=list(HealthCheck))
    @given(strategy)
    def collect(example):
        out.append(example)

    collect()
    return out
