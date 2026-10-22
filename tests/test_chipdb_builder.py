import unittest

from apycula.chipdb_builder import DEVICE_PARAMS, gen_hdr


class HeaderTests(unittest.TestCase):
    # https://github.com/YosysHQ/apicula/issues/566
    def test_gw5a_25a_keeps_legacy_command_byte(self):
        header = gen_hdr("GW5A-25A", DEVICE_PARAMS["GW5A-25A"])

        self.assertIn(bytearray(b"\x10\x00\x00\x00\x00\xae\x00\x00"), header)

    def test_gw5a_25b_uses_revision_b_command_byte(self):
        # GW5A-25B shares the IDCODE and the configuration data with GW5A-25A,
        # but needs 0x02 as the header command byte - with 0xae revision B
        # chips never complete INIT and WAKEUP.
        header = gen_hdr("GW5A-25B", DEVICE_PARAMS["GW5A-25A"])

        self.assertIn(bytearray(b"\x10\x00\x00\x00\x00\x02\x00\x00"), header)
        # same IDCODE as GW5A-25A
        self.assertIn(bytearray(b"\x06\x00\x00\x00\x00\x01\x28\x1b"), header)
        # the GW5A-25 extra header line is present
        self.assertIn(bytearray(b"\x62\x00\x00\x00\x00\x00\x00\x40"), header)


if __name__ == "__main__":
    unittest.main()
