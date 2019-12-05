import re
import os
import tempfile
import subprocess
from collections import deque
from itertools import chain, count
from random import shuffle, seed
from warnings import warn
from math import factorial
import numpy as np
from multiprocessing.dummy import Pool

import codegen
import bslib
import pindef

import sys, pdb
# resource sets
# CFU=CLU?
# ENABLE: only one fuzzer switches things on and off at the same time
# IOB, CLU_LUT, CLU_MUX, CLU_DFF, CFU, BRAM, DSP, ENABLE

gowinhome = os.getenv("GOWINHOME")
if not gowinhome:
    raise Exception("GOWINHOME not set")

def np_to_vector(array):
    return "{}'b{}".format(
            len(array),
            ''.join(str(int(n)) for n in array))

def popcnt(x):
    res = 0
    while x:
        if x & 1:
            res += 1
        x >>= 1
    return res

def get_cb_size(n):
    return factorial(n) // factorial(n // 2) // factorial((n + 1) // 2)

def gen_cb(n):
    res = []
    for i in range(1, 2**n):
        if popcnt(i) == (n + 1) // 2:
            res.append(i)
    assert len(res) == get_cb_size(n)
    return res

def get_codes(n):
    bits = n.bit_length()
    while get_cb_size(bits) < n:
        bits += 1
    cb = gen_cb(bits)
    return bits, cb[:n]

def configbits(bitlen, codes):
    """
    Given n bits of configuration data
    generate uniquely identifying
    bit patterns for each configuration bit.
    This makes each configuration bit uniquely
    identifiable in the bitstream.
    """
    codelen = len(codes)
    byteview = np.array(codes, dtype=np.uint32).view(np.uint8)
    bits = np.unpackbits(byteview, bitorder='little')
    return bits.reshape(codelen, 32)[:,:bitlen].T

def configcodes(stack):
    "Turn bit arrays back into numbers"
    bytestack = np.packbits(stack, axis=0, bitorder='little').astype(np.uint32)
    sequences = np.zeros(bytestack.shape[1:], dtype=np.uint32)
    for i in range(bytestack.shape[0]):
        sequences += bytestack[i] << (i*8)
    return sequences

def find_bits(stack):
    sequences = configcodes(stack)
    indices = np.where((sequences>0) & (sequences<sequences.max()))
    return indices, sequences[indices]

class Fuzzer:
    # a set of resources used by this fuzzer
    resources = set()
    # added to name to avoid conflicts
    prefix = ""
    # values higher than this will trigger a warning
    max_std = 20
    # bits of side-effects
    se_bits = 0
    # list of side-effect identifiers
    se_loc = []

    @property
    def cfg_bits(self):
        return len(self.locations)*self.loc_bits

    @property
    def se_bits(self):
        # this is dumb and potentially slow
        return self.side_effects(np.zeros((0, self.cfg_bits), dtype=np.uint8)).shape[1]

    def location_to_name(self, location):
        return self.prefix + re.sub("\[([0-4AB])\]", "_\\1", location)

    def location_chunks(self, bits):
        return zip(self.locations, bslib.chunks(bits, self.loc_bits))

    def primitives(self, mod, bits):
        "Generate verilog for this fuzzer"
        raise NotImplementedError

    def constraints(self, constr, bits):
        "Generate cst lines for this fuzzer"
        raise NotImplementedError

    def side_effects(self, bits):
        """
        Returns a list of codes that
        don't map 1-1 to bitstream bits.
        e.g. OR/AND of several other bits.
        """
        return np.zeros((1, 0))

    def side_effect_cfg(self):
        """
        For each side-effect, return a set of
        config bits that triggers
        the corresponding side-effect.
        """
        return np.zeros((0, self.cfg_bits))

    def check(self, bits):
        "Perform some basic checks on the bitstream bits"
        if len(self.locations)*self.loc_bits != len(bits):
            warn("{} clusters expected, but {} clusters found".format(
                len(self.locations)*self.loc_bits,
                len(bits)))

        for loc, b in self.location_chunks(bits):
            a = np.array(b)
            std = np.std(a, axis=1)
            if np.any(std > self.max_std):
                warn("High deviation in location {}".format(loc))


    def report(self, bits):
        """Generate a report of the bistream locations
           corresponding to the provided config bits"""
        for loc, b in self.location_chunks(bits):
            print(self.__class__.__name__, loc, b)

    def report_side_effects(self, bits):
        """Generate a report of the bistream locations
           corresponding to side-effect bits"""
        for se, b in zip(self.se_loc, bits):
            print(self.__class__.__name__, "se", se, b)

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

        shuffle(self.locations)

    def constraints(self, constr, bits):
        "Generate cst lines for this fuzzer"
        for loc in self.locations:
            name = self.location_to_name(loc)
            constr.cells[name] = loc

