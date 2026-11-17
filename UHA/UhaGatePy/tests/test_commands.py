"""Command channel (CMD_spec.md): YAML commands, packet 0x52, rate limit, gateway send, HTTP API, DB table."""
import asyncio
import http.client
import json
import os
import sqlite3
import struct
import tempfile
import threading
import time
import unittest

from uhagatepy import commands, config, rpiserp, vars_def
from uhagatepy.api import ApiServer
from uhagatepy.gateway import Gateway

from .helpers import FIXTURES, REAL_YAML


def cmd_defs():
    return vars_def.load(os.path.join(FIXTURES, "cmd_vars.yaml"))


def load_text(text: str) -> vars_def.VarsFile:
    with tempfile.TemporaryDirectory() as folder:
        path = os.path.join(folder, "vars.yaml")
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        return vars_def.load(path)


BASE = """
nodes: {IOBOARD_U: 2, TECHM: 3, RPI: 15}
enums: {BlindCmd: {0: None, 1: Up}}
groups:
  S:
    producer: IOBOARD_U
    vars: [{id: 400, name: ST_LIGHT_A, type: uint32, period_ms: 20000, agg: event},
           {id: 440, name: ST_TECHM, type: uint32, period_ms: 20000, agg: event, producer: TECHM}]
commands:
"""
GOOD = "  - {id: 201, name: CMD_A, target: IOBOARD_U, type: uint32, min: 0, max: 100, state: ST_LIGHT_A}\n"


class YamlCommandsTest(unittest.TestCase):
    def test_fixture(self):
        defs = cmd_defs()
        self.assertEqual(list(defs.commands), ["CMD_LIGHT_LOFT_WEST", "CMD_LIGHT_LOFT_EAST_1", "CMD_SCREEN_EAST",
                                               "CMD_TEST_FLOAT"])
        c = defs.commands["CMD_LIGHT_LOFT_WEST"]
        self.assertEqual((c.id, c.target, c.target_id, c.type, c.min, c.max, c.unit, c.state),
                         (201, "IOBOARD_U", 2, "uint32", 0, 100, "%", "ST_LIGHT_LOFT_WEST"))
        screen = defs.commands["CMD_SCREEN_EAST"]
        self.assertEqual((screen.enum, screen.min, screen.max), ("BlindCmd", 0, 3))   # range from the enum

    def test_no_section_no_commands(self):
        self.assertEqual(load_text(BASE.replace("commands:\n", "")).commands, {})
        self.assertEqual(load_text(BASE).commands, {})                                 # empty section

    def test_good_entry(self):
        self.assertEqual(list(load_text(BASE + GOOD).commands), ["CMD_A"])

    def test_broken_entries_refuse_to_load(self):
        cases = (
            (GOOD.replace("CMD_A", "LIGHT_A"), "must start with CMD_"),
            (GOOD + GOOD.replace("CMD_A", "CMD_B"), "duplicate"),
            (GOOD + GOOD.replace("201", "202"), "duplicate"),
            (GOOD.replace("201", "301"), "outside the range of IOBOARD_U (200..299)"),
            (GOOD.replace("IOBOARD_U", "RPI").replace("201", "1501"), "not RPI"),
            (GOOD.replace("IOBOARD_U", "NOBODY"), "must be a node"),
            (GOOD.replace("uint32", "string"), "unknown type"),
            (GOOD.replace("min: 0, max: 100", "min: 100, max: 0"), "min 100 > max 0"),
            (GOOD.replace("min: 0", "min: -1"), "whole numbers in 0.."),
            (GOOD.replace("min: 0, ", ""), "min must be a number"),
            (GOOD.replace("ST_LIGHT_A", "ST_NONE"), "is not a variable"),
            (GOOD.replace("ST_LIGHT_A", "ST_TECHM"), "produced by TECHM, not by the target IOBOARD_U"),
            (GOOD.replace("type: uint32", "type: enum, enum: Nope"), "unknown enum"),
        )
        for entry, reason in cases:
            with self.subTest(reason=reason):
                with self.assertRaises(vars_def.VarsDefError) as ctx:
                    load_text(BASE + entry)
                self.assertIn(reason, str(ctx.exception))

    def test_not_a_list(self):
        with self.assertRaises(vars_def.VarsDefError):
            load_text(BASE.replace("commands:\n", "commands: {CMD_A: 1}\n"))

    @unittest.skipUnless(os.path.exists(REAL_YAML), "real uha_vars.yaml not available")
    def test_real_yaml_still_loads(self):
        """The real file (with or without its commands section) loads; the pilot commands fit it."""
        defs = vars_def.load(REAL_YAML)
        with open(REAL_YAML, encoding="utf-8") as f:
            real = f.read()
        if "\ncommands:" not in real:
            with open(os.path.join(FIXTURES, "commands_pilot.yaml"), encoding="utf-8") as f:
                defs = load_text(real + "\n" + f.read())
            self.assertEqual(len(defs.commands), 12)
        for c in defs.commands.values():
            self.assertEqual(defs.nodes[c.target], c.target_id)


