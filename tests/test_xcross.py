import os
import unittest
from pathlib import Path

from apycula import chipdb, dat_parser

ROOT = Path(__file__).resolve().parent.parent


class GW5AXwireCrossingTests(unittest.TestCase):
    # Columns where NETLIST::chip::buildXwireNodeCrossDelayValueFlag (IDE
    # 1.9.10.03) flags crossing X wires on GW5A-25A, in Apicula coordinates.

    def test_gw5a_25a_columns(self):
        path = ROOT / 'apycula' / 'GW5A-25A.msgpack.xz'
        if not path.exists():
            self.skipTest(f'{path.name} not built')
        db = chipdb.load_chipdb(str(path))
        for groups in db.timing.values():
            cols = {k: v for k, v in groups['xcross'].items() if k.startswith('C')}
            self.assertEqual(cols, {
                'C9': 7, 'C18': 9, 'C27': 7, 'C36': 9, 'C45': 6,
                'C54': 9, 'C63': 7, 'C72': 9, 'C81': 7,
            })

    def test_gw5a_25a_spine_column_table(self):
        # read by hand at file offset 0xa6a1a of GW5A-25A.dat
        gowinhome = os.environ.get('GOWINHOME')
        if not gowinhome:
            self.skipTest('GOWINHOME not set')
        dat = dat_parser.Datfile(Path(gowinhome) / 'IDE/share/device/GW5A-25A/GW5A-25A.dat')
        self.assertEqual(dat.gw5aStuff['SpineColumn'], [19, 37, 55, 73, -1, -1, -1, -1])


if __name__ == '__main__':
    unittest.main()