class Lut4BitsFuzzer(CluFuzzer):
    """
    This fuzzer finds the lookuptable bits of a LUT4
    """
    resources = {"CLU_LUT"}
    loc_bits = 16
    scope = "LUT"
    prefix = "LUT"

    def primitives(self, mod, bits):
        "Generate verilog for LUT4s"
        for location, bits in self.location_chunks(bits):
            name = self.location_to_name(location)
            lut = codegen.Primitive("LUT4", name)
            lut.params["INIT"] = np_to_vector(1^bits) # inverted
            lut.portmap['F'] = name+"_F"
            lut.portmap['I0'] = name+"_I0"
            lut.portmap['I1'] = name+"_I1"
            lut.portmap['I2'] = name+"_I2"
            lut.portmap['I3'] = name+"_I3"
            mod.wires.update(lut.portmap.values())
            mod.primitives[name] = lut

class DffFuzzer(CluFuzzer):
    """
    This fuzzer finds the bits for a DFF
    But includes an empty LUT because otherwise
    a pass-through LUT is created.
    """
    resources = {"CLU_LUT", "CLU_DFF"}
    loc_bits = 1
    scope = "CLS"
    ncls = 3 # CLS 3 has no DFF

    def primitives(self, mod, bits):
        "Generate verilog for a LUT4 and DFF"
        for location, bits in self.location_chunks(bits):
            if bits[0]:
                name = self.location_to_name(location)
                location_a = location+"[A]_LUT"
                name_a_lut = self.location_to_name(location_a)
                lut = codegen.Primitive("LUT4", name_a_lut)
                lut.params["INIT"] = "16'hffff"
                lut.portmap['F'] = name_a_lut+"_F"
                lut.portmap['I0'] = name_a_lut+"_I0"
                lut.portmap['I1'] = name_a_lut+"_I1"
                lut.portmap['I2'] = name_a_lut+"_I2"
                lut.portmap['I3'] = name_a_lut+"_I3"
                mod.wires.update(lut.portmap.values())
                mod.primitives[name_a_lut] = lut

                location_b = location+"[B]_LUT"
                name_b_lut = self.location_to_name(location_b)
                lut = codegen.Primitive("LUT4", name_b_lut)
                lut.params["INIT"] = "16'hffff"
                lut.portmap['F'] = name_b_lut+"_F"
                lut.portmap['I0'] = name_b_lut+"_I0"
                lut.portmap['I1'] = name_b_lut+"_I1"
                lut.portmap['I2'] = name_b_lut+"_I2"
                lut.portmap['I3'] = name_b_lut+"_I3"
                mod.wires.update(lut.portmap.values())
                mod.primitives[name_b_lut] = lut

                location_a = location+"[A]_DFF"
                name_a_dff = self.location_to_name(location_a)
                dff = codegen.Primitive("DFF", name_a_dff)
                dff.portmap['CLK'] = name+"_CLK" # share clk
                dff.portmap['D'] = name_a_lut+"_F"
                dff.portmap['Q'] = name_a_dff+"_Q"
                mod.wires.update(dff.portmap.values())
                mod.primitives[name_a_dff] = dff

                location_a = location+"[B]_DFF"
                name_b_dff = self.location_to_name(location_a)
                dff = codegen.Primitive("DFF", name_b_dff)
                dff.portmap['CLK'] = name+"_CLK"
                dff.portmap['D'] = name_b_lut+"_F"
                dff.portmap['Q'] = name_b_dff+"_Q"
                mod.wires.update(dff.portmap.values())
                mod.primitives[name_b_dff] = dff

    def constraints(self, constr, bits):
        for loc, bits in self.location_chunks(bits):
            if bits[0]:
                name = self.location_to_name(loc+"[A]_LUT")
                constr.cells[name] = loc
                name = self.location_to_name(loc+"[B]_LUT")
                constr.cells[name] = loc
                name = self.location_to_name(loc+"[A]_DFF")
                constr.cells[name] = loc
                name = self.location_to_name(loc+"[B]_DFF")
                constr.cells[name] = loc

