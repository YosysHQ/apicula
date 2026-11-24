"""Check every DSP IOPATH and SETUPHOLD in an IDE SDF of dsp_sdf.v against the
chipdb's DSP timing groups, using the rules in doc/agent/timing.md, "GW5A DSP".

    PYTHONPATH=. python3 tools/timing/dsp_sdf.py GW5A-25A C1/I0 impl/pnr/top.sdf

A quad gives IOPATH (min(e0, e1), max(e2, e3)), setup (e0, e2) and hold
(e0, e2) minus 0.344 (STA::addMuxDelayForDspHld, GW2A/GW5A). An input that
passes k stages to its register is charged k times, hold included.
"""
import os, re, sys
from apycula import chipdb

HOLD_ADJ = 0.344
dev, speed, sdf = sys.argv[1:4]
tm = chipdb.load_chipdb(os.path.join(os.path.dirname(chipdb.__file__), f'{dev}.msgpack.xz')).timing[speed]


def f(name):
    grp, key = name.split('.')
    return tm[grp][key]


def add(*names):
    return [sum(v) for v in zip(*(f(n) for n in names))]


def iopath(q, k=1):
    return (k * min(q[0], q[1]), k * max(q[2], q[3]))


def mult_reg(clk_k, sh_k, sel):
    arcs = {('IOPATH', 'CLK', 'DOUT'): iopath(f('mult.clk_mout_1'), clk_k)}
    for pin, s, h in (('A', 'clk_mdias', 'clk_mdiah'), ('B', 'clk_mdibs', 'clk_mdibh')):
        s, h = f(f'mult.{s}_{sel}'), f(f'mult.{h}_{sel}')
        arcs[('SETUP', pin)] = (sh_k * s[0], sh_k * s[2])
        arcs[('HOLD', pin)] = (sh_k * (h[0] - HOLD_ADJ), sh_k * (h[2] - HOLD_ADJ))
    return arcs


# per instance of dsp_sdf.v
expected = {
    'm_comb': {('IOPATH', 'A', 'DOUT'): iopath(f('mult.mdia_mout')),
               ('IOPATH', 'B', 'DOUT'): iopath(f('mult.mdib_mout'))},
    'm_reg': mult_reg(1, 1, 1),   # AREG/BREG and OREG
    'm_pipe': mult_reg(2, 6, 0),  # PREG only
    'm_oreg': mult_reg(1, 8, 0),  # OREG only
    'm_alu': {('IOPATH', 'A', 'DOUT'): iopath(add('mult.mdia_mout', 'alu54.md0_dout')),
              ('IOPATH', 'B', 'DOUT'): iopath(add('mult.mdib_mout', 'alu54.md0_cout'))},
    'm_addalu': {('IOPATH', 'A0', 'DOUT'): iopath(add('mult.mdia_mout', 'alu54.md0_dout')),
                 ('IOPATH', 'B0', 'DOUT'): iopath(add('mult.mdib_mout', 'alu54.md0_dout')),
                 ('IOPATH', 'A1', 'DOUT'): iopath(add('mult.mdia_mout', 'alu54.md1_dout')),
                 ('IOPATH', 'B1', 'DOUT'): iopath(add('mult.mdib_mout', 'alu54.md1_dout'))},
    'm_27x36': {('IOPATH', 'A', 'DOUT'): iopath(f('mult36x36.mdia_mout')),
                ('IOPATH', 'B', 'DOUT'): iopath(f('mult36x36.mdib_mout'))},
}

num = r'(-?[\d.]+):[-\d.]+:(-?[\d.]+)'
iopath_re = re.compile(rf'\(IOPATH (\w+)(?:\[\d+\])? (\w+)(?:\[\d+\])? \({num}\)')
setuphold_re = re.compile(rf'\(SETUPHOLD \((?:pos|neg)edge (\w+)(?:\[\d+\])?\) \(posedge CLK(?:\[\d+\])?\) '
                          rf'\({num}\) \({num}\)')
# any other line that opens a construct is an arc or check the regexes missed
other_re = re.compile(r'\s*\((?!CELLTYPE|INSTANCE|DELAY|ABSOLUTE|TIMINGCHECK)[A-Z]')
total = bad = skipped = 0
seen = set()
for cell in re.split(r'\(CELL\b', open(sdf).read()):
    m = re.search(r'\(CELLTYPE "(\w+)"\)\s*\(INSTANCE ([^)]*)\)', cell)
    if not m or not m[1].startswith('MULT'):
        continue
    inst = m[2].strip().split('/')[-1]
    got = {}
    for line in cell.splitlines():
        if k := iopath_re.search(line):
            got.setdefault(('IOPATH', k[1], k[2]), set()).add((float(k[3]), float(k[4])))
        elif k := setuphold_re.search(line):
            got.setdefault(('SETUP', k[1]), set()).add((float(k[2]), float(k[3])))
            got.setdefault(('HOLD', k[1]), set()).add((float(k[4]), float(k[5])))
        elif other_re.match(line):
            skipped += 1
            print(f'SKIP {inst:9} {line.strip()}')
    for arc, vals in sorted(got.items()):
        want = expected.get(inst, {}).get(arc)
        seen.add((inst, arc))
        for v in sorted(vals):
            total += 1
            off = None if want is None else max(abs(a - b) for a, b in zip(v, want))
            ok = off is not None and off <= 0.001 + 1e-9
            bad += not ok
            wstr = '-' if want is None else f'{want[0]:.4f}/{want[1]:.4f}'
            print(f'{"ok " if ok else "BAD"} {inst:9} {" ".join(arc):16} sdf {v[0]:.3f}/{v[1]:.3f}'
                  f'  chipdb {wstr}' + ('' if off is None else f'  off {off * 1000:.1f} ps'))
for inst, exp in expected.items():
    for arc in exp:
        if (inst, arc) not in seen:
            bad += 1
            print(f'MISSING {inst} {" ".join(arc)}')
print(f'{dev} {speed}: {total} distinct arc values, {bad} off by more than 1 ps or missing, '
      f'{skipped} SDF lines skipped')
