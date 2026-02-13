"""CRC-16 ARC calculator with optional C acceleration.

Uses crcmod (C extension) when available, falls back to a pre-computed
256-entry lookup table implementation.

CRC-16 ARC params: width=16, poly=0x8005, init=0, refIn=True, refOut=True, xorOut=0
"""

def make_crc16_calculator():
    """Return an object with .checksum(data) -> int."""
    try:
        import crcmod.predefined
        fn = crcmod.predefined.mkPredefinedCrcFun('crc-16')
        return _CrcmodWrap(fn)
    except ImportError:
        pass

    return _TableCRC16()


class _CrcmodWrap:
    __slots__ = ('_fn',)

    def __init__(self, fn):
        self._fn = fn

    def checksum(self, data):
        return self._fn(data)


class _TableCRC16:
    """CRC-16 ARC using a pre-computed 256-entry lookup table."""

    __slots__ = ('_table',)

    def __init__(self):
        table = [0] * 256
        for i in range(256):
            crc = i
            for _ in range(8):
                if crc & 1:
                    crc = (crc >> 1) ^ 0xA001  # 0x8005 bit-reversed
                else:
                    crc >>= 1
            table[i] = crc
        self._table = table

    def checksum(self, data):
        crc = 0
        table = self._table
        for byte in data:
            crc = table[(crc ^ byte) & 0xFF] ^ (crc >> 8)
        return crc
