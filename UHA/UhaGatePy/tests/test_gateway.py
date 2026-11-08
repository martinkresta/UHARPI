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

    def test_only_old_packets_work_alone(self):
        """The situation before ELECON sends the tunnel: everything must work from 0x221 only."""
        self.gateway._on_packet(old_packet(10, 64))
        self.gateway._on_packet(old_packet(11, 532))
        self.gateway._on_packet(old_packet(49, 31))                  # a variable that is not in the YAML
        self.write()
        uha = self.read("uha.json")
        self.assertEqual((uha["VAR_BAT_SOC"], uha["VAR_BAT_VOLTAGE_V10"], uha["VAR_MPPT_ENERGY_TODAY_WH"]),
                         (64, 532, 31))
        self.assertEqual(self.read("bms.json")["LiveData"]["TotalVoltageV"], 53.2)
        uha2 = self.read("uha2.json")["Vars"]
        self.assertEqual((uha2["BAT_VOLTAGE_V"]["source"], uha2["BAT_VOLTAGE_V"]["value"]), ("old", 53.2))
        self.assertEqual(self.read("uha_status.json")["Counters"]["OldPackets"], 3)

    def test_tunnel_value_is_published_in_old_format(self):
        self.gateway._on_packet(old_packet(11, 500))
        self.gateway._on_packet(float_packet(4, 11, 53.2))
        self.write()
        self.assertEqual(self.read("uha.json")["VAR_BAT_VOLTAGE_V10"], 532)
        status = self.read("uha_status.json")
        self.assertEqual(status["Counters"]["TunnelPackets"], 1)
        self.assertEqual(status["Nodes"]["ELECON"]["TunnelPackets"], 1)
        self.assertEqual(status["Comparison"]["Mismatched"], 1)      # 532 against the old 500
        self.assertEqual(status["Comparison"]["Vars"]["BAT_VOLTAGE_V"]["MeanDiff"], 32)
        self.assertIn("BAT_SOC", status["Vars2"]["NeverReceived"])

    def test_bad_packets_are_counted_not_fatal(self):
        self.gateway._on_packet(Packet(0x221, bytes([0, 10])))        # too short
        self.gateway._on_packet(old_packet(500, 1))                   # id beyond the old range
        self.gateway._on_packet(float_packet(4, 999, 1.0))            # unknown VARS2 id
        self.gateway._on_packet(Packet(0x184, bytes(3)))              # wrong length
        self.gateway._on_packet(Packet(0x7FF, b""))                   # unknown packet
        c = self.gateway.counters
        self.assertEqual((c.malformed, c.out_of_range_vars, c.unknown_packets), (1, 1, 1))
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

    def test_summaries_do_not_crash(self):
        self.gateway._on_packet(old_packet(11, 532))
        self.gateway._on_packet(float_packet(4, 11, 53.2))
        self.gateway._error_summary()
        self.gateway._compare_summary()
        self.gateway._compare_summary()

    def test_tunnel_rate_counts_from_the_first_packet(self):
        self.gateway._on_packet(float_packet(4, 11, 53.2))
        node = self.gateway.tunnel_nodes[4]
        node.first_mono -= 100                                        # the tunnel has been running for 100 s
        node.packets = 5000
        self.write()
        self.assertAlmostEqual(self.read("uha_status.json")["Nodes"]["ELECON"]["TunnelAvgPerS"], 50, delta=1)

    def test_summary_reports_an_offset(self):
        for i in range(30):                                          # VARS2 always 10 % too high: a real error
            self.gateway._on_packet(old_packet(11, 500 + i))
            self.gateway._on_packet(float_packet(4, 11, (500 + i) * 1.1 / 10))
        with self.assertLogs("uhagatepy", level="INFO") as logged:
            self.gateway._compare_summary()
        text = " | ".join(r.getMessage() for r in logged.records)
        self.assertIn("1 OFFSET", text)
        self.assertIn("BAT_VOLTAGE_V", text)
        self.assertEqual([r.levelname for r in logged.records][0], "WARNING")

    def test_unwritable_folder_is_reported_once(self):
        self.gateway.cfg.out_dir = os.path.join(self.folder.name, "missing")
        with self.assertLogs("uhagatepy", level="ERROR") as logged:
            self.write()
            self.write()
        self.assertEqual(len(logged.records), 4)                      # 4 files, each logged once
        self.assertEqual(self.gateway.counters.write_errors, 8)


if __name__ == "__main__":
    unittest.main()