class DffsrFuzzer(CluFuzzer):
    """
    This fuzzer finds the DFF bits that control
     1. clock polarity
     2. sync/async
     3. reset value
    it does not find
     4. unknown (DFF/DFFN)
     5. unknown (always 1)
    Layout:
    ..4
    2.5
    .31
    """
    resources = {"CLU_DFF"}
    loc_bits = 3
    scope = "CLS"
    ncls = 3 # CLS 3 has no DFF
    prefix = "DFF"

    # clkpol, sync/async, set/reset
    ffmap = {
        (0, 0, 0): ("DFFSE", "SET"),
        (0, 0, 1): ("DFFRE", "RESET"),
        (0, 1, 0): ("DFFPE", "PRESET"),
        (0, 1, 1): ("DFFCE", "CLEAR"),
        (1, 0, 0): ("DFFNSE", "SET"),
        (1, 0, 1): ("DFFNRE", "RESET"),
        (1, 1, 0): ("DFFNPE", "PRESET"),
        (1, 1, 1): ("DFFNCE", "CLEAR"),
    }

    def primitives(self, mod, bits):
        "Generate verilog for a DFF at this location"
        for location, bits in self.location_chunks(bits):
            prim, port = self.ffmap[tuple(bits)]
            name = self.location_to_name(location)
            dff = codegen.Primitive(prim, name)
            dff.portmap['CLK'] = name+"_CLK"
            dff.portmap['D'] = name+"_F"
            dff.portmap['Q'] = name+"_Q"
            dff.portmap['CE'] = name+"_CE"
            dff.portmap[port] = name+"_"+port
            mod.wires.update(dff.portmap.values())
            mod.primitives[name] = dff

class OneHopWireFuzzer(CluFuzzer):
    """
    This fuzzer finds wires to adjacent tiles
    """
    resources = {"CLU_LUT"}
    loc_bits = 4
    scope = "LUT"
    prefix = "LUT"

    def neighbours(self, location):
        for r, c in [(1,0), (0, 1), (-1, 0), (0, -1)]:
            yield re.sub(
                "R(\\d+)C(\\d+)",
                lambda m: "R{}C{}".format(
                    int(m[1])+r, int(m[2])+c),
                location)

    def primitives(self, mod, bits):
        "Generate verilog for LUT4s"
        for location, bits in self.location_chunks(bits):
            name = self.location_to_name(location)
            lut = codegen.Primitive("LUT4", name)
            lut.params["INIT"] = "16'h0000"
            lut.portmap['F'] = name+"_F"
            neigh = self.neighbours(location)
            for i, ne, bit in zip(count(), neigh, bits):
                if bit:
                    ne_name = self.location_to_name(ne)
                    lut.portmap['I{}'.format(i)] = ne_name+"_F"
                else:
                    lut.portmap['I{}'.format(i)] = name+"_I{}".format(i)

            mod.wires.update(lut.portmap.values())
            mod.primitives[name] = lut

