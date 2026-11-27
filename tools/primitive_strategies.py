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

TOOLS = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.dirname(TOOLS), TOOLS]  # this checkout's apycula
import gowin_primitives  # noqa: E402
from apycula import gowin_pll  # noqa: E402
from apycula.gowin_pack import BankDesc  # noqa: E402

# Pseudo-primitives, not in primitive.xml: a flip-flop fed by an input pad
# (IOB_IREG), driving an output pad (IOB_OREG), or one of each on an inout pad
# (IOB_IOREG), which the tools pack into the pad's I/O logic when asked to
# (vendor -ireg_in_iob/-oreg_in_iob/-ioreg_in_iob, nextpnr --vopt <same>);
# and IO_BANK, several buffers in one bank (io_bank_case).
IOB_REGS = ['IOB_IREG', 'IOB_OREG', 'IOB_IOREG']

# Which kind of site each supported primitive occupies. The tiled fuzzer knows
# how to place each site kind.
DFFS = ['DFF', 'DFFE', 'DFFS', 'DFFSE', 'DFFR', 'DFFRE', 'DFFP', 'DFFPE', 'DFFC', 'DFFCE',
        'DFFN', 'DFFNE', 'DFFNS', 'DFFNSE', 'DFFNR', 'DFFNRE', 'DFFNP', 'DFFNPE', 'DFFNC', 'DFFNCE']
SITES = {
    **{f'LUT{n}': 'lut' for n in range(1, 5)},
    **{name: 'dff' for name in DFFS},
    # latches share the flip-flop slots
    **{name: 'dff' for name in ['DL', 'DLE', 'DLC', 'DLCE', 'DLP', 'DLPE',
                                'DLN', 'DLNE', 'DLNC', 'DLNCE', 'DLNP', 'DLNPE']},
    'OSC': 'osc',
    'OSCA': 'osc',
    'ALU': 'alu',
    # DSP: one case per DSP block
    **{name: 'dsp' for name in ['MULT9X9', 'MULT18X18', 'MULT36X36', 'MULTALU18X18', 'MULTALU36X18',
                                'MULTADDALU18X18', 'PADD9', 'PADD18', 'ALU54D',
                                'MULT12X12', 'MULT27X36', 'MULTADDALU12X12', 'MULTALU27X18']},
    # SSRAM: a whole logic tile
    **{name: 'ssram' for name in ['RAM16SDP1', 'RAM16SDP2', 'RAM16SDP4', 'ROM16', 'RAM16S1', 'RAM16S2', 'RAM16S4']},
    'rPLL': 'pll',
    'PLL': 'pll',  # GW1N/GW2A non-reconfigurable PLL; same sites as rPLL
    'PLLA': 'plla',
    # wide LUTs: a MUX2_LUTn tree with LUT4 leaves
    **{f'MUX2_LUT{n}': 'widelut' for n in range(5, 9)},
    # clock buffers, dividers and selectors: one per design, driving the harness output
    **{name: 'clock' for name in ['CLKDIV', 'CLKDIV2', 'DCS', 'DQCE', 'DHCEN', 'BUFG', 'BUFS',
                                  'DCC', 'DCCG', 'DHCENC', 'DHCE', 'DCE', 'CLKDIVG']},
    # oscillators of other devices
    **{name: 'osc' for name in ['OSCZ', 'OSCH', 'OSCW', 'OSCO', 'OSCF', 'OSCB']},
    **{name: 'iob' for name in ['IBUF', 'OBUF', 'TBUF', 'IOBUF']},
    **{f'{kind}_{buf}': 'diob' for kind in ('TLVDS', 'ELVDS') for buf in ('IBUF', 'OBUF', 'TBUF', 'IOBUF')},
    # I/O logic: placed with an I/O buffer on a pin
    **{name: 'iol' for name in ['IDDR', 'IDDRC', 'ODDR', 'ODDRC', 'IDES4', 'IDES8', 'IDES10', 'IDES16',
                                'OSER4', 'OSER8', 'OSER10', 'OSER16', 'IODELAY', 'IVIDEO', 'OVIDEO',
                                'IODELAYA', 'IODELAYC', 'IDES14', 'IDES32', 'OSER14']},
    **{name: 'bsram' for name in ['SP', 'SPX9', 'pROM', 'pROMX9', 'ROM', 'SDP', 'SDPB', 'SDPX9B',
                                  'DP', 'DPB', 'DPX9B', 'DPX9', 'SDPX9', 'ROMX9',
                                  'rROM', 'rROMX9', 'rSDP', 'rSDPX9']},
    **{name: 'iobreg' for name in IOB_REGS},
    'IO_BANK': 'iobank',
}

