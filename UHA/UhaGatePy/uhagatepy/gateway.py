"""The gateway: one asyncio event loop that

  - reads the serial port when data arrives and sorts the packets (old 0x221, VARS2 tunnel, log),
  - once per second writes the JSON files, sends the RTC sync every minute and checks the link,
  - logs start-up, link changes and periodic summaries (never one line per second).

Everything runs in one thread, so the stores need no locks.
"""
import asyncio
import os
import signal
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, Set

from . import VERSION, config, event_log, outputs, rpiserp, rtc, status, tunnel
from .legacy_table import NUM_OF_VARS
from .log import log
from .serial_link import LinkError, SerialLink
from .store import Store
from .vars_def import VarsFile

PACKET_OLD_VARIABLE = 0x221      # ELECON -> RPi: id(2) value(2) valid(2), all big-endian int16
PACKET_LOG = 0x620               # ELECON -> RPi: node log message, 8 bytes


@dataclass
class Counters:
    old_packets: int = 0
    tunnel_packets: int = 0
    log_packets: int = 0
    unknown_packets: int = 0          # packet ids we do not know
    malformed: int = 0                # known packet id but too short
    out_of_range_vars: int = 0        # old variable id >= NUM_OF_VARS
    wrong_producer: int = 0           # tunnel packet from a node that is not the variable's producer
    tx_packets: int = 0
    tx_errors: int = 0
    rtc_sent: int = 0
    write_errors: int = 0             # output files
    event_log_errors: int = 0         # log.txt
    tunnel_drops: Dict[str, int] = field(default_factory=lambda: {"length": 0, "unknown_id": 0, "bad_value": 0})


@dataclass
class NodeStats:
    packets: int = 0
    last_mono: float = 0.0
    last_unix: int = 0
    last_event: str = ""