class PinFuzzer(Fuzzer):
    def __init__(self, series, package):
        self.locations = []
        self.banks = pindef.get_pins(series, package)
        self.se_loc = self.banks.keys()
        for bank in self.banks.values():
            self.locations.extend(bank)
        shuffle(self.locations)
        self.bank_indices = {
            bank: [self.locations.index(pin)
                for pin in pins]
            for bank, pins in self.banks.items()
        }

    def constraints(self, constr, bits):
        "Generate cst lines for this fuzzer"
        for loc in self.locations:
            name = "IOB{}".format(loc)
            constr.ports[name] = loc

class IobFuzzer(PinFuzzer):
    resources = {"IOB"}
    loc_bits = 1
    kindmap = {
            "IBUF": {"wires": ["O"], "inputs": ["I"]},
            "OBUF": {"wires": ["I"], "outputs": ["O"]},
            "TBUF": {"wires": ["I", "OEN"], "outputs": ["O"]},
            "IOBUF": {"wires": ["I", "O", "OEN"], "inouts": ["IO"]},
        #"TLVDS_IBUF": ["I", "IB", "O"],
        #"TLVDS_OBUF": ["I", "OB", "O"],
        #"TLVDS_TBUF": ["I", "OB", "O", "OEN"],
        #"TLVDS_IOBUF": ["I", "IO", "IOB", "O", "OEN"],
        #"MIPI_IBUF_HS": ["I", "IB", "OH"],
        #"MIPI_IBUF_LP": ["I", "IB", "OL", "OB"],
        #"MIPI_IBUF": ["I", "IB", "HSREN", "OEN", "OENB", "OH", "OB", "IO", "IOB"],
        #"MIPI_OBUF": ["MODESEL", "I", "IB", "O", "OB"],
        #"I3C_IOBUF": ["MODESEL", "I", "O", "IO"],
    }

    def __init__(self, kind, pins, exclude):
        super().__init__(pins, exclude)
        self.kind = kind
        self.ports = self.kindmap[kind]

    def primitives(self, mod, bits):
        "Generate verilog for an IOB at this location"
        for location, bits in self.location_chunks(bits):
            if bits[0]:
                name = "IOB{}".format(location)
                dff = codegen.Primitive(self.kind, name)
                for port in chain.from_iterable(self.ports.values()):
                    dff.portmap[port] = name+"_"+port

                for direction, wires in self.ports.items():
                    wnames = [name+"_"+w for w in wires]
                    getattr(mod, direction).update(wnames)
                mod.primitives[name] = dff

    def constraints(self, constr, bits):
        for loc, bits in self.location_chunks(bits):
            if bits[0]:
                name = "IOB{}".format(loc)
                constr.ports[name] = loc

    def side_effects(self, bits):
        "If any pin is turned on, the bank is also enabled"
        return np.array([
            np.any(bits[:,idc], axis=1)
            for bank, idc in self.bank_indices.items()
        ]).T

    def side_effect_cfg(self):
        "Turn each bank on seperately"
        cfglist = []
        for bank, indices in self.bank_indices.items():
            cfg = np.zeros(self.cfg_bits, dtype=np.uint8)
            cfg[indices] = 1
            cfglist.append(cfg)
        return np.vstack(cfglist)

def run_pnr(fuzzers, bits):
    #TODO generalize/parameterize
    mod = codegen.Module()
    constr = codegen.Constraints()
    start = 0
    for fuzzer in fuzzers:
        cb = bits[start:start+fuzzer.cfg_bits]
        start += fuzzer.cfg_bits
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
        subprocess.run([gowinhome+"/IDE/bin/gw_sh", tmpdir+"/run.tcl"])
        #print(tmpdir); input()
        try:
            return bslib.read_bitstream(tmpdir+"/impl/pnr/top.fs")[0]
        except FileNotFoundError:
            return None