class PureLogicTest(unittest.TestCase):
    def setUp(self):
        self.defs = cmd_defs()

    def test_user_from_dn(self):
        for dn, user in (("CN=martin-pc,O=UHA", "martin-pc"), ("O=UHA,CN=zena-telefon", "zena-telefon"),
                         ("/O=UHA/CN=martin-telefon", "martin-telefon"), ("CN=a\\,b,O=x", "a,b"),
                         ("", None), (None, None), ("O=UHA", None), ("CN=", None)):
            with self.subTest(dn=dn):
                self.assertEqual(commands.user_from_dn(dn), user)

    def test_check_value(self):
        light = self.defs.commands["CMD_LIGHT_LOFT_WEST"]
        self.assertEqual(commands.check_value(light, 100), 100)
        self.assertEqual(commands.check_value(light, 100.0), 100)
        self.assertEqual(commands.check_value(light, 250), 250)          # out of min/max: the node clamps
        for bad in (True, "100", None, 1.5, -1, 2 ** 32, float("nan"), float("inf")):
            with self.subTest(value=bad):
                with self.assertRaises(commands.BadValue):
                    commands.check_value(light, bad)
        f = self.defs.commands["CMD_TEST_FLOAT"]
        self.assertEqual(commands.check_value(f, 1), 1.0)
        self.assertIsInstance(commands.check_value(f, 1), float)
        screen = self.defs.commands["CMD_SCREEN_EAST"]
        self.assertEqual(commands.check_value(screen, -5), -5)          # enum = int32

    def test_packet_data_spec_layout(self):
        """Spec section 2: target | cmd id u16 LE | value 4 B LE | seq, built here byte by byte."""
        light = self.defs.commands["CMD_LIGHT_LOFT_WEST"]
        self.assertEqual(commands.packet_data(light, 100, 5), bytes([2, 201, 0, 100, 0, 0, 0, 5]))
        self.assertEqual(commands.packet_data(light, 0x01020304, 255), bytes([2, 201, 0, 4, 3, 2, 1, 255]))
        screen = self.defs.commands["CMD_SCREEN_EAST"]
        self.assertEqual(commands.packet_data(screen, -1, 0), bytes([2, 250, 0, 0xFF, 0xFF, 0xFF, 0xFF, 0]))
        f = self.defs.commands["CMD_TEST_FLOAT"]
        self.assertEqual(commands.packet_data(f, 1.5, 7)[3:7], struct.pack("<f", 1.5))
        frame = rpiserp.encode(commands.PACKET_COMMAND, commands.packet_data(light, 100, 5))
        self.assertEqual(frame[:5], bytes([0x7F, 0xAA, 10, 0x00, 0x52]))      # len = 2 + 8
        self.assertEqual(frame[-1], sum(frame[:-1]) & 0xFF)

    def test_rate_limit(self):
        rate = commands.RateLimit()
        t = 1000.0
        for i in range(10):
            self.assertTrue(rate.allowed(t + i * 0.01))
            rate.sent(t + i * 0.01)
        self.assertFalse(rate.allowed(t + 0.5))                         # 11th in the same second
        self.assertTrue(rate.allowed(t + 1.2))
        for i in range(10):
            rate.sent(t + 1.2 + i * 0.01)
        self.assertFalse(rate.allowed(t + 30))                          # 20 in the last minute
        self.assertTrue(rate.allowed(t + 60.5))                         # the first 10 are older than 60 s


