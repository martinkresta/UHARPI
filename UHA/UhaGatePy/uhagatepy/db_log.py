"""VARS2 log into a SQLite database (for the Grafana charts).

Which variables: those with `log_s` (10 or 60) in uha_vars.yaml. `agg` says how an interval becomes one value:
  avg    mean of the valid values received in [ts, ts + log_s); none -> NULL (a gap in the chart)
  delta  counter (energy / water today or total): the increment since the previous interval is stored, so any
         consumption is SUM(value). A drop below half of the previous value is a reset (midnight, node restart):
         the increment is then the new value itself. The increment may be slightly negative (LEMON counters can
         drop a little) - it is kept, the sum stays right.
  event  states (lights, relays, modes; YAML group States, no log_s): one row in `events` per change of the value
         or of valid (invalid -> NULL). Refresh frames with the same value are dropped. After a gateway start the
         first value of each event variable is stored, so the state is known again.

Two halves:
  DbLog    runs in the asyncio loop of the gateway. Gets every tunnel value (on_value) and the 1 s tick, collects
           the intervals in memory and hands a batch of finished rows to the writer about every 60 s. Cheap, never
           touches the disk, never blocks.
  _Writer  one thread that does all SQLite work: opens the file, waits for NTP, writes the batches (one
           transaction each), computes agg_15min, deletes old raw rows once a day, guards the size, logs a summary.

Nothing here may stop the gateway: every exception is caught and logged (rate-limited). If the database cannot
be opened the gateway runs without logging (the writer retries every minute).

Tables (time = UTC unix seconds, ts = start of the interval, a multiple of its length):
  vars           id, name, unit, log_s, agg - all YAML variables, refreshed at every start (log_s NULL = not logged)
  raw            var_id, ts, value - one row per variable and log_s interval, kept log-raw-days
  agg_15min      var_id, ts, value - AVG (avg) or SUM (delta) of raw over 15 min, kept forever
  counter_state  var_id, ts, value - last counter value of each delta variable, so a restart continues the deltas
  events         var_id, ts, value - one row per change of an event variable (ts = receive time; two changes in
                 one second: the last one is kept), kept forever
"""
import os
import queue
import shutil
import sqlite3
import subprocess
import threading
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from .log import log
from .vars_def import VarsFile

AGG_S = 900                  # agg_15min window
SUMMARY_S = 600              # journal summary period
RETENTION_PERIOD_S = 86400   # delete old raw rows once a day
OPEN_RETRY_S = 60            # retry opening the database
NTP_RETRY_S = 10             # re-check the NTP state while waiting
ERROR_REPEAT_S = 600         # the same error is logged at most once in this time
SPACE_WARN_S = 3600          # "not writing, no space" at most once an hour
QUEUE_BATCHES = 30           # batches the loop may hand over before the writer catches up (30 min)

SCHEMA = """
CREATE TABLE IF NOT EXISTS vars (id INTEGER PRIMARY KEY, name TEXT, unit TEXT, log_s INTEGER, agg TEXT);
CREATE TABLE IF NOT EXISTS raw (var_id INTEGER, ts INTEGER, value REAL, PRIMARY KEY (var_id, ts)) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS agg_15min (var_id INTEGER, ts INTEGER, value REAL, PRIMARY KEY (var_id, ts)) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS counter_state (var_id INTEGER PRIMARY KEY, ts INTEGER, value REAL);
CREATE TABLE IF NOT EXISTS events (var_id INTEGER, ts INTEGER, value REAL, PRIMARY KEY (var_id, ts)) WITHOUT ROWID;
"""

# AVG or SUM of the raw rows per variable and 15 min window. "vars CROSS JOIN raw" makes SQLite loop over the
# variables and read each one's range from the raw primary key, instead of scanning the whole raw table.
AGG_SQL = """
INSERT OR REPLACE INTO agg_15min (var_id, ts, value)
SELECT r.var_id, r.ts - r.ts % 900, CASE WHEN v.agg = 'delta' THEN SUM(r.value) ELSE AVG(r.value) END
FROM vars v CROSS JOIN raw r ON r.var_id = v.id AND r.ts >= ? AND r.ts < ?
WHERE v.log_s IS NOT NULL
GROUP BY r.var_id, r.ts - r.ts % 900
"""