def get_extra_bits(fuzzers, bits):
    "Extend bits with configurations that test side-effects"
    groups = []
    start = 0
    for fuzzer in fuzzers:
        cfg = fuzzer.side_effect_cfg()
        group = np.zeros((cfg.shape[0], bits.shape[1]), dtype=np.uint8)
        group[:,start:start+fuzzer.cfg_bits] = cfg
        start += fuzzer.cfg_bits
        groups.append(group)
    gstack = np.vstack(groups)

    nrofbits = gstack.shape[0]
    if nrofbits > 0:
        codelen, codes = get_codes(nrofbits)
        shuffle(codes)
        sebits = configbits(codelen, codes)
        rows = [np.sum(gstack[row==1], axis=0) for row in sebits]
        rows.append(bits)
        return codelen, np.vstack(rows)
    else:
        return 0, bits

def get_extra_codes(fuzzers, bits):
    "Get codes produces by fuzzer side-effects"
    extra_bits = []
    start = 0
    for fuzzer in fuzzers:
        cb = bits[:,start:start+fuzzer.cfg_bits]
        start += fuzzer.cfg_bits
        se = fuzzer.side_effects(cb)
        if se.size:
            extra_bits.append(se)
    if extra_bits:
        return configcodes(np.hstack(extra_bits))
    else:
        return []

def run_batch(fuzzers):
    nrofbits = sum([f.cfg_bits for f in fuzzers])
    codelen, codes = get_codes(nrofbits)
    shuffle(codes)
    bits = configbits(codelen, codes)

    secodelen, bits = get_extra_bits(fuzzers, bits)
    codes = configcodes(bits) # extended codes
    extra_codes = get_extra_codes(fuzzers, bits)

    if True:
        p = Pool()
        bitstreams = p.map(lambda cb: run_pnr(fuzzers, cb), bits)
        stack = np.stack([b for b in bitstreams if b is not None])
        np.savez_compressed("bitstreams.npz", *bitstreams)
    else:
        stack = np.stack(list(np.load("bitstreams.npz").values()), axis=0)

    indices, sequences = find_bits(stack)

    #debug image
    bitmap = np.zeros(stack.shape[1:], dtype=np.uint8)
    bitmap[indices] = 1
    bslib.display("indices.png", bitmap)

    seqloc = np.array([sequences, *indices]).T
    c_set = set(codes)
    ec_set = set(extra_codes)
    for s, x, y in seqloc:
        if s in c_set:
            print("Valid sequence at: {}, {}".format(x, y))
            continue
        if s in ec_set:
            print("Side effect at: {}, {}".format(x, y))
            continue
        raise ValueError("invalid sequence at: {}, {}".format(x, y))

    mapping = {}
    for seq, x, y in seqloc:
        mapping.setdefault(seq, []).append((x, y))

    codesq = deque(codes)
    extra_codesq = deque(extra_codes)
    for fuzzer in fuzzers:
        bits = []
        extra_bits = []
        for _ in range(fuzzer.cfg_bits):
            code = codesq.popleft()
            bits.append(mapping[code])
        for _ in range(fuzzer.se_bits):
            code = extra_codesq.popleft()
            extra_bits.append(mapping[code])

        fuzzer.report(bits)
        fuzzer.report_side_effects(extra_bits)
        fuzzer.check(bits)

if __name__ == "__main__":
    seed(0xdeadbeef)
    fuzzers = [
        #Lut4BitsFuzzer(28, 47, {10, 19, 28}),
        #DffFuzzer(28, 47, {10, 19, 28}),
        #DffsrFuzzer(28, 47, {10, 19, 28}),
        OneHopWireFuzzer(28, 47, {10, 19, 28}),
        #IobFuzzer("IBUF", "GW1NR-9", "QN881"),
    ]
    run_batch(fuzzers)
