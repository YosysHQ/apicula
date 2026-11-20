import os
import unittest

import apycula
from apycula import chipdb

DSP_GROUPS = ('mult', 'mult36x36', 'mac', 'multadd', 'padd', 'alu54')


def timing(device):
    path = os.path.join(os.path.dirname(apycula.__file__), f'{device}.msgpack.xz')
    if not os.path.exists(path):
        raise unittest.SkipTest(f'{device} chipdb not built')
    return chipdb.load_chipdb(path).timing


class Gw5aDspTimingTests(unittest.TestCase):
    # The IDE times GW5A DSPs with the old-format record, unscaled; values from
    # its SDF for a combinational MULT12X12 A->DOUT on GW5A-25A (min:typ:max)
    def test_mult_from_old_record(self):
        tm = timing('GW5A-25A')
        # C1/I0 reads record 0: 2.210:2.920:3.630, without the new block's x1.25
        for got, want in zip(tm['C1/I0']['mult']['mdia_mout'], [2.21, 2.32, 3.457, 3.63]):
            self.assertAlmostEqual(got, want, places=3)
        # C2/I1 reads record 2: 1.905:2.517:3.129
        self.assertAlmostEqual(tm['C2/I1']['mult']['mdia_mout'][3], 3.129, places=3)

    def test_same_dsp_groups_on_all_gw5a(self):
        ref = timing('GW5A-25A')
        for device in ('GW5AT-60B', 'GW5AST-138C'):
            tm = timing(device)
            for speed in ref:
                for group in DSP_GROUPS:
                    with self.subTest(device=device, speed=speed, group=group):
                        self.assertEqual(tm[speed][group], ref[speed][group])


if __name__ == '__main__':
    unittest.main()
