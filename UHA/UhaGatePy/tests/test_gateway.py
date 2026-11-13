"""Packets in, files out: the gateway without a serial port and without the event loop."""
import json
import os
import tempfile
import time
import unittest

from uhagatepy import config
from uhagatepy.gateway import Gateway
from uhagatepy.rpiserp import Packet

from .helpers import float_packet, mini_defs, old_packet


class GatewayTest(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        cfg = config.Config(out_dir=self.folder.name, log_file=os.path.join(self.folder.name, "log.txt"))
        self.gateway = Gateway(cfg, mini_defs())

    def tearDown(self):
        self.folder.cleanup()

    def write(self):
        self.gateway._write_outputs(time.monotonic(), time.time())

    def read(self, name):
        with open(os.path.join(self.folder.name, name)) as f:
            return json.load(f)

    def test_old_packets_change_nothing(self):
        """The old 0x221 format is ignored: only counted, the outputs come from VARS2 alone."""
        self.gateway._on_packet(float_packet(4, 11, 53.2))
        mono, now = time.monotonic(), time.time()                    # same time for both writes
        self.gateway._write_outputs(mono, now)
        before = {name: self.read(name) for name in ("uha.json", "bms.json", "uha2.json")}
        self.gateway._on_packet(old_packet(11, 500))                 # different value for a VARS2 variable
        self.gateway._on_packet(old_packet(10, 64))                  # VARS2 variable never received
        self.gateway._on_packet(old_packet(49, 31))                  # variable that is not in the YAML
        self.gateway._write_outputs(mono, now)
        for name, data in before.items():
            self.assertEqual(self.read(name), data, name)
        uha = self.read("uha.json")
        self.assertEqual((uha["VAR_BAT_VOLTAGE_V10"], uha["VAR_BAT_SOC"], uha["VAR_MPPT_ENERGY_TODAY_WH"]), (532, 0, 0))
        self.assertEqual(self.read("uha_status.json")["Counters"]["IgnoredOldPackets"], 3)

    def test_tunnel_value_is_published_in_old_format(self):
        self.gateway._on_packet(float_packet(4, 11, 53.2))
        self.write()
        self.assertEqual(self.read("uha.json")["VAR_BAT_VOLTAGE_V10"], 532)
        self.assertEqual(self.read("bms.json")["LiveData"]["TotalVoltageV"], 53.2)
        status = self.read("uha_status.json")
        self.assertEqual(status["Counters"]["TunnelPackets"], 1)
        self.assertEqual(status["Nodes"]["ELECON"]["TunnelPackets"], 1)
        self.assertEqual(status["Vars"]["VAR_BAT_VOLTAGE_V10"]["Count"], 1)
        self.assertNotIn("Comparison", status)
        self.assertIn("BAT_SOC", status["Vars2"]["NeverReceived"])

    def test_bad_packets_are_counted_not_fatal(self):
        self.gateway._on_packet(float_packet(4, 999, 1.0))            # unknown VARS2 id
        self.gateway._on_packet(Packet(0x184, bytes(3)))              # wrong length
        self.gateway._on_packet(Packet(0x7FF, b""))                   # unknown packet
        c = self.gateway.counters
        self.assertEqual(c.unknown_packets, 1)
        self.assertEqual(c.tunnel_drops, {"length": 1, "unknown_id": 1, "bad_value": 0})
        self.write()                                                  # still writes everything

    def test_wrong_producer_is_counted_but_stored(self):
        self.gateway._on_packet(float_packet(7, 10, 55.0))            # BAT_SOC belongs to ELECON, not ELECON_D
        self.assertEqual(self.gateway.counters.wrong_producer, 1)
        self.write()
        self.assertEqual(self.read("uha.json")["VAR_BAT_SOC"], 55)

    def test_log_message_goes_to_log_txt(self):
        self.gateway._on_packet(Packet(0x620, bytes([4, 0, 12, 0, 0, 0, 0, 0])))
        with open(os.path.join(self.folder.name, "log.txt")) as f:
            self.assertRegex(f.read(), r"^\d\d\.\d\d\.\d{4} \d\d:\d\d:\d\d ELECON STARTUP 12 0 0 0 0 0\n$")
        self.write()
        self.assertEqual(self.read("uha_status.json")["Nodes"]["ELECON"]["LastLogEvent"], "STARTUP")

    def test_summaries(self):
        self.gateway._on_packet(float_packet(4, 11, 53.2))
        self.gateway._error_summary()
        with self.assertLogs("uhagatepy", level="INFO") as logged:
            self.gateway._vars2_summary(time.monotonic())
        self.assertIn("VARS2 stream: 1 of", logged.output[0])
        self.assertIn("never", logged.output[0])
        with self.assertLogs("uhagatepy", level="WARNING") as logged:
            self.gateway._vars2_summary(time.monotonic() + 100)       # now stale
        self.assertIn("stale 1 (BAT_VOLTAGE_V)", logged.output[0])

    def test_tunnel_rate_counts_from_the_first_packet(self):
        self.gateway._on_packet(float_packet(4, 11, 53.2))
        node = self.gateway.tunnel_nodes[4]
        node.first_mono -= 100                                        # the tunnel has been running for 100 s
        node.packets = 5000
        self.write()
        self.assertAlmostEqual(self.read("uha_status.json")["Nodes"]["ELECON"]["TunnelAvgPerS"], 50, delta=1)

    def test_unwritable_folder_is_reported_once(self):
        self.gateway.cfg.out_dir = os.path.join(self.folder.name, "missing")
        with self.assertLogs("uhagatepy", level="ERROR") as logged:
            self.write()
            self.write()
        self.assertEqual(len(logged.records), 4)                      # 4 files, each logged once
        self.assertEqual(self.gateway.counters.write_errors, 8)


if __name__ == "__main__":
    unittest.main()
