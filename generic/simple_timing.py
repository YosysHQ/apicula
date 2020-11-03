import os
import pickle
from apycula import chipdb

device = os.getenv("DEVICE")
if not device:
    raise Exception("DEVICE not set")

timing_class = "C6/I5" # TODO parameterize

with importlib.resources.open_binary("apycula", f"{device}.pickle") as f:
    db = pickle.load(f)

timing = db.timing[timing_class]

for cname, cell in ctx.cells:
    if cell.type != "GENERIC_SLICE":
        continue
    if cname in ("$PACKER_GND", "$PACKER_VCC"):
        continue
    ports = ['a', 'b', 'c', 'd']
    ctx.addCellTimingClock(cell=cname, port="CLK")
    for i, port in enumerate(ports):
        setup = ctx.getDelayFromNS(max(timing['dff']['di_clksetpos']))
        hold = ctx.getDelayFromNS(max(timing['dff']['di_clkholdpos']))
        ctx.addCellTimingSetupHold(cell=cname, port="I[%d]" % i, clock="CLK", setup=setup, hold=hold)
    clkout = ctx.getDelayFromNS(max(timing['dff']['clk_qpos']))
    ctx.addCellTimingClockToOut(cell=cname, port="Q", clock="CLK", clktoq=clkout)
    for i, port in enumerate(ports):
        delay = ctx.getDelayFromNS(max(timing['lut'][f'{port}_f']))
        ctx.addCellTimingDelay(cell=cname, fromPort="I[%d]" % i, toPort="F", delay=delay)