# Parameters held at their default. BSRAM contents are not in the vendor
# bitstream (bit_incl_bsram_init is off), so they cannot be compared yet.
KEEP_DEFAULT = re.compile(r'INIT_RAM_[0-9A-F]{2}$')

# rPLL frequency limits: apycula/gowin_pll.py's table, by device and the speed
# grade of the part the fuzzer uses. GW1NR-9 C6/I5 (VCO 400-1200 MHz) agrees
# with the vendor's PA2078 message for GW1NR-9C. Too few valid divider
# combinations survive a filter, so rPLL dividers are drawn to satisfy them
# (see pll_dividers).
PLL_LIMITS = {
    'GW1N-1': 'GW1N-1 C6/I5', 'GW1NZ-1': 'GW1NZ-1 C6/I5', 'GW1N-4': 'GW1NR-4 C6/I5',
    'GW1N-9': 'GW1NR-9 C6/I5', 'GW1N-9C': 'GW1NR-9 C6/I5', 'GW1NS-4': 'GW1NSR-4C C7/I6',
    'GW2A-18': 'GW2A-18 C8/I7', 'GW2A-18C': 'GW2A-18 C8/I7',
}


@st.composite
def pll_dividers(draw, spec, device):
    """FCLKIN, IDIV_SEL, FBDIV_SEL and ODIV_SEL of an rPLL within the device's
    limits: PFD = FCLKIN/(IDIV+1), CLKOUT = PFD*(FBDIV+1), VCO = CLKOUT*ODIV."""
    lim = gowin_pll.DEVICE_LIMITS[PLL_LIMITS[device]]
    lo, hi = lim['pfd_min'], lim['pfd_max']
    fclkin = draw(st.sampled_from([f for f in REAL_VALUES if float(f) >= lo]))
    f = float(fclkin)
    idiv = draw(st.sampled_from([i for i in range(64) if lo <= f / (i + 1) <= hi]))
    pfd = f / (idiv + 1)
    choices = [(fb, od) for fb in range(64) for od in map(int, spec['ODIV_SEL']['values'])
               if lim['clkout_min'] <= pfd * (fb + 1) <= lim['clkout_max']
               and lim['vco_min'] <= pfd * (fb + 1) * od <= lim['vco_max']]
    if not choices:
        return {}
    fb, od = draw(st.sampled_from(choices))
    return {'FCLKIN': f'"{fclkin}"', 'IDIV_SEL': str(idiv), 'FBDIV_SEL': str(fb), 'ODIV_SEL': str(od)}


# I/O settings are constraint-file attributes (IO_PORT), not primitive
# parameters, so primitive.xml has no domain for them. Values are those the
# chipdb's IOB logicinfo knows. The bank voltage each IO_TYPE needs is
# gowin_pack's (BankDesc._vcc_ios), so cases are grouped by bank as it groups them.
IO_STANDARDS = ['LVTTL33', 'LVCMOS33', 'PCI33', 'SSTL33_I', 'SSTL33_II',
                'LVCMOS25', 'SSTL25_I', 'SSTL25_II',
                'LVCMOS18', 'SSTL18_I', 'SSTL18_II', 'HSTL18_I', 'HSTL18_II',
                'LVCMOS15', 'SSTL15', 'HSTL15_I', 'LVCMOS12']
# Differential standards: true LVDS buffers (TLVDS_*) need true-LVDS pins,
# emulated ones (ELVDS_*) use a pair of single-ended drivers.
DIFF_STANDARDS = {
    'TLVDS': ['LVDS25', 'RSDS', 'MINILVDS', 'PPLVDS', 'LVPECL33'],
    'ELVDS': ['LVDS25E', 'BLVDS25E', 'MLVDS25E', 'RSDS25E', 'LVPECL33E', 'SSTL15D', 'SSTL18D_I', 'SSTL25D_I',
              'SSTL33D_I', 'HSTL15D_I', 'HSTL18D_I', 'LVCMOS33D', 'LVCMOS25D', 'LVCMOS18D', 'LVCMOS15D', 'LVCMOS12D'],
}


IOL_IO_TYPE = 'LVCMOS33'  # standard of the buffer an I/O logic case is placed with


def io_vccio(case, device):
    """Bank voltage an I/O case needs: its IO_TYPE's, else its BANK_VCCIO,
    else that of the vendor's default IO_TYPE."""
    params = dict(case.params)
    io_type = IOL_IO_TYPE if case.site in ('iol', 'iobreg') else params.get('IO_TYPE')
    if io_type is None and 'BANK_VCCIO' in params:
        return params['BANK_VCCIO']
    return BankDesc._vcc_ios[io_type or DEFAULT_IO_TYPE[family(device)]]


