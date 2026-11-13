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
        self.store = Store(self.defs)

    def v2(self, var_id, value, mono, valid=True, node=4):
        tv = tunnel.decode(float_packet(node, var_id, value, 1 if valid else 0), self.defs)
        return self.store.set_v2(tv, mono, 1000)

    def test_nothing_received_is_zero(self):
        self.assertEqual(self.store.legacy_raw(10), 0)
        r = self.store.reading(self.defs.by_id[10], 1.0)
        self.assertEqual((r.value, r.valid, r.age_s, r.producer), (None, False, None, None))

    def test_value_converted_to_old_raw(self):
        self.v2(11, 53.2, 1.0)                                       # BAT_VOLTAGE_V, scale 10
        self.assertEqual(self.store.legacy_raw(11), 532)

    def test_old_value_is_kept_when_stale_but_marked_invalid(self):
        self.v2(10, 70.0, 1.0)                                       # BAT_SOC timeout is 3 s
        self.assertEqual(self.store.legacy_raw(10), 70)
        d = self.defs.by_id[10]
        self.assertTrue(self.store.reading(d, 3.9).valid)
        r = self.store.reading(d, 100.0)
        self.assertEqual((r.value, r.valid, r.age_s), (70, False, 99.0))

    def test_invalid_flag(self):
        self.v2(10, 70.0, 1.0, valid=False)
        self.assertEqual(self.store.legacy_raw(10), 70)
        self.assertFalse(self.store.reading(self.defs.by_id[10], 1.0).valid)

    def test_variable_not_in_yaml_is_zero(self):
        self.assertEqual(self.store.legacy_raw(49), 0)
        self.assertEqual(self.store.snapshot()["VAR_MPPT_ENERGY_TODAY_WH"], 0)

    def test_physical_value(self):
        self.v2(180, 3.305, 1.0, node=7)                             # cell 1 in V, old raw in mV
        self.assertEqual(self.store.reading(self.defs.by_id[180], 1.0).value, 3.305)
        self.assertEqual(self.store.snapshot()["VAR_BMS1_CELL1_MV"], 3305)

    def test_set_v2_reports_a_change(self):
        self.assertFalse(self.v2(11, 53.2, 1.0))                     # first value: nothing to compare with
        self.assertFalse(self.v2(11, 53.2, 2.0))
        self.assertTrue(self.v2(11, 53.3, 3.0))
        self.assertEqual(self.store.v2[11].count, 3)

    def test_clamp_counted_once_per_value(self):
        self.v2(8, 40000.0, 1.0)
        self.store.snapshot()
        self.store.snapshot()
        self.assertEqual(self.store.clamped, 1)

    def test_vars2_health(self):
        self.v2(10, 50.0, 10.0)                                      # BAT_SOC
        self.v2(11, 53.0, 10.0, valid=False)                         # invalid flag
        self.v2(9, 100.0, 10.0)                                      # timeout 9 s
        health = self.store.vars2_health(25.0)                       # 15 s later
        self.assertEqual(health["invalid"], ["BAT_VOLTAGE_V"])
        self.assertEqual(sorted(health["stale"]), ["BAT_SOC", "SOLAR_ENERGY_TODAY_WH"])
        self.assertIn("SOLAR_POWER_W", health["never"])
        self.assertEqual(health["fresh"], [])


if __name__ == "__main__":
    unittest.main()
