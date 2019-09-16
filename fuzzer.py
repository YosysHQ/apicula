import sys, pdb
import re
import os
import tempfile
import subprocess
from collections import deque
import numpy as np
import codegen
import bslib
from multiprocessing.dummy import Pool
# resource sets
# CFU=CLU?
# ENABLE: only one fuzzer switches things on and off at the same time
# IOB, CLU_LUT, CLU_MUX, CLU_DFF, CFU, BRAM, DSP, ENABLE

def location_to_name(location):
    return re.sub("\[([0-4AB])\]", "_\\1", location)

def np_to_vector(array):
    return "{}'b{}".format(
            len(array),
            ''.join(str(int(n)) for n in array))

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

def find_bits(stack):
    bytestack = np.packbits(stack, axis=0, bitorder='little').astype(np.uint32)
    #sequences = (bytestack[2]<<16)+(bytestack[1]<<8)+bytestack[0]
    sequences = np.zeros(bytestack.shape[1:], dtype=np.uint32)
    for i in range(bytestack.shape[0]):
        sequences += bytestack[i] << (i*8)
    indices = np.where((sequences>0) & (sequences<sequences.max()))
    return indices, sequences[indices]

class Fuzzer:
    # a set of resources used by this fuzzer
    resources = set()

    @property
    def cfg_bits(self):
        return len(self.locations)*self.loc_bits

    def primitives(self, mod, bits):
        "Generate verilog for this fuzzer"
        raise NotImplementedError

    def constraints(self, constr, bits):
        "Generate cst lines for this fuzzer"
        raise NotImplementedError

    def report(self, bits):
        """Generate a report of the bistream locations
           corresponding to the provided config bits"""
        for location, bits in zip(self.locations, bslib.chunks(bits, self.loc_bits)):
            print(self.__class__.__name__, location, bits)

class CluFuzzer(Fuzzer):
    scope = "CLU"
    ncls = 4 # 3 for REG
    def __init__(self, rows, cols, exclude):
        self.locations = []
        if self.scope == "CLU":
            for row in range(2, rows):
                if row not in exclude:
                    for col in range(2, cols):
                       self.locations.append("R{}C{}".format(row, col))
        elif self.scope == "CLS":
            for row in range(2, rows):
                if row not in exclude:
                    for col in range(2, cols):
                        for cls in range(self.ncls):
                            self.locations.append("R{}C{}[{}]".format(row, col, cls))
        else:
            for row in range(2, rows):
                if row not in exclude:
                    for col in range(2, cols):
                        for cls in range(self.ncls):
                            for lut in ["A", "B"]:
                                self.locations.append("R{}C{}[{}][{}]".format(row, col, cls, lut))

    def constraints(self, constr, bits):
        "Generate cst lines for this fuzzer"
        for loc in self.locations:
            name = location_to_name(loc)
            constr.cells[name] = loc


class Lut4BitsFuzzer(CluFuzzer):
    resources = {"CLU_LUT"}
    loc_bits = 16
    scope = "LUT"

    def primitives(self, mod, bits):
        "Generate verilog for LUT4s"
        for location, bits in zip(self.locations, bslib.chunks(bits, self.loc_bits)):
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

class Lut4EnableFuzzer(CluFuzzer):
    resources = {"CLU_LUT", "ENABLE"}
    loc_bits = 1
    scope = "CLS"
    ncls = 3 # CLS 3 has no initialisation values

    def primitives(self, mod, bits):
        "Generate verilog for a LUT4 at this location"
        for location, bits in zip(self.locations, bslib.chunks(bits, self.loc_bits)):
            location_a = location+"[A]"
            name = location_to_name(location_a)
            lut = codegen.Primitive("LUT4", name)
            lut.params["INIT"] = "16'hffff"
            lut.portmap['F'] = name+"_F"
            lut.portmap['I0'] = name+"_I0"
            lut.portmap['I1'] = name+"_I1"
            lut.portmap['I2'] = name+"_I2"
            lut.portmap['I3'] = name+"_I3"
            mod.wires.extend(lut.portmap.values())
            if bits[0]:
                mod.primitives.append(lut)

            location_b = location+"[B]"
            name = location_to_name(location_b)
            lut = codegen.Primitive("LUT4", name)
            lut.params["INIT"] = "16'hffff"
            lut.portmap['F'] = name+"_F"
            lut.portmap['I0'] = name+"_I0"
            lut.portmap['I1'] = name+"_I1"
            lut.portmap['I2'] = name+"_I2"
            lut.portmap['I3'] = name+"_I3"
            mod.wires.extend(lut.portmap.values())
            if bits[0]:
                mod.primitives.append(lut)

    def constraints(self, constr, bits):
        for loc, bits in zip(self.locations, bslib.chunks(bits, self.loc_bits)):
            if bits[0]:
                name = location_to_name(loc+"[A]")
                constr.cells[name] = loc
                name = location_to_name(loc+"[B]")
                constr.cells[name] = loc

