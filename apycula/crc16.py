"""CRC-16 ARC calculator with optional Rust acceleration.

Uses fastcrc (Rust extension) when available, falls back to a pre-computed
256-entry lookup table implementation.

CRC-16 ARC params: width=16, poly=0x8005, init=0, refIn=True, refOut=True, xorOut=0
"""

def make_crc16_calculator():
    """Return an object with .checksum(data) -> int."""
    try:
        from fastcrc import crc16
        return _Checksum(crc16.arc)
    except ImportError:
        pass

    import warnings
    warnings.warn("fastcrc is not available, performance will be degraded.")

    return _Checksum(_TableCRC16())


class _Checksum:
    """Thin wrapper so callers can always use .checksum(data)."""
    __slots__ = ('checksum',)

    def __init__(self, fn):
        self.checksum = fn


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

    def __call__(self, data):
        crc = 0
        table = self._table
        for byte in data:
            crc = table[(crc ^ byte) & 0xFF] ^ (crc >> 8)
        return crc
