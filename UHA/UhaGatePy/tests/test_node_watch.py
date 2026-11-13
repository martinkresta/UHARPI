import json
import os
import tempfile
import time
import unittest

from uhagatepy import config
from uhagatepy.gateway import Gateway
from uhagatepy.node_watch import MAX_THRESHOLD_S, REMINDER_S, NodeWatch

from .helpers import float_packet, mini_defs, old_packet


class NodeWatchTest(unittest.TestCase):
    def setUp(self):
        self.watch = NodeWatch(frozen_after_s=120)

    def test_nothing_seen_nothing_reported(self):
        self.assertEqual(self.watch.check(10_000), [])
        self.assertFalse(self.watch.is_frozen("ELECON_D", 10_000))

    def test_reported_when_nothing_changed_for_the_limit(self):
        self.watch.seen("ELECON_D", 0)
        self.assertEqual(self.watch.check(119), [])
        self.assertEqual([n for n, _ in self.watch.check(121)], ["ELECON_D"])

    def test_a_change_restarts_the_clock(self):
        self.watch.seen("ELECON_D", 0)
        self.watch.changed("ELECON_D", 40)                                # a normal gap of 40 s: limit stays 120 s
        self.assertEqual(self.watch.check(150), [])                       # 110 s since the change: under the limit
        self.assertEqual([n for n, _ in self.watch.check(161)], ["ELECON_D"])

    def test_reported_once_then_reminded(self):
        self.watch.seen("ELECON_D", 0)
        self.assertEqual(len(self.watch.check(130)), 1)
        self.assertEqual(self.watch.check(131), [])
        self.assertEqual(self.watch.check(130 + REMINDER_S - 1), [])
        self.assertEqual(len(self.watch.check(130 + REMINDER_S + 1)), 1)

    def test_back_again_is_reported_by_changed(self):
        self.watch.seen("ELECON_D", 0)
        self.watch.check(500)
        self.assertEqual(self.watch.changed("ELECON_D", 600), 600)       # quiet time of the outage
        self.assertFalse(self.watch.is_frozen("ELECON_D", 601))
        self.assertEqual(self.watch.changed("ELECON_D", 610), 0.0)

    def test_quiet_nodes_get_a_longer_limit(self):
        self.watch.seen("IOBOARD_D", 0)
        self.watch.changed("IOBOARD_D", 300)                              # normal gap of 300 s
        self.assertEqual(self.watch.threshold_s("IOBOARD_D"), 900)
        self.assertEqual(self.watch.check(300 + 800), [])
        self.assertEqual(len(self.watch.check(300 + 901)), 1)

    def test_an_outage_is_not_learned(self):
        self.watch.seen("ELECON_D", 0)
        self.watch.changed("ELECON_D", 10)
        self.watch.check(500)                                             # reported frozen
        self.watch.changed("ELECON_D", 20_000)                            # wakes up after hours
        self.assertEqual(self.watch.threshold_s("ELECON_D"), 120)         # still the default: detection not disabled

    def test_limit_is_capped(self):
        self.watch.seen("SLOW", 0)
        self.watch.changed("SLOW", 100_000)                               # a very long normal gap
        self.assertEqual(self.watch.threshold_s("SLOW"), MAX_THRESHOLD_S)


class GatewayWatchTest(unittest.TestCase):
    """Values in, frozen warning and status out (mini YAML: variable 180 and 181 belong to ELECON_D)."""

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        cfg = config.Config(out_dir=self.folder.name, log_file=os.path.join(self.folder.name, "log.txt"))
        self.gateway = Gateway(cfg, mini_defs())

    def tearDown(self):
        self.folder.cleanup()

    def status(self, mono):
        self.gateway._write_outputs(mono, time.time())
        with open(os.path.join(self.folder.name, "uha_status.json")) as f:
            return json.load(f)["Nodes"]

    def test_repeating_the_same_values_is_frozen(self):
        for _ in range(5):                                                # ELECON keeps repeating the stored value
            self.gateway._on_packet(float_packet(7, 180, 3.305))
            self.gateway._on_packet(float_packet(7, 181, 3.306))
        now = time.monotonic()
        self.assertEqual(self.gateway.watch.check(now + 10), [])
        with self.assertLogs("uhagatepy", level="WARNING") as logged:
            self.gateway._report_frozen("ELECON_D", 130, now + 130)
        self.assertIn("ELECON_D FROZEN", logged.output[0])
        self.assertEqual([n for n, _ in self.gateway.watch.check(now + 200)], ["ELECON_D"])

    def test_changing_values_are_not_frozen(self):
        self.gateway._on_packet(float_packet(7, 180, 3.305))
        self.gateway._on_packet(float_packet(7, 180, 3.306))                    # changed
        self.assertEqual(self.gateway.watch.check(time.monotonic() + 100), [])
        self.gateway._on_packet(float_packet(7, 181, 3.306))
        self.gateway._on_packet(float_packet(7, 181, 3.307))              # VARS2 value changed
        self.assertEqual(self.gateway.watch.check(time.monotonic() + 100), [])

    def test_status_shows_frozen_and_back_again(self):
        self.gateway._on_packet(float_packet(7, 180, 3.305))
        self.gateway._on_packet(float_packet(7, 180, 3.305))
        nodes = self.status(time.monotonic() + 500)
        self.assertTrue(nodes["ELECON_D"]["Frozen"])
        self.assertGreaterEqual(nodes["ELECON_D"]["QuietS"], 499)
        self.assertEqual(nodes["ELECON_D"]["FrozenLimitS"], 120)
        self.assertFalse(nodes["ELECON"]["Frozen"])                       # never seen: no verdict
        self.assertIsNone(nodes["ELECON"]["QuietS"])
        self.gateway.watch.check(time.monotonic() + 500)                   # now reported
        with self.assertLogs("uhagatepy", level="INFO") as logged:
            self.gateway._on_packet(float_packet(7, 180, 3.4))
        self.assertIn("changing again", logged.output[0])
        self.assertFalse(self.status(time.monotonic())["ELECON_D"]["Frozen"])

    def test_old_packets_do_not_feed_the_watch(self):
        self.gateway._on_packet(old_packet(180, 3305))
        self.gateway._on_packet(old_packet(180, 3306))
        self.assertEqual(self.gateway.watch.nodes, {})


if __name__ == "__main__":
    unittest.main()