class DffEnableFuzzer(CluFuzzer):
    resources = {"CLU_DFF", "ENABLE"}
    loc_bits = 1
    scope = "DFF"
    ncls = 3 # CLS 3 has no DFF

    def primitives(self, mod, bits):
        "Generate verilog for a DFF at this location"
        for location, bits in zip(self.locations, bslib.chunks(bits, self.loc_bits)):
            name = location_to_name(location)
            dff = codegen.Primitive("DFF", name)
            dff.portmap['CLK'] = name[:-2]+"_CLK"
            dff.portmap['D'] = name+"_F"
            dff.portmap['Q'] = name+"_Q"
            mod.wires.extend(dff.portmap.values())
            if bits[0]:
                mod.primitives.append(dff)

    def constraints(self, constr, bits):
        for loc, bits in zip(self.locations, bslib.chunks(bits, self.loc_bits)):
            if bits[0]:
                name = location_to_name(loc)
                constr.cells[name] = loc

def run_pnr(fuzzers, bits):
    #TODO generalize/parameterize
    mod = codegen.Module()
    constr = codegen.Constraints()
    for fuzzer in fuzzers:
        cb = bits[:fuzzer.cfg_bits]
        bits = bits[fuzzer.cfg_bits:]
        fuzzer.primitives(mod, cb)
        fuzzer.constraints(constr, cb)

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

    opt = codegen.PnrOptions(["warning_all"])
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
        #print(tmpdir); input()
        return bslib.read_bitstream(tmpdir+"/impl/pnr/top.fs")

def run_batch(fuzzers, fname=None):
    nrofbits = sum([f.cfg_bits for f in fuzzers])
    bits = configbits(nrofbits)
    p = Pool()
    if fname:
        try:
            stack = np.stack(list(np.load(fname).values()), axis=0)
        except FileNotFoundError:
            bitstreams = p.map(lambda cb: run_pnr(fuzzers, cb), bits)
            stack = np.stack(bitstreams)
            np.savez_compressed(fname, *bitstreams)
    else:
        bitstreams = p.map(lambda cb: run_pnr(fuzzers, cb), bits)
        stack = np.stack(bitstreams)
    indices, sequences = find_bits(stack)
    #debug image
    bitmap = np.zeros(stack.shape[1:], dtype=np.uint8)
    bitmap[indices] = 1
    bslib.display("indices.png", bitmap)

    seqloc = np.sort(np.array([sequences, *indices]).T, axis=0)
    assert np.all(np.diff(seqloc[:,0])<=1), "sequences are missing"

    mapping = {}
    for seq, x, y in seqloc:
        mapping.setdefault(seq, []).append((x, y))

    seqs = deque(range(1, nrofbits+1))
    for fuzzer in fuzzers:
        bits = []
        for _ in range(fuzzer.cfg_bits):
            bit = seqs.popleft()
            bits.append(mapping[bit])

        fuzzer.report(bits)


if __name__ == "__main__":
    fuzzers = [
        #Lut4BitsFuzzer(28, 47, {10, 19, 28}),
        #Lut4EnableFuzzer(28, 47, {10, 19, 28}),
        DffEnableFuzzer(28, 47, {10, 19, 28}),
    ]
    run_batch(fuzzers, "bitstreams.npz")
