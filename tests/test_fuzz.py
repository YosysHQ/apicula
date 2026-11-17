"""Compare Apicula with the vendor on random primitive configurations
(tools/tiled_fuzzer.py), one test per device and primitive.

    GOWINHOME=... pytest tests/test_fuzz.py --device GW1N-9C [--fuzz-jobs 4] -rxX

Without --device, nothing runs. One fuzzer run per device makes all its
designs; the tests read its results. Failures are logged with the differing
fuses; the full reports are in --fuzz-out. Primitives in BROKEN are known
broken, with the evidence in doc/agent/tiled-fuzzer.md; cases the vendor
rejects are a generator limit, not a failure.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'tools'))
import tiled_fuzzer  # noqa: E402


def broken(prims, why):
    return dict.fromkeys(prims.split(), why)


BROKEN = {
    # Apicula
    **broken('IBUF OBUF TBUF IOBUF', 'I/O: DRIVE/OPENDRAIN, ODMUX and PULLMODE rows and unused-I/O bank '
             'fuses differ; SSTL/HSTL inputs decode as outputs'),
    **broken('TLVDS_IBUF TLVDS_OBUF TLVDS_TBUF TLVDS_IOBUF ELVDS_IBUF ELVDS_OBUF ELVDS_TBUF ELVDS_IOBUF',
             'differential I/O: placement on true LVDS pins, ELVDS and bank rows; they decode as single-ended'),
    **broken('IDDR IDDRC ODDR ODDRC IDES4 IDES8 IDES10 IDES16 OSER16 IVIDEO OVIDEO IODELAY',
             'I/O logic: GW5A FCLKSEL; ODDR OUTMODE; IDES16/OSER16: nextpnr\'s auxiliary cell has no GSREN/LSREN; '
             'on GW1N-9C the vendor moves the output pad off a VCCIO-locked bank (IDES4, IDES10); '
             'IVIDEO and IODELAY unpack to no cell, IDDR and IDDRC to each other'),
    **broken('OSER4 OSER8 OSER10', 'OSER: on GW5A-25A, FCLKSEL, LSROMUX_0, IOB PULLMODE/SLEWRATE and HCLK '
             'TO_IHCLK rows, and with OSER8 on an IOBB pad Apicula sets OUTMODE/CLKOMUX/WRFCLKSEL rows the vendor '
             'does not; on GW1N-9C the vendor moves the output pad off a VCCIO-locked bank, adding IOB '
             'ODMUX/TRI_MUX/SLEWRATE rows'),
    **broken('ALU', 'constant CIN: Apicula adds a head ALU where the vendor folds it into the LUTs; ALU_MODE=5'),
    **broken('ALU54D MULT9X9 MULT18X18 MULTALU18X18 PADD9 PADD18',
             'DSP: input register muxes (AIRMUX/BIRMUX), RSTGEN muxes, pre-adder rows'),
    **broken('MULT12X12 MULT27X36 MULTADDALU12X12 MULTALU27X18',
             'GW5A DSP: MULT_RESET_MODE, CASO, CE muxes, PRELOAD_BIT, DYN_P_ADDSUB rows'),
    **broken('SDPB SDPX9B', 'GW5A DBLWB=X36; GW5A-25A: nextpnr rejects BIT_WIDTH_0 of 32/36 with a different '
             'BIT_WIDTH_1'),
    **broken('rPLL', 'rPLL: FBSEL on GW2A; the unpacker does not invert several parameters'),
    **broken('PLLA', 'GW5A PLLA: phase/duty, charge pump, loop filter, KVCO, ODIV rows'),
    **broken('OSCA', 'GW5A OSCA: FREQ_DIV=3 rejected; unpacked as OSC'),
    **broken('ADC', 'GW5A ADC: Apicula sets 5A_PCLK_ENABLE'),
    **broken('TLVDS_IBUF_ADC', 'gowin_pack rejects the ADC bus of the pins the vendor chose'),
    **broken('I3C_IOBUF', 'I3C: DRIVE/OPENDRAIN rows; nextpnr: pin not I3C capable on GW5A'),
    **broken('MIPI_OBUF', 'MIPI: Apicula sets an IOB row where the vendor sets a bank row'),
    # nextpnr
    **broken('ROM16', 'nextpnr: ROM16 becomes a LUT'),
    **broken('SDP DP ROM pROM DPX9 SDPX9 ROMX9', 'nextpnr: unsupported BSRAM type, or bel type mismatch'),
    **broken('PLL BUFS RAM16S1 RAM16S2 RAM16S4 LUT5 LUT6 LUT7 LUT8 MUX2 IDES14 IDES32 OSER14 DDRDLL DHCE DCE '
             'OTP SAMB CMSERA IBUF_R IOBUF_R ELVDS_IBUF_R ELVDS_IOBUF_R ELVDS_IBUF_MIPI MIPI_IBUF_HS MIPI_IBUF_LP',
             'nextpnr has no cell or bel for it'),
    **broken('MIPI_IBUF MIPI_OBUF_A MIPI_CPHY_IBUF MIPI_CPHY_OBUF', 'nextpnr rejects the pins the vendor chose'),
    **broken('DCS', 'GW5A: nextpnr crashes routing DCS inputs from pins'),
    **broken('DQS DLLDLY', 'needs a DLL, which Yosys lacks (GW1N/GW2A) or nextpnr cannot place (GW5A)'),
    **broken('INV', 'nextpnr makes a LUT of it; the vendor removes it'),
    **broken('FLASH608K', 'nextpnr adds LUTs and flip-flops around user flash'),
    # Yosys' cell library
    **broken('rROM rROMX9 rSDP rSDPX9 IODELAYA IODELAYC DLL DCC ADC_DB MUX4 MUX8 MUX16 MUX32',
             'no Yosys cell definition'),
}

# fuse differences in tiles no case owns, and designs that fail although each
# of their cases passes alone
BROKEN_UNATTRIBUTED = ('I/O bank and GW5A I/O row fuses of unused pins; HCLK BRGMUX*_BRGOUT rows '
                       '(GW1N-9C, GW2A-18C, GW2A-18; inferred: from the harness clock)')
BROKEN_COMBINATIONS = ('nextpnr: two DSP cases in one block (more than 4 RESET networks, or two nets on one '
                       'source wire); an I/O logic pin already taken by another case\'s buffer')


def pytest_generate_tests(metafunc):
    devices = metafunc.config.getoption('device')
    if 'prim' in metafunc.fixturenames:
        params = [(d, p) for d in devices for p in tiled_fuzzer.primitives(d)]
        metafunc.parametrize('device,prim', params, ids=[f'{d}-{p}' for d, p in params])
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
    failures = run.failures(prim)
    details = '\n'.join(tiled_fuzzer.describe_result(r) for r in failures)
    if prim in BROKEN and failures:
        pytest.xfail(f'{BROKEN[prim]}\n{details}')
    assert not failures, f'{len(failures)} of {len(results)} cases failed:\n{details}'


def test_unattributed(run, device):
    details = '\n'.join(f'{design} {tile}: {bits[:3]}' for (design, tile), bits in run.unattributed.items())
    if run.unattributed:
        pytest.xfail(f'{BROKEN_UNATTRIBUTED}: {len(run.unattributed)} tiles\n{details}')


def test_combinations(run, device):
    failing = [c for c in run.combinations if c['alone_ok']]
    details = '\n'.join(f'{c["design"]}: {[x["prim"] for x in c["cases"]]}: {c["why"][:2]}' for c in failing)
    if failing:
        pytest.xfail(f'{BROKEN_COMBINATIONS}\n{details}')