_errors_logged: Dict[str, float] = {}       # error key -> monotonic time it was last logged


def _log_error(key: str, message: str, *args, exc: bool = False) -> None:
    """Log an error, but the same `key` at most once every ERROR_REPEAT_S (no spam from a broken disk)."""
    now = time.monotonic()
    if now - _errors_logged.get(key, -1e9) >= ERROR_REPEAT_S:
        _errors_logged[key] = now
        (log.exception if exc else log.error)("DB log: " + message, *args)


def _round7(x: float) -> float:
    """7 significant digits (float32 precision): 3.305 instead of 3.3050000667572021."""
    return float(f"{x:.7g}")


@dataclass
class Batch:
    rows: List[Tuple[int, int, Optional[float]]]          # (var_id, ts, value) for the raw table
    counters: List[Tuple[int, int, float]]                # (var_id, ts, value) for counter_state
    closed_until: int                                     # all 60 s intervals before this time are in `rows`
    events: List[Tuple[int, int, Optional[float]]] = field(default_factory=list)   # (var_id, ts, value) for events


@dataclass
class Stats:
    """Counters for the summary (the loop and the writer each write their own fields)."""
    rows: int = 0               # rows written
    null_rows: int = 0          # of them NULL (no valid value)
    batches: int = 0
    agg_rows: int = 0
    skipped_batches: int = 0    # not written: size limit or no free disk space
    dropped_batches: int = 0    # queue full (writer too slow or stuck)
    write_errors: int = 0
    event_rows: int = 0         # rows written into events
    max_write_ms: float = 0.0
    reported: Dict[str, int] = field(default_factory=dict)


