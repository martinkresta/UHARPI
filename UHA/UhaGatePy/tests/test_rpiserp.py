import unittest

from uhagatepy import rpiserp
from uhagatepy.rpiserp import Parser


def feed_in_chunks(data: bytes, size: int):
    parser = Parser()
    packets = []
    for i in range(0, len(data), size):
        packets += parser.feed(data[i:i + size])
    return parser, packets


class EncodeTest(unittest.TestCase):
    def test_rtc_frame(self):
        frame = rpiserp.encode(0x51, bytes([1, 2, 3, 4]))
        self.assertEqual(frame[:9], bytes([0x7F, 0xAA, 6, 0x00, 0x51, 1, 2, 3, 4]))
        self.assertEqual(frame[9], (0x7F + 0xAA + 6 + 0x51 + 1 + 2 + 3 + 4) & 0xFF)

    def test_too_long(self):
        with self.assertRaises(ValueError):
            rpiserp.encode(0x51, bytes(9))


class ParserTest(unittest.TestCase):
    def test_split_at_every_position(self):
        frame = rpiserp.encode(0x221, bytes([0, 10, 0xFF, 0x9C, 0, 1]))
        for size in (1, 2, 3, 5, 100):
            parser, packets = feed_in_chunks(frame, size)
            self.assertEqual(len(packets), 1, size)
            self.assertEqual(packets[0].id, 0x221)
            self.assertEqual(packets[0].data, bytes([0, 10, 0xFF, 0x9C, 0, 1]))
            self.assertEqual(parser.discarded_bytes, 0)

    def test_start_byte_at_end_of_chunk(self):
        # UhaGate5 lost the frame when a read ended right after 0x7F
        stream = bytes([0x11, 0x22]) + rpiserp.encode(0x620, bytes(8))
        parser, packets = feed_in_chunks(stream, 3)            # chunk ends: 11 22 7F | AA ...
        self.assertEqual(len(packets), 1)
        self.assertEqual(parser.discarded_bytes, 2)

    def test_garbage_and_errors(self):
        bad = bytearray(rpiserp.encode(0x221, bytes([0, 2, 0, 2, 0, 1])))
        bad[-1] ^= 0xFF                                         # wrong checksum
        stream = (bytes([0x00, 0x7F, 0x00, 0xAA])               # garbage with a lone 0x7F
                  + rpiserp.encode(0x221, bytes([0, 1, 0, 1, 0, 1]))
                  + bytes(bad)
                  + bytes([0x7F, 0xAA, 0x00, 0x7F, 0xAA, 0x01, 0x7F, 0xAA, 0x0B])   # len 0, 1, 11
                  + rpiserp.encode(0x180, bytes([0x7F, 0xAA, 0x7F, 0xAA]))          # start sequence in data
                  + rpiserp.encode(0x123, b""))                                      # no data at all
        for size in (1000, 1, 7):
            parser, packets = feed_in_chunks(stream, size)
            self.assertEqual([p.id for p in packets], [0x221, 0x180, 0x123], size)
            self.assertEqual(packets[1].data, bytes([0x7F, 0xAA, 0x7F, 0xAA]))
            self.assertGreaterEqual(parser.checksum_errors, 1)
            self.assertEqual(parser.length_errors, 3)

    def test_all_data_lengths(self):
        stream = b"".join(rpiserp.encode(0x100 + n, bytes((0x7F + i * 0x2B) & 0xFF for i in range(n)))
                          for n in range(9))
        parser, packets = feed_in_chunks(stream, 4)
        self.assertEqual([len(p.data) for p in packets], list(range(9)))
        self.assertEqual((parser.checksum_errors, parser.discarded_bytes), (0, 0))

    def test_reset_drops_partial_frame(self):
        frame = rpiserp.encode(0x221, bytes(6))
        parser = Parser()
        self.assertEqual(parser.feed(frame[:5]), [])
        parser.reset()
        self.assertEqual(len(parser.feed(frame)), 1)


if __name__ == "__main__":
    unittest.main()
