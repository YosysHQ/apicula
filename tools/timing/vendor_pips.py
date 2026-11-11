"""Decode used PIPs from a vendor bitstream: vendor_pips.py DEVICE BITSTREAM OUT.json"""
import importlib.resources, json, sys
from apycula import chipdb, gowin_unpack
from apycula.chipdb import load_chipdb
from apycula.gowin_unpack import read_bitstream, parse_tile_
dev, fs, out = sys.argv[1:4]
gowin_unpack._device = dev
with importlib.resources.path('apycula', f'{dev}.msgpack.xz') as p:
    db = load_chipdb(p)
bitmap, _, _, _ = read_bitstream(fs)
bm = chipdb.tile_bitmap(db, bitmap)
pips, clock, dflt = [], [], []
for (row, col), t in bm.items():
    try:
        bels, tp, cp = parse_tile_(db, row, col, t, bm, default=False, noiostd=False)
        _, tpd, _ = parse_tile_(db, row, col, t, bm, default=True, noiostd=False)
        dflt += [f"X{col}Y{row}/{d}/{s}" for d, s in tpd.items() if tp.get(d) != s]
    except Exception as e:
        print('tile', row, col, 'failed:', e); continue
    pips += [f'X{col}Y{row}/{d}/{s}' for d, s in tp.items()]
    clock += [f'X{col}Y{row}/{d}/{s}' for d, s in cp.items()]
json.dump({"pips": pips, "clock_pips": clock, "default_pips": dflt}, open(out, 'w'))
print(len(pips), 'pips', len(clock), 'clock pips')