class DbLog:
    """Loop side. Created by the Gateway; does nothing when log-db is not set."""

    def __init__(self, cfg, defs: VarsFile) -> None:
        self.cfg = cfg
        self.enabled = bool(cfg.log_db)
        self.logged = sorted((d for d in defs.by_id.values() if d.log_s), key=lambda d: d.id)
        self.by_id = {d.id: d for d in self.logged}
        self.events = {d.id: d for d in defs.by_id.values() if d.agg == "event"}   # one row per change
        self.periods: Dict[int, list] = {}                # log_s -> its variables
        for d in self.logged:
            self.periods.setdefault(d.log_s, []).append(d)
        self.stats = Stats()
        self.ready = False                                # True once the writer has opened the DB and NTP is ok

        self._slot: Dict[int, Optional[int]] = {p: None for p in self.periods}   # log_s -> start of current slot
        self._acc: Dict[int, List[float]] = {}            # avg: var_id -> [sum, count] in the current slot
        self._last: Dict[int, float] = {}                 # delta: var_id -> last valid value in the current slot
        self._prev: Dict[int, Tuple[int, float]] = {}     # delta: var_id -> (ts, previous counter value)
        self._check: Dict[int, List[float]] = {}          # delta self-check: var_id -> [start value, sum of deltas]
        self._rows: List[Tuple[int, int, Optional[float]]] = []
        self._ev_last: Dict[int, Optional[float]] = {}    # event: var_id -> value last stored (None = invalid)
        self._ev_rows: List[Tuple[int, int, Optional[float]]] = []
        self._queue: "queue.Queue[Optional[Batch]]" = queue.Queue(maxsize=QUEUE_BATCHES)
        self._writer = _Writer(self, defs) if self.enabled else None

    # ---- called by the gateway -------------------------------------------------------------

    def start(self) -> None:
        if not self.enabled:
            log.info("DB log: off (log-db not set)")
            return
        n10 = len(self.periods.get(10, []))
        n_delta = sum(1 for d in self.logged if d.agg == "delta")
        log.info("DB log: %s, %d variables (%d every 10 s, %d every 60 s, %d of them counters), raw kept %d days, "
                 "limits %d MB / free %d MB", self.cfg.log_db, len(self.logged), n10, len(self.logged) - n10, n_delta,
                 self.cfg.log_raw_days, self.cfg.log_max_mb, self.cfg.log_min_free_mb)
        log.info("DB log: %d event variables (one row per change, table events)", len(self.events))
        if not self.logged:
            log.warning("DB log: no variable has log_s in the YAML - nothing to log")
        self._writer.start()

    def on_value(self, var_id: int, value: float, valid: bool, unix: int) -> None:
        """A VARS2 value arrived (from Gateway._on_tunnel)."""
        if not self.ready:
            return
        if var_id in self.events:
            self._on_event(var_id, value, valid, unix)
            return
        definition = self.by_id.get(var_id)
        if definition is None:
            return
        try:
            self._advance(unix)                 # a value of the next interval closes the current one first
            if not valid:
                return                          # invalid = no value; an interval without any valid value is NULL
            if definition.agg == "delta":
                self._last[var_id] = float(value)
            else:
                acc = self._acc.get(var_id)
                if acc is None:
                    self._acc[var_id] = [float(value), 1]
                else:
                    acc[0] += value
                    acc[1] += 1
        except Exception:
            _log_error("on_value", "error while collecting a value", exc=True)

    def _on_event(self, var_id: int, value: float, valid: bool, unix: int) -> None:
        """Event variable: a row only when value or valid differ from what was stored last (first value: always)."""
        try:
            new = _round7(float(value)) if valid else None
            if var_id in self._ev_last and self._ev_last[var_id] == new:
                return                          # refresh frame, same state
            self._ev_last[var_id] = new
            self._ev_rows.append((var_id, int(unix), new))
        except Exception:
            _log_error("on_event", "error while collecting an event", exc=True)

    def tick(self, now: float) -> None:
        """Every second (from Gateway._on_tick): close finished intervals."""
        if not self.enabled:
            return
        try:
            if not self.ready:
                if self._writer.init_done.is_set():
                    self._begin(self._writer.init_counters)
                return
            self._advance(int(now))
        except Exception:
            _log_error("tick", "error in the periodic task", exc=True)

    def stop(self) -> None:
        """Hand the finished rows to the writer and let it finish (the current, unfinished intervals are lost)."""
        if not self.enabled or not self._writer.is_alive():
            return
        try:
            if self.ready and (self._rows or self._ev_rows):
                self._send(closed_until=0)
            self._queue.put(None, timeout=2)
        except Exception:
            _log_error("stop", "error while stopping", exc=True)
        self._writer.join(timeout=10)
        if self._writer.is_alive():
            log.warning("DB log: writer did not finish in 10 s")

    def status(self) -> dict:
        """Small block for uha_status.json."""
        s = self.stats
        w = self._writer
        return {
            "Enabled": self.enabled, "Writing": self.ready and not (w and w.space_blocked),
            "State": w.state if w else "off",
            "Rows": s.rows, "NullRows": s.null_rows, "Batches": s.batches, "AggRows": s.agg_rows,
            "EventRows": s.event_rows, "SkippedBatches": s.skipped_batches, "DroppedBatches": s.dropped_batches, "WriteErrors": s.write_errors,
            "DbMb": round(w.db_bytes / 1e6, 1) if w else None, "FreeMb": int(w.free_bytes / 1e6) if w else None,
            "LastWriteUnix": w.last_write_unix if w else None,
        }

    # ---- intervals -------------------------------------------------------------------------

    def _begin(self, counters: Dict[int, Tuple[int, float]]) -> None:
        """The writer is ready: take the counter values saved by the last run and start collecting."""
        self._prev = {var_id: tv for var_id, tv in counters.items() if var_id in self.by_id}
        self._check = {var_id: [tv[1], 0.0] for var_id, tv in self._prev.items()}
        self.ready = True
        log.info("DB log: collecting (%d counters continue from the last run)", len(self._prev))

    def _advance(self, unix: int) -> None:
        """Close every interval that ended before `unix`; after a 60 s interval send the batch."""
        sent_until = None
        for period, definitions in self.periods.items():
            slot = unix - unix % period
            current = self._slot[period]
            if current is None:
                self._slot[period] = slot               # first interval after the start (only partly covered)
            elif slot > current:                        # a clock jump backwards keeps collecting into `current`
                self._close(definitions, current)
                self._slot[period] = slot
                if period == 60:
                    sent_until = current + 60
        if sent_until is not None:
            self._send(sent_until)

    def _close(self, definitions: list, ts: int) -> None:
        for d in definitions:
            if d.agg == "delta":
                value = self._counter_delta(d, ts)
            else:
                acc = self._acc.pop(d.id, None)
                value = _round7(acc[0] / acc[1]) if acc else None
            self._rows.append((d.id, ts, value))

    def _counter_delta(self, d, ts: int) -> Optional[float]:
        """Increment of a counter in the interval starting at ts (None = no valid value, or only the baseline)."""
        new = self._last.pop(d.id, None)
        if new is None:
            return None                             # prev stays, the next valid value gives the whole increment
        new = _round7(new)
        previous = self._prev.get(d.id)
        self._prev[d.id] = (ts, new)
        if previous is None:                        # very first value ever: only the baseline
            self._check[d.id] = [new, 0.0]
            log.info("DB log: counter %s starts at %g", d.name, new)
            return None
        prev = previous[1]
        check = self._check.setdefault(d.id, [prev, 0.0])
        if prev > 0 and new < 0.5 * prev:           # reset (midnight or node restart)
            self._report_reset(d, prev, new, check)
            self._check[d.id] = [0.0, new]
            return new
        delta = _round7(new - prev)
        check[1] += delta
        return delta

    @staticmethod
    def _report_reset(d, prev: float, new: float, check: List[float]) -> None:
        """Self-check: the deltas summed since the last reset (or start) must equal how far the counter went."""
        start, total = check
        expected = prev - start
        log.info("DB log: counter %s reset %g -> %g; deltas since the last reset/start sum to %g, counter went "
                 "%g -> %g = %g (difference %g)", d.name, prev, new, total, start, prev, expected,
                 _round7(total - expected))

    def _send(self, closed_until: int) -> None:
        counters = [(var_id, ts, value) for var_id, (ts, value) in self._prev.items()]
        batch = Batch(self._rows, counters, closed_until, self._ev_rows)
        self._rows = []
        self._ev_rows = []
        try:
            self._queue.put_nowait(batch)
        except queue.Full:
            self.stats.dropped_batches += 1
            _log_error("queue", "writer is behind, %d rows + %d events dropped (queue of %d batches full)",
                       len(batch.rows), len(batch.events), QUEUE_BATCHES)


