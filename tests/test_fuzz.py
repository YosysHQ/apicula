"""Compare Apicula with the vendor on random primitive configurations
(tools/tiled_fuzzer.py), one test per device and primitive.

    GOWINHOME=... pytest tests/test_fuzz.py --device GW1N-9C [--fuzz-jobs 4] -rxX

Without --device, nothing runs. One fuzzer run per device makes all its
designs; the tests read its results. Failures are logged with the differing
fuses; the full reports are in --fuzz-out. Known bugs are in KNOWN, with the
evidence in doc/agent/tiled-fuzzer.md. Cases the vendor rejects for the
harness or the netlist (invalid) are a generator limit, not a failure;
settings it rejects as illegal must make the Apicula flow fail too.
"""
import functools
import os
import re
import sys
import warnings

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'tools'))
import primitive_strategies as ps  # noqa: E402
import tiled_fuzzer  # noqa: E402


def any_params(p):
    """The trigger is not narrowed down yet: every case of the primitive."""
    return True


ALL = '.*'

# Known bugs, each the region of inputs that triggers it, in the shape of
# primitive_strategies.RULES: (primitive regex, device regex, predicate, reason).
# The primitive regex must match the whole name, the device regex its start.
# The predicate sees the case's parameters as Verilog literals, omitted ones at
# their primitive.xml default. A failing case no entry matches fails the test,
# even if its primitive has other known bugs; a passing case an entry matches
# is reported as a warning, so stale entries show up.
KNOWN = [
    # Apicula
    ('IBUF|OBUF|TBUF|IOBUF|IO_BANK', ALL, any_params,
     'I/O: DRIVE/OPENDRAIN, ODMUX and PULLMODE rows and unused-I/O bank fuses differ; SSTL/HSTL inputs decode '
     'as outputs; one IO_TYPE per bank, where the vendor allows any standard of one voltage; attribute values '
     'the vendor calls illegal for the IO_TYPE (CT1108) are packed'),
    ('OBUF|TBUF|IOBUF', ALL, lambda p: 'IO_TYPE' not in p,
     'default IO_TYPE (issue pending): without IO_TYPE gowin_pack makes an output LVCMOS12, the vendor LVCMOS18 '
     'on GW1N/GW2A and LVCMOS33 on GW5A'),
    ('IO_BANK', ALL, lambda p: len({v for k, v in p.items() if k.endswith('_IO_TYPE')}) > 1,
     'one IO_TYPE per bank: gowin_pack stops with "IO_TYPE conflict" on standards the vendor accepts together'),
    ('(TLVDS|ELVDS)_(IBUF|OBUF|TBUF|IOBUF)', ALL, any_params,
     'differential I/O: placement on true LVDS pins, ELVDS and bank rows; they decode as single-ended'),
    ('TLVDS_(OBUF|TBUF|IOBUF)', 'GW2A', any_params,
     '#534 (the freeze is reported with a TLVDS output): a TLVDS buffer sets IOB BANK_VCCIO on its bank, and '
     'the bank tile\'s LVDS25 rows differ from the vendor\'s; TLVDS_IBUF shows the same rows'),
    ('IDDR|IDDRC|ODDR|ODDRC', ALL, any_params,
     'I/O logic: IDDR/IDDRC and ODDR/ODDRC unpack as each other; ODDR OUTMODE; on GW5A-25A, FCLKSEL, IOB and '
     'HCLK TO_IHCLK rows'),
    ('IOB_IREG|IOB_OREG|IOB_IOREG', ALL, any_params,
     '#668: a flip-flop packed into I/O logic lacks the CLKIMUX/CLKOMUX, SRMODE, CE mux, OUTMODE=OREG and '
     'register mode rows, and sets LSR mux rows the vendor leaves off; on GW5A-25A also IREG_REGSET/OREG_REGSET '
     'and IOB PULLMODE, SLEWRATE and IOB_UNKNOWN67 rows'),
    ('IODELAY', ALL, any_params,
     'IODELAY unpacks to no cell; on GW5A-25A (placed since nextpnr#1923) it lacks the INDEL/IDEL rows and sets '
     'LSR mux rows the vendor leaves off'),
    ('IDES4|IDES8|IDES10|IDES16|OSER16|IVIDEO|OVIDEO', 'GW5A', any_params,
     'GW5A I/O logic: FCLKSEL, IOB and HCLK TO_IHCLK rows; IDES8 (INMODE reads as UNK76), IDES10 and IVIDEO '
     'unpack to no cell; nextpnr cannot place IDES16/OSER16 on the pins the harness chose'),
    ('OSER4|OSER8|OSER10', 'GW5A', any_params,
     'GW5A OSER: FCLKSEL, IOB PULLMODE/SLEWRATE and HCLK TO_IHCLK rows'),
    ('ALU', ALL, any_params,
     'constant CIN: Apicula adds a head ALU where the vendor folds it into the LUTs; ALU_MODE=5'),
    ('MULT9X9|MULT18X18|PADD9|PADD18', ALL, any_params,
     'DSP: input register muxes (AIRMUX/BIRMUX), RSTGEN muxes, pre-adder rows'),
    ('ALU54D', 'GW1N|GW2A', any_params,
     'DSP: input register muxes (AIRMUX/BIRMUX, IRMATCH), pre-adder rows (PRAD_MUXA1, PRAD_FBB1); not in the '
     'parameters: on GW2A-18C it shares a DSP block, and the same differing bits, with a MULT18X18'),
    ('MULTALU18X18', ALL, any_params,
     'DSP: input register muxes (AIRMUX/BIRMUX, IRMATCH), RSTGEN*MUX_REGC0 rows; gowin_pack stops with '
     'KeyError CLK_BSIGN12'),
    ('MULT9X9|PADD9|MULTALU18X18|MULTADDALU18X18', ALL, any_params,
     'DSP: the vendor and Apicula configure different pairs of the macro (vendor PRAD0 rows, Apicula PRAD1, '
     'AIRMUX/BIRMUX, IREG1B); the harness pins only the macro (DSP_R<row>[n][A])'),
    ('MULT12X12|MULT27X36|MULTADDALU12X12|MULTALU27X18', ALL, any_params,
     'GW5A DSP: MULT_RESET_MODE, CASO, CE muxes, PRELOAD_BIT, DYN_P_ADDSUB rows; omitted ACC_SEL and C_SEL '
     'pack no row'),
    ('SDPB|SDPX9B', 'GW5A', lambda p: p['BIT_WIDTH_1'] in ('32', '36') and p['BIT_WIDTH_0'] != p['BIT_WIDTH_1'],
     'GW5A BSRAM: with a 32/36-bit read port and a narrower write port, Apicula sets DBLWB=X36, the vendor does '
     'not'),
    ('SDPB|SDPX9B', 'GW5A-25A', lambda p: p['BIT_WIDTH_0'] in ('32', '36') and p['BIT_WIDTH_1'] != p['BIT_WIDTH_0'],
     'nextpnr rejects BIT_WIDTH_0 of 32/36 with a different BIT_WIDTH_1'),
    ('DPB|DPX9B', ALL,
     lambda p: p['BIT_WIDTH_0'] != p['BIT_WIDTH_1'] and {'16', '18'} & {p['BIT_WIDTH_0'], p['BIT_WIDTH_1']},
     'BSRAM: with mixed port widths Apicula enables the byte enables (BELB/BEHB) of the 16/18-bit port, the '
     'vendor does not'),
    ('rPLL', ALL, any_params, 'rPLL: FBSEL on GW2A; the unpacker does not invert several parameters'),
    ('PLLA', ALL, any_params, 'GW5A PLLA: phase/duty, charge pump, loop filter, KVCO, ODIV rows'),
    ('OSCA', ALL, any_params, 'GW5A OSCA: FREQ_DIV=3 rejected; unpacked as OSC'),
    ('TLVDS_IBUF_ADC', ALL, any_params, 'gowin_pack rejects the ADC bus of the pins the vendor chose'),
    ('I3C_IOBUF', ALL, any_params, 'I3C: DRIVE/OPENDRAIN rows; nextpnr: pin not I3C capable on GW5A'),
    ('MIPI_OBUF', ALL, any_params, 'MIPI: Apicula sets an IOB row where the vendor sets a bank row'),
    # nextpnr
    ('ROM16', ALL, any_params, 'nextpnr: ROM16 becomes a LUT'),
    ('SDP|DP|ROM|DPX9|SDPX9|ROMX9', ALL, any_params, 'nextpnr: unsupported BSRAM type, or bel type mismatch'),
    ('PLL|BUFS|RAM16S1|RAM16S2|RAM16S4|LUT5|LUT6|LUT7|LUT8|MUX2|IDES14|IDES32|OSER14|DDRDLL|DHCE|DCE|OTP|SAMB|'
     'CMSERA|IBUF_R|IOBUF_R|ELVDS_IBUF_R|ELVDS_IOBUF_R|ELVDS_IBUF_MIPI|MIPI_IBUF_HS|MIPI_IBUF_LP', ALL, any_params,
     'nextpnr has no cell or bel for it'),
    ('MIPI_IBUF|MIPI_OBUF_A|MIPI_CPHY_IBUF|MIPI_CPHY_OBUF', ALL, any_params,
     'nextpnr rejects the pins the vendor chose'),
    ('DCS', 'GW5A', any_params, 'GW5A: nextpnr crashes routing DCS inputs from pins'),
    ('DQS|DLLDLY', ALL, any_params, 'needs a DLL, which Yosys lacks (GW1N/GW2A) or nextpnr cannot place (GW5A)'),
    ('INV', ALL, any_params, 'nextpnr makes a LUT of it; the vendor removes it'),
    ('FLASH608K', ALL, any_params, 'nextpnr adds LUTs and flip-flops around user flash'),
    # Yosys' cell library
    ('rROM|rROMX9|rSDP|rSDPX9|IODELAYA|IODELAYC|DLL|DCC|ADC_DB|MUX4|MUX8|MUX16|MUX32', ALL, any_params,
     'no Yosys cell definition'),
]

