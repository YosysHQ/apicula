from math import ceil
import array
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

def read_bitstream_version(fname):
    ver = "UNKNOWN"
    with open(fname) as inp:
        for line in inp:
            if line.startswith("//Tool Version:"):
                ver = line[16:]
                break
    return ver

def read_bitstream(fname):
    bitmap = []
    returnBitmap = []
    hdr = []
    ftr = []
    # additional slots
    # { slot_no: bitmap }
    extra_slots = {}
    current_slot = 0xff
    is_hdr = True
    crcdat = bytearray()
    preamble = 3
    frames = 0
    c = 0
    is5ASeries = False

    calc = crc.Calculator(crc16arc)
    compressed = False
    compress_keys = {}
    with open(fname) as inp:
        for line in inp:
            if line.startswith("//"):
                #print("line: ", line)
                continue
            ba = bytearr(line)
            if not frames:
                if is_hdr:
                    #print("header:", ba)
                    hdr.append(ba)
                    if ba[0] == 0x10 and (int.from_bytes(ba, 'big') & (1 << 13)):
                        compressed = True
                    if ba[0] == 0x51:
                        compress_keys[f'{ba[5]:08b}'] = 8
                        if ba[6]:
                            compress_keys[f'{ba[6]:08b}'] = 4
                            if ba[7]:
                                compress_keys[f'{ba[7]:08b}'] = 2
                else:
                    #print("footer:", ba)
                    # Slots
                    if ba[0] == 0x6a:
                        if ba[7] == 0xff: # start of slots
                            continue
                        current_slot = ba[7]
                        #print("Slot:", current_slot)
                        continue
                    if ba[0] == 0x6b and ba[1] == 0x80 and ba[2] == 0: # slot data
                        slot_size = ba[3]
                        #print("Slot size:", slot_size)
                        slot_bitmap = []
                        for byt in chunks(line.strip()[8 * 4:-8 * 18], 8):
                            slot_bitmap.append([int(n, base=2) for n in byt])
                        slot_bitmap = bitmatrix.fliplr(slot_bitmap)
                        extra_slots[current_slot] = bitmatrix.transpose(slot_bitmap)
                        #for rd in extra_slots[current_slot]:
                        #    print(rd)
                        continue
                    ftr.append(ba)
                if not preamble and ba[0] != 0xd2: # SPI address
                    #print("spi address", ba)
                    crcdat.extend(ba)
                if not preamble and ba[0] == 0x3b: # frame count
                    frames = int.from_bytes(ba[2:], 'big')
                    #print(f"frames:{frames}");
                    is_hdr = False
                if not preamble and ba[0] == 0x06: # device ID
                    if ba == b'\x06\x00\x00\x00\x11\x00\x58\x1b':     # GW1N-9
                        padding = 4
                        compress_padding = 44 # <-- when using compression, the width of one row in bits must be a multiple of 64
                    elif ba == b'\x06\x00\x00\x00\x11\x00H\x1b':      # GW1N-9C
                        padding = 4
                        compress_padding = 44
                    elif ba == b'\x06\x00\x00\x00\x09\x00\x28\x1b':   # GW1N-1
                        padding = 0
                        compress_padding = 0
                    elif ba == b'\x06\x00\x00\x00\x01\x008\x1b':      # GW1N-4
                        padding = 0
                        compress_padding = 8
                    elif ba == b'\x06\x00\x00\x00\x01\x00h\x1b':      # GW1NZ-1
                        padding = 0
                        compress_padding = 0
                    elif ba == b'\x06\x00\x00\x00\x01\x00\x98\x1b':   # GW1NS-4
                        padding = 0
                        compress_padding = 8
                    elif ba == b'\x06\x00\x00\x00\x00\x00\x08\x1b':   # GW2A-18(C)
                        padding = 0
                        compress_padding = 16
                    elif ba == b'\x06\x00\x00\x00\x00\x01\x28\x1b':   # GW5A-25A
                        padding = 3
                        compress_padding = 43
                        is5ASeries = True
                    else:
                        raise ValueError("Unsupported device", ba)
                preamble = max(0, preamble-1)
                continue
            if is5ASeries == False:
                crcdat.extend(ba[:-8])
                crc1 = (ba[-7] << 8) + ba[-8]
                crc2 = calc.checksum(crcdat)
                assert crc1 == crc2, f"Not equal {crc1} {crc2} for {crcdat}"
                if crc1 != crc2:
                    print("frame: ", c, ba, len(ba))
                    print("crcdata: ", crcdat, len(crcdat))
                    print("crc error - frame:", c, frames, " : ", crc1, " != ", crc2)

                crcdat = ba[-6:]
            if compressed:
                uncompressed_line = ''
                for byte_str in chunks(line[:-64], 8):
                    if byte_str in compress_keys:
                        for _ in range(compress_keys[byte_str]):
                            uncompressed_line += "00000000"
                    else:
                        uncompressed_line += byte_str

                uncompressed_line += line[-64:]
                bitmap.append(bitarr(uncompressed_line, compress_padding))
            else:
                bitmap.append(bitarr(line, padding))

            frames = max(0, frames-1)
            c = c + 1

        returnBitmap = bitmatrix.fliplr(bitmap)
        if is5ASeries:
            returnBitmap = bitmatrix.transpose(returnBitmap)

        return returnBitmap, hdr, ftr, extra_slots

