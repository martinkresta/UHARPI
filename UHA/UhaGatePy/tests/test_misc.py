import os
import tempfile
import time
import unittest
from unittest import mock

from uhagatepy import config, event_log, rtc


class RtcTest(unittest.TestCase):
    NOW = 1768478400                      # 2026-01-15 12:00:00 UTC

    def fake_local(self, dst):
        local = time.struct_time((2026, 1, 15, 13, 0, 0, 3, 15, dst))
        return mock.patch("uhagatepy.rtc.time.localtime", return_value=local)

    def test_winter(self):
        with self.fake_local(0):
            data, summer = rtc.payload(self.NOW)
        self.assertEqual((int.from_bytes(data, "big"), summer), (self.NOW + 3600, False))

    def test_summer(self):
        with self.fake_local(1):
            data, summer = rtc.payload(self.NOW)
        self.assertEqual((int.from_bytes(data, "big"), summer), (self.NOW + 7200, True))
        self.assertEqual(len(data), 4)


class EventLogTest(unittest.TestCase):
    WHEN = time.struct_time((2026, 3, 5, 7, 8, 9, 3, 64, 0))
    NODES = {4: "ELECON", 7: "ELECON_D"}

    def test_line_format_is_the_same_as_uhagate6(self):
        line = event_log.format_line(bytes([4, 0, 12, 0, 0, 0, 0, 255]), self.NODES, self.WHEN)
        self.assertEqual(line, "05.03.2026 07:08:09 ELECON STARTUP 12 0 0 0 0 255\n")

    def test_unknown_node_and_event(self):
        line = event_log.format_line(bytes([99, 9, 1, 2, 3, 4, 5, 6]), self.NODES, self.WHEN)
        self.assertEqual(line, "05.03.2026 07:08:09 UNKNOWN UNKNOWN_EVENT 1 2 3 4 5 6\n")

    def test_short_packet_is_padded(self):
        line = event_log.format_line(bytes([7, 1]), self.NODES, self.WHEN)
        self.assertEqual(line, "05.03.2026 07:08:09 ELECON_D ERROR 0 0 0 0 0 0\n")

    def test_append(self):
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "log.txt")
            event_log.append(path, "a\n")
            event_log.append(path, "b\n")
            with open(path) as f:
                self.assertEqual(f.read(), "a\nb\n")


class ConfigTest(unittest.TestCase):
    def test_defaults_are_the_uhagate6_values(self):
        cfg = config.parse([])
        self.assertEqual((cfg.out_dir, cfg.log_file, cfg.json_period_ms, cfg.rtc_period_s, cfg.reopen_s),
                         ("/home/pi/Web", "/home/pi/Web/log.txt", 1000, 60, 5))
        self.assertIn("/dev/serial/by-id/", cfg.port)

    def test_file_then_command_line(self):
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "c.conf")
            with open(path, "w") as f:
                f.write("# comment\nport = /dev/ttyUSB7\nout-dir = /dev/shm   # in RAM\n"
                        "json-period-ms = 2000\nverbose = yes\n")
            cfg = config.parse(["-c", path, "--out-dir", "/tmp/x"])
        self.assertEqual((cfg.port, cfg.out_dir, cfg.json_period_ms, cfg.verbose),
                         ("/dev/ttyUSB7", "/tmp/x", 2000, True))

    def test_errors_exit(self):
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "bad.conf")
            with open(path, "w") as f:
                f.write("no-such-option = 1\n")
            with self.assertRaises(SystemExit):
                config.parse(["-c", path])
        with self.assertRaises(SystemExit):
            config.parse(["--json-period-ms", "5"])               # below the minimum
        with self.assertRaises(SystemExit):
            config.parse(["-c", "/does/not/exist.conf"])


if __name__ == "__main__":
    unittest.main()
