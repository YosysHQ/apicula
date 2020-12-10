import os
import sys
import json
import struct

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

def to_int(s):
    return struct.unpack('I', s)[0]

def int_data(data, paths):
    res = {}
    for i, name in enumerate(paths):
        res[name] = to_int(data[i*4:i*4+4])
    return res

def parse_lut(data):
    paths = ['a_f', 'b_f', 'c_f', 'd_f', 'a_ofx', 'b_ofx', 'c_ofx', 'd_ofx', 'm0_ofx0', 'm1_ofx1', 'fx_ofx1']
    return float_data(data, paths)

def parse_alu(data):
    paths = ['a_f', 'b_f', 'd_f', 'a0_fco', 'b0_fco', 'd0_fco', 'fci_fco', 'fci_f0']
    return float_data(data, paths)

def parse_sram(data):
    paths = [
        'rad0_do', # 0 also unnumbered
        'rad1_do', # 4
        'rad2_do', # 8
        'rad3_do', # 0xc
        'clk_di_set', # 0x10
        'clk_di_hold', # 0x14
        'clk_wre_set', # 0x18
        'clk_wre_hold', # 0x1c
        'clk_wad0_set', # 0x20 also unnumbered
        'clk_wad0_hold', # 0x24 also unnumbered
        'clk_wad1_set', # 0x28
        'clk_wad1_hold', # 0x2c
        'clk_wad2_set', # 0x30
        'clk_wad2_hold', # 0x34
        'clk_wad3_set', # 0x38
        'clk_wad3_hold', # 0x3c
        'clk_do', # 0x40
    ]
    return float_data(data, paths)

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
        'clkb_blkset_set', # 0x6c
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
        'clk_reset_hold', # 0xb4
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

def parse_dsp(data):
    pass

def parse_fanout(data):
    paths = [
        'X0Fan', # 0x00
        'X1Fan', # 0x04
        'SX1Fan', # 0x08
        'X2Fan', # 0x0C
        'X8Fan', # 0x10
        'FFan', # 0x14
        'QFan', # 0x18
        'OFFan', # 0x1c
    ]
    int_paths = [
        'X0FanNum',
        'X1FanNum',
        'SX1FanNum',
        'X2FanNum',
        'X8FanNum',
        'FFanNum',
        'QFanNum',
        'OFFanNum',
    ]
    return {**float_data(data, paths), **int_data(data[0x80:], int_paths)}

# P/S = primary/secondary clock?
# clock path:
# CIB/PIO -> CENT -> SPINE -> TAP -> BRANCH
# CIB in ECP5 = configurable interconnect block
# PIO in ECP5 = programmable IO
def parse_glbsrc(data):
    paths = [
        'CIB_CENT_PCLK', # 0x00
        'PIO_CENT_PCLK', # 0x04
        'CENT_SPINE_PCLK', # 0x08
        'SPINE_TAP_PCLK', # 0x0c
        'TAP_BRANCH_PCLK', # 0x10
        'BRANCH_PCLK', # 0x14
        'CIB_PIC_INSIDE', # 0x18
        'CIB_CENT_SCLK', # 0x1c
        'PIO_CENT_SCLK', # 0x20
        'CENT_SPINE_SCLK', # 0x24
        'SPINE_TAP_SCLK_0', # 0x28
        'SPINE_TAP_SCLK_1', # 0x2c (getter takes index)
        'TAP_BRANCH_SCLK', # 0x30
        'BRANCH_SCLK', # 0x34
        'GSRREC_SET', # 0x38
        'GSRREC_HLD', # 0x3c
        'GSR_MPW', # 0x40
    ]
    return float_data(data, paths)


# HclkPathDly = 0x8 + 0x0 + 0xc
def parse_hclk(data):
    paths = [
        'HclkInMux', # 0x0
        'HclkHbrgMux', # 0x4
        'HclkOutMux', # 0x8
        'HclkDivMux', # 0xc
    ]
    return float_data(data, paths)

def parse_iodelay(data):
    paths = ['GI_DO', 'SDTAP_DO', 'SETN_DO', 'VALUE_DO',
             'SDTAP_DF', 'SETN_DF', 'VALUE_DF']
    return float_data(data, paths)

def parse_io(data):
    pass

def parse_iregoreg(data):
    pass

def parse_wire(data):
    paths = [
        'X0', # 0x00
        'FX1', # 0x04
        'X2', # 0x08
        'X8', # 0x0C
        'ISB', # 0x10
        'X0CTL', # 0x14
        'X0CLK', # 0x18
        'X0ME', # 0x1C
    ]
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
        yield parser.__name__[6:], parser(chunk[off:])


def read_tm(f, device):
    if device.lower().startswith("gw1n"):
        chunk_order = [
            "C5/I4",
            "C5/I4_LV",
            "C6/I5",
            "C6/I5_LV",
            "ES",
            "ES_LV",
            "A4",
            "A4_LV",
        ]
    elif device.lower().startswith("gw2a"):
        chunk_order = [
            "C8/I7",
            "C8/I7_LV",
            "C7/I6",
            "C7/I6_LV",
            "A6",
            "A6_LV",
            "C9/I8",
            "C9/I8_LV",
        ]
    else:
        raise Exception("unknown family")

    tmdat = {}
    for i, chunk in enumerate(iter(lambda: f.read(chunklen), b'')):
        try:
            speed_class = chunk_order[i]
        except IndexError:
            speed_class = i
        tmdat[speed_class] = {}
        assert len(chunk) == chunklen
        res = parse_chunk(chunk)
        for name, tm in res:
            if tm:
                tmdat[speed_class][name] = tm
    return tmdat