# IO_TYPE of a single-ended buffer without one, from the vendor's top.io.cst
# (measured with an OBUF on GW1N-9C, GW2A-18C and GW5A-25A, assumed for the rest
# of each family)
DEFAULT_IO_TYPE = {'gw1n': 'LVCMOS18', 'gw2a': 'LVCMOS18', 'gw5a': 'LVCMOS33'}
BANK_VCCIOS = ['3.3', '2.5', '1.8', '1.5', '1.2']


IO_INPUT_ATTRS = {'PULL_MODE': ['UP', 'DOWN', 'NONE', 'KEEPER'], 'HYSTERESIS': ['NONE', 'H2L', 'L2H', 'HIGH']}
IO_OUTPUT_ATTRS = {'PULL_MODE': ['UP', 'DOWN', 'NONE', 'KEEPER'], 'DRIVE': ['4', '8', '12', '16', '24'],
                   'SLEW_RATE': ['SLOW', 'FAST'], 'OPEN_DRAIN': ['ON', 'OFF']}


def io_case(prim):
    """An I/O buffer with a random subset of its attributes. A single-ended
    buffer may also omit IO_TYPE (the vendor then uses DEFAULT_IO_TYPE) and
    set BANK_VCCIO. The Case params are the IO_PORT attributes."""
    attrs, fields = {}, {}
    kind, _, buf = prim.rpartition('_')
    if kind:  # differential
        fields['IO_TYPE'] = st.sampled_from(sorted(DIFF_STANDARDS[kind]))
        attrs['PULL_MODE'] = ['UP', 'DOWN', 'NONE']
        if buf in ('IBUF', 'IOBUF'):
            attrs['DIFF_RESISTOR'] = ['ON', 'OFF']
    else:
        attrs.update(IO_TYPE=sorted(IO_STANDARDS), BANK_VCCIO=BANK_VCCIOS)
        if buf in ('IBUF', 'IOBUF'):
            attrs.update(IO_INPUT_ATTRS)
        if buf in ('OBUF', 'TBUF', 'IOBUF'):
            attrs.update(IO_OUTPUT_ATTRS)
    fields.update({k: st.one_of(st.none(), st.sampled_from(v)) for k, v in attrs.items()})
    return st.fixed_dictionaries(fields).map(
        lambda d: Case(prim, tuple(sorted((k, v) for k, v in d.items() if v is not None))))


