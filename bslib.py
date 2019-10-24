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

def crc(frame):
    bs = bytearr(frame)
    data = bs[-6:] + bs[:-8]
    crc = (bs[-7] << 8) + bs[-8]
    #print(data)
    return crc, crc16arc(data)

def bitarr(frame):
    "Array of *content* bits"
    data = frame.strip()[4:-64]
    return [int(n, base=2) for n in data]


def read_bitstream(fname):
    bitmap = []
    with open(fname) as inp:
        for line in inp:
            if line.startswith("//") or len(line) < 1000: continue
            crc1, crc2 = crc(line)
            #if crc1 != crc2: print(crc1, crc2)
            bitmap.append(bitarr(line))

    return np.fliplr(np.array(bitmap))

def display(fname, data):
    im = Image.frombytes(
            mode='1',
            size=data.shape[::-1],
            data=np.packbits(data, axis=1))
    im.save(fname)
