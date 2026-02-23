"""CRC-16 ARC calculator.

Uses fastcrc (Rust extension) for high-performance CRC computation.

CRC-16 ARC params: width=16, poly=0x8005, init=0, refIn=True, refOut=True, xorOut=0
"""

from fastcrc import crc16


def make_crc16_calculator():
    """Return an object with .checksum(data) -> int."""
    return _FastCRC16()


class _FastCRC16:
    __slots__ = ()

    def checksum(self, data):
        return crc16.arc(data)
