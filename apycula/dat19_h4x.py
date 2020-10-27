import os
import sys
import json

gowinhome = os.getenv("GOWINHOME")
if not gowinhome:
    raise Exception("GOWINHOME not set")

device = sys.argv[1]

with open(f"{gowinhome}/IDE/share/device/{device}/{device}.dat", 'rb') as f:
    d = f.read()

data = {}

def insap(path, val):
    ref = data
    for seg in path[:-1]:
        ref = ref.setdefault(seg, {})

    if path[-1] in ref:
        try:
            ref[path[-1]].append(val)
        except:
            ref[path[-1]] = [ref[path[-1]], val]
    else:
        ref[path[-1]] = val

def print_u8(name, pos):
    v = d[pos]
    insap(name, v)
    print(f'{name} [0x{pos:06x}]: {v} [0x{v:02x}]')
    return pos + 1

def print_u16(name, pos):
    v = int.from_bytes(d[pos:pos+2], 'little')
    insap(name, v)
    print(f'{name} [0x{pos:06x}]: {v} [0x{v:04x}]')
    return pos + 2

def print_u64(name, pos):
    v = int.from_bytes(d[pos:pos+8], 'little')
    insap(name, v)
    print(f'{name} [0x{pos:06x}]: {v} [0x{v:016x}]')
    return pos + 8


pos = 0x026060
z = [
    int.from_bytes(d[pos + i * 2 : pos + i * 2 + 2], 'little')
    for i in range(4)
]
grid_h, grid_w, cc_y, cc_x = z
data['rows'] = grid_h
data['cols'] = grid_w
data['center'] = (cc_y, cc_x)
print(grid_h, grid_w)
print(cc_y, cc_x)

for i in [2, 1, 0]:
    print('    ', end='')
    for x in range(grid_w):
        n = x // 10**i % 10
        print(n, end='')
    print()

print()

data['grid'] = []
for y in range(150):
    if y in range(grid_h):
        print(f'{y:3} ', end='')
        row = []
        data['grid'].append(row)
    for x in range(200):
        idx = y * 200 + x
        pos = 5744 + 4 * idx
        a = int.from_bytes(d[pos:pos+4], 'little')
        pos = 125744
        b = d[pos+idx]
        c = {
            (0, 0): ' ', # empty
            (1, 1): 'I', # I/O
            (2, 1): 'L', # LVDS (GW2A* only)
            (3, 1): 'R', # routing?
            (4, 0): 'c', # CFU, disabled
            (4, 1): 'C', # CFU
            (5, 1): 'M', # CFU with RAM option
            (6, 0): 'b', # blockram padding
            (6, 1): 'B', # blockram
            (7, 0): 'd', # dsp padding
            (7, 1): 'D', # dsp
            (8, 0): 'p', # pll padding
            (8, 1): 'P', # pll
            (9, 1): 'Q', # dll
        }[a, b]
        if y in range(grid_h) and x in range(grid_w):
            row.append(c)
            if x == cc_x and y == cc_y:
                assert c == 'b'
                print('#', end='')
            else:
                print(f'{c}', end='')
        else:
            assert c == ' '
    if y in range(grid_h):
        print()

print()

def print_arr8(name, pos, num, used):
    arr = list(d[pos:pos+num])
    print(name, hex(pos), arr[:used])
    insap(name, tuple(arr[:used]))
    for i in range(used, num):
        assert arr[i] == 0
    return pos + num

def print_arr16(name, pos, num, used=None):
    if used is None:
        used = num
    arr = [int.from_bytes(d[pos+i*2:pos+i*2+2], 'little', signed=True) for i in range(num)]
    print(name, hex(pos), arr[:used])
    insap(name, tuple(arr[:used]))
    for i in range(used, num):
        assert arr[i] == -1
    return pos + num * 2

def print_arr32(name, pos, num, used=None):
    if used is None:
        used = num
    arr = [int.from_bytes(d[pos+i*4:pos+i*4+4], 'little', signed=True) for i in range(num)]
    print(name, hex(pos), arr[:used])
    insap(name, tuple(arr[:used]))
    for i in range(used, num):
        assert arr[i] == 0
    return pos + num * 4

print()
pos = 0xc8
pos = print_u8(['NumLuts'], pos)
pos = print_u8(['NumLutIns'], pos)
for i in range(32):
    pos = print_arr16(['LutIns'], pos, 0x1c)
pos = print_arr16(['Luts'], pos, 32)

print()
pos = print_u8(['NumX0s'], pos)
pos = print_u8(['NumX0Ins'], pos)
for i in range(8):
    pos = print_arr16(['X0Ins'], pos, 0x1c)
pos = print_arr16(['X0s'], pos, 8)

