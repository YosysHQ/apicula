import unittest

from apycula import gowin_pack


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


if __name__ == '__main__':
    unittest.main()