# fuse differences in tiles no case owns, and designs that fail although each
# of their cases passes alone
BROKEN_UNATTRIBUTED = ('I/O bank and GW5A I/O row fuses of unused pins; HCLK BRGMUX*_BRGOUT rows '
                       '(GW1N-9C, GW2A-18C, GW2A-18; inferred: from the harness clock)')
BROKEN_COMBINATIONS = ('nextpnr: two DSP cases in one block (more than 4 RESET networks, or two nets on one '
                       'source wire); an I/O logic pin already taken by another case\'s buffer')

# Cases the generator does not reach, from bug reports: (device, primitive,
# params, pads, issue, status). pads are pin names or numbers, None for the
# first site of the primitive's kind. Each runs in a design of its own; the
# vendor decides what is right. status is the one the case gets: ok or
# rejected (both flows reject it) for a case that must pass, else the failing
# status the issue explains, which xfails. Any other status fails; a known
# failure that passes is reported as a warning, so stale entries show up.
PLL_ODIV3 = {'FCLKIN': '"27"', 'IDIV_SEL': '0', 'FBDIV_SEL': '9', 'ODIV_SEL': '3'}
PINNED = [
    # ODIV_SEL is 2, 4, 8, ... 128 in primitive.xml; the vendor rejects 3 (PA1002)
    ('GW1N-9C', 'rPLL', PLL_ODIV3, None, '#409', 'accepted'),
    ('GW2A-18C', 'rPLL', PLL_ODIV3, None, '#409', 'accepted'),
    # pin 80 is in bank 3, wired to the in-package PSRAM (SiP-locked)
    ('GW1N-9C', 'IBUF', {'IO_TYPE': 'LVCMOS33'}, ['80'], '#622', 'mismatch'),
    ('GW1N-9C', 'OBUF', {'IO_TYPE': 'LVCMOS33'}, ['80'], '#622', 'accepted'),
    # pin 15 of the report (Tang Nano 20K LED); the vendor rejects both (CT1108)
    ('GW2A-18C', 'OBUF', {'BANK_VCCIO': '3.3', 'PULL_MODE': 'UP', 'DRIVE': '8'}, ['IOL47A'], '#433', 'rejected'),
    ('GW2A-18C', 'OBUF', {'IO_TYPE': 'LVCMOS33', 'BANK_VCCIO': '1.8', 'PULL_MODE': 'UP', 'DRIVE': '8'},
     ['IOL47A'], '#433', 'rejected'),
]