print()
pos = print_u8(['NumX1s'], pos)
pos = print_u8(['NumX1Ins'], pos)
for i in range(12):
    pos = print_arr16(['X1Ins'], pos, 0x14)
pos = print_arr16(['X1s'], pos, 12)

print()
pos = print_u8(['NumX2s'], pos)
pos = print_u8(['NumX2Ins'], pos)
for i in range(32):
    pos = print_arr16(['X2Ins'], pos, 0x15)
pos = print_arr16(['X2s'], pos, 32)

print()
pos = print_u8(['NumX8s'], pos)
pos = print_u8(['NumX8Ins'], pos)
for i in range(16):
    pos = print_arr16(['X8Ins'], pos, 0x14)
pos = print_arr16(['X8s'], pos, 16)

print()
pos = print_u8(['NumClks'], pos)
pos = print_u8(['NumClkIns'], pos)
for i in range(3):
    pos = print_arr16(['ClkIns'], pos, 0x1c)
pos = print_arr16(['Clks'], pos, 3)

print()
pos = print_u8(['NumLsrs'], pos)
pos = print_u8(['NumLsrIns'], pos)
for i in range(3):
    pos = print_arr16(['LsrIns'], pos, 0x14)
pos = print_arr16(['Lsrs'], pos, 3)

print()
pos = print_u8(['NumCe'], pos)
pos = print_u8(['NumCeIns'], pos)
for i in range(3):
    pos = print_arr16(['CeIns'], pos, 0x14)
pos = print_arr16(['Ces'], pos, 3)

print()
pos = print_u8(['NumSels'], pos)
pos = print_u8(['NumSelIns'], pos)
for i in range(8):
    pos = print_arr16(['SelIns'], pos, 9)
pos = print_arr16(['Sels'], pos, 8)

print()
pos = print_u8(['NumX11s'], pos)
pos = print_u8(['NumX11Ins'], pos)
for i in range(8):
    pos = print_arr16(['X11Ins'], pos, 1)
pos = print_arr16(['X11s'], pos, 8)

assert pos == 0x166e

pos = 0x026068
print()
pos = print_arr16(['Dqs', 'TA'], pos, 200, grid_w)
pos = print_arr16(['Dqs', 'BA'], pos, 200, grid_w)
pos = print_arr16(['Dqs', 'LA'], pos, 150, grid_h)
pos = print_arr16(['Dqs', 'RA'], pos, 150, grid_h)
pos = print_arr16(['Dqs', 'TB'], pos, 200, grid_w)
pos = print_arr16(['Dqs', 'BB'], pos, 200, grid_w)
pos = print_arr16(['Dqs', 'LB'], pos, 150, grid_h)
pos = print_arr16(['Dqs', 'RB'], pos, 150, grid_h)

print()
pos = print_arr32(['Cfg', 'TA'], pos, 200, grid_w)
pos = print_arr32(['Cfg', 'BA'], pos, 200, grid_w)
pos = print_arr32(['Cfg', 'LA'], pos, 150, grid_h)
pos = print_arr32(['Cfg', 'RA'], pos, 150, grid_h)
pos = print_arr32(['Cfg', 'TB'], pos, 200, grid_w)
pos = print_arr32(['Cfg', 'BB'], pos, 200, grid_w)
pos = print_arr32(['Cfg', 'LB'], pos, 150, grid_h)
pos = print_arr32(['Cfg', 'RB'], pos, 150, grid_h)
pos = print_arr32(['SpecCfg', 'IOL'], pos, 10, 10)
pos = print_arr32(['SpecCfg', 'IOR'], pos, 10, 10)

print()
pos = print_arr16(['Bank', 'TA'], pos, 200, grid_w)
pos = print_arr16(['Bank', 'BA'], pos, 200, grid_w)
pos = print_arr16(['Bank', 'LA'], pos, 150, grid_w)
pos = print_arr16(['Bank', 'RA'], pos, 150, grid_w)
pos = print_arr16(['Bank', 'TA'], pos, 200, grid_w)
pos = print_arr16(['Bank', 'BA'], pos, 200, grid_w)
pos = print_arr16(['Bank', 'LA'], pos, 150, grid_w)
pos = print_arr16(['Bank', 'RA'], pos, 150, grid_w)
pos = print_arr16(['Bank', 'SpecIOL'], pos, 10, 10)
pos = print_arr16(['Bank', 'SpecIOR'], pos, 10, 10)

