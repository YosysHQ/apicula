#!/usr/bin/env python3
"""Find HIL batches nextpnr can actually place. Run from apicula's examples/.

  hil-pack.py BOARD greedy TEST...        greedy first-fit packing (largest tests first)
  hil-pack.py BOARD try "t1 t2" "t3" ...   check candidate batches in parallel

Each candidate is built to nextpnr JSON through the Makefile's batch mechanism
(make hil-<name>-<board>.json HIL_BATCH_<name>="..."); exit status = placed or not.
Intermediates are removed. Capacity counts do not predict placement: measure.
"""
import itertools, os, subprocess, sys
from concurrent.futures import ThreadPoolExecutor

board, mode, args = sys.argv[1], sys.argv[2], sys.argv[3:]
env = dict(os.environ, PYTHONPATH='..')
ids = itertools.count()

def places(batch):
    name = f'pk{next(ids)}'
    target = f'hil-{name}-{board}.json'
    r = subprocess.run(['make', '-s', target, f'HIL_BATCH_{name}={" ".join(batch)}'],
                       env=env, capture_output=True, text=True)
    for f in (target, f'hil-{name}.v', f'hil-{name}-{board}-synth.json'):
        if os.path.exists(f):
            os.remove(f)
    return r.returncode == 0

if mode == 'try':
    cands = [a.split() for a in args]
    with ThreadPoolExecutor(8) as ex:
        for c, ok in zip(cands, ex.map(places, cands)):
            print('OK  ' if ok else 'FAIL', ' '.join(c), flush=True)
else:
    batches = []
    for t in args:
        with ThreadPoolExecutor(max(len(batches), 1)) as ex:
            fits = list(ex.map(lambda b: places(b + [t]), batches))
        target = next((b for b, ok in zip(batches, fits) if ok), None)
        if target is None:
            batches.append([t])
        else:
            target.append(t)
        print(t, '->', batches, flush=True)
    print('RESULT', board, batches)
