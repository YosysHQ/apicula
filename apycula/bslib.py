from math import ceil
import crc
from apycula import bitmatrix

crc16arc = crc.Configuration(width=16, polynomial=0x8005, reverse_input=True, reverse_output=True)

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
    calc = crc.Calculator(crc16arc)
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
                    elif ba == b'\x06\x00\x00\x00\x11\x00H\x1b':
                        padding = 4
                    elif ba == b'\x06\x00\x00\x00\x09\x00\x28\x1b':
                        padding = 0
                    elif ba == b'\x06\x00\x00\x00\x01\x008\x1b':
                        padding = 0
                    elif ba == b'\x06\x00\x00\x00\x01\x00h\x1b':
                        padding = 0
                    elif ba == b'\x06\x00\x00\x00\x03\x00\x18\x1b':
                        padding = 0
                    elif ba == b'\x06\x00\x00\x00\x01\x00\x98\x1b':
                        padding = 0
                    elif ba == b'\x06\x00\x00\x00\x00\x00\x08\x1b':
                        padding = 0
                    else:
                        raise ValueError("Unsupported device", ba)
                preamble = max(0, preamble-1)
                continue
            crcdat.extend(ba[:-8])
            crc1 = (ba[-7] << 8) + ba[-8]
            crc2 = calc.checksum(crcdat)
            assert crc1 == crc2, f"Not equal {crc1} {crc2} for {crcdat}"
            crcdat = ba[-6:]
            bitmap.append(bitarr(line, padding))
            frames = max(0, frames-1)

    return bitmatrix.fliplr(bitmap), hdr, ftr

def compressLine(line, key8Z, key4Z, key2Z):
    newline = []
    for i in range(0, len(line), 8):
        val = line[i:i+8].tobytes().replace(8 * b'\x00', bytes([key8Z]))
        val = val.replace(4 * b'\x00', bytes([key4Z]))
        newline += val.replace(2 * b'\x00', bytes([key2Z]))
    return newline

def write_bitstream_with_bsram_init(fname, bs, hdr, ftr, compress, bsram_init):
    new_bs = bitmatrix.vstack(bs, bsram_init)
    new_hdr = hdr.copy()
    frames = int.from_bytes(new_hdr[-1][2:], 'big') + bitmatrix.shape(bsram_init)[0]
    new_hdr[-1][2:] = frames.to_bytes(2, 'big')
    write_bitstream(fname, new_bs, new_hdr, ftr, compress)

def write_bitstream(fname, bs, hdr, ftr, compress):
    bs = bitmatrix.fliplr(bs)
    if compress:
        padlen = (ceil(bitmatrix.shape(bs)[1] / 64) * 64) - bitmatrix.shape(bs)[1]
    else:
        padlen = bitmatrix.shape(bs)[1] % 8
    pad = bitmatrix.ones(bitmatrix.shape(bs)[0], padlen)
    bs = bitmatrix.hstack(pad, bs)
    assert bitmatrix.shape(bs)[1] % 8 == 0
    bs=bitmatrix.packbits(bs, axis = 1)

    if compress:
        # search for smallest values not used in the bitstream
        lst = bitmatrix.histogram(bs, bins=[i for i in range(257)]) # 257 iso that the last basket is [255, 256] and not [254, 255]
        [key8Z, key4Z, key2Z] = [i for i,val in enumerate(lst) if val==0][0:3]

        # update line 0x51 with keys
        hdr51 = int.from_bytes(hdr[5], 'big') & ~0xffffff
        hdr51 = hdr51 | (key8Z << 16) | (key4Z << 8) | (key2Z)
        hdr[5] = bytearray.fromhex(f"{hdr51:016x}")

    crcdat = bytearray()
    preamble = 3
    calc = crc.Calculator(crc16arc)
    with open(fname, 'w') as f:
        for ba in hdr:
            if not preamble and ba[0] != 0xd2: # SPI address
                crcdat.extend(ba)
            preamble = max(0, preamble-1)
            f.write(''.join(f"{b:08b}" for b in ba))
            f.write('\n')
        for ba in bs:
            if compress:
                ba = compressLine(ba, key8Z, key4Z, key2Z)
            f.write(''.join(f"{b:08b}" for b in ba))
            crcdat.extend(ba)
            crc_ = calc.checksum(crcdat)
            crcdat = bytearray(b'\xff'*6)
            f.write(f"{crc_&0xff:08b}{crc_>>8:08b}")
            f.write('1'*48)
            f.write('\n')
        for ba in ftr:
            preamble = max(0, preamble-1)
            f.write(''.join(f"{b:08b}" for b in ba))
            f.write('\n')


def display(fname, data):
    from PIL import Image
    im = Image.frombytes(
            mode='1',
            size=data.shape[::-1],
            data=bitmatrix.packbits(data, axis = 1))
    if fname:
        im.save(fname)
    return im
