import os
import unittest
from pathlib import Path

from apycula import chipdb, dat_parser

ROOT = Path(__file__).resolve().parent.parent


class GW5AXwireCrossingTests(unittest.TestCase):
    # Spine columns, flagged by NETLIST::chip::buildXwireNodeCrossDelayValueFlag
    # (IDE 1.9.10.03) on GW5A-25A.

    def test_gw5a_25a_spine_columns(self):
        # spine columns 19, 37, 55, 73 read by hand from GW5A-25A.dat (vendor
        # coordinates, Apicula = vendor - 1); flag 9 = X*_HOS_SPINE
        path = ROOT / 'apycula' / 'GW5A-25A.msgpack.xz'
        if not path.exists():
            self.skipTest(f'{path.name} not built')
        db = chipdb.load_chipdb(str(path))
        for groups in db.timing.values():
            for col in ('C18', 'C36', 'C54', 'C72'):
                self.assertEqual(groups['xcross'].get(col), 9, col)

    def test_gw5a_25a_spine_column_table(self):
        # read by hand at file offset 0xa6a1a of GW5A-25A.dat
        gowinhome = os.environ.get('GOWINHOME')
        if not gowinhome:
            self.skipTest('GOWINHOME not set')
        dat = dat_parser.Datfile(Path(gowinhome) / 'IDE/share/device/GW5A-25A/GW5A-25A.dat')
        self.assertEqual(dat.gw5aStuff['SpineColumn'], [19, 37, 55, 73, -1, -1, -1, -1])


if __name__ == '__main__':
    unittest.main()
