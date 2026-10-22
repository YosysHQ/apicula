import os
import tempfile
import unittest

from apycula.bslib import read_bitstream, write_bitstream


class FsMetadataCommentTests(unittest.TestCase):
    # Gowin programmer tools refuse to process an FS file that carries no
    # "//UserCode" comment (https://github.com/YosysHQ/apicula/issues/566)
    def _make_stream(self):
        hdr = [
            bytearray(b'\xff' * 20),
            bytearray(b'\xff' * 2),
            bytearray(b'\xa5\xc3'),
            bytearray(b'\x06\x00\x00\x00\x00\x01\x28\x1b'),  # GW5A-25A
            bytearray(b'\x10\x00\x00\x00\x00\xae\x00\x00'),
            bytearray(b'\x3b\x80\x00\x00\x00\x00\x00\x00'),  # frame count line
        ]
        ftr = [
            bytearray(b'\x68\x00\x00\x00\x00\x00\x00\x00'),
            bytearray(b'\x0a\x00\x00\x00\x00\x00\x6e\x38'),
            bytearray(b'\x08\x00\x00\x00'),
            bytearray(b'\xff' * 8),
            bytearray(b'\xff' * 2),
        ]
        bs = [[0] * 8, [1] * 8]
        return hdr, bs, ftr

    def test_write_emits_usercode_comment(self):
        hdr, bs, ftr = self._make_stream()
        with tempfile.TemporaryDirectory() as tmp:
            fs = os.path.join(tmp, 'test.fs')
            write_bitstream(fs, bs, hdr, ftr, compress=False, extra_slots=None)
            with open(fs) as f:
                lines = f.read().splitlines()

        # the vendor default sets UserCode equal to the footer checksum
        self.assertEqual(lines[0], '//CheckSum: 0x6E38')
        self.assertEqual(lines[1], '//UserCode: 0x00006E38')

    def test_read_skips_metadata_comments(self):
        hdr, bs, ftr = self._make_stream()
        with tempfile.TemporaryDirectory() as tmp:
            fs = os.path.join(tmp, 'test.fs')
            write_bitstream(fs, bs, hdr, ftr, compress=False, extra_slots=None)
            bitmap, hdr_out, ftr_out, _ = read_bitstream(fs)

        self.assertIn(bytearray(b'\x10\x00\x00\x00\x00\xae\x00\x00'), hdr_out)
        self.assertIn(bytearray(b'\x0a\x00\x00\x00\x00\x00\x6e\x38'), ftr_out)


if __name__ == '__main__':
    unittest.main()