def compressLine(line, key8Z, key4Z, key2Z):
    newline = []
    for i in range(0, len(line), 8):
        val = array.array('B', line[i:i+8]).tobytes().replace(8 * b'\x00', bytes([key8Z]))
        if key4Z:
            val = val.replace(4 * b'\x00', bytes([key4Z]))
            if key2Z:
                val = val.replace(2 * b'\x00', bytes([key2Z]))
        newline += val
    return newline

def write_gw5_bsram_init_map(f, crcdat, calc, gw5a_bsram_init_map, gw5a_bsrams):
    # BSRAM init part. Count used columns
    last_col = -1
    used_blocks = 0
    block_seq = {}   # start col of block sequence: number of blocks
    last_block_seq = None
    for bsram in gw5a_bsrams:
        col, _, _, _, _ = bsram
        if col != last_col:
            used_blocks += 1
            if col - last_col != 3:         # 3 cells for one BSRAM, if the columns are 3 cells apart
                block_seq.setdefault(col // 3, 0)  #  when the BSRAMs are neighbours
                last_block_seq = col // 3
            block_seq[last_block_seq] += 1
            last_col = col
    # rearrange init map - cut unused tail blocks - we don't need zero init data after last used block
    tail = used_blocks * 256
    w = bitmatrix.shape(gw5a_bsram_init_map)[1]
    bitInitMap = [[gw5a_bsram_init_map[i][w - j - 1] for j in range(w)] for i in range(tail)]
    assert bitmatrix.shape(bitInitMap)[1] % 8 == 0
    byteInitMap = bitmatrix.packbits(bitInitMap, axis = 1)

    # write BSRAM init data
    data_first_col = 0
    for start, cnt in block_seq.items():
        ba = bytearray(b'\x12\x00\x00\x00')
        crcdat.extend(ba)
        f.write(''.join(f"{b:08b}" for b in ba))
        f.write('\n')

        # empty cols
        ba = bytearray(b'\x70\x00\x00')
        crcdat.extend(ba)
        f.write(''.join(f"{b:08b}" for b in ba))
        ba = bytearray.fromhex(f"{start + 1:02x}")
        crcdat.extend(ba)
        f.write(''.join(f"{b:08b}" for b in ba))
        ba = bytearray(b'\x00' * (start + 1))
        crcdat.extend(ba)
        f.write(''.join(f"{b:08b}" for b in ba))
        f.write('\n')

        # data cols
        ba = bytearray(b'\x4e\x80')
        crcdat.extend(ba)
        f.write(''.join(f"{b:08b}" for b in ba))
        ba = bytearray.fromhex(f"{cnt % 256 :02x}")
        crcdat.extend(ba)
        f.write(''.join(f"{b:08b}" for b in ba))
        ba = bytearray.fromhex(f"{cnt >> 8 :02x}")
        crcdat.extend(ba)
        f.write(''.join(f"{b:08b}" for b in ba))
        f.write('\n')

        # data
        for data_row in byteInitMap[data_first_col : data_first_col + 256 * cnt]:
            f.write(''.join(f"{b:08b}" for b in data_row))
            crcdat.extend(data_row)
            crc_ = calc.checksum(crcdat)
            crcdat = bytearray(b'\xff'*6)
            f.write(f"{crc_&0xff:08b}{crc_>>8:08b}")
            f.write('1'*48)
            f.write('\n')

        data_first_col += 256 * cnt

        # end of block
        ba = bytearray(b'\xff' * 18)
        crcdat.extend(ba)
        f.write(''.join(f"{b:08b}" for b in ba))
        crc_ = calc.checksum(crcdat)
        crcdat = bytearray()
        f.write(f"{crc_&0xff:08b}{crc_>>8:08b}")
        f.write('\n')

def write_bitstream_with_bsram_init(fname, bs, hdr, ftr, compress, extra_slots, bsram_init):
    new_bs = bitmatrix.vstack(bs, bsram_init)
    new_hdr = hdr.copy()
    write_bitstream(fname, new_bs, new_hdr, ftr, compress, extra_slots)

def write_bitstream(fname, bs, hdr, ftr, compress, extra_slots, gw5a_bsram_init_map = None, gw5a_bsrams = None):
    bs = bitmatrix.fliplr(bs)
    hdr[-1][2:] = bitmatrix.shape(bs)[0].to_bytes(2, 'big')

    if compress:
        padlen = (ceil(bitmatrix.shape(bs)[1] / 64) * 64) - bitmatrix.shape(bs)[1]
    else:
        padlen = (ceil(bitmatrix.shape(bs)[1] / 8) * 8) - bitmatrix.shape(bs)[1]
    pad = bitmatrix.ones(bitmatrix.shape(bs)[0], padlen)
    no_compress_pad_bytes = (padlen - ((ceil(bitmatrix.shape(bs)[1] / 8) * 8) - bitmatrix.shape(bs)[1])) // 8
    bs = bitmatrix.hstack(pad, bs)
    assert bitmatrix.shape(bs)[1] % 8 == 0
    bs = bitmatrix.packbits(bs, axis = 1)

    unused_bytes = []
    if compress:
        # search for smallest values not used in the bitstream
        lst = bitmatrix.byte_histogram(bs)
        unused_bytes = [i for i,val in enumerate(lst) if val==0]
        if unused_bytes:
            # We may simply not have the bytes we need for the keys.
            [key8Z, key4Z, key2Z] = (unused_bytes + [0, 0])[0:3]
            # update line 0x10 with compress enable bit
            hdr10 = int.from_bytes(hdr[4], 'big') | (1 << 13)
            hdr[4] = bytearray.fromhex(f"{hdr10:016x}")

            # update line 0x51 with keys
            hdr51 = int.from_bytes(hdr[5], 'big') & ~0xffffff
            hdr51 = hdr51 | (key8Z << 16) | (key4Z << 8) | (key2Z)
            hdr[5] = bytearray.fromhex(f"{hdr51:016x}")
        else:
            print("Warning. No unused bytes, will be uncompressed.")

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
                if unused_bytes:
                    ba = compressLine(ba, key8Z, key4Z, key2Z)
                else:
                    ba = ba[no_compress_pad_bytes : ]
            f.write(''.join(f"{b:08b}" for b in ba))
            crcdat.extend(ba)
            crc_ = calc.checksum(crcdat)
            crcdat = bytearray(b'\xff'*6)
            f.write(f"{crc_&0xff:08b}{crc_>>8:08b}")
            f.write('1'*48)
            f.write('\n')

        # end of main grid
        f.write(''.join(f"{b:08b}" for b in ftr[0]))
        f.write('\n')

        if extra_slots:
            # slot preamble
            crcdat = bytearray()
            ba = bytearray(b'\x6a\x00\x00\x00\x00\x00\x00\xff')
            crcdat.extend(ba)
            f.write(''.join(f"{b:08b}" for b in ba))
            f.write('\n')
            ba = bytearray(b'\x6d\x00\x00\x00')
            crcdat.extend(ba)
            f.write(''.join(f"{b:08b}" for b in ba))
            ba = bytearray(b'\xff'*16)
            f.write(''.join(f"{b:08b}" for b in ba))
            f.write('\n')

            for slot_idx, slot_bitmap in extra_slots.items():
                # slot header
                ba = bytearray(b'\x6a\x00\x00\x00\x00\x00\x00')
                crcdat.extend(ba)
                f.write(''.join(f"{b:08b}" for b in ba))
                ba = bytearray.fromhex(f"{slot_idx:02x}")
                crcdat.extend(ba)
                f.write(''.join(f"{b:08b}" for b in ba))
                f.write('\n')

                ba = bytearray(b'\x6b\x80\x00')
                crcdat.extend(ba)
                f.write(''.join(f"{b:08b}" for b in ba))
                shape = bitmatrix.shape(slot_bitmap)
                ba = bytearray.fromhex(f"{shape[0] * shape[1] // 8:02x}")
                crcdat.extend(ba)
                f.write(''.join(f"{b:08b}" for b in ba))

                # slot bitmap
                bs = bitmatrix.transpose(slot_bitmap)
                bs = bitmatrix.fliplr(bs)
                bs = bitmatrix.packbits(bs, axis = 1)
                for ba in bs:
                    crcdat.extend(ba)
                    f.write(''.join(f"{b:08b}" for b in ba))
                crc_ = calc.checksum(crcdat)
                crcdat = bytearray(b'\xff'*2)
                f.write(f"{crc_&0xff:08b}{crc_>>8:08b}")
                f.write('1'*128)
                f.write('\n')
        else:
            crcdat = bytearray()
        if gw5a_bsram_init_map:
            write_gw5_bsram_init_map(f, crcdat, calc, gw5a_bsram_init_map, gw5a_bsrams)
            crcdat = bytearray()

        for ba in ftr[1:]:
            f.write(''.join(f"{b:08b}" for b in ba))
            f.write('\n')


def display(fname, data):
    from PIL import Image
    """
    im = Image.frombytes(
            mode='1',
            size=data.shape[::-1],
            data=bitmatrix.packbits(data, axis = 1))
    """

    tdata = bitmatrix.packbits(data, axis = 1)
    im = Image.new('RGB', bitmatrix.shape(tdata)[::-1], 255)
    idata = im.load()
    for x in range(im.size[0]):
        for y in range(im.size[1]):
            idata[x, y] = (tdata[y][x], tdata[y][x], tdata[y][x])
    if fname:
        im.save(fname)
    return im
