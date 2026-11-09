#!/usr/bin/env python3
"""Compare two directories of chipdb files by content.

    PYTHONPATH=. python3 tools/chipdb_compare.py OLD_DIR NEW_DIR

Rebuilt files never match byte for byte, because sets are serialized in an order
that changes between runs, so the databases are loaded through the Device schema
and compared field by field. Exits with status 1 if any database differs.
"""
import dataclasses
import glob
import os
import sys

from apycula import chipdb


def diff(old, new, path, out):
    if type(old) is not type(new):
        out.append((path, 'type', type(old).__name__, type(new).__name__))
    elif dataclasses.is_dataclass(old):
        for field in dataclasses.fields(old):
            a, b = getattr(old, field.name), getattr(new, field.name)
            if a != b:
                diff(a, b, f'{path}.{field.name}', out)
    elif isinstance(old, dict):
        for key in old.keys() | new.keys():
            sub = f'{path}/{str(key)[:30]}'
            if key not in old or key not in new:
                side = new if key in new else old
                size = len(side[key]) if hasattr(side[key], '__len__') else ''
                out.append((sub, 'only in ' + ('new' if key in new else 'old'), size))
            elif old[key] != new[key]:
                diff(old[key], new[key], sub, out)
    elif isinstance(old, (list, tuple)) and len(old) == len(new):
        for i, (a, b) in enumerate(zip(old, new)):
            if a != b:
                diff(a, b, f'{path}[{i}]', out)
    elif isinstance(old, (list, tuple)):
        out.append((path, 'length', len(old), len(new)))
    else:
        out.append((path, str(old)[:40], str(new)[:40]))


def main(argv):
    if len(argv) != 3:
        print(__doc__)
        return 2
    status = 0
    for path in sorted(glob.glob(os.path.join(argv[2], '*.msgpack.xz'))):
        name = os.path.basename(path)
        out = []
        diff(chipdb.load_chipdb(os.path.join(argv[1], name)), chipdb.load_chipdb(path), '', out)
        print(name, 'identical' if not out else f'{len(out)} differences: {out[:8]}', flush=True)
        status |= bool(out)
    return status


if __name__ == '__main__':
    sys.exit(main(sys.argv))
