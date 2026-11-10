import os
import sys
import struct

tc = 8 # number of timing classes
chunklen = 15552 # length of each class

def to_float(s):
    return struct.unpack('f', s)[0]

def float_data(data, paths):
    res = {}
    for i, name in enumerate(paths):
        for j in range(4):
            idx = i*4+j
            res.setdefault(name,[]).append(to_float(data[idx*4:idx*4+4]))
    return res

def offset_data(data, fields):
    """{name: 4 floats} for fields at the given byte offsets."""
    return {name: list(struct.unpack_from('<4f', data, off)) for name, off in fields.items()}

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
    # field offsets from the STA::DlTmModel::get* getters (IDE 1.9.10.03)
    fields = {
        'di_clksetpos': 0x0,
        'di_clksetneg': 0x10,
        'di_clkholdpos': 0x20,
        'di_clkholdneg': 0x30,
        'ce_clksetpos': 0x40,
        'ce_clksetneg': 0x50,
        'ce_clkholdpos': 0x60,
        'ce_clkholdneg': 0x70,
        'clk_qpos': 0x80,
        'clk_qneg': 0x90,
        'lsr_q': 0xa0,
        'lsr_clksetpos_asyn': 0xb0,
        'lsr_clksetneg_asyn': 0xc0,
        'lsr_clkholdpos_asyn': 0xd0,
        'lsr_clkholdneg_asyn': 0xe0,
        'clk_clk': 0xf0,
        'lsr_lsr': 0x100,
    }
    return offset_data(data, fields)

def parse_iddroddr(data):
    # field offsets from the STA::IddrOddrTmModel::get* getters (IDE 1.9.10.03); 0x0-0x2c not read by any getter
    fields = {
        'iclkmpwp': 0x2c,
        'iclkmpwn': 0x3c,
        'oclkmpwp': 0x4c,
        'oclkmpwn': 0x5c,
        'clk_ces_p': 0x6c,
        'clk_ceh_p': 0x7c,
        'clk_ces_n': 0x8c,
        'clk_ceh_n': 0x9c,
        'iclk_dis_p': 0xac,
        'iclk_dih_p': 0xbc,
        'iclk_dis_n': 0xcc,
        'iclk_dih_n': 0xdc,
        'iclk_srs_s_p': 0xec,
        'iclk_srh_s_p': 0xfc,
        'iclk_srs_s_n': 0x10c,
        'iclk_srh_s_n': 0x11c,
        'iclk_srs_a_p': 0x12c,
        'iclk_srh_a_p': 0x13c,
        'iclk_srs_a_n': 0x14c,
        'iclk_srh_a_n': 0x15c,
        'iclk_q0': 0x16c,
        'iclk_q1': 0x17c,
        'isr_q0': 0x18c,
        'isr_q1': 0x19c,
        'clk_oposs': 0x1ac,
        'clk_oposh': 0x1bc,
        'clk_onegs': 0x1cc,
        'clk_onegh': 0x1dc,
        'oclk_srs_p_s': 0x1ec,
        'oclk_srs_n_s': 0x1fc,
        'oclk_srh_p_s': 0x20c,
        'oclk_srh_n_s': 0x21c,
        'oclk_srs_p_a': 0x22c,
        'oclk_srs_n_a': 0x23c,
        'oclk_srh_p_a': 0x24c,
        'oclk_srh_n_a': 0x25c,
        'oclk_q_p': 0x26c,
        'oclk_q_n': 0x27c,
        'osr_q_p': 0x28c,
        'osr_q_n': 0x29c,
        'tclk_tss': 0x2ac,
        'tclk_tsh': 0x2bc,
        'tclk_srs_s': 0x2cc,
        'tclk_srh_s': 0x2dc,
        'tclk_srs_a': 0x2ec,
        'tclk_srh_a': 0x2fc,
        'tclk_q': 0x30c,
        'tsr_q': 0x31c,
    }
    return offset_data(data, fields)

