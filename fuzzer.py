import sys, pdb
import re
import os
import tempfile
import subprocess
import numpy as np
import codegen
import bslib
from multiprocessing.dummy import Pool
# resource sets
# IOB, CLU, CFU, BRAM, DSP

def location_to_name(location):
    return re.sub("\[([0-4AB])\]", "_\\1", location)

def np_to_vector(array):
    return "{}'b{}".format(
            len(array),
            ''.join(str(int(n)) for n in array))

def tile_locations(rows, cols, exclude=set()):
    for row in range(2, rows):
        for col in range(2, cols):
            for cls in range(4):
                for lut in ["A", "B"]:
                    if row not in exclude:
                        yield "R{}C{}[{}][{}]".format(row, col, cls, lut)

def configbits(n):
    """
    Given n bits of configuration data
    generate ceil(log2(n)) uniquely identifying
    bit patterns for each configuration bit.
    This makes each configuration bit uniquely
    identifiable in the bitstream.
    """
    n += 2 # exclude 0000 and FFFF to avoid trouble
    byteview = np.arange(n, dtype=np.uint32).view(np.uint8)
    bits = np.unpackbits(byteview, bitorder='little')
    size = np.ceil(np.log2(n)).astype(np.int)
    return bits.reshape(n, 32)[1:-1,:size].T

def find_bits(stack, n):
    #flipstack = np.flip(stack, axis=0)
    bytestack = np.packbits(stack, axis=0, bitorder='little').astype(np.uint32)
    sequences = (bytestack[2]<<16)+(bytestack[1]<<8)+bytestack[0]
    indices = np.where((sequences>0) & (sequences<sequences.max()))
    return indices, sequences[indices]

class Fuzzer:
    # a set of resources used by this fuzzer
    resources = set()
    # the number of configuration bits per instance
    cfg_bits = 0

    def primitives(self, mod, location, bits):
        "Generate verilog for this location"
        raise NotImplementedError

    def constraints(self, constr, location):
        "Generate cst lines for this location"
        name = location_to_name(location)
        constr.cells[name] = location

    def report(self, location, bitstream_locations):
        """Generate a report of the bistream locations
           corresponding to the provided config bits"""
        print(self.__class__.__name__, location, bitstream_locations)

class Lut4Fuzzer(Fuzzer):
    resources = {"CLU"}
    cfg_bits = 16

    def primitives(self, mod, location, bits):
        "Generate verilog for a LUT4 at this location"
        name = location_to_name(location)
        lut = codegen.Primitive("LUT4", name)
        lut.params["INIT"] = np_to_vector(1^bits) # inverted
        lut.portmap['F'] = name+"_F"
        lut.portmap['I0'] = name+"_I0"
        lut.portmap['I1'] = name+"_I1"
        lut.portmap['I2'] = name+"_I2"
        lut.portmap['I3'] = name+"_I3"
        mod.wires.extend(lut.portmap.values())
        mod.primitives.append(lut)


def run_pnr(locations, fuzzer, bits):
    #TODO generalize/parameterize
    mod = codegen.Module()
    for loc, cb in zip(locations, bslib.chunks(bits, fuzzer.cfg_bits)):
        fuzzer.primitives(mod, loc, cb)

    constr = codegen.Constraints()
    for loc in locations:
        fuzzer.constraints(constr, loc)

    cfg = codegen.DeviceConfig({
        "JTAG regular_io": "false",
        "SSPI regular_io": "false",
        "MSPI regular_io": "false",
        "READY regular_io": "false",
        "DONE regular_io": "false",
        "RECONFIG_N regular_io": "false",
        "MODE regular_io": "false",
        "CRC_check": "true",
        "compress": "false",
        "encryption": "false",
        "security_bit_enable": "true",
        "bsram_init_fuse_print": "true",
        "download_speed": "250/100",
        "spi_flash_address": "0x00FFF000",
        "format": "txt",
        "background_programming": "false",
        "secure_mode": "false"})

    opt = codegen.PnrOptions([])
            #"sdf", "oc", "ibs", "posp", "o",
            #"warning_all", "timing", "reg_not_in_iob"])

    pnr = codegen.Pnr()
    pnr.device = "GW1NR-9-QFN88-6"
    pnr.partnumber = "GW1NR-LV9QN88C6/I5"

    with tempfile.TemporaryDirectory() as tmpdir:
        pnr.outdir = tmpdir
        with open(tmpdir+"/top.v", "w") as f:
            mod.write(f)
        pnr.netlist = tmpdir+"/top.v"
        with open(tmpdir+"/top.cst", "w") as f:
            constr.write(f)
        pnr.cst = tmpdir+"/top.cst"
        with open(tmpdir+"/device.cfg", "w") as f:
            cfg.write(f)
        pnr.cfg = tmpdir+"/device.cfg"
        with open(tmpdir+"/pnr.cfg", "w") as f:
            opt.write(f)
        pnr.opt = tmpdir+"/pnr.cfg"
        with open(tmpdir+"/run.tcl", "w") as f:
            pnr.write(f)
        subprocess.run(["/home/pepijn/bin/gowin/IDE/bin/gw_sh", tmpdir+"/run.tcl"])
        return bslib.read_bitstream(tmpdir+"/impl/pnr/top.fs")

def run_batch():
    #TODO generalize/parameterize
    locations = list(tile_locations(28, 47, {10, 19, 28}))
    nrofbits = len(locations)*Lut4Fuzzer.cfg_bits
    bits = configbits(nrofbits)
    p = Pool()
    bitstreams = p.map(lambda cb: run_pnr(locations, Lut4Fuzzer(), cb), bits)
    np.savez_compressed("bitstreams.npz", *bitstreams)
    stack = np.stack(bitstreams)
    indices, sequences = find_bits(stack, nrofbits)
    #debug image
    bitmap = np.zeros(stack[0].shape, dtype=np.uint8)
    bitmap[indices] = 1
    bslib.display("indices.png", bitmap)
    mapping = {}
    for x, y, seq in zip(*indices, sequences):
        mapping[seq] = (x, y)
    lf = Lut4Fuzzer()
    for loc, bits in zip(locations, bslib.chunks(range(1, nrofbits+1), lf.cfg_bits)):
        lf.report(loc, [mapping[i] for i in bits])



if __name__ == "__main__":
    run_batch()
