import os
import unittest

import apycula
from apycula import chipdb

def timing(device):
    path = os.path.join(os.path.dirname(apycula.__file__), f'{device}.msgpack.xz')
    if not os.path.exists(path):
        raise unittest.SkipTest(f'{device} chipdb not built')
    return chipdb.load_chipdb(path).timing


def iopath(test, q, want, msg=None):
    # The SDF gives IOPATH (min(e0, e1), max(e2, e3)) as min:max
    test.assertAlmostEqual(min(q[0], q[1]), want[0], places=3, msg=msg)
    test.assertAlmostEqual(max(q[2], q[3]), want[1], places=3, msg=msg)


class Gw5aDspTimingTests(unittest.TestCase):
    # The IDE times GW5A DSPs with the old-format record, unscaled; values from
    # its SDF for a combinational MULT12X12 A->DOUT on GW5A-25A (min:typ:max)
    def test_mult_from_old_record(self):
        tm = timing('GW5A-25A')
        # C1/I0 reads record 0: 2.210:2.920:3.630, without the new block's x1.25
        iopath(self, tm['C1/I0']['mult']['mdia_mout'], (2.210, 3.630))
        # C2/I1 reads record 2: 1.905:2.517:3.129
        iopath(self, tm['C2/I1']['mult']['mdia_mout'], (1.905, 3.129))

    # One SDF-checked value per field the DSP rules use, GW5A-25A C1/I0. Setup
    # and hold are (e0, e2).
    def test_dsp_fields_from_sdf(self):
        tm = timing('GW5A-25A')['C1/I0']

        def path(name, want):
            grp, key = name.split('.')
            iopath(self, tm[grp][key], want, msg=name)

        def check(name, want):
            grp, key = name.split('.')
            q = tm[grp][key]
            self.assertAlmostEqual(q[0], want[0], places=3, msg=name)
            self.assertAlmostEqual(q[2], want[1], places=3, msg=name)

        # MULTALU27X18 A->DOUT 2.417/3.871 minus MULT12X12 A->DOUT 2.210/3.630
        path('alu54.md0_dout', (0.207, 0.241))
        path('mult36x36.mdia_mout', (3.429, 3.760))  # MULT27X36 A->DOUT
        path('mult.clk_mout_1', (0.205, 0.223))      # CLK->DOUT, all registers
        check('mult.clk_mdias_1', (0.223, 0.249))    # A setup, AREG
        # A hold -0.127/-0.108, before the -0.344 of addMuxDelayForDspHld
        check('mult.clk_mdiah_1', (0.217, 0.236))


class MultaddTimingTests(unittest.TestCase):
    # CLK->DOUT of a MULTALU18X18 or MULTADDALU18X18 with PIPE_REG set and
    # OUT_REG clear reads the third clk_mout quad; values from the IDE's SDF
    def test_clk_mout_pipe_reg_only(self):
        iopath(self, timing('GW2A-18C')['C8/I7']['multadd']['clk_mout_2'], (0.067, 0.082))
        iopath(self, timing('GW1N-9C')['C6/I5']['multadd']['clk_mout_2'], (0.084, 0.102))


if __name__ == '__main__':
    unittest.main()