def parse_pll(data):
    # field offsets from the STA::PLLTmModel::get* getters (IDE 1.9.10.03)
    fields = {
        'clkin_clkout': 0x0,
        'clkin_lock': 0x10,
        'clkin_clkoutp': 0x20,
        'clkin_clkoutd': 0x30,
        'clkin_clkoutd3': 0x40,
    }
    return offset_data(data, fields)

def parse_dll(data):
    # field offsets from the STA::DLLTmModel::get* getters (IDE 1.9.10.03)
    fields = {
        'clkin_step': 0x0,
        'clkin_lock': 0x10,
        'hclkin_lock': 0x20,
        'hclkin_step': 0x30,
    }
    return offset_data(data, fields)

def parse_clkdiv(data):
    # field offsets from the STA::ClkdivTmModel::get* getters (IDE 1.9.10.03)
    fields = {
        'hclkin_sel35_set': 0x0,
        'hclkin_sel35_hold': 0x10,
        'hclkin_resetn_rec': 0x20,
        'hclkin_resetn_rem': 0x30,
        'hclkin_clkout': 0x40,
        'resetn_clkout': 0x50,
    }
    return offset_data(data, fields)

def parse_bram(data):
    paths = [
        'clka_doa', # 0
        'clkb_dob', # 4
        'clkb_do', # 8
        'clk_do', # 0xc
        'clka_doa_bypass', # 0x10
        'clkb_dob_bypass', # 0x14
        'clkb_do_bypass', # 0x18
        'clk_do_bypass', # 0x1c
        'clka_reseta_set', # 0x20
        'clka_ocea_set', # 0x24
        'clka_cea_set', # 0x28
        'clka_wrea_set', # 0x2c
        'clka_dia_set', # 0x30
        'clka_di_set', # 0x34
        'clka_ada_set', # 0x38
        'clka_blksel_set', # 0x3c
        'clka_reseta_hold', # 0x40
        'clka_ocea_hold', # 0x44
        'clka_cea_hold', # 0x48
        'clka_wrea_hold', # 0x4c
        'clka_dia_hold', # 0x50
        'clka_di_hold', # 0x54
        'clka_ada_hold', # 0x58
        'clka_blksel_hold', # 0x50
        'clkb_resetb_set', # 0x60
        'clkb_oceb_set', # 0x64
        'clkb_ceb_set', # 0x68
        'clkb_oce_set', # 0x6c
        'clkb_wreb_set', # 0x70
        'clkb_dib_set', # 0x74
        'clkb_adb_set', # 0x78
        'clkb_blksel_set', # 0x7c
        'clkb_resetb_hold', # 0x80
        'clkb_oceb_hold', # 0x84
        'clkb_ceb_hold', # 0x88
        'clkb_oce_hold', # 0x8c
        'clkb_wreb_hold', # 0x90
        'clkb_dib_hold', # 0x94
        'clkb_adb_hold', # 0x98
        'clkb_blksel_hold', # 0x9c
        'clk_ce_set', # 0xa0
        'clk_oce_set', # 0xa4
        'clk_reset_set', # 0xa8
        'clk_wre_set', # 0xac
        'clk_ad_set', # 0xb0
        'clk_di_set', # 0xb4
        'clk_blksel_set', # 0xb8
        'clk_ce_hold', # 0xbc
        'clk_oce_hold', # 0xc0
        'clk_reset_hold', # 0xc4
        'clk_wre_hold', # 0xc8
        'clk_ad_hold', #0xcc
        'clk_di_hold', # 0xd0
        'clk_blksel_hold', # 0xd4
        'clk_reset_set_syn', # 0xd8
        'clk_reset_hold_syn', # 0xdc
        'clka_reseta_set_syn', # 0xe0
        'clka_reseta_hold_syn', # 0xe4
        'clkb_resetb_set_syn', # 0xe8
        'clkb_resetb_hold_syn', # 0xec
        'clk_clk', # 0xf0
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
    # field offsets from the STA::IregOregTmModel::get* getters (IDE 1.9.10.03); 0x0-0x2c not read by any getter
    fields = {
        'iclkmpwp': 0x2c,
        'iclkmpwn': 0x3c,
        'oclkmpwp': 0x4c,
        'oclkmpwn': 0x5c,
        'clk_ces': 0x6c,
        'clk_ceh': 0x7c,
        'iclk_srs_s': 0x8c,
        'iclk_srh_s': 0x9c,
        'iclk_srs_a': 0xac,
        'iclk_srh_a': 0xbc,
        'iclk_dis': 0xcc,
        'iclk_dih': 0xdc,
        'iclk_q': 0xec,
        'isr_q': 0xfc,
        'clk_oposs': 0x10c,
        'clk_oposh': 0x11c,
        'oclk_srs_s': 0x12c,
        'oclk_srh_s': 0x13c,
        'oclk_srs_a': 0x14c,
        'oclk_srh_a': 0x15c,
        'oclk_q': 0x16c,
        'osr_q': 0x17c,
        'tclk_tss': 0x18c,
        'tclk_tsh': 0x19c,
        'tclk_srs_s': 0x1ac,
        'tclk_srh_s': 0x1bc,
        'tclk_srs_a': 0x1cc,
        'tclk_srh_a': 0x1dc,
        'tclk_q': 0x1ec,
        'tsr_q': 0x1fc,
    }
    return offset_data(data, fields)

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
    0x85c: parse_clkdiv,
    0x8bc: parse_bram,
    0xc8c: parse_dsp,
    0x381c: parse_fanout,
    0x38bc: parse_glbsrc,
    0x39cc: parse_hclk,
    0x3728: parse_iodelay,
    0x3278: parse_io,
    0x306c: parse_iregoreg,
    0x379c: parse_wire,
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
        if off < len(chunk):
            yield parser.__name__[6:], parser(chunk[off:])

# GW5A devices: the IDE reads delays from a self-describing block that follows
# three old-format records (STA::TmModelNew::readTmData, IDE 1.9.10.03). The
# old-format records in these files are placeholders copied from GW2A-18C. See
# doc/agent/timing.md.
#
#   char hdr[15]; i32 magic = 0x37
#   u16 n_class_enum; u16 n_models; u16 values_per_group; i32 max_fanout
#   i16 class_enum2idx[n_class_enum]
#   per model:  u16 n_var_enum; u16 n_vars; i16 var_enum2idx[n_var_enum]
#               n_vars * (i16 len; f32 values[len])
#               the FANOUT model (class 6) is followed by
#               u16 n; u16 k; i16 idx[n]; k * u16[max_fanout + 1]
#   i32 magic = 0x37
NEW_CLASSES = ['LUT', 'ALU', 'DFF', 'DL', 'SSRAM', 'XWIRE', 'FANOUT', 'GLBSRC', 'HCLK', 'IBUF', 'OBUF4mA',
               'OBUF8mA', 'BSRAM']

def parse_new_block(data, offset=3 * chunklen):
    """Return {class name: {var enum: [floats]}} and the number of values per group."""
    pos = offset + 15
    def take(fmt):
        nonlocal pos
        v = struct.unpack_from('<' + fmt, data, pos)
        pos += struct.calcsize('<' + fmt)
        return v if len(v) > 1 else v[0]
    if take('i') != 0x37:
        raise ValueError('bad TmModelNew header')
    n_enum, n_models, per_group, max_fan = take('H'), take('H'), take('H'), take('i')
    enum2idx = [take('h') for _ in range(n_enum)]
    models = []
    for m in range(n_models):
        n_var_enum, n_vars = take('H'), take('H')
        var2idx = [take('h') for _ in range(n_var_enum)]
        values = []
        for _ in range(n_vars):
            length = take('h')
            values.append(list(struct.unpack_from(f'<{length}f', data, pos)))
            pos += 4 * length
        if m == enum2idx[6]:
            n, k = take('H'), take('H')
            pos += 2 * n + 2 * k * (max_fan + 1)
        models.append((var2idx, values))
    if take('i') != 0x37:
        raise ValueError('bad TmModelNew trailer')
    res = {}
    for cls, mi in enumerate(enum2idx):
        if 0 <= mi < len(models) and cls < len(NEW_CLASSES):
            var2idx, values = models[mi]
            res[NEW_CLASSES[cls]] = {en: values[vi] for en, vi in enumerate(var2idx) if 0 <= vi < len(values)}
    return res, per_group

# New-model variable (class, enum) for each key of the old-style groups that
# nextpnr reads. Enum names are from STA::TmModelBase::get*VarName.
_new_vars = {
    'lut': {'a_f': ('LUT', 0),        # A_F
            'b_f': ('LUT', 2),        # B_F
            'c_f': ('LUT', 4),        # C_F
            'd_f': ('LUT', 6),        # D_F
            'a_ofx': ('LUT', 8),      # A_OFX0
            'b_ofx': ('LUT', 9),      # B_OFX0
            'c_ofx': ('LUT', 10),     # C_OFX0
            'd_ofx': ('LUT', 11),     # D_OFX0
            'm0_ofx0': ('LUT', 12),   # M0_OFX0
            'm1_ofx1': ('LUT', 13),   # M1_OFX1
            'fx_ofx1': ('LUT', 14)},  # FXA_FX1
    'alu': {'a_f': ('ALU', 0),        # A_F
            'b_f': ('ALU', 2),        # B_F
            'd_f': ('ALU', 3),        # D_F
            'a0_fco': ('ALU', 4),     # A0_FCO0
            'b0_fco': ('ALU', 6),     # B0_FCO0
            'd0_fco': ('ALU', 8),     # D0_FCO0
            'fci_fco': ('ALU', 11),   # FCI_FCO
            'fci_f0': ('ALU', 13)},   # FCI0_F0
    # D comes from the LUT F of the same slot, so the DI_FS arcs apply
    # (STA::TmModelNew::getDffPinToPinDly).
    'dff': {'di_clksetpos': ('DFF', 4), 'di_clksetneg': ('DFF', 5),
            'di_clkholdpos': ('DFF', 6), 'di_clkholdneg': ('DFF', 7),
            'ce_clksetpos': ('DFF', 12), 'ce_clksteneg': ('DFF', 13),
            'ce_clkholdpos': ('DFF', 14), 'ce_clkholdneg': ('DFF', 15),
            'lsr_clksetpos_syn': ('DFF', 16), 'lsr_clksetneg_syn': ('DFF', 17),
            'lsr_clkholdpos_syn': ('DFF', 18), 'lsr_clkholdneg_syn': ('DFF', 19),
            'clk_qpos': ('DFF', 24), 'clk_qneg': ('DFF', 25), 'lsr_q': ('DFF', 26),
            'lsr_clksetpos_asyn': ('DFF', 27), 'lsr_clksetneg_asyn': ('DFF', 28),
            'lsr_clkholdpos_asyn': ('DFF', 29), 'lsr_clkholdneg_asyn': ('DFF', 30),
            'clk_clk': ('DFF', 32), 'lsr_lsr': ('DFF', 33)},
    # DL variables (STA::TmModelBase::getDlVarName): DI_M 0-3, DI_FS 4-7, DI_OFX 8-11,
    # CE 12-15, LSR_SYN 16-19, CLK_QPos 20, CLK_QNeg 21, D_*_to_Q 22-24, LSR_Q 25,
    # LSR_ASYN 26-29. D is taken from DI_FS, as for DFF.
    'dl': {'di_clksetpos': ('DL', 4), 'di_clksetneg': ('DL', 5),
           'di_clkholdpos': ('DL', 6), 'di_clkholdneg': ('DL', 7),
           'ce_clksetpos': ('DL', 12), 'ce_clksetneg': ('DL', 13),
           'ce_clkholdpos': ('DL', 14), 'ce_clkholdneg': ('DL', 15),
           'clk_qpos': ('DL', 20), 'clk_qneg': ('DL', 21), 'lsr_q': ('DL', 25),
           'lsr_clksetpos_asyn': ('DL', 26), 'lsr_clksetneg_asyn': ('DL', 27),
           'lsr_clkholdpos_asyn': ('DL', 28), 'lsr_clkholdneg_asyn': ('DL', 29)},
    'sram': {'rad0_do': ('SSRAM', 0), 'rad1_do': ('SSRAM', 1), 'rad2_do': ('SSRAM', 2), 'rad3_do': ('SSRAM', 3),
             'clk_di_set': ('SSRAM', 4), 'clk_di_hold': ('SSRAM', 6),
             'clk_wre_set': ('SSRAM', 8), 'clk_wre_hold': ('SSRAM', 10),
             'clk_wad0_set': ('SSRAM', 12), 'clk_wad0_hold': ('SSRAM', 14),
             'clk_wad1_set': ('SSRAM', 16), 'clk_wad1_hold': ('SSRAM', 18),
             'clk_wad2_set': ('SSRAM', 20), 'clk_wad2_hold': ('SSRAM', 22),
             'clk_wad3_set': ('SSRAM', 24), 'clk_wad3_hold': ('SSRAM', 26),
             'clk_do': ('SSRAM', 28)},
    'bram': {'clka_doa': ('BSRAM', 0), 'clka_doa_bypass': ('BSRAM', 1),
             'clkb_dob': ('BSRAM', 4), 'clkb_dob_bypass': ('BSRAM', 5),
             'clkb_do': ('BSRAM', 8), 'clkb_do_bypass': ('BSRAM', 9),
             'clk_do': ('BSRAM', 0), 'clk_do_bypass': ('BSRAM', 1),
             'clka_reseta_set': ('BSRAM', 14), 'clka_ocea_set': ('BSRAM', 16), 'clka_cea_set': ('BSRAM', 17),
             'clka_wrea_set': ('BSRAM', 18), 'clka_dia_set': ('BSRAM', 19), 'clka_di_set': ('BSRAM', 19),
             'clka_ada_set': ('BSRAM', 21), 'clka_blksel_set': ('BSRAM', 22),
             'clka_reseta_hold': ('BSRAM', 23), 'clka_ocea_hold': ('BSRAM', 25), 'clka_cea_hold': ('BSRAM', 26),
             'clka_wrea_hold': ('BSRAM', 27), 'clka_dia_hold': ('BSRAM', 28), 'clka_di_hold': ('BSRAM', 28),
             'clka_ada_hold': ('BSRAM', 30), 'clka_blksel_hold': ('BSRAM', 31),
             'clkb_resetb_set': ('BSRAM', 32), 'clkb_oceb_set': ('BSRAM', 33), 'clkb_ceb_set': ('BSRAM', 34),
             'clkb_oce_set': ('BSRAM', 35), 'clkb_wreb_set': ('BSRAM', 36), 'clkb_dib_set': ('BSRAM', 37),
             'clkb_adb_set': ('BSRAM', 38), 'clkb_blksel_set': ('BSRAM', 39),
             'clkb_resetb_hold': ('BSRAM', 40), 'clkb_oceb_hold': ('BSRAM', 41), 'clkb_ceb_hold': ('BSRAM', 42),
             'clkb_oce_hold': ('BSRAM', 43), 'clkb_wreb_hold': ('BSRAM', 44), 'clkb_dib_hold': ('BSRAM', 45),
             'clkb_adb_hold': ('BSRAM', 46), 'clkb_blksel_hold': ('BSRAM', 47),
             'clk_ce_set': ('BSRAM', 17), 'clk_oce_set': ('BSRAM', 16), 'clk_reset_set': ('BSRAM', 14),
             'clk_wre_set': ('BSRAM', 18), 'clk_ad_set': ('BSRAM', 21), 'clk_di_set': ('BSRAM', 19),
             'clk_blksel_set': ('BSRAM', 22),
             'clk_ce_hold': ('BSRAM', 26), 'clk_oce_hold': ('BSRAM', 25), 'clk_reset_hold': ('BSRAM', 23),
             'clk_wre_hold': ('BSRAM', 27), 'clk_ad_hold': ('BSRAM', 30), 'clk_di_hold': ('BSRAM', 28),
             'clk_blksel_hold': ('BSRAM', 31),
             'clk_reset_set_syn': ('BSRAM', 15), 'clk_reset_hold_syn': ('BSRAM', 24),
             'clka_reseta_set_syn': ('BSRAM', 15), 'clka_reseta_hold_syn': ('BSRAM', 24),
             'clkb_resetb_set_syn': ('BSRAM', 48), 'clkb_resetb_hold_syn': ('BSRAM', 49)},
}
# Routing is not taken from the new block yet. The IDE charges different
# delays for wires that cross BSRAM/DSP columns or the spine (X*_VBUF_*,
# X*_HBUF_*, X*_HOS_*, *_LOAD_DERATE), selected per wire by a flag of its
# routing graph. With the plain X0/X1/X2/X8 values alone nextpnr's routing
# delays on IDE-routed GW5A-25A designs come out 17% low, against 2% low with
# the placeholder values, so the 'wire' and 'fanout' groups keep those.

# Speed grade -> (old-format placeholder record, slow-corner multiplier).
# STA::TmAnalyzer::getTmModelDelayMultByDevice returns 1.25 for GW5A and it is
# applied when the record index is 0 (C1/I0, A0); C2/I1 uses index 2 and 1.0.
# ES is treated like C1/I0.
_gw5a_speeds = {'C1/I0': (0, 1.25), 'A0': (0, 1.25), 'ES': (0, 1.25), 'C2/I1': (1, 1.0)}
# The IDE uses core type 1 by default (STA::TmModelNew::setCoreType)
_gw5a_core_type = 1

_gw5a_no_placeholder = {'dl', 'iddroddr', 'pll', 'dll', 'clkdiv', 'iregoreg'}

def read_tm_gw5a(data):
    new, per_group = parse_new_block(data)
    tmdat = {}
    for speed, (rec, mult) in _gw5a_speeds.items():
        # groups without a new-model counterpart keep the placeholder values, except
        # those parsed after the placeholder was introduced, which would be GW2A data
        groups = {name: tm for name, tm in parse_chunk(data[rec * chunklen:(rec + 1) * chunklen])
                  if tm and name not in _gw5a_no_placeholder}
        for group, keys in _new_vars.items():
            for key, (cls, var) in keys.items():
                vals = new.get(cls, {}).get(var)
                if vals is None:
                    continue
                quad = vals[_gw5a_core_type * per_group:(_gw5a_core_type + 1) * per_group]
                groups.setdefault(group, {})[key] = [v * mult for v in quad]
        tmdat[speed] = groups
    return tmdat

def read_tm(f, device):
    if device.lower().startswith("gw5a"):
        return read_tm_gw5a(f.read())
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
            "8",
            "9",
            "10",
            "11",
            "C7/I6",
            "C7/I6_LV"
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
    #a = enumerate(iter(lambda: f.read(chunklen), b''))
    for i, chunk in enumerate(iter(lambda: f.read(chunklen), b'')):
        try:
            speed_class = chunk_order[i]
        except IndexError:
            speed_class = str(i)
        if len(chunk) != chunklen:
            continue
        tmdat[speed_class] = {}
        #print(f'{i:2} class:{speed_class}' , "len(chunk):", len(chunk), "chunklen:", chunklen)
        #assert len(chunk) == chunklen # 5A the last chunk is smaller 12922 vs. 15552
        res = parse_chunk(chunk)
        for name, tm in res:
            if tm:
                tmdat[speed_class][name] = tm
    return tmdat


if __name__ == "__main__":
    gowinhome = os.getenv("GOWINHOME")
    if not gowinhome:
        raise Exception("GOWINHOME not set")
    device = sys.argv[1]

    with open(f"{gowinhome}/IDE/share/device/{device}/{device}.tm", 'rb') as f:
        read_tm(f, device)
