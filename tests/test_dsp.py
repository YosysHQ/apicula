import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from apycula import bslib, chipdb, gowin_pack


def match_attrs(prim, mac, idx):
    """MATCH attributes Apicula sets for a lone pre-adder at DSP slot mac/idx."""
    dev = object.__new__(gowin_pack.GW2A)
    dev.common_dsp_handler = lambda bel, attr_vals: attr_vals
    cell = gowin_pack.CellDesc(name='p', typ=prim, parms={}, attrs={}, connections={})
    bel = gowin_pack.BelDesc(0, 0, f'{mac}{idx}', cell)
    attr_vals = getattr(dev, f'get_{prim}_fuses')(bel)
    return {av.attr for av in attr_vals if av.attr.startswith('MATCH')}


class PaddMatchTests(unittest.TestCase):
    # IDE 1.9.10.03 bitstreams on GW2A-18C, each pre-adder pinned with INS_LOC
    # R19C20[macro][slot]: only slot B of a macro (PADD9 C/D, PADD18 B) sets
    # MATCH and MATCH_SHFEN, as setPaddMuxSD @0x1fad9e3 does.
    def test_padd9(self):
        for mac in (0, 1):
            for idx, slot in enumerate('ABCD'):
                want = {'MATCH', 'MATCH_SHFEN'} if slot in 'CD' else set()
                with self.subTest(mac=mac, slot=slot):
                    self.assertEqual(match_attrs('PADD9', mac, idx), want)

    def test_padd18(self):
        for mac in (0, 1):
            for idx, slot in enumerate('AB'):
                want = {'MATCH', 'MATCH_SHFEN'} if slot == 'B' else set()
                with self.subTest(mac=mac, slot=slot):
                    self.assertEqual(match_attrs('PADD18', mac, idx), want)

ROOT = Path(__file__).resolve().parent.parent
CHIPDB = ROOT / 'apycula' / 'GW5A-25A.msgpack.xz'


def pack_one_cell(typ, bel, params):
    """ Pack a netlist holding a single placed cell with gowin_pack and return
    the tiles of the bitstream. """
    netlist = {'modules': {'top': {
        'settings': {'packer.chipdb': 'GW5A-25A'},
        'netnames': {
            '$PACKER_GND': {'bits': [2], 'attributes': {'ROUTING': ''}},
            '$PACKER_VCC': {'bits': [3], 'attributes': {'ROUTING': ''}},
        },
        'cells': {'dut': {
            'type': typ,
            'parameters': params,
            'attributes': {'NEXTPNR_BEL': bel},
            'connections': {},
        }},
    }}}
    with tempfile.TemporaryDirectory() as tmp:
        with open(os.path.join(tmp, 'pnr.json'), 'w') as f:
            json.dump(netlist, f)
        subprocess.run([sys.executable, '-m', 'apycula.gowin_pack', '-d', 'GW5A-25A', '-o', 'top.fs', 'pnr.json'],
                       cwd=tmp, check=True, capture_output=True, env={**os.environ, 'PYTHONPATH': str(ROOT)})
        bm, _, _, _ = bslib.read_bitstream(os.path.join(tmp, 'top.fs'))
    return chipdb.tile_bitmap(chipdb.load_chipdb(str(CHIPDB)), bm, empty=True)


class GW5ADynamicCasiSelTests(unittest.TestCase):
    """ A fabric-driven CASISEL is not inverted (#665).

    The IDE sets CASISEL_PAD=INV only for an inverter absorbed into the
    CASISEL pin (fusegenMem::setAlu48Attr @0x309cf58, IDE 1.9.10.03). In its
    bitstreams for a plain DYN_CASI_SEL="TRUE" (GW5A-25A, the DSP's CASI fed
    by another DSP's CASO, CASISEL from a fabric net) the third tile of the
    DSP has (12,28) set, for DYN_CASI_SEL, and (12,37) clear, which is the
    inversion. """

    def setUp(self):
        if not CHIPDB.exists():
            self.skipTest(f'{CHIPDB.name} not built')

    def check(self, typ, col):
        tiles = pack_one_cell(typ, f'X{col}Y18/{typ}00', {'DYN_CASI_SEL': 'TRUE'})
        tile = tiles[(18, col + 2)]
        self.assertEqual((tile[12][28], tile[12][37]), (1, 0))

    def test_multaddalu12x12(self):
        self.check('MULTADDALU12X12', 16)

    def test_multalu27x18(self):
        self.check('MULTALU27X18', 28)


if __name__ == '__main__':
    unittest.main()