print()
pos = print_arr16(['X16', 'TA'], pos, 200, grid_w)
pos = print_arr16(['X16', 'BA'], pos, 200, grid_w)
pos = print_arr16(['X16', 'LA'], pos, 150, grid_w)
pos = print_arr16(['X16', 'RA'], pos, 150, grid_w)
pos = print_arr16(['X16', 'TA'], pos, 200, grid_w)
pos = print_arr16(['X16', 'BA'], pos, 200, grid_w)
pos = print_arr16(['X16', 'LA'], pos, 150, grid_w)
pos = print_arr16(['X16', 'RA'], pos, 150, grid_w)
pos = print_arr16(['X16', 'SpecIOL'], pos, 10, 10)
pos = print_arr16(['X16', 'SpecIOR'], pos, 10, 10)


print()
pos = print_arr8(['TrueLvds', 'TopA'], pos, 200, grid_w)
pos = print_arr8(['TrueLvds', 'BottomA'], pos, 200, grid_w)
pos = print_arr8(['TrueLvds', 'LeftA'], pos, 150, grid_h)
pos = print_arr8(['TrueLvds', 'RightA'], pos, 150, grid_h)
pos = print_arr8(['TrueLvds', 'TopB'], pos, 200, grid_w)
pos = print_arr8(['TrueLvds', 'BottomB'], pos, 200, grid_w)
pos = print_arr8(['TrueLvds', 'LeftB'], pos, 150, grid_h)
pos = print_arr8(['TrueLvds', 'RightB'], pos, 150, grid_h)
pos = print_arr8(['TrueLvds', 'SpecIOL'], pos, 10, 10)
pos = print_arr8(['TrueLvds', 'SpecIOR'], pos, 10, 10)

print()
pos = print_arr32(['Type', 'TopA'], pos, 200, grid_w)
pos = print_arr32(['Type', 'BottomA'], pos, 200, grid_w)
pos = print_arr32(['Type', 'LeftA'], pos, 150, grid_h)
pos = print_arr32(['Type', 'RightA'], pos, 150, grid_h)
pos = print_arr32(['Type', 'TopB'], pos, 200, grid_w)
pos = print_arr32(['Type', 'BottomB'], pos, 200, grid_w)
pos = print_arr32(['Type', 'LeftB'], pos, 150, grid_h)
pos = print_arr32(['Type', 'RightB'], pos, 150, grid_h)

print(hex(pos))

print()
pos = 0x2dee4
for i in range(10):
    pos = print_arr8(['SpecIOL', i], pos, 10, 10)
print()
for i in range(10):
    pos = print_arr8(['SpecIOR', i], pos, 10, 10)
print(hex(pos))

print()

#print(d[pos:][:0x200].hex())

def print_outs(name, pos, num):
    print(f'{name} 0x{pos:06x} [{num}]')
    for i in range(num):
        a = int.from_bytes(d[pos:pos+2], 'little', signed=True)
        b = int.from_bytes(d[pos+2:pos+4], 'little', signed=True)
        c = int.from_bytes(d[pos+4:pos+6], 'little', signed=True)
        insap(name, (a, b, c))
        if a != -1 or b != -1 or c != -1:
            print(f'\t{i:2}: {a}, {b}, {c}')
        pos += 6
    return pos

def print_mult(name, pos, num):
    print(f'{name} 0x{pos:06x} [{num}]')
    for i in range(num):
        a = int.from_bytes(d[pos:pos+2], 'little', signed=True)
        b = int.from_bytes(d[pos+2:pos+4], 'little', signed=True)
        c = int.from_bytes(d[pos+4:pos+6], 'little', signed=True)
        e = int.from_bytes(d[pos+6:pos+8], 'little', signed=True)
        insap(name, (a, b, c, e))
        if a != -1 or b != -1 or c != -1 or e != -1:
            print(f'\t{i:2}: {a}, {b}, {c}, {e}')
        pos += 8
    return pos

def print_clkins(name, pos, num):
    print(f'{name} 0x{pos:06x} [{num}]')
    for i in range(num):
        a = int.from_bytes(d[pos:pos+2], 'little', signed=True)
        b = int.from_bytes(d[pos+2:pos+4], 'little', signed=True)
        insap(name, (a, b))
        if a != -1 or b != -1:
            print(f'\t{i:2}: {a}, {b}')
        pos += 4
    return pos

pos = 0x44194

print('FS GRID')
for _ in range(grid_h-2):
    cur = d[pos:pos+200]
    assert not any(cur[grid_w-2:])
    pos += 200
    print(cur[:grid_w-2].decode())
for _ in range(grid_h-2, 150):
    cur = d[pos:pos+200]
    assert not any(cur)
    pos += 200
print()