@functools.cache
def primitives(device):
    return ps.Primitives(device, tiled_fuzzer.DEVICES[device][0])


def known(device, case):
    """Reasons of the KNOWN entries whose region holds `case`."""
    params = {**primitives(device).defaults(case['prim']), **case['params']}
    return [why for prim, dev, region, why in KNOWN
            if re.fullmatch(prim, case['prim']) and re.match(dev, device) and region(params)]


def pytest_generate_tests(metafunc):
    devices = metafunc.config.getoption('device')
    if 'prim' in metafunc.fixturenames:
        params = [(d, p) for d in devices for p in tiled_fuzzer.primitives(d)]
        metafunc.parametrize('device,prim', params, ids=[f'{d}-{p}' for d, p in params])
    elif 'pinned' in metafunc.fixturenames:
        params = [i for i, entry in enumerate(PINNED) if entry[0] in devices]
        metafunc.parametrize('pinned', params, ids=[f'{PINNED[i][0]}-{PINNED[i][4]}-{PINNED[i][1]}' for i in params])
    elif 'device' in metafunc.fixturenames:
        metafunc.parametrize('device', devices)


_runs = {}


@pytest.fixture
def run(request, device):
    """The fuzzer run of `device`, made once."""
    if device not in _runs:
        opt = request.config.getoption
        _runs[device] = tiled_fuzzer.fuzz(device, os.path.join(opt('fuzz_out'), device), opt('fuzz_count'),
                                          opt('fuzz_seed'), opt('fuzz_jobs'), log=lambda line: None)
    return _runs[device]