class _Writer(threading.Thread):
    """All SQLite work, in its own thread."""

    def __init__(self, owner: DbLog, defs: VarsFile) -> None:
        super().__init__(name="db_log", daemon=True)
        self.owner = owner
        self.cfg = owner.cfg
        self.defs = defs
        self.path = owner.cfg.log_db
        self.folder = os.path.dirname(os.path.abspath(self.path))
        self.stats = owner.stats
        self.con: Optional[sqlite3.Connection] = None
        self.init_done = threading.Event()                 # DB open + NTP ok: the loop may start collecting
        self.init_counters: Dict[int, Tuple[int, float]] = {}
        self.state = "starting"                            # for uha_status.json
        self.space_blocked = False
        self.db_bytes = 0
        self.free_bytes = 0
        self.last_write_unix: Optional[int] = None
        self._agg_next: Optional[int] = None               # first 15 min window not yet aggregated
        self._space_warned = -1e9
        self._ntp_since: Optional[float] = None            # when the wait for NTP started
        self._ntp_logged = 0.0
        self._next_summary = time.monotonic() + SUMMARY_S
        self._next_retention = 0.0

    def run(self) -> None:
        try:
            self._main()
        except Exception:
            self.state = "crashed"
            log.exception("DB log: writer stopped by an error - no more logging, the gateway runs on")
        finally:
            if self.con is not None:
                try:
                    self.con.close()
                except sqlite3.Error:
                    pass

    def _main(self) -> None:
        if not self._wait(self._open, "open", OPEN_RETRY_S):
            return
        if not self._wait(self._ntp_ok, "ntp", NTP_RETRY_S):
            return
        self.init_counters = {var_id: (ts, value) for var_id, ts, value in
                              self.con.execute("SELECT var_id, ts, value FROM counter_state")}
        self.state = "writing"
        self.init_done.set()
        self._next_retention = time.monotonic() + 300      # first clean-up 5 min after the start
        while True:
            try:
                item = self.owner._queue.get(timeout=5)
            except queue.Empty:
                item = False
            if item is None:
                break                                       # stop
            try:
                if item:
                    self._write(item)
                now = time.monotonic()
                if now >= self._next_retention:
                    self._next_retention = now + RETENTION_PERIOD_S
                    self._retention()
                if now >= self._next_summary:
                    self._next_summary = now + SUMMARY_S
                    self._summary()
            except Exception:
                _log_error("writer", "error in the writer", exc=True)
        log.info("DB log: writer stopped (%d rows written since start)", self.stats.rows)

    def _wait(self, step, what: str, retry_s: int) -> bool:
        """Repeat `step` until it returns True. False when the gateway stops meanwhile."""
        while not step():
            try:
                if self.owner._queue.get(timeout=retry_s) is None:
                    return False
            except queue.Empty:
                pass
        return True

    # ---- open, NTP -------------------------------------------------------------------------

    def _open(self) -> bool:
        self.state = "opening"
        try:
            os.makedirs(self.folder, exist_ok=True)
            new_file = not os.path.exists(self.path)
            # Grafana (the group of the folder) must read the file and write the -shm file. SQLite gives -wal / -shm
            # the mode of the database file, so the file gets 0660 before SQLite opens it (an empty file is a valid
            # empty database); files of an older run are fixed as well.
            if new_file:
                os.close(os.open(self.path, os.O_CREAT | os.O_WRONLY, 0o660))
            for suffix in ("", "-wal", "-shm"):
                if os.path.exists(self.path + suffix):
                    os.chmod(self.path + suffix, 0o660)
            con = sqlite3.connect(self.path, timeout=30, isolation_level=None)   # autocommit, BEGIN/COMMIT below
            has_tables = con.execute("SELECT count(*) FROM sqlite_master WHERE type = 'table'").fetchone()[0] > 0
            if not has_tables:
                con.execute("PRAGMA auto_vacuum = INCREMENTAL")    # only works before the first table exists
            mode = con.execute("PRAGMA journal_mode = WAL").fetchone()[0]
            con.execute("PRAGMA synchronous = NORMAL")              # safe with WAL, fewer writes to the SD card
            con.executescript(SCHEMA)
            con.execute("BEGIN")
            con.execute("DELETE FROM vars")
            con.executemany("INSERT INTO vars (id, name, unit, log_s, agg) VALUES (?, ?, ?, ?, ?)",
                            [(d.id, d.name, d.unit, d.log_s or None,
                              d.agg if d.log_s or d.agg == "event" else None)
                             for d in sorted(self.defs.by_id.values(), key=lambda d: d.id)])
            con.execute("COMMIT")
            self._agg_next = self._last_agg_end(con)
            auto_vacuum = con.execute("PRAGMA auto_vacuum").fetchone()[0]
        except (sqlite3.Error, OSError) as e:
            self.state = "cannot open"
            _log_error("open", "cannot open %s: %s (retrying every %d s, the gateway runs without logging)",
                       self.path, e, OPEN_RETRY_S)
            return False
        self.con = con
        self._update_sizes()
        log.info("DB log: opened %s (%s, journal %s, auto_vacuum %s), %.1f MB, %d MB free%s", self.path,
                 "new file" if new_file else "existing", mode, {0: "none", 1: "full", 2: "incremental"}.get(auto_vacuum),
                 self.db_bytes / 1e6, self.free_bytes / 1e6,
                 "" if self._agg_next is None else ", agg_15min up to " + _local(self._agg_next))
        if auto_vacuum != 2:
            log.warning("DB log: auto_vacuum is not incremental, the file will not shrink after the clean-up")
        return True

    def _last_agg_end(self, con: sqlite3.Connection) -> Optional[int]:
        """End of the newest agg_15min window (one index lookup per variable, no full scan)."""
        newest = None
        for d in self.owner.logged:
            ts = con.execute("SELECT MAX(ts) FROM agg_15min WHERE var_id = ?", (d.id,)).fetchone()[0]
            if ts is not None and (newest is None or ts > newest):
                newest = ts
        return None if newest is None else newest + AGG_S

    def _ntp_ok(self) -> bool:
        """The Pi has no RTC and boots with the last saved time: write only once NTP has set the clock."""
        self.state = "waiting for NTP"
        try:
            out = subprocess.run(["timedatectl", "show", "-p", "NTPSynchronized", "--value"],
                                 capture_output=True, text=True, timeout=10).stdout.strip()
        except FileNotFoundError:
            log.warning("DB log: timedatectl not found, assuming the clock is right")
            return True
        except (OSError, subprocess.SubprocessError) as e:
            out = f"error {e}"
        if out == "yes":
            log.info("DB log: clock is NTP synchronized")
            return True
        now = time.monotonic()
        if self._ntp_since is None:
            self._ntp_since = self._ntp_logged = now
            log.warning("DB log: waiting for NTP sync before writing (NTPSynchronized=%s)", out or "?")
        elif now - self._ntp_logged >= 300:
            self._ntp_logged = now
            log.warning("DB log: still waiting for NTP sync (%d s)", now - self._ntp_since)
        return False

    # ---- writing ---------------------------------------------------------------------------

    def _update_sizes(self) -> None:
        size = 0
        for suffix in ("", "-wal"):
            try:
                size += os.path.getsize(self.path + suffix)
            except OSError:
                pass
        self.db_bytes = size
        self.free_bytes = shutil.disk_usage(self.folder).free

    def _space_ok(self) -> bool:
        self._update_sizes()
        too_big = self.db_bytes > self.cfg.log_max_mb * 1e6
        too_full = self.free_bytes < self.cfg.log_min_free_mb * 1e6
        if too_big or too_full:
            now = time.monotonic()
            if not self.space_blocked or now - self._space_warned >= SPACE_WARN_S:
                self._space_warned = now
                log.warning("DB log: NOT WRITING - %s (DB %.0f MB, limit %d MB; free %.0f MB, minimum %d MB)",
                            "database too big" if too_big else "disk almost full", self.db_bytes / 1e6,
                            self.cfg.log_max_mb, self.free_bytes / 1e6, self.cfg.log_min_free_mb)
            self.space_blocked = True
            self.state = "no space"
            return False
        if self.space_blocked:
            log.info("DB log: space is back, writing again (DB %.0f MB, free %.0f MB)",
                     self.db_bytes / 1e6, self.free_bytes / 1e6)
            self.space_blocked = False
            self.state = "writing"
        return True

    def _write(self, batch: Batch) -> None:
        if not self._space_ok():
            self.stats.skipped_batches += 1
            return
        start = time.monotonic()
        con = self.con
        try:
            con.execute("BEGIN")
            con.executemany("INSERT OR REPLACE INTO raw (var_id, ts, value) VALUES (?, ?, ?)", batch.rows)
            con.executemany("INSERT OR REPLACE INTO counter_state (var_id, ts, value) VALUES (?, ?, ?)",
                            batch.counters)
            # same second twice: the later row replaces the earlier one (the last change is kept)
            con.executemany("INSERT OR REPLACE INTO events (var_id, ts, value) VALUES (?, ?, ?)", batch.events)
            agg_rows = self._aggregate(batch.closed_until) if batch.closed_until else 0
            con.execute("COMMIT")
        except sqlite3.Error as e:
            self.stats.write_errors += 1
            try:
                con.execute("ROLLBACK")
            except sqlite3.Error:
                pass
            _log_error("write", "cannot write %d rows: %s", len(batch.rows), e)
            return
        ms = (time.monotonic() - start) * 1000
        s = self.stats
        s.rows += len(batch.rows)
        s.null_rows += sum(1 for row in batch.rows if row[2] is None)
        s.event_rows += len(batch.events)
        s.batches += 1
        s.agg_rows += agg_rows
        s.max_write_ms = max(s.max_write_ms, ms)
        self.last_write_unix = int(time.time())
        if ms > 5000:
            log.warning("DB log: writing %d rows took %d ms", len(batch.rows), ms)

    def _aggregate(self, closed_until: int) -> int:
        """Fill agg_15min for all 15 min windows that are complete (also the ones missed while not running)."""
        end = closed_until - closed_until % AGG_S
        earliest = end - self.cfg.log_raw_days * 86400          # older raw rows are gone anyway
        start = earliest if self._agg_next is None else max(self._agg_next, earliest)
        if end <= start:
            return 0
        rows = self.con.execute(AGG_SQL, (start, end)).rowcount
        if end - start > AGG_S:
            log.info("DB log: agg_15min filled %s .. %s (%d rows)", _local(start), _local(end), rows)
        self._agg_next = end
        return rows

    # ---- daily clean-up, summary -----------------------------------------------------------

    def _retention(self) -> None:
        """Delete raw rows older than log-raw-days and give the free pages back to the file system."""
        start = time.monotonic()
        limit = int(time.time()) - self.cfg.log_raw_days * 86400
        con = self.con
        deleted = 0
        try:
            con.execute("BEGIN")
            for (var_id,) in con.execute("SELECT id FROM vars").fetchall():   # per variable: uses the primary key
                deleted += con.execute("DELETE FROM raw WHERE var_id = ? AND ts < ?", (var_id, limit)).rowcount
            con.execute("COMMIT")
            free_pages = con.execute("PRAGMA freelist_count").fetchone()[0]
            con.execute("PRAGMA incremental_vacuum").fetchall()
            con.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchall()
        except sqlite3.Error as e:
            try:
                con.execute("ROLLBACK")
            except sqlite3.Error:
                pass
            _log_error("retention", "clean-up failed: %s", e)
            return
        self._update_sizes()
        log.info("DB log: clean-up: %d raw rows older than %s deleted, %d free pages returned, DB %.1f MB, %d ms",
                 deleted, _local(limit), free_pages, self.db_bytes / 1e6, (time.monotonic() - start) * 1000)

    def _summary(self) -> None:
        s = self.stats
        r = s.reported
        delta = {}
        for key in ("rows", "null_rows", "batches", "agg_rows", "skipped_batches", "dropped_batches", "write_errors",
                    "event_rows"):
            value = getattr(s, key)
            delta[key] = value - r.get(key, 0)
            r[key] = value
        self._update_sizes()
        wal = 0
        try:
            wal = os.path.getsize(self.path + "-wal")
        except OSError:
            pass
        events_total = -1
        try:
            events_total = self.con.execute("SELECT count(*) FROM events").fetchone()[0]
        except sqlite3.Error:
            pass
        problems = delta["skipped_batches"] or delta["dropped_batches"] or delta["write_errors"]
        (log.warning if problems else log.info)(
            "DB log: last %d s: %d rows (%d NULL) in %d batches, %d agg rows, %d events (%d in the table), "
            "slowest write %d ms; skipped %d, dropped %d, errors %d; DB %.1f MB (WAL %.1f MB), free %d MB",
            SUMMARY_S, delta["rows"], delta["null_rows"], delta["batches"], delta["agg_rows"], delta["event_rows"],
            events_total, s.max_write_ms, delta["skipped_batches"], delta["dropped_batches"], delta["write_errors"],
            self.db_bytes / 1e6, wal / 1e6, self.free_bytes / 1e6)
        s.max_write_ms = 0.0


def _local(unix: int) -> str:
    return time.strftime("%d.%m. %H:%M", time.localtime(unix))
