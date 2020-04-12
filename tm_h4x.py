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

def float_data(data, paths):
    res = {}
    for i, name in enumerate(paths):
        for j in range(4):
            idx = i*4+j
            res.setdefault(name,[]).append(to_float(data[idx*4:idx*4+4]))
    return res

def parse_lut(data):
    paths = ['a_f', 'b_f', 'c_f', 'd_f', 'a_ofx', 'b_ofx', 'c_ofx', 'd_ofx', 'm0_ofx0', 'm1_ofx1', 'fx_ofx1']
    return float_data(data, paths)

def parse_alu(data):
    paths = ['a_f', 'b_f', 'd_f', 'a0_fco', 'b0_fco', 'd0_fco', 'fci_fco', 'fci_f0']
    return float_data(data, paths)

def parse_sram(data):
    pass

def parse_dff(data):
    paths = [
        'di_clksetpos', # 0x0
        'di_clksetneg', # 0x4
        'di_clkholdpos', # 0x8
        'di_clkholdneg', # 0xc
        'ce_clksetpos', # 0x10
        'ce_clksteneg', # 0x14
        'ce_clkholdpos', # 0x18
        'ce_clkholdneg', # 0x1c
        'lsr_clksetpos_syn', # 0x20
        'lsr_clksetneg_syn', # 0x24
        'lsr_clkholdpos_syn', # 0x28
        'lsr_clkholdneg_syn', # 0x2c
        'clk_qpos', # 0x30
        'clk_qneg', # 0x34
        'lsr_q', # 0x38
        'lsr_clksetpos_asyn', # 0x3c
        'lsr_clksetneg_asyn', # 0x40
        'lsr_clkholdpos_asyn', # 0x44
        'lsr_clkholdneg_asyn', # 0x48
        'clk_clk', # 0x4c
        'lsr_lsr', # 0x50
    ]
    return float_data(data, paths)

def parse_dl(data):
    pass

def parse_iddroddr(data):
    pass

def parse_pll(data):
    pass

def parse_dll(data):
    pass

def parse_bram(data):
    paths = [
        'clka_doa', # 0
        'clkb_dob', # 4
        'clkb_do', # 8
        'clk_do', # 0xc
        'clka_reseta_set', # 0x10
        'clka_ocea_set', # 0x14
        'clka_cea_set', # 0x18
        'clka_wrea_set', # 0x1c
        'clka_dia_set', # 0x20
        'clka_di_set', # 0x24
        'clka_ada_set', # 0x28
        'clka_blksel_set', # 0x2c
        'clka_reseta_hold', # 0x30
        'clka_ocea_hold', # 0x34
        'clka_cea_hold', # 0x38
        'clka_wrea_hold', # 0x3c
        'clka_dia_hold', # 0x40
        'clka_di_hold', # 0x44
        'clka_ada_hold', # 0x48
        'clka_blkset_hold', # 0x4c
        'clkb_resetb_set', # 0x50
        'clkb_oceb_set', # 0x54
        'clkb_ceb_set', # 0x58
        'clkb_oce_set' # 0x5c
        'clkb_wreb_set', # 0x60
        'clkb_dib_set', # 0x64
        'clkb_adb_set', # 0x68
        'clkb_blkset_set' # 0x6c
        'clkb_resetb_hold', # 0x70
        'clkb_oceb_hold', # 0x74
        'clkb_ceb_hold', # 0x78
        'clkb_oce_hold', # 0x7c
        'clkb_wreb_hold', # 0x80
        'clkb_dib_hold', # 0x84
        'clkb_adb_hold', # 0x88
        'clkb_blksel_hold', # 0x8c
        'clk_ce_set', # 0x90
        'clk_oce_set', # 0x94
        'clk_reset_set', # 0x98
        'clk_wre_set', # 0x9c
        'clk_ad_set', # 0xa0
        'clk_di_set', # 0xa4
        'clk_blksel_set', # 0a8
        'clk_ce_hold', # 0xac
        'clk_oce_hold', # 0xb0
        'clk_reset_hold' # 0xb4
        'clk_wre_hold', # 0xb8
        'clk_ad_hold', #0xbc
        'clk_di_hold', # 0xc0
        'clk_blksel_hold', # 0xc4
        'clk_reset_set_syn', # 0xc8
        'clk_reset_hold_syn', # 0xcc
        'clka_reseta_set_syn', # 0xd0
        'clka_reseta_hold_syn', # 0xd4
        'clkb_resetb_set_syn', # 0xd8
        'clkb_resetb_hold_syn', # 0xdc
        'clk_clk', # 0xe0
    ]
    return float_data(data, paths)
    pass

def parse_dsp(data):
    pass

def parse_fanout(data):
    #TODO fan num?
    paths = ['OXFan', 'X1Fan', 'SX1Fan', 'X2Fan', 'X8Fan', 'FFan', 'QFan']
    return float_data(data, paths)

def parse_glbsrc(data):
    pass

def parse_hclk(data):
    pass

def parse_iodelay(data):
    paths = ['GI_DO', 'SDTAP_DO', 'SETN_DO', 'VALUE_DO',
             'SDTAP_DF', 'SETN_DF', 'VALUE_DF']
    return float_data(data, paths)

def parse_io(data):
    pass

def parse_iregoreg(data):
    pass

def parse_wire(data):
    paths = ['OX', 'FX1', 'X2', 'X8', 'ISB', 'X0CTL', 'X0CLK', 'X0ME']
    return float_data(data, paths)

offsets = {
    0x0: parse_lut,
    0xb0: parse_alu,
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
                    print(name)
                    print(tm)

