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
}

# Parameters whose legal value depends on the device rather than on the XML.
# Called with the vendor device name (as passed to set_device).
DEVICE_PARAMS = {
    ('OSC', 'DEVICE'): lambda vendor_device: vendor_device,
}


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
    raise ValueError(f'no strategy for {kind} parameters')


class Primitives:
    """Strategies for one device, from the XML of its family."""

    def __init__(self, device, vendor_device, gowinhome=None):
        gowinhome = gowinhome or os.environ['GOWINHOME']
        xml = os.path.join(gowinhome, gowin_primitives.XML_PATHS[family(device)])
        self.spec = gowin_primitives.load(xml)
        self.vendor_device = vendor_device

    def case(self, prim):
        fields = {}
        for name, param in self.spec[prim]['params'].items():
            fixed = DEVICE_PARAMS.get((prim, name))
            if fixed:
                fields[name] = st.just(literal(param, fixed(self.vendor_device)))
            else:
                fields[name] = param_strategy(param).map(lambda v, p=param: literal(p, v))
        return st.fixed_dictionaries(fields).map(lambda d: Case(prim, tuple(sorted(d.items()))))

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
