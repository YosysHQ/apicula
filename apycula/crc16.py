"""CRC-16 ARC calculator with optional Rust acceleration.

Uses fastcrc (Rust extension) when available, falls back to a pre-computed
256-entry lookup table implementation.

CRC-16 ARC params: width=16, poly=0x8005, init=0, refIn=True, refOut=True, xorOut=0
"""

def make_crc16_arc():
    """Return a function: crc16_arc(data: bytes) -> int."""
    try:
        from fastcrc import crc16
        _arc = crc16.arc
        return lambda data: _arc(bytes(data))
    except ImportError:
        pass

    import warnings
    warnings.warn("fastcrc is not available, performance will be degraded.")

    table = [0] * 256
    for i in range(256):
        crc = i
        for _ in range(8):
            if crc & 1:
                crc = (crc >> 1) ^ 0xA001  # 0x8005 bit-reversed
            else:
                crc >>= 1
        table[i] = crc

    def crc16_arc(data):
        crc = 0
        for byte in data:
            crc = table[(crc ^ byte) & 0xFF] ^ (crc >> 8)
        return crc

    return crc16_arc