class Gateway:
    def __init__(self, cfg: config.Config, defs: VarsFile) -> None:
        self.cfg = cfg
        self.defs = defs
        self.link = SerialLink(cfg.port)
        self.parser = rpiserp.Parser()
        self.store = Store(defs, cfg.compare_window_ms / 1000)
        self.counters = Counters()
        self.tunnel_nodes: Dict[int, NodeStats] = {}   # node id -> tunnel packets from that producer
        self.log_nodes: Dict[int, NodeStats] = {}      # node id -> log messages from that node

        self.start_mono = time.monotonic()
        self.start_unix = int(time.time())
        self.link_change_mono = self.start_mono        # when the link last went up or down
        self.link_change_unix = self.start_unix
        self.reconnects = 0
        self.had_link = False
        self.receiving = False            # a packet arrived since the link went up (or since a silence warning)
        self.silence_warned = False
        self.last_packet_mono = -1.0
        self.last_open_error = ""
        self._last_open_error_log = -1e9
        self._open_attempts = 0
        self._next_reopen_mono = 0.0
        self._last_rtc_slot = -1

        self._logged: Set[str] = set()    # error messages already logged in this summary period
        self._reported: Dict[str, int] = {}
        self._compare_prev: Dict[int, tuple] = {}
        self._next_error_summary = self.start_mono + cfg.error_summary_s
        self._next_compare_summary = self.start_mono + cfg.compare_summary_s
        self._next_hourly = self.start_mono + 3600
        self._loop: asyncio.AbstractEventLoop = None  # type: ignore[assignment]
        self._stop: asyncio.Event = None              # type: ignore[assignment]

    # ---- run -------------------------------------------------------------------------------

    async def run(self) -> int:
        self._loop = asyncio.get_running_loop()
        self._stop = asyncio.Event()
        for sig in (signal.SIGINT, signal.SIGTERM):
            self._loop.add_signal_handler(sig, self._on_stop_signal, sig)
        self._loop.add_signal_handler(signal.SIGHUP, lambda: log.info("SIGHUP ignored (restart the service to reload)"))

        log.info("UhaGatePy %s starting (pid %d)", VERSION, os.getpid())
        log.info("%s", config.describe(self.cfg))
        log.info("variables: %d from %s (yaml version %d, sha %s)", len(self.defs.by_id), self.cfg.vars_yaml,
                 self.defs.version, self.defs.sha)
        for warning in self.defs.warnings:
            log.warning("variable definitions: %s", warning)
        if not os.access(self.cfg.out_dir, os.W_OK):
            log.error("output folder %s is not writable", self.cfg.out_dir)

        self._open_link()
        ticker = asyncio.create_task(self._tick_loop())
        await self._stop.wait()
        ticker.cancel()
        self._close_link()
        log.info("UhaGatePy stopped")
        return 0

    def _on_stop_signal(self, sig: int) -> None:
        log.info("stopping on signal %s", signal.Signals(sig).name)
        self._stop.set()

    async def _tick_loop(self) -> None:
        """Call _on_tick every json_period_ms without drifting."""
        period = self.cfg.json_period_ms / 1000
        next_time = self._loop.time() + period
        while True:
            await asyncio.sleep(max(0.0, next_time - self._loop.time()))
            next_time += period
            if next_time < self._loop.time():
                next_time = self._loop.time() + period        # we fell behind, do not burst
            try:
                self._on_tick()
            except Exception:                                  # a bug must not stop the gateway
                self._log_once("tick", log.exception, "error in the periodic task")

    def _log_once(self, key: str, log_function: Callable[..., None], message: str, *args) -> None:
        """Log an error only the first time in each error-summary period (no repeating spam)."""
        if key not in self._logged:
            self._logged.add(key)
            log_function(message, *args)

    # ---- serial link -----------------------------------------------------------------------

    def _open_link(self) -> None:
        mono = time.monotonic()
        self._open_attempts += 1
        if self.link.open():
            self._loop.add_reader(self.link.fileno(), self._on_readable)
            if self.had_link:
                self.reconnects += 1
                log.info("serial link up again: %s (down %d s, %d attempts)", self.link.path,
                         mono - self.link_change_mono, self._open_attempts)
            else:
                log.info("serial link up: %s", self.link.path)
            self.had_link = True
            self._open_attempts = 0
            self.last_open_error = ""
            self.link_change_mono = mono
            self.link_change_unix = int(time.time())
            self.receiving = False
            self.silence_warned = False
            self.parser.reset()
            # the nodes get the time right away instead of up to a minute later
            self._last_rtc_slot = int(time.time()) // self.cfg.rtc_period_s
            self._send_rtc()
            return

        self._next_reopen_mono = mono + self.cfg.reopen_s
        if self.link.last_error != self.last_open_error or mono - self._last_open_error_log >= 600:
            log.warning("cannot open serial port %s: %s (retrying every %d s)", self.link.path,
                        self.link.last_error, self.cfg.reopen_s)
            self.last_open_error = self.link.last_error
            self._last_open_error_log = mono

    def _close_link(self) -> None:
        if self.link.is_open:
            try:
                self._loop.remove_reader(self.link.fileno())
            except (OSError, ValueError):
                pass
            self.link.close()

    def _link_lost(self, reason: str) -> None:
        if not self.link.is_open:
            return
        mono = time.monotonic()
        log.warning("serial link lost: %s (was up %d s)", reason, mono - self.link_change_mono)
        self._close_link()
        self.parser.reset()
        self.link_change_mono = mono
        self.link_change_unix = int(time.time())
        self._next_reopen_mono = mono + self.cfg.reopen_s
        self.receiving = False
        self.silence_warned = False
        self.last_open_error = ""

    # ---- receiving -------------------------------------------------------------------------

    def _on_readable(self) -> None:
        try:
            for _ in range(16):                       # bounded, so a flood cannot starve the timer
                data = self.link.read()
                if not data:
                    return
                for packet in self.parser.feed(data):
                    self._on_packet(packet)
        except LinkError as e:
            self._link_lost(str(e))
        except Exception:
            self._log_once("rx", log.exception, "error while processing received data")

    def _on_packet(self, packet: rpiserp.Packet) -> None:
        mono = time.monotonic()
        unix = int(time.time())
        if not self.receiving:
            log.info("receiving data")
            self.receiving = True
            self.silence_warned = False
        self.last_packet_mono = mono

        if packet.id == PACKET_OLD_VARIABLE:
            self._on_old_variable(packet, mono, unix)
        elif tunnel.is_tunnel(packet.id):
            self._on_tunnel(packet, mono, unix)
        elif packet.id == PACKET_LOG:
            self._on_log_message(packet, mono, unix)
        else:
            self.counters.unknown_packets += 1
            log.debug("unknown packet id 0x%03X, %d data bytes", packet.id, len(packet.data))

    def _on_old_variable(self, packet: rpiserp.Packet, mono: float, unix: int) -> None:
        self.counters.old_packets += 1
        data = packet.data
        if len(data) < 4:
            self.counters.malformed += 1
            return
        var_id = (data[0] << 8) | data[1]
        raw = int.from_bytes(data[2:4], "big", signed=True)
        valid = len(data) < 6 or int.from_bytes(data[4:6], "big") != 0   # UhaGate6 ignored this field
        if var_id >= NUM_OF_VARS:
            self.counters.out_of_range_vars += 1
            return
        log.debug("old var %d = %d%s", var_id, raw, "" if valid else " (invalid)")
        self.store.set_old(var_id, raw, valid, mono, unix)

    def _on_tunnel(self, packet: rpiserp.Packet, mono: float, unix: int) -> None:
        self.counters.tunnel_packets += 1
        self._touch(self.tunnel_nodes, packet.id & 0x0F, mono, unix)
        try:
            value = tunnel.decode(packet, self.defs)
        except tunnel.TunnelDrop as drop:
            self.counters.tunnel_drops[drop.reason] += 1
            log.debug("tunnel packet 0x%03X dropped: %s", packet.id, drop.reason)
            return
        definition = self.defs.by_id[value.var_id]
        if self.defs.node_names.get(value.producer) != definition.producer:
            self.counters.wrong_producer += 1             # still stored: the value itself is fine
            log.debug("%s came from node %d, YAML says %s", definition.name, value.producer, definition.producer)
        mismatch = self.store.set_v2(value, mono, unix)
        if mismatch is not None:
            log.debug("mismatch %s: VARS2 gives %d, old value is %d", definition.name, mismatch[0], mismatch[1])

    def _on_log_message(self, packet: rpiserp.Packet, mono: float, unix: int) -> None:
        self.counters.log_packets += 1
        line = event_log.format_line(packet.data, self.defs.node_names, time.localtime())
        node = packet.data[0] if packet.data else 0
        event = event_log.EVENT_NAMES.get(packet.data[1] if len(packet.data) > 1 else -1, "UNKNOWN_EVENT")
        self._touch(self.log_nodes, node, mono, unix, event)
        log.info("node event: %s", line.split(" ", 2)[2].rstrip())      # the journal has its own time stamp
        try:
            event_log.append(self.cfg.log_file, line)
        except OSError as e:
            self.counters.event_log_errors += 1
            self._log_once("log.txt", log.error, "cannot append to %s: %s", self.cfg.log_file, e)

    @staticmethod
    def _touch(nodes: Dict[int, NodeStats], node: int, mono: float, unix: int, event: str = "") -> None:
        stats = nodes.setdefault(node, NodeStats())
        stats.packets += 1
        stats.last_mono = mono
        stats.last_unix = unix
        if event:
            stats.last_event = event

    # ---- sending ---------------------------------------------------------------------------

    def _send(self, packet_id: int, data: bytes) -> bool:
        try:
            sent = self.link.write(rpiserp.encode(packet_id, data))
        except LinkError as e:
            self.counters.tx_errors += 1
            self._link_lost(str(e))
            return False
        if sent:
            self.counters.tx_packets += 1
        else:
            self.counters.tx_errors += 1
        return sent

    def _send_rtc(self) -> None:
        now = time.time()
        payload, summer = rtc.payload(now)
        if self._send(rtc.PACKET_ID, payload):
            self.counters.rtc_sent += 1
            log.info("RTC sync sent: %s (%s time)", time.strftime("%d.%m.%Y %H:%M:%S", time.localtime(now)),
                     "summer" if summer else "winter")
        else:
            log.warning("RTC sync not sent: %s", self.link.last_error)

    # ---- once per period -------------------------------------------------------------------

    def _on_tick(self) -> None:
        mono = time.monotonic()
        now = time.time()

        if not self.link.is_open and mono >= self._next_reopen_mono:
            self._open_link()

        self._write_outputs(mono, now)

        slot = int(now) // self.cfg.rtc_period_s          # changes every minute with the default 60 s
        if slot != self._last_rtc_slot:
            self._last_rtc_slot = slot
            if self.link.is_open:
                self._send_rtc()

        if self.link.is_open and not self.silence_warned:
            reference = self.last_packet_mono if self.receiving else self.link_change_mono
            if mono - reference > self.cfg.silence_warn_s:
                log.warning("serial link open but no packets for %d s", self.cfg.silence_warn_s)
                self.silence_warned = True
                self.receiving = False

        self._periodic_reports(mono)

    def _write_outputs(self, mono: float, now: float) -> None:
        unix = int(now)
        raw = self.store.snapshot(mono)
        builders = {
            "uha.json": lambda: outputs.build_uha_json(raw, unix),
            "bms.json": lambda: outputs.build_bms_json(raw, unix),
            "uha2.json": lambda: outputs.build_uha2_json(self.store, self.defs, mono, unix),
            "uha_status.json": lambda: outputs.to_json(status.build(self, unix, mono)),
        }
        for name, build in builders.items():
            path = os.path.join(self.cfg.out_dir, name)
            try:
                outputs.write_atomic(path, build())
            except OSError as e:
                self.counters.write_errors += 1
                self._log_once("write " + name, log.error, "cannot write %s: %s", path, e)
            except Exception:
                self._log_once("build " + name, log.exception, "cannot build %s", name)

    # ---- summaries -------------------------------------------------------------------------

    def _delta(self, key: str, value: int) -> int:
        """Increase of a counter since the last summary."""
        change = value - self._reported.get(key, 0)
        self._reported[key] = value
        return change

    def _periodic_reports(self, mono: float) -> None:
        if mono >= self._next_error_summary:
            self._next_error_summary = mono + self.cfg.error_summary_s
            self._logged.clear()
            self._error_summary()
        if mono >= self._next_compare_summary:
            self._next_compare_summary = mono + self.cfg.compare_summary_s
            self._compare_summary()
        if mono >= self._next_hourly:
            self._next_hourly = mono + 3600
            old_vars = len(self.store.old)
            log.info("hourly: link %s, packets %d (old %d, tunnel %d), variables seen: old %d / VARS2 %d, "
                     "checksum errors %d, reconnects %d, RTC syncs %d, RSS %d kB",
                     "up" if self.link.is_open else "down", self.parser.packets, self.counters.old_packets,
                     self.counters.tunnel_packets, old_vars, len(self.store.v2), self.parser.checksum_errors,
                     self.reconnects, self.counters.rtc_sent, status.rss_kb())

    def _error_summary(self) -> None:
        c = self.counters
        problems = {
            "checksum errors": self._delta("checksum", self.parser.checksum_errors),
            "length errors": self._delta("length", self.parser.length_errors),
            "unknown packet ids": self._delta("unknown", c.unknown_packets),
            "short packets": self._delta("malformed", c.malformed),
            "old ids out of range": self._delta("range", c.out_of_range_vars),
            "tunnel packets dropped": self._delta("drops", sum(c.tunnel_drops.values())),
            "tunnel packets from the wrong node": self._delta("producer", c.wrong_producer),
            "values clamped to int16": self._delta("clamped", self.store.clamped),
            "transmit errors": self._delta("tx", c.tx_errors),
            "output write errors": self._delta("write", c.write_errors),
            "log.txt write errors": self._delta("logfile", c.event_log_errors),
        }
        found = [f"{count} {what}" for what, count in problems.items() if count > 0]
        if found:
            log.warning("in the last %d s: %s", self.cfg.error_summary_s, ", ".join(found))

    def _compare_summary(self) -> None:
        """Old vs VARS2: the main check of the migration (every format sends the same data)."""
        compared = mismatched = 0
        worst = []
        for var_id, (total, bad) in self.store.compared.items():
            previous_total, previous_bad = self._compare_prev.get(var_id, (0, 0))
            compared += total - previous_total
            mismatched += bad - previous_bad
            if bad > previous_bad:
                worst.append((bad - previous_bad, total - previous_total, self.defs.by_id[var_id].name))
            self._compare_prev[var_id] = (total, bad)
        period = self.cfg.compare_summary_s
        if compared == 0:
            log.info("old vs VARS2 (last %d s): nothing to compare, %d variables received in VARS2 format",
                     period, len(self.store.v2))
            return
        worst.sort(reverse=True)
        text = "old vs VARS2 (last %d s): %d values compared, %d mismatches (%.1f %%)" % (
            period, compared, mismatched, 100.0 * mismatched / compared)
        if worst:
            text += "; worst: " + ", ".join("%s %d/%d" % (name, bad, total) for bad, total, name in worst[:5])
        (log.warning if mismatched * 20 > compared else log.info)("%s", text)