assert pos == 0x4b6c4
pos = print_u16(['IobufAIn'], pos)
pos = print_u16(['IobufAOut'], pos)
pos = print_u16(['IobufAOE'], pos)
pos = print_u16(['IObufAIO'], pos)
pos = print_u16(['IobufBIn'], pos)
pos = print_u16(['IobufBOut'], pos)
pos = print_u16(['IobufBOE'], pos)
pos = print_u16(['IObufBIO'], pos)
pos = print_arr16(['IobufIns'], pos, 10)
pos = print_arr16(['IobufOuts'], pos, 10)
pos = print_arr16(['IobufOes'], pos, 10)
pos = print_arr16(['IologicAIn'], pos, 0x2b)
pos = print_arr16(['IologicAOut'], pos, 0x15)
pos = print_arr16(['IologicBIn'], pos, 0x2b)
pos = print_arr16(['IologicBOut'], pos, 0x15)
pos = print_arr16(['BsramIn'], pos, 0x84)
pos = print_arr16(['BsramOut'], pos, 0x48)
pos = print_arr16(['BsramInDlt'], pos, 0x84)
pos = print_arr16(['BsramOutDlt'], pos, 0x48)
pos = print_arr16(['SsramIO'], pos, 0x1c)
pos = print_arr16(['PllIn'], pos, 0x24)
pos = print_arr16(['PllOut'], pos, 0x5)
pos = print_arr16(['PllInDlt'], pos, 0x24)
pos = print_arr16(['PllOutDlt'], pos, 0x5)
pos = print_clkins(['PllClkin'], pos, 6)
pos = print_arr16(['DllIn'], pos, 4)
pos = print_arr16(['DllOut'], pos, 9)
pos = print_mult(['MultIn'], pos, 0x4f)
pos = print_mult(['MultOut'], pos, 0x48)
pos = print_mult(['MultInDlt'], pos, 0x4f)
pos = print_mult(['MultOutDlt'], pos, 0x48)
pos = print_mult(['PaddIn'], pos, 0x4c)
pos = print_mult(['PaddOut'], pos, 0x36)
pos = print_mult(['PaddInDlt'], pos, 0x4c)
pos = print_mult(['PaddOutDlt'], pos, 0x36)
pos = print_clkins(['AluIn'], pos, 0xa9)
pos = print_clkins(['AluOut'], pos, 0x6d)
pos = print_clkins(['AluInDlt'], pos, 0xa9)
pos = print_clkins(['AluOutDlt'], pos, 0x6d)
pos = print_clkins(['MdicIn'], pos, 0x36)
pos = print_clkins(['MdicInDlt'], pos, 0x36)
pos = print_mult(['CtrlIn'], pos, 0xe)
pos = print_mult(['CtrlInDlt'], pos, 0xe)
print()
#print(hex(pos))
print(d[pos:320314].hex())
pos = 320314
#print(hex(pos))
for i in range(320):
    pos = print_arr16(['CiuConnection', i], pos, 60)
pos = print_arr16(['CiuFanoutNum'], pos, 320)
for i in range(320):
    pos = print_arr16(['CiuBdConnection', i], pos, 60)
pos = print_arr16(['CiuBdFanoutNum'], pos, 320)
for i in range(320):
    pos = print_arr16(['CiuCornerConnection', i], pos, 60)
pos = print_arr16(['CiuCornerFanoutNum'], pos, 320)
for i in range(106):
    pos = print_arr16(['CmuxInNodes', i], pos, 73)
for i in range(106):
    pos = print_arr16(['CmuxIns', i], pos, 3)
print()
pos = print_arr16(['DqsRLoc'], pos, 0x16)
pos = print_arr16(['DqsCLoc'], pos, 0x16)
pos = print_arr16(['JtagIns'], pos, 5)
pos = print_arr16(['JtagOuts'], pos, 11)
pos = print_arr16(['ClksrcIns'], pos, 0x26)
pos = print_arr16(['ClksrcOuts'], pos, 16)
pos = print_outs(['UfbIns'], pos, 0x5a)
pos = print_outs(['UfbOuts'], pos, 0x20)
pos = print_outs(['McuIns'], pos, 0x109)
pos = print_outs(['McuOuts'], pos, 0x174)
pos = print_outs(['AdcIns'], pos, 0xf)
pos = print_outs(['AdcOuts'], pos, 13)
pos = print_outs(['Usb2PhyIns'], pos, 0x46)
pos = print_outs(['Usb2PhyOuts'], pos, 0x20)
pos = print_outs(['Eflash128kIns'], pos, 0x39)
#assert pos == 0x6f89e

print(d[0x6f89e:0x6f8da].hex())

pos = 0x6f8da
pos = print_outs(['Eflash128kOuts'], pos, 0x21)
pos = print_outs(['SpmiIns'], pos, 0x17)
pos = print_outs(['SpmiOuts'], pos, 0x2f)
pos = print_outs(['I3cIns'], pos, 0x26)
pos = print_outs(['I3cOuts'], pos, 0x28)
#assert pos == 0x6fd18

with open(f'{device}.json', 'w') as f:
    json.dump(data, f)
