import os
import sys
import json
import struct

gowinhome = os.getenv("GOWINHOME")
if not gowinhome:
    raise Exception("GOWINHOME not set")

device = os.getenv("DEVICE")
if not device:
    raise Exception("DEVICE not set")

tc = 8 # number of timing classes
chunklen = 0x3ab8 # length of each class

def to_float(s):
    return struct.unpack('f', s)[0]

def parse_lut(data):
    res = {}
    paths = ['a_f', 'b_f', 'c_f', 'd_f', 'a_ofx', 'b_ofx', 'c_ofx', 'd_ofx']
    for i, name in enumerate(paths):
        for j in range(4):
            idx = i*4+j
            res.setdefault(name,[]).append(to_float(data[i*4:i*4+4]))
    return res

def parse_sram(data):
    pass

def parse_dff(data):
    pass

def parse_dl(data):
    pass

def parse_iddroddr(data):
    pass

def parse_pll(data):
    pass

def parse_dll(data):
    pass

def parse_bram(data):
    pass

def parse_dsp(data):
    pass

def parse_fanout(data):
    pass

def parse_glbsrc(data):
    pass

def parse_hclk(data):
    pass

def parse_iodelay(data):
    pass

def parse_io(data):
    pass

def parse_iregoreg(data):
    pass

def parse_wire(data):
    pass

offsets = {
    #0x0: parse_alu,
    0x0: parse_lut,
    0x130: parse_sram,
    0x240: parse_dff,
    0x390: parse_dl,
    0x4a0: parse_iddroddr,
    0x7cc: parse_pll,
    0x81c: parse_dll,
    0x8bc: parse_bram,
    0xc4c: parse_dsp,
    0x3638: parse_fanout,
    0x36d8: parse_glbsrc,
    0x37e8: parse_hclk,
    0x3548: parse_iodelay,
    0x3098: parse_io,
    0x2e8c: parse_iregoreg,
    0x35b8: parse_wire,
}
dspoffsets = {
    0x0: 'mult', #DSP
    0x410: 'mac', #DSP
    0x6b0: 'multadd', #DSP
    0xaf0: 'multaddsum', #DSP
    0x1300: 'padd', #DSP
    0x1560: 'alu45', #DSP
}
def parse_chunk(chunk):
    for off, parser in offsets.items():
        yield parser.__name__, parser(chunk[off:])


if __name__ == "__main__":
    with open(f"{gowinhome}/IDE/share/device/{device}/{device}.tm", 'rb') as f:
        for chunk in iter(lambda: f.read(chunklen), b''):
            assert len(chunk) == chunklen
            res = parse_chunk(chunk)
            for name, tm in res:
                if tm:
                    print(name, tm)

