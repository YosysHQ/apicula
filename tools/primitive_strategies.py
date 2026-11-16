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
    **{name: 'iob' for name in ['IBUF', 'OBUF', 'TBUF', 'IOBUF']},
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
IO_INPUT_ATTRS = {'PULL_MODE': ['UP', 'DOWN', 'NONE', 'KEEPER'], 'HYSTERESIS': ['NONE', 'H2L', 'L2H', 'HIGH']}
IO_OUTPUT_ATTRS = {'PULL_MODE': ['UP', 'DOWN', 'NONE', 'KEEPER'], 'DRIVE': ['4', '8', '12', '16', '24'],
                   'SLEW_RATE': ['SLOW', 'FAST'], 'OPEN_DRAIN': ['ON', 'OFF']}


def io_case(prim):
    """An I/O buffer with IO_TYPE and a random subset of its attributes. The
    Case params are the IO_PORT attributes."""
    attrs = {}
    if prim in ('IBUF', 'IOBUF'):
        attrs.update(IO_INPUT_ATTRS)
    if prim in ('OBUF', 'TBUF', 'IOBUF'):
        attrs.update(IO_OUTPUT_ATTRS)
    fields = {'IO_TYPE': st.sampled_from(sorted(IO_STANDARDS))}
    fields.update({k: st.one_of(st.none(), st.sampled_from(v)) for k, v in attrs.items()})
    return st.fixed_dictionaries(fields).map(
        lambda d: Case(prim, tuple(sorted((k, v) for k, v in d.items() if v is not None))))


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
        if SITES.get(prim) == 'iob':
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