class FakeLink:
    def __init__(self, is_open=True, ok=True):
        self.path = "/dev/fake"
        self.is_open = is_open
        self.ok = ok
        self.last_error = ""
        self.written = []

    def write(self, data):
        self.written.append(data)
        return self.ok


class GatewaySendTest(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        cfg = config.Config(out_dir=self.folder.name, log_file=os.path.join(self.folder.name, "log.txt"))
        self.gateway = Gateway(cfg, cmd_defs())
        self.gateway.link = FakeLink()
        self.light = self.gateway.defs.commands["CMD_LIGHT_LOFT_WEST"]

    def tearDown(self):
        self.folder.cleanup()

    def test_sent_with_increasing_seq(self):
        self.assertEqual(self.gateway.execute_command(self.light, 100, "martin-pc"), (200, {"ok": True, "seq": 0}))
        self.assertEqual(self.gateway.execute_command(self.light, 0, "martin-pc"), (200, {"ok": True, "seq": 1}))
        parser = rpiserp.Parser()
        packets = parser.feed(b"".join(self.gateway.link.written))
        self.assertEqual([(p.id, p.data) for p in packets],
                         [(0x52, bytes([2, 201, 0, 100, 0, 0, 0, 0])), (0x52, bytes([2, 201, 0, 0, 0, 0, 0, 1]))])
        self.assertEqual(self.gateway.counters.commands_sent, 2)
        self.assertEqual(self.gateway.last_command["User"], "martin-pc")

    def test_seq_wraps(self):
        self.gateway.cmd_seq = 255
        self.gateway.execute_command(self.light, 1, "u")
        self.assertEqual(self.gateway.cmd_seq, 0)

    def test_link_down_503(self):
        self.gateway.link = FakeLink(is_open=False)
        self.assertEqual(self.gateway.execute_command(self.light, 1, "u")[0], 503)
        self.gateway.link = FakeLink(ok=False)
        self.assertEqual(self.gateway.execute_command(self.light, 1, "u")[0], 503)
        self.assertEqual(self.gateway.cmd_seq, 0)                         # nothing sent: seq unchanged
        self.assertEqual(self.gateway.counters.commands_link_down, 2)

    def test_rate_limit_429(self):
        answers = [self.gateway.execute_command(self.light, 1, "u")[0] for _ in range(12)]
        self.assertEqual(answers, [200] * 10 + [429, 429])
        self.assertEqual(len(self.gateway.link.written), 10)

    def test_status_block(self):
        self.gateway.execute_command(self.light, 100, "martin-pc")
        self.gateway._write_outputs(time.monotonic(), time.time())
        with open(os.path.join(self.folder.name, "uha_status.json")) as f:
            block = json.load(f)["Commands"]
        self.assertEqual((block["Defined"], block["Sent"], block["Last"]["Cmd"], block["Api"]),
                         (4, 1, "CMD_LIGHT_LOFT_WEST", None))


class ApiTest(unittest.TestCase):
    """The real HTTP server on an ephemeral port, the loop in a thread, a fake send."""

    @classmethod
    def setUpClass(cls):
        cls.defs = cmd_defs()
        cls.loop = asyncio.new_event_loop()
        cls.loop_thread = threading.Thread(target=cls.loop.run_forever, daemon=True)
        cls.loop_thread.start()
        cls.calls = []

        def execute(cmd, value, user):
            assert threading.current_thread() is cls.loop_thread          # the send runs in the loop
            cls.calls.append((cmd.name, value, user))
            return 200, {"ok": True, "seq": len(cls.calls) - 1}

        cls.api = ApiServer(0, cls.defs, execute, "https://ctrl.uha.mkresta.cz")
        assert cls.api.start(cls.loop)

    @classmethod
    def tearDownClass(cls):
        cls.api.stop()
        cls.loop.call_soon_threadsafe(cls.loop.stop)
        cls.loop_thread.join(timeout=5)
        cls.loop.close()

    def request(self, method, path, body=None, headers=None, dn="CN=martin-pc,O=UHA"):
        con = http.client.HTTPConnection("127.0.0.1", self.api.port, timeout=5)
        h = {"Content-Type": "application/json"}
        if dn is not None:
            h["X-Client-DN"] = dn
        h.update(headers or {})
        data = body if isinstance(body, (bytes, str)) or body is None else json.dumps(body)
        con.request(method, path, body=data, headers=h)
        r = con.getresponse()
        answer = r.status, json.loads(r.read() or b"null")
        con.close()
        return answer

    def test_commands_list(self):
        status, body = self.request("GET", "/api/commands")
        self.assertEqual(status, 200)
        self.assertEqual([c["name"] for c in body][:2], ["CMD_LIGHT_LOFT_WEST", "CMD_LIGHT_LOFT_EAST_1"])
        self.assertEqual(body[0]["state"], "ST_LIGHT_LOFT_WEST")
        self.assertEqual(body[2]["enum"], {"0": "None", "1": "Up", "2": "Down", "3": "Stop"})

    def test_send(self):
        status, body = self.request("POST", "/api/cmd", {"cmd": "CMD_LIGHT_LOFT_WEST", "value": 100},
                                    headers={"Origin": "https://ctrl.uha.mkresta.cz"})
        self.assertEqual((status, body["ok"]), (200, True))
        self.assertEqual(self.calls[-1], ("CMD_LIGHT_LOFT_WEST", 100, "martin-pc"))

    def test_rejections(self):
        before = len(self.calls)
        cases = (
            (("GET", "/api/commands", None, None, None), 403),
            (("POST", "/api/cmd", {"cmd": "CMD_LIGHT_LOFT_WEST", "value": 1}, None, None), 403),
            (("POST", "/api/cmd", {"cmd": "CMD_LIGHT_LOFT_WEST", "value": 1}, None, "O=UHA"), 403),
            (("POST", "/api/cmd", {"cmd": "CMD_LIGHT_LOFT_WEST", "value": 1}, {"Origin": "https://evil.example"},
              "CN=x"), 403),
            (("POST", "/api/cmd", {"cmd": "CMD_LIGHT_LOFT_WEST", "value": 1}, {"Content-Type": "text/plain"},
              "CN=x"), 415),
            (("POST", "/api/cmd", {"cmd": "CMD_NOPE", "value": 1}, None, "CN=x"), 400),
            (("POST", "/api/cmd", {"cmd": "CMD_LIGHT_LOFT_WEST", "value": "on"}, None, "CN=x"), 400),
            (("POST", "/api/cmd", {"cmd": "CMD_LIGHT_LOFT_WEST"}, None, "CN=x"), 400),
            (("POST", "/api/cmd", "{not json", None, "CN=x"), 400),
            (("POST", "/api/cmd", "x" * 2000, None, "CN=x"), 413),
            (("POST", "/api/other", {"cmd": "CMD_LIGHT_LOFT_WEST", "value": 1}, None, "CN=x"), 404),
            (("GET", "/api/cmd", None, None, "CN=x"), 404),
            (("DELETE", "/api/cmd", None, None, "CN=x"), 405),
        )
        for (method, path, body, headers, dn), expected in cases:
            with self.subTest(method=method, path=path, body=str(body)[:40], expected=expected):
                status, answer = self.request(method, path, body, headers, dn)
                self.assertEqual(status, expected)
                self.assertFalse(answer["ok"])
        self.assertEqual(len(self.calls), before)                        # nothing reached the loop

    def test_loop_timeout_is_503(self):
        api = ApiServer(0, self.defs, lambda c, v, u: time.sleep(4) or (200, {}), "https://x")
        self.assertTrue(api.start(self.loop))
        try:
            con = http.client.HTTPConnection("127.0.0.1", api.port, timeout=10)
            con.request("POST", "/api/cmd", json.dumps({"cmd": "CMD_LIGHT_LOFT_WEST", "value": 1}),
                        {"Content-Type": "application/json", "X-Client-DN": "CN=x"})
            self.assertEqual(con.getresponse().status, 503)
            con.close()
        finally:
            api.stop()


class ApiLogTest(unittest.TestCase):
    """GET /api/log reads the commands table (written by the DB log) with its own read-only connection."""

    def setUp(self):
        from uhagatepy.db_log import DbLog
        self.folder = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.folder.name, "log.db")
        self.defs = cmd_defs()
        db = DbLog(config.Config(log_db=self.path), self.defs)
        db._writer._ntp_ok = lambda: True
        db.start()
        self.assertTrue(db._writer.init_done.wait(10))
        db.tick(time.time())
        for i, (cmd_id, value) in enumerate(((201, 100.0), (201, 0.0), (250, 2.0), (299, 1.5), (777, 1.0))):
            db.on_command(1000 + i, "martin-pc" if i < 4 else "zena-telefon", cmd_id, value, i)
        db.stop()
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self.loop.run_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.loop.call_soon_threadsafe(self.loop.stop)
        self.thread.join(timeout=5)
        self.loop.close()
        self.folder.cleanup()

    def get(self, api, path, dn="CN=martin-pc"):
        self.assertTrue(api.start(self.loop))
        try:
            con = http.client.HTTPConnection("127.0.0.1", api.port, timeout=5)
            con.request("GET", path, headers={"X-Client-DN": dn} if dn else {})
            r = con.getresponse()
            answer = r.status, json.loads(r.read())
            con.close()
            return answer
        finally:
            api.stop()

    def test_newest_first_with_names(self):
        status, rows = self.get(ApiServer(0, self.defs, None, "https://x", self.path), "/api/log")
        self.assertEqual(status, 200)
        self.assertEqual([(r["ts"], r["user"], r["cmd"], r["value"], r["seq"]) for r in rows], [
            (1004, "zena-telefon", "#777", 1.0, 4),                     # id no longer in the YAML: still shown
            (1003, "martin-pc", "CMD_TEST_FLOAT", 1.5, 3),
            (1002, "martin-pc", "CMD_SCREEN_EAST", 2, 2),
            (1001, "martin-pc", "CMD_LIGHT_LOFT_WEST", 0, 1),
            (1000, "martin-pc", "CMD_LIGHT_LOFT_WEST", 100, 0)])
        self.assertEqual(rows[3]["desc"], "Loft west light, 0 = off, 100 = on")

    def test_limit_and_errors(self):
        api = lambda path="": ApiServer(0, self.defs, None, "https://x", path)     # noqa: E731
        self.assertEqual(len(self.get(api(self.path), "/api/log?limit=2")[1]), 2)
        self.assertEqual(self.get(api(self.path), "/api/log?limit=x")[0], 400)
        self.assertEqual(self.get(api(self.path), "/api/log", dn=None)[0], 403)
        self.assertEqual(self.get(api(""), "/api/log")[0], 503)                    # no log-db
        self.assertEqual(self.get(api(os.path.join(self.folder.name, "none.db")), "/api/log")[0], 503)


class DbCommandsTest(unittest.TestCase):
    def test_command_rows(self):
        from uhagatepy.db_log import DbLog
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "log.db")
            db = DbLog(config.Config(log_db=path), cmd_defs())
            db._writer._ntp_ok = lambda: True                              # no timedatectl in the test
            db.on_command(1000, "early", 201, 100.0, 0)                    # before the DB is ready: waits
            db.start()
            self.assertTrue(db._writer.init_done.wait(10))
            db.tick(time.time())                                           # -> ready
            db.on_command(1001, "martin-pc", 201, 0.0, 1)
            db.stop()
            con = sqlite3.connect(path)
            rows = con.execute("SELECT ts, user, cmd_id, value, seq FROM commands ORDER BY ts").fetchall()
            con.close()
        self.assertEqual(rows, [(1000, "early", 201, 100.0, 0), (1001, "martin-pc", 201, 0.0, 1)])


if __name__ == "__main__":
    unittest.main()