def test_primitive(run, device, prim):
    results = [r for r in run.cases if r['case']['prim'] == prim]
    if results and all(r['status'] == 'invalid' for r in results):
        pytest.skip('the vendor rejected every case: ' + '; '.join(results[0].get('why', []))[:200])
    for r in results:
        if r['status'] == 'ok' and (reasons := known(device, r['case'])):
            warnings.warn(f'{device} {prim} {r["case"]["params"]} passes; KNOWN: {reasons}')
    failures = run.failures(prim)
    unknown = [r for r in failures if not known(device, r['case'])]
    details = '\n'.join(tiled_fuzzer.describe_result(r) for r in unknown or failures)
    assert not unknown, f'{len(unknown)} of {len(results)} cases failed outside KNOWN:\n{details}'
    if failures:
        reasons = dict.fromkeys(why for r in failures for why in known(device, r['case']))
        pytest.xfail('\n'.join(reasons) + f'\n{details}')


def test_unattributed(run, device):
    details = '\n'.join(f'{design} {tile}: {bits[:3]}' for (design, tile), bits in run.unattributed.items())
    if run.unattributed:
        pytest.xfail(f'{BROKEN_UNATTRIBUTED}: {len(run.unattributed)} tiles\n{details}')


def test_combinations(run, device):
    failing = [c for c in run.combinations if c['alone_ok']]
    details = '\n'.join(f'{c["design"]}: {[x["prim"] for x in c["cases"]]}: {c["why"][:2]}' for c in failing)
    if failing:
        pytest.xfail(f'{BROKEN_COMBINATIONS}\n{details}')


_pinned_runs = {}


@functools.cache
def pinned_cases(device):
    """{index in PINNED: (case, site)} of the device's entries."""
    return {i: tiled_fuzzer.pinned_case(*entry[:4]) for i, entry in enumerate(PINNED) if entry[0] == device}


PASSING = ('ok', 'rejected')


def test_pinned(request, pinned):
    device, *_, issue, expected = PINNED[pinned]
    if device not in _pinned_runs:
        opt = request.config.getoption
        _pinned_runs[device] = tiled_fuzzer.fuzz(device, os.path.join(opt('fuzz_out'), f'{device}-pinned'),
                                                 jobs=opt('fuzz_jobs'), replay=list(pinned_cases(device).values()),
                                                 log=lambda line: None)
    case = pinned_cases(device)[pinned][0].to_json()
    r = next(r for r in _pinned_runs[device].cases if r['case'] == case)
    status, details = r['status'], tiled_fuzzer.describe_result(r)
    if status in PASSING and expected not in PASSING:
        warnings.warn(f'{device} {issue} pinned {r["case"]["prim"]} is {status}, PINNED expects {expected}')
        return
    assert status == expected, f'{issue}: {status}, PINNED expects {expected}\n{details}'
    if status not in PASSING:
        pytest.xfail(f'{issue}: {status}\n{details}')
