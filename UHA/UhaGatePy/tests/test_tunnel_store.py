import struct
import unittest

from uhagatepy import tunnel
from uhagatepy.rpiserp import Packet
from uhagatepy.store import Store, round_half_away, to_legacy_raw

from .helpers import float_packet, mini_defs, tunnel_packet


class TunnelDecodeTest(unittest.TestCase):
    def setUp(self):
        self.defs = mini_defs()

    def test_float(self):
        v = tunnel.decode(float_packet(4, 10, 76.5), self.defs)       # BAT_SOC from ELECON
        self.assertEqual((v.var_id, v.value, v.valid, v.producer), (10, 76.5, True, 4))

    def test_little_endian_inside_big_endian_packet_id(self):
        # variable id 0x0132 = 306 is sent as 32 01; the packet id 0x187 stays big-endian in the RPISERP header
        v = tunnel.decode(tunnel_packet(7, 306, struct.pack("<I", 1)), self.defs)
        self.assertEqual((v.var_id, v.value, v.producer), (306, 1, 7))

    def test_bool_is_zero_or_one(self):
        v = tunnel.decode(tunnel_packet(7, 306, struct.pack("<I", 0x100)), self.defs)
        self.assertEqual(v.value, 1)

    def test_enum(self):
        v = tunnel.decode(tunnel_packet(3, 80, struct.pack("<I", 2)), self.defs)
        self.assertEqual(v.value, 2)

    def test_valid_flag(self):
        self.assertFalse(tunnel.decode(float_packet(4, 10, 1.0, flags=0), self.defs).valid)
        self.assertTrue(tunnel.decode(float_packet(4, 10, 1.0, flags=0b101), self.defs).valid)   # reserved bits ignored

    def test_drops(self):
        for packet, reason in ((Packet(0x184, bytes(7)), "length"),
                               (float_packet(4, 999, 1.0), "unknown_id"),
                               (tunnel_packet(4, 10, struct.pack("<f", float("nan"))), "bad_value"),
                               (tunnel_packet(4, 10, struct.pack("<f", float("inf"))), "bad_value")):
            with self.assertRaises(tunnel.TunnelDrop) as caught:
                tunnel.decode(packet, self.defs)
            self.assertEqual(caught.exception.reason, reason)

    def test_id_range(self):
        self.assertTrue(tunnel.is_tunnel(0x180) and tunnel.is_tunnel(0x18F))
        self.assertFalse(tunnel.is_tunnel(0x17F) or tunnel.is_tunnel(0x190) or tunnel.is_tunnel(0x221))


class LegacyConversionTest(unittest.TestCase):
    def test_rounding_is_half_away_from_zero(self):
        self.assertEqual([round_half_away(x) for x in (2.5, -2.5, 0.5, -0.5, 1.4, -1.4)], [3, -3, 1, -1, 1, -1])

    def test_scales(self):
        self.assertEqual(to_legacy_raw(3.305, 1000)[0], 3305)
        self.assertEqual(to_legacy_raw(53.2, 10)[0], 532)
        self.assertEqual(to_legacy_raw(12340.0, 0.1)[0], 1234)       # *_TODAY_WH: old unit is 10 Wh
        self.assertEqual(to_legacy_raw(-3.1, 10)[0], -31)

    def test_clamp_to_int16(self):
        self.assertEqual(to_legacy_raw(40000, 1), (32767, True))
        self.assertEqual(to_legacy_raw(-40000, 1), (-32768, True))
        self.assertEqual(to_legacy_raw(100, 1), (100, False))


class StoreTest(unittest.TestCase):
    def setUp(self):
        self.defs = mini_defs()
        self.store = Store(self.defs, compare_window_s=2.0)

    def v2(self, var_id, value, mono, valid=True):
        tv = tunnel.decode(float_packet(4, var_id, value, 1 if valid else 0), self.defs)
        return self.store.set_v2(tv, mono, 1000)

    def test_nothing_received_is_zero(self):
        self.assertEqual(self.store.legacy_raw(10, 0.0), 0)

    def test_old_only(self):
        self.store.set_old(10, 64, True, 1.0, 1000)
        self.assertEqual(self.store.legacy_raw(10, 50.0), 64)       # old values never time out (as UhaGate6)

    def test_fresh_vars2_wins(self):
        self.store.set_old(11, 531, True, 1.0, 1000)
        self.v2(11, 53.2, 1.5)                                       # BAT_VOLTAGE_V, scale 10
        self.assertEqual(self.store.legacy_raw(11, 2.0), 532)

    def test_timed_out_vars2_falls_back_to_old(self):
        self.store.set_old(10, 64, True, 1.0, 1000)
        self.v2(10, 70.0, 1.0)                                       # BAT_SOC timeout is 3 s
        self.assertEqual(self.store.legacy_raw(10, 3.9), 70)
        self.assertEqual(self.store.legacy_raw(10, 4.1), 64)

    def test_invalid_vars2_falls_back_to_old(self):
        self.store.set_old(10, 64, True, 1.0, 1000)
        self.v2(10, 70.0, 1.0, valid=False)
        self.assertEqual(self.store.legacy_raw(10, 1.5), 64)

    def test_stale_vars2_without_old_value_is_kept(self):
        self.v2(10, 70.0, 1.0)
        self.assertEqual(self.store.legacy_raw(10, 100.0), 70)
        self.assertEqual(self.store.reading(self.defs.by_id[10], 100.0).source, "stale")

    def test_variable_not_in_yaml_uses_old_value(self):
        self.store.set_old(49, 31, True, 1.0, 1000)
        self.assertEqual(self.store.legacy_raw(49, 5.0), 31)

    def test_reading_sources(self):
        d = self.defs.by_id[10]
        self.assertEqual(self.store.reading(d, 1.0).source, "none")
        self.store.set_old(10, 64, True, 1.0, 1000)
        r = self.store.reading(d, 2.0)
        self.assertEqual((r.source, r.value, r.valid), ("old", 64.0, True))
        self.v2(10, 65.0, 2.0)
        r = self.store.reading(d, 2.5)
        self.assertEqual((r.source, r.value, r.valid, r.producer), ("vars2", 65.0, True, 4))

    def test_physical_value_of_old_scaled_variable(self):
        self.store.set_old(180, 3305, True, 1.0, 1000)               # cell 1 in mV
        self.assertEqual(self.store.reading(self.defs.by_id[180], 1.0).value, 3.305)

    def test_comparison_counts_mismatches(self):
        self.store.set_old(11, 532, True, 1.0, 1000)
        self.assertIsNone(self.v2(11, 53.2, 1.2))                    # equal
        self.assertIsNone(self.v2(11, 53.3, 1.3))                    # off by one raw unit is tolerated
        self.assertEqual(self.v2(11, 54.0, 1.4), (540, 532))         # mismatch
        self.assertEqual(self.store.compared[11], [3, 1])

    def test_comparison_needs_both_close_in_time_and_valid(self):
        self.store.set_old(11, 532, True, 1.0, 1000)
        self.assertIsNone(self.v2(11, 99.0, 10.0))                   # old value is too old to compare
        self.assertNotIn(11, {k for k, v in self.store.compared.items() if v[0] > 0})
        self.store.set_old(10, 64, False, 1.0, 1000)
        self.assertIsNone(self.v2(10, 99.0, 1.1))                    # old value is flagged invalid

    def test_clamp_counted_once_per_value(self):
        self.v2(8, 40000.0, 1.0)
        self.store.snapshot(1.5)
        self.store.snapshot(2.5)
        self.assertEqual(self.store.clamped, 1)


if __name__ == "__main__":
    unittest.main()
