"""Round trip, one test per device and design group: random designs through
Yosys, nextpnr, gowin_pack and gowin_unpack, the unpacked netlist proven equal
to the synthesised one (tools/roundtrip.py). No IDE, no board.

    pytest tests/test_roundtrip.py --device GW1N-9C [--roundtrip-jobs 4] -rxX

Without --device, nothing runs. A group whose failures all have a known cause
in KNOWN is logged as xfail with the issue; anything else fails, as does a
check that misses the mutation control (a LUT inverted in a design that
proved). The design and its blind spots are in doc/agent/roundtrip.md.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'tools'))
import roundtrip  # noqa: E402

# GW5A-25A: unpack gaps #585 does not cover (doc/agent/roundtrip.md)
DEVICES = ('GW1N-9C', 'GW2A-18C')

# kind of failure (roundtrip.classify) -> its issue
KNOWN = {
    'unpack-gap': '#585: gowin_unpack leaves nets undriven (clock aliases, long wires, empty tiles, '
                  'alone-node fuses)',
    'alu-i2': "#288: gowin_unpack gives ALU an I2 port, which Yosys' ALU does not have",
    'lost-iob-reg': '#668: a register nextpnr packs into I/O logic (ireg/oreg/ioreg_in_iob) is not in '
                    'the bitstream',
}


def pytest_generate_tests(metafunc):
    if 'group' in metafunc.fixturenames:
        params = [(d, g) for d in metafunc.config.getoption('device') for g in roundtrip.GROUPS]
        metafunc.parametrize('device,group', params, ids=[f'{d}-{g}' for d, g in params])


def test_roundtrip(request, device, group):
    if device not in DEVICES:
        pytest.skip(f'the round trip runs on {", ".join(DEVICES)}')
    opt = request.config.getoption
    results, control = roundtrip.roundtrip(device, group, opt('roundtrip_out'), opt('roundtrip_count'),
                                           opt('roundtrip_seed'), opt('roundtrip_jobs'))
    failed = [(w, r) for w, r in results if r['status'] != 'proved']
    details = '\n'.join(roundtrip.describe(w, r) for w, r in failed)
    if control:
        assert None in roundtrip.kinds(control[1]), \
            f'{control[0]}: with {control[1]["mutated"]} inverted, the check gave ' \
            f'{control[1]["status"]}, not an unexplained failure:\n{roundtrip.describe(*control)}'
    else:
        assert failed, 'no design to run the mutation control on'
    kinds = set().union(*(roundtrip.kinds(r) for _, r in failed))
    assert kinds <= KNOWN.keys(), f'{len(failed)} of {len(results)} designs failed:\n{details}'
    if failed:
        pytest.xfail('; '.join(KNOWN[k] for k in sorted(kinds))
                     + f' ({len(failed)} of {len(results)} designs)\n{details}')
