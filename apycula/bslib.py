import numpy as np
from PIL import Image
from crcmod.predefined import mkPredefinedCrcFun

crc16arc = mkPredefinedCrcFun('crc-16')

def chunks(l, n):
    """Yield successive n-sized chunks from l."""
    for i in range(0, len(l), n):
        yield l[i:i + n]

def bytearr(frame):
    "array of all bytes of the frame"
    return bytearray([int(n, base=2) for n in chunks(frame.strip(), 8)])

def bitarr(frame, pad):
    "Array of *content* bits"
    data = frame.strip()[pad:-64]
    return [int(n, base=2) for n in data]


def read_bitstream(fname):
    bitmap = []
    hdr = []
    ftr = []
    is_hdr = True
    crcdat = bytearray()
    preamble = 3
    frames = 0
    with open(fname) as inp:
        for line in inp:
            if line.startswith("//"): continue
            ba = bytearr(line)
            if not frames:
                if is_hdr:
                    hdr.append(ba)
                else:
                    ftr.append(ba)
                if not preamble and ba[0] != 0xd2: # SPI address
                    crcdat.extend(ba)
                if not preamble and ba[0] == 0x3b: # frame count
                    frames = int.from_bytes(ba[2:], 'big')
                    is_hdr = False
                if not preamble and ba[0] == 0x06: # device ID
                    if ba == b'\x06\x00\x00\x00\x11\x00\x58\x1b':
                        padding = 4
                    elif ba == b'\x06\x00\x00\x00\x09\x00\x28\x1b':
                        padding = 0
                    else:
                        raise ValueError("Unsupported device", ba)
                preamble = max(0, preamble-1)
                continue
            crcdat.extend(ba[:-8])
            crc1 = (ba[-7] << 8) + ba[-8]
            crc2 = crc16arc(crcdat)
            assert crc1 == crc2, f"Not equal {crc1} {crc2}"
            crcdat = ba[-6:]
            bitmap.append(bitarr(line, padding))
            frames = max(0, frames-1)

    return np.fliplr(np.array(bitmap)), hdr, ftr


def write_bitstream(fname, bs, hdr, ftr):
    bs = np.fliplr(bs)
    padlen = bs.shape[1] % 8
    pad = np.ones((bs.shape[0], padlen), dtype=np.uint8)
    bs = np.hstack([pad, bs])
    assert bs.shape[1] % 8 == 0
    bs=np.packbits(bs, axis=1)

    crcdat = bytearray()
    preamble = 3
    with open(fname, 'w') as f:
        for ba in hdr:
            if not preamble and ba[0] != 0xd2: # SPI address
                crcdat.extend(ba)
            preamble = max(0, preamble-1)
            f.write(''.join(f"{b:08b}" for b in ba))
            f.write('\n')
        for ba in bs:
            f.write(''.join(f"{b:08b}" for b in ba))
            crcdat.extend(ba)
            crc = crc16arc(crcdat)
            crcdat = bytearray(b'\xff'*6)
            f.write(f"{crc&0xff:08b}{crc>>8:08b}")
            f.write('1'*48)
            f.write('\n')
        for ba in ftr:
            preamble = max(0, preamble-1)
            f.write(''.join(f"{b:08b}" for b in ba))
            f.write('\n')


def display(fname, data):
    im = Image.frombytes(
            mode='1',
            size=data.shape[::-1],
            data=np.packbits(data, axis=1))
    if fname:
        im.save(fname)
    return im