def io_bank_case():
    """IO_BANK: two or three single-ended buffers in one bank, each with its own
    type and attributes, as params IO<n> (the buffer) and IO<n>_<attribute>."""
    def flatten(bufs):
        return Case('IO_BANK', tuple(sorted(
            (k, v) for n, b in enumerate(bufs)
            for k, v in [(f'IO{n}', b.prim), *((f'IO{n}_{a}', x) for a, x in b.params)])))
    buf = st.sampled_from(['IBUF', 'OBUF', 'TBUF', 'IOBUF']).flatmap(io_case)
    return st.lists(buf, min_size=2, max_size=3).map(flatten)


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
    - PA2096: CLKOUTn_PE_COARSE < ODIVn_SEL. The message says "less than or
      equal", but every case with equal values was rejected (7 cases);
    - PA2115: channel n disabled when CLKn_OUT_SEL=1'b1;
    - PA2093: DEn_EN and DYN_PEn_SEL must be FALSE when DYN_DPA_EN=FALSE, and
      CLKn_IN_SEL=1'b1 needs CLKn_OUT_SEL=1'b1 under some dynamic settings
      (avoided by not combining them)."""
    p = dict(p)
    for n in range(7):
        pe, od = f'CLKOUT{n}_PE_COARSE', f'ODIV{n}_SEL'
        if pe in p and od in p and int(p[pe]) >= int(p[od]):
            p[pe] = str(int(p[od]) - 1)
        if p.get('DYN_DPA_EN') != '"TRUE"':
            for k in (f'DE{n}_EN', f'DYN_PE{n}_SEL'):
                if k in p:
                    p[k] = '"FALSE"'
        if p.get(f'CLK{n}_OUT_SEL') == "1'b1":
            p[f'CLKOUT{n}_EN'] = '"FALSE"'
        elif p.get(f'CLK{n}_IN_SEL', "1'b0") not in ("1'b0", "2'b00"):
            p[f'CLK{n}_IN_SEL'] = "2'b00" if n == 4 else "1'b0"
    return p


def gw5a_dsp_clock_fixup(p):
    """PA2113 on GW5A-25A: a register clock may not be BYPASS when a feature
    needs the register. MULTALU27X18: AREG_CLK with SOA_PREG_EN, OREG_CLK with
    FB_PREG_EN; MULTADDALU12X12: OREG_CLK with DYN_ACC_SEL (dynamic
    accumulation). Applied to every GW5A DSP that has these parameters."""
    p = dict(p)
    for feature, clock in (('SOA_PREG_EN', 'AREG_CLK'), ('FB_PREG_EN', 'OREG_CLK'), ('DYN_ACC_SEL', 'OREG_CLK')):
        if p.get(feature) == '"TRUE"' and p.get(clock) == '"BYPASS"':
            p[clock] = '"CLK0"'
    return p


def accload_fixup(p):
    """PA2079 on GW1N-9C MULTALU36X18: "Level of ACCLOAD-path ... should not be
    more than data-path(INPUT_REG + PIPE_REG)'s via register". Rejected with
    ACCLOAD_REG0/1 = 1/1 and AREG/BREG/PIPE_REG = 0/1/0. Which input register
    counts is inferred: the larger of the A and B registers, plus the pipeline
    registers. ACCLOAD stages are dropped until they fit."""
    p = gw5a_dsp_clock_fixup(p)
    if 'ACCLOAD_REG0' not in p:
        return p
    p = dict(p)
    on = lambda k: p.get(k, "1'b0").endswith('1')
    data = max([on(k) for k in p if re.fullmatch(r'[AB]\d?REG', k)] or [0]) + \
        max([on(k) for k in p if re.fullmatch(r'PIPE\d?_REG', k)] or [0])
    for k in ('ACCLOAD_REG1', 'ACCLOAD_REG0'):
        if on('ACCLOAD_REG0') + on('ACCLOAD_REG1') > data and on(k):
            p[k] = "1'b0"
    return p


# Rules across parameters, or values the XML allows but the vendor rejects.
# Found by running the vendor (doc/agent/primitive-params.md); each is (primitive regex, predicate on the
# case's {name: literal}, vendor message it avoids).
RULES = [
    (r'DP', lambda p: "2'b10" not in (p.get('WRITE_MODE0'), p.get('WRITE_MODE1')),
     "PA2122: dual-port BSRAM does not support WRITE_MODE 2'b10"),
]

# Not in the device: "PA2085: No '<primitive>' resource in current device",
# found by running every primitive through the vendor
UNAVAILABLE = {
    'GW1N-9C': set('''TLVDS_IOBUF BANDGAP CLKDIVG DCCG DQS ELVDS_IBUF_R ELVDS_IOBUF_R EMCU FLASH128K
        FLASH256K FLASH64K FLASH64KZ FLASH96K FLASH96KA I3C IBUF_R IDDR_MEM IDES4_MEM IDES8_MEM IEM
        IOBUF_R IODELAYB MCU MIPI_DPHY_RX ODDR_MEM OSCH OSCO OSCW OSCZ OSER4_MEM OSER8_MEM OTP PLLO
        PLLVR PWRGRD SAMB SPMI SPMI_DEBUG_GOWIN TLVDS_OEN_BK USB20_PHY'''.split()),
    'GW2A-18C': set('''IDES16 OSER16 BANDGAP CLKDIVG DCC DCCG DHCENC EMCU FLASH128K FLASH256K
        FLASH608K FLASH64K FLASH64KZ FLASH96K FLASH96KA I3C I3C_IOBUF IODELAYB IODELAYC MCU
        MIPI_DPHY_RX MIPI_IBUF MIPI_IBUF_HS MIPI_IBUF_LP MIPI_OBUF MIPI_OBUF_A OSCH OSCO OSCW OSCZ OTP
        PLLO PLLVR PWRGRD SAMB SPMI SPMI_DEBUG_GOWIN TLVDS_OEN_BK USB20_PHY'''.split()),
    'GW5A-25A': set('''DFF DFFC DFFE DFFN DFFNC DFFNCE DFFNE DFFNP DFFNPE DFFNR DFFNRE DFFNS DFFNSE
        DFFP DFFR DFFS OSC ADCA_DB ADCLRC ADCLRC_DB ADCULC ADCULC_DB ADC_SAR ADC_SAR_DB AE350_RAM
        AE350_SOC CMSER CMSERB DL DLC DLCEA DLE DLN DLNC DLNCE DLNE DLNP DLNPE DLP DLPEA JPEG_DB LICD
        MULTACC OSCB PLL RAM16S1 RAM16S2 RAM16S4 RAM16SDP1 RAM16SDP2 RAM16SDP4 SAMBA SDP136K
        SDP36KE'''.split()),
}

# Constants and placeholders, not primitives to test. VIRTUAL_BUF is in the XML
# but not defined (PA2050).
NOT_PRIMITIVES = {'GND', 'VCC', 'VIRTUAL_BUF'}


def site_kind(prim):
    """Site kind of a primitive; everything without one of its own is 'lone':
    one per design, placed by both tools."""
    return SITES.get(prim, 'lone')


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
        return site_kind(self.prim)

    def to_json(self):
        return {'prim': self.prim, 'params': dict(self.params)}

    @staticmethod
    def from_json(d):
        return Case(d['prim'], tuple(sorted(d['params'].items())))


def default_literal(param):
    """Verilog literal of a parameter's primitive.xml default."""
    return f'"{param["default"]}"' if param['type'] == 'string' else param['default']


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
        values = st.integers(0, (hi - lo) // step).map(lambda i: lo + i * step)
        if param.get('extra'):
            values = st.one_of(values, st.sampled_from(param['extra']))
        return values
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
        self.device, self.vendor_device = device, vendor_device
        # IOB_* params: the flip-flop's TYPE (cell name) and INIT
        types = [t for t in DFFS if t in self.spec and t not in UNAVAILABLE.get(device, ())]
        params = {'TYPE': {'type': 'cell', 'kind': 'enum', 'values': types, 'default': types[0]},
                  'INIT': self.spec[types[0]]['params']['INIT']}
        self.spec.update({prim: {'ports': {}, 'params': params} for prim in IOB_REGS})
        self.spec['IO_BANK'] = {'ports': {}, 'params': {}}

    def fixed(self, name, param):
        """Literal for a parameter whose value depends on the device, else None.
        DEVICE parameters list the devices a primitive exists on; use this one."""
        if name == 'DEVICE' and param['kind'] == 'enum' and self.vendor_device in param['values']:
            return literal(param, self.vendor_device)
        if KEEP_DEFAULT.match(name):
            return default_literal(param)
        return None

    def defaults(self, prim):
        """Literals of a primitive's primitive.xml defaults, by parameter name."""
        return {name: default_literal(param) for name, param in self.spec[prim]['params'].items()}

    def case(self, prim):
        kind = site_kind(prim)
        if kind in ('iob', 'diob'):
            return io_case(prim)
        if kind == 'iobank':
            return io_bank_case()
        if kind == 'widelut':
            # leaf INITs, distinct and not constant, so each leaf can be found
            # in a bitstream; leaf j is reached with select bits j (I0 = 0)
            n = 1 << (int(prim[-1]) - 4)
            return st.lists(st.integers(1, 0xfffe), min_size=n, max_size=n, unique=True).map(
                lambda inits: Case(prim, tuple((f'INIT{j}', f"16'h{v:04x}") for j, v in enumerate(inits))))
        # Each parameter is set or omitted, as designs do, so gowin_pack's
        # defaults are tested too. Kept: the fixed parameters, and a LUT's
        # INIT, without which the tools fold the LUT away.
        required, optional, defaults = {}, {}, self.defaults(prim)
        for name, param in self.spec[prim]['params'].items():
            fixed = self.fixed(name, param)
            if fixed is not None:
                required[name] = st.just(fixed)
            elif kind == 'lut' and name == 'INIT':
                required[name] = param_strategy(param).map(lambda v, p=param: literal(p, v))
            else:
                optional[name] = param_strategy(param).map(lambda v, p=param: literal(p, v))
        # parameters drawn together to satisfy frequency rules, and fixups for
        # rules between parameters
        extra, fixup = st.just({}), (lambda d: d)
        if kind == 'dsp':
            fixup = accload_fixup
        elif prim in ('rPLL', 'PLL'):
            extra = pll_dividers(self.spec[prim]['params'], self.device)
        elif prim == 'PLLA':
            extra, fixup = plla_dividers(), plla_fixup
        rules = [ok for pat, ok, _ in RULES if re.match(pat, prim)]

        # the fixup and rules see omitted parameters at their default; a
        # parameter the fixup moves off its default is set
        def case(drawn):
            full = fixup({**defaults, **drawn})
            return full, Case(prim, tuple(sorted((k, v) for k, v in full.items() if k in drawn or v != defaults[k])))
        return (st.tuples(st.fixed_dictionaries(required, optional=optional), extra)
                .map(lambda t: case({**t[0], **t[1]}))
                .filter(lambda t: all(ok(t[0]) for ok in rules))
                .map(lambda t: t[1]))


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
