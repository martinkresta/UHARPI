# UhaGatePy — findings and plan

Status (2026-11-01): **PRODUCTION runs UhaGatePy since 2026-11-01 09:32** (switched on Martin's request after test
window 1; UhaGate6 disabled, kept as backup, rollback: `sudo /home/pi/UhaGatePy/rollback_to_v6.sh`).
Implemented, reviewed, tested on the PC, on the Pi with a fake ELECON and in a 3-min window on the real link.
Martin approved the plan and the decisions in §6.
On the Pi: `python3-serial` + `python3-yaml` installed (apt), code in `/home/pi/UhaGatePy`,
`uhagatepy.service` enabled (production). Results in §7.
Task: `tasks/uhagatepy_python_gateway.md`. Contract with ELECON: `VARS2_spec.md` §7 (UHA_FW repo).

**Version 0.2.0 (2026-11-13, task `tasks/uhagatepy_vars2_only.md`): VARS2 only.** The old-vs-VARS2 comparison has
done its job, so the old `0x221` path and the comparison are removed. `0x221` packets are only counted
(`Counters.IgnoredOldPackets`). All values come from the VARS2 tunnel; the YAML is the only variable definition.
`uha.json` keys whose id is not in the YAML are 0. Sections 1–7 below describe the earlier two-protocol version
(0.1.x) where they talk about the old path or the comparison; §2 is updated.

**Version 0.3.0 (2026-11-14, task `tasks/vars2_db_logging_grafana.md`): VARS2 log into SQLite** for Grafana
(`db_log.py`, section "VARS2 DB log" below; Grafana files in `UHA/Grafana/`). Prepared and tested on the Pi with the
fake ELECON; **not yet in production** (waiting for Martin's go).

> **Rollback warning:** UhaGate6 (`rollback_to_v6.sh`) reads only `0x221`. Once the nodes stop the old format
> (migration step 6b) it shows no live data.

---

## 1. Findings

### The data we have to handle (`uha_vars.yaml`, version 0)

| Item | Finding |
|------|---------|
| Values | 257 (arrays expanded): 254 float, 2 bool, 1 enum. Max id 381. |
| Producers | ELECON 118, ELECON_D 76, TECHM 31, IOBOARD_D 16, RECU 11, IOBOARD_U 5. |
| `legacy_scale` | 1 (136), 10 (61), 1000 (48), 100 (9), **0.1 (3)** — the 0.1 ones are `*_TODAY_WH` (old unit 10 Wh). |
| `timeout_ms` | 3 s, 6 s, 9 s, 15 s (`auto` = 3 × `period_ms`). |
| `on_can: false` | 112 values (ELECON-local, tunnel only). |
| Old id = VARS2 id | By construction for all rows (checked in step 1), so one id space for both stores. |

### Old `0x221` packet really carries a valid field

On the live link each `0x221` frame is 12 bytes: 6 data bytes = `id(2) value(2) valid(2)` (all big-endian).
UhaGate6 reads only the first 4 and ignores `valid`. UhaGatePy will store the valid flag too.

### `uha.json` (256 keys in UhaGate6) vs. the YAML

- 252 keys map 1:1 to a YAML `legacy:` name.
- **3 keys have no YAML entry:** `VAR_CONS_TODAY_WH` (computed in `uha_json_body.inc` as
  `VAR_CONS_TODAY_10WH * 10`), and two **live variables that are not in the YAML:**
  `VAR_MPPT_ENERGY_TODAY_WH` (id 49) and `VAR_CURR_RECU_A` (id 142). Both arrive on the old
  path (≈ 200 updates in the 12-min test window). They can never come through VARS2 until they
  are added to the YAML (UHA_FW repo, not my task). UhaGatePy keeps them working through the old path.
- 5 YAML legacy names are not in `uha.json` (`AXPERT_BAT_CHARGING_A`, `AXPERT_BAT_DISCHARGING_A`,
  `CONS_TODAY_10WH`, `MPPT_TEMP_C`, `TEMP_KOLARNA`); `AXPERT_BAT_CHARGING_A` and
  `MPPT_BAT_CURRENT_A10` are used for `ChargingA` in `bms.json`. They only show up in `uha2.json`.
- `bms.json` formulas (integer divisions such as `SunPowerW / 11200`, `TodayDiffKwh` in Wh,
  the three keys that never appear) are ported unchanged — quirks included.

### Label mismatch found: id 49

The gateway's old table (`UHA.h`, copied into UhaGate5/6) calls id 49 `VAR_MPPT_ENERGY_TODAY_WH`; the firmware
(`VARS.h`) and the YAML call it `VAR_MPPT_TEMP_C` — the live value (≈ 31..34) is a temperature. The `uha.json` key
keeps the old name (compatibility, brief). The loader accepts such label differences with a warning at start-up;
a real id conflict (same name, different id) stops the program. Id 147 (`TEMP_KOLARNA`) is in the YAML but not in the
old table, so it appears only in `uha2.json`.

### Pi (read-only)

Python 3.11.2, `python3-venv` present, `python3-serial` and `python3-yaml` were missing (installed with Martin's OK, see §7).
Simulation `apt-get -s install python3-serial python3-yaml`: installs exactly these two
(`python3-serial 3.5-1.1`, `python3-yaml 6.0-3+b2`, both from Debian 12.9) and nothing else,
no upgrades, no removals. RAM free ≈ 760 MB, disk 9.3 GB free, production = `uhagate6` (enabled).

---

## 2. Design

Single-threaded `asyncio` loop: `loop.add_reader(serial_fd)` + one 1-second timer + signal handlers.
No threads, no extra packages (journald logging by `<level>` prefixes on stdout, as in UhaGate6).

```
serial bytes ─► rpiserp.Parser ─► packet id? ─┬─ 0x221  ─► ignored (counted)
                                              ├─ 0x180..0x18F ─► tunnel.decode ─► store.v2[id] = value, valid, time, producer
                                              └─ 0x620  ─► event_log (log.txt + journal)
every second:  outputs.write_all(store)  ─► uha.json  bms.json  uha2.json  uha_status.json   (temp file + os.replace)
every minute:  rtc.send()                ─► 0x051, identical to UhaGate6
```

### Modules (`UHA/UhaGatePy/uhagatepy/`, each short and commented)

| File | Content |
|------|---------|
| `main.py` | start-up: configuration, variable definitions, run the gateway |
| `config.py` | defaults, `key = value` file, `argparse` options (same keys as UhaGate6 + `vars-yaml`) |
| `log.py` | logging with journald level prefixes, no per-second output |
| `rpiserp.py` | frame parser (split frames, checksum, length) + encoder, counters |
| `serial_link.py` | open/read/write with pyserial, reconnect every 5 s, link state |
| `vars_def.py` | loads `uha_vars.yaml` (flat `vars:` groups and, since 2026-11-14, `subgroups:`): defaults, producer inheritance (subgroup, else group), arrays, `timeout auto`; `struct`/`validity`/`field` ignored; clear error + exit if invalid |
| `legacy_table.py` | **generated once** from UhaGate6 (`uha_json_body.inc`, `uha_vars.h`): the 256 `uha.json` keys in order with ids. Not invented, not hand-edited |
| `tunnel.py` | decode of a `0x18n` packet (id u16 LE, value 4 B LE as float32 / int32 / uint32, flags, seq) |
| `store.py` | VARS2 store, freshness, legacy conversion |
| `outputs.py` | `uha.json`, `bms.json`, `uha2.json`, `uha_status.json`, atomic writes |
| `event_log.py` | `log.txt` line (same format as UhaGate6) |
| `rtc.py` | RTC sync payload (`0x051`) |
| `status.py` | content of `uha_status.json` |
| `gateway.py` | the event loop: serial link, packet handling, timers, summaries |
| `db_log.py` | (0.3.0) VARS2 log into SQLite: collects intervals in the loop, one writer thread does all disk work |

### Values (0.2.0: VARS2 only)

`uha.json` / `bms.json`: the last received VARS2 value of any age, converted back with `round(value * legacy_scale)`;
0 if never received or not in the YAML (like UhaGate6 for missing values). Freshness (`VALID` and age ≤ `timeout_ms`)
is shown as `valid` in `uha2.json` and in the `Vars2` state lists of `uha_status.json`; a dead producer is caught
by the frozen-node watch. Rounding is half away from zero like C `round()` (Python's `round` is banker's rounding); the result is
clamped to the int16 range and a clamp is counted/logged once.

### `uha.json` / `bms.json` compatibility

Same keys, same order (Python dicts keep it), integral numbers printed as integers (like cJSON), tab indentation.
Text is not byte-identical to UhaGate6 (`"key": value` instead of `"key":<tab>value`, and a few doubles print with
16 instead of 17 digits, e.g. `-7.800000000000001`); both parse to the same numbers. Allowed by the brief. Proof: golden
test against the real UhaGate6 builders compares parsed content, key order included (§5).
`uha2.json` and `uha_status.json` are written compact (one line): with `indent` Python cannot use its fast C encoder
and the Pi spent 7 % of a core on it. View with a browser or `python3 -m json.tool`.

### `uha2.json` (new)

Per YAML name: `value` (physical units; enum also `enum_name`; bool `true/false`), `unit`, `valid`, `age_s`,
`producer` (from the packet id). `valid` = `VALID` flag and age ≤ `timeout_ms`; `value` is `null` if never received.

### `uha_status.json`

All UhaGate6 fields (link, counters, vars, uptime, RSS) plus: packets per id class (tunnel / log / ignored old),
tunnel packets per producer node with last-seen and rate, frozen state per node, unknown VARS2 ids,
wrong-producer count, YAML version, and `Vars2` (count of fresh variables, lists of invalid / stale / never received).

### VARS2 stream summary

Journal every `vars2-summary-s` (10 min): `VARS2 stream: N of 257 fresh; invalid …; stale …; never …`
(warning if anything is stale). The old-vs-new comparison of 0.1.x is removed.

### Config (`uhagatepy.conf`, same style as `uhagate6.conf`)

`port` (default the by-id CP2102 path), `out-dir` (`/dev/shm` in production), `log-file`, `json-period-ms`,
`rtc-period-s`, `reopen-s`, `silence-warn-s`, `error-summary-s`, `vars2-summary-s`, `frozen-after-s`, `vars-yaml`, `verbose`;
0.3.0: `log-db`, `log-raw-days`, `log-max-mb`, `log-min-free-mb` (see "VARS2 DB log").

### Service `uhagatepy.service` (installed, **not enabled**)

`Conflicts=uhagate5.service uhagate6.service`, `Restart=always`, `RestartSec=2`, `MemoryMax=128M`,
`ExecStart=/usr/bin/python3 -u /home/pi/UhaGatePy/uhagatepy.py -c /home/pi/UhaGatePy/uhagatepy.conf`, runs as root like v6.

---

## 3. Scripts (in `UHA/UhaGatePy/`)

| Script | Runs on | What it does |
|--------|---------|--------------|
| `deploy.sh` | PC | copy code + `uha_vars.yaml` to `/home/pi/UhaGatePy`, run unit tests there, install the unit (not enabled), nothing started |
| `test_window.sh [min≤15]` | Pi | as in UHA6 (transient unit, backstop timer, `trap`), but production is **uhagate6**: stops it, runs UhaGatePy, **always restores uhagate6**; saves snapshots, CPU/RSS samples, journal |
| `switch_to_py.sh` | Pi | `enable --now uhagatepy`, `disable uhagate6`; auto-rollback if it does not start |
| `rollback_to_v6.sh` | Pi | `disable --now uhagatepy`, `enable --now uhagate6` (warns: no live data once the nodes send VARS2 only) |
| `tools/fake_elecon.py` | Pi (Linux) | optional: writes tunnel (+ `0x221` with `--old`) + `0x620` frames into a pseudo-terminal, so UhaGatePy can be run completely **without touching the production serial port** (output to `/tmp`) |

`compare_json.py` from the brief is `uhatest.py compare` in `UHA/UHA6` (reused, copied).

---

## 4. Work after approval

1. Install the two packages (with Martin's OK), generate `legacy_table.py`.
2. Implement: (a) serial + parser + RTC, (b) YAML + store + outputs + comparison — may be done by two subagents.
3. Independent reviewer subagent: output compatibility with UhaGate6, spec §7, readability, Pi rules.
4. Test windows (§5). Small commits on `uhagatepy`. No merge, no switch of production.

## 5. Test plan

- **Unit tests** (stdlib `unittest`, PC and Pi): parser (split frames, `0x7F` at chunk end, bad checksum,
  garbage, len 0/1/11), tunnel decode (float / int32 / bool / enum, LE payload in BE packet id, flags,
  NaN), legacy conversion (all scales, rounding half away from zero, int16 clamp, `0.1`), freshness
  selection (fresh / timed out / invalid → old), JSON key order, comparison tolerance.
- **Golden test vs. UhaGate6:** a tiny C++ tool built from `UHA/UHA6/src/outputs.cpp` prints `uha.json`/`bms.json`
  for random variable sets; the Python builders get the same values; keys, order and values must be equal.
- **Fake ELECON on the Pi** (`fake_elecon.py` + pty, output in `/tmp`): full process test incl. tunnel and
  mismatch counters while production keeps running.
- **Test window 1 (old path only, ELECON unchanged):** `uha.json`/`bms.json` vs. UhaGate6 snapshots
  (same keys/order/types, values equal within sampling), CPU, RSS over 10+ min, journal volume, atomic-write reader
  (0 errors), RTC every minute, link state.
- **Test window 2 (after Martin flashes ELECON step 2):** tunnel rates per node, `uha2.json` plausible,
  old-vs-new mismatch summary ≈ 0, no unknown ids / wrong producers.

---

## 6. Decisions (Martin, 2026-11-01: all approved)

1. Install `python3-serial` and `python3-yaml` with apt on the Pi: **done**.
2. Variables 49 and 142 stay on the old path only (142 is not in the YAML; 49 is in the YAML under another name).
3. Old `valid` flag: stored and shown in `uha2.json`; the value is used even when `valid = 0` (as UhaGate6).
4. `tools/fake_elecon.py`: included.
5. Test windows (≤ 15 min, production restored automatically) are allowed — **but Martin wants to be told and to
   confirm before UhaGate6 is stopped** for each one. Tests without the production port (unit tests, fake ELECON in
   `/tmp`) run without asking.

## 7. Results so far

### PC and Pi, no production port
- 56 unit tests (PC and Pi): parser, tunnel decoding (float / int32 / uint32 / bool / enum, LE inside BE id, flags,
  NaN), legacy conversion (all scales incl. 0.1, rounding half away from zero, int16 clamp), freshness selection,
  uha.json key order, uha2.json, atomic write incl. symlink, config, RTC (winter/summer), log.txt line, gateway
  packets-in/files-out.
- Golden test: the real UhaGate6 builders (`outputs.cpp` + cJSON compiled in the test) vs. the Python builders, 40 random
  value sets + all zero: identical keys, order and values.
- Fake ELECON on the Pi (pseudo-terminal, output in `/tmp`, production untouched), 100 s at the real expected rate of
  ≈ 216 packets/s (old + tunnel, all 257 variables, one tunnel value deliberately 10 % wrong):
  0 checksum / length errors, 0 dropped tunnel packets, all 257 variables `vars2`,
  comparison found exactly the wrong variable (`BAT_SOC` 100 % mismatched, every other 0), 684 reader parses of the 4 files
  with 0 errors, RTC sent every minute, log messages written to `log.txt`.
  **CPU ≈ 10 % of one core, RSS 24.8 MB and flat** (UhaGate6: 2.5 % / 3.8 MB; UhaGate5: 100 % / growing).
  Cost split on the Pi: receiving 216 packets/s ≈ 1 %, writing the 4 outputs ≈ 3.4 % per second, the rest event loop.

### Independent review (separate agent, did not write the code)
Output compatibility, spec §7 and memory/CPU safety: no defect found. Script findings fixed: the backstop timer is now
stopped only if production really came back (otherwise uhagate5 is tried), a missing backstop aborts the window, the
`switch_to_py.sh` check needs link up + packets (not just a fresh timestamp) and cannot leave the Pi without a gateway
if `enable` fails, `rollback_to_v6.sh` falls back to uhagate5, `deploy.sh` works from any folder, one bad packet no longer
drops the rest of a read.
Not changed, for Martin to decide: after `switch_to_py.sh` UhaGate6 is disabled and `uhagatepy` restarts forever
(`StartLimitIntervalSec=0`); a permanently broken `uha_vars.yaml` after a reboot would restart-loop without a gateway
until someone runs `rollback_to_v6.sh`. Keep the YAML deployment in step with the nodes.

### Test window 1 — real link, old path only (2026-11-01 09:26, 3 min as agreed with Martin)
Production uhagate6 was stopped for 3 min, UhaGatePy ran on the real serial port, uhagate6 was restored
automatically (`uhagate6: active`, `uhagatepy: inactive` afterwards).

| Check | Result |
|-------|--------|
| Link / data | link up from the first second, 17 144 old packets in 181 s (≈ 95/s), 0 checksum / length errors, 0 unknown or short packets, 0 discarded bytes |
| CPU / RSS | **8.4 % of one core**, RSS 24 820 kB constant (UhaGate6: 2.7 %, 4.7 MB) |
| Atomic writes | reader parsed the four JSON files 20×/s: 9 984 good reads, **0 errors** |
| Journal | 13 lines in 3 min (start-up, config, 2 label warnings, link up, receiving data, RTC syncs) |
| `uha.json` vs. production snapshot | 256 / 256 keys, same order, same types; 136 values equal, 120 differ — real changes during the 3 min between the two snapshots (power, temperatures, cell voltages), not format errors |
| `bms.json` vs. production snapshot | 53 / 53 keys, same order and types |
| Tunnel / comparison | 0 tunnel packets (ELECON step 2 not flashed), comparison empty — expected |

Found in this window: systemd ignored `StartLimitIntervalSec` in `[Service]` (it belongs to `[Unit]`), so the
"never stop restarting" protection was not active. Fixed (`StartLimitIntervalUSec=0` verified on the Pi).
The `/home/pi/Web/uha2.json` symlink to `/dev/shm` was created for this window (the only change in `/home/pi/Web`).

### Switch to production (2026-11-01 09:32)
`switch_to_py.sh`: its own check passed (link up, 764 packets after 10 s). After one more minute: 7 632 packets,
0 checksum errors, `uha.json` 1.0 s old with 256 keys, all four JSON files served by nginx (HTTP 200), CPU 9 %,
RSS 24.7 MB. Only the old format arrives until ELECON step 2 is flashed.

### VARS2 on the live link (2026-11-08, ELECON with the new bridge since 11:24)
Tunnel ≈ 110 packets/s next to ≈ 94/s old (≈ 205/s total, CPU ≈ 10.6 % of a core, RSS 24.7 MB flat after 7 days
without restart). 0 checksum / length errors, 0 dropped tunnel packets, 0 unknown ids, 0 wrong producers.
All 249 delivered variables arrive at the rate of their `period_ms`; nothing stale.
Not delivered in either format: `POW_KITCHEN_A/B_W`, `CONS_KITCHEN_A/B_WH` (IOBOARD_D). Flagged invalid by the
firmware: `MPPT_SOLAR_MAX_VOLTAGE_V`, `MPPT_MAX_BAT_CURRENT_A`, `SHUNT_PCK1_CURRENT_A`, `TEMP_BOARD_ELECON_D_C` (-3276.8,
sensor error value). Scales checked physically: sum of the 16 cells = pack voltage for BMS1/2/3, `LOAD_W` = A x V,
MPPT battery power ≈ 96 % of solar power.

The first comparison counted only differences beyond +-1 raw unit: 23 % "mismatches", concentrated in fast signals
(load, battery current, wind), which says little. Comparison improved (bias, relative size, verdict per variable,
slow variables compared within their own period). Result after 250 s on 248 variables:
177 ok, 56 close, 14 noisy (mean difference ≈ 0 with alternating sign, samples 1-5 s apart: sampling time), 1 "offset".
That one, `POW_WS_HEATING_W`, differs by +12.7 W on ≈ 1050 W (2.1 %, VARS2 is the newer sample, the heater was ramping) —
not a scale or unit error, but worth a look in the next summaries. Only `TEMP_KOLARNA_C` is never compared (it has no
old counterpart in the gateway's old table).

### Frozen-node watch (2026-11-12)
Incident: ELECON and ELECON_D stopped transmitting on CAN (ELECON_D's VARS2 stopped 10:00:56, TECHM showed
`EleconComError`); ELECON kept re-sending ELECON_D's last stored values over the serial link marked valid, so the
gateway published 6.5 h old BMS1 data as fresh ("age 0 s"). Both nodes recovered after an NMT reset (16:38).
Age of a value cannot show this, a value that never changes can. New module `node_watch.py`: a node is **frozen**
when none of its variables (old or VARS2, node = YAML producer) changed for `frozen-after-s` (default 120 s). The limit
grows by itself for legitimately quiet nodes (3 x the longest quiet gap seen, at most 30 min; a frozen gap is not
learned, so one outage cannot switch the detection off: IOBOARD_D settled at 304 s within 2 minutes).
Output: journal warning `node X FROZEN: none of its N variables has changed for S s ...` (repeated every 30 min),
`... data is changing again after S s` when it wakes up; `uha_status.json` `Nodes.<X>.Frozen / QuietS / FrozenLimitS`;
a "Data" column on `WS/uha-status.html`. Limitation: it only sees nodes whose values stop moving. ELECON's own CAN
transmit failure is not caught this way (its local measurements keep changing); that showed as TECHM
`EL_HEATER_STATUS = 8 (EleconComError)`.

### VARS2 DB log (0.3.0, 2026-11-14)
**What is logged:** every variable with `log_s` in `uha_vars.yaml` (176 values: 85 every 10 s, 91 every 60 s, 21 of
them counters with `agg: delta`). `avg`: mean of the valid values in `[ts, ts+log_s)`, `NULL` if there was none
(invalid flag or nothing received). `delta` (energy / water counters): increment against the previous 60 s value,
a drop below half = reset (midnight, node restart) -> the increment is the new value; may be slightly negative
(kept, the sum stays right); a `NULL` interval keeps `prev`, the next valid value carries the whole increment; the very
first value is only the baseline. So consumption over any time = `SUM(value)`.

**Schema** (`/var/lib/uhalog/uha_log.db`, WAL, `auto_vacuum=INCREMENTAL`; times UTC unix seconds, `ts` = interval start):
`vars(id, name, unit, log_s, agg)` all YAML variables, refreshed at every start (`log_s` NULL = not logged);
`raw(var_id, ts, value)` kept `log-raw-days`; `agg_15min(var_id, ts, value)` AVG / SUM of raw per 15 min, kept
forever (filled when a window is complete, missing windows after a restart too);
`counter_state(var_id, ts, value)` last counter values, so a restart continues the deltas.
Not under `/home`: Grafana's unit has `ProtectHome=true`. Folder `root:grafana 2770`, files 0660 (Grafana writes `-shm`).

**How it runs:** `Gateway._on_tunnel` -> `DbLog.on_value` (cheap, in the loop) collects the intervals; every 60 s a
batch goes through a queue to the writer thread (one transaction). The writer opens the DB (retries every 60 s;
the gateway runs without logging meanwhile), waits for `timedatectl NTPSynchronized=yes`, computes agg_15min,
deletes old raw rows once a day (5 min after the start, then every 24 h; per variable via the primary key, then
`incremental_vacuum` + WAL truncate) and checks before each batch DB + WAL size (`log-max-mb`) and free disk
(`log-min-free-mb`): over the limit -> the batch is skipped, warning once an hour, resumes by itself. Every exception
in the logger is caught and logged (the same error at most every 10 min); it cannot stop the gateway.

**Config:** `log-db` (empty = off), `log-raw-days = 30` (60 on an SSD), `log-max-mb = 2048`, `log-min-free-mb = 1024`.

**How to check:** journal `DB log: ...` lines: start (`opened ...`, `clock is NTP synchronized`, `collecting`), every
10 min `DB log: last 600 s: N rows (M NULL) in K batches, A agg rows, slowest write T ms; skipped, dropped, errors;
DB x MB (WAL y MB), free z MB`, the daily `clean-up`, and after midnight one self-check line per counter
`counter X reset a -> b; deltas since the last reset/start sum to S, counter went c -> a = E (difference D)` (D must be ~0).
`uha_status.json` -> `DbLog` (state, rows, sizes, last write). SQL: `sudo sqlite3 /var/lib/uhalog/uha_log.db
"select count(*) from raw; select count(*) from agg_15min;"`.

**Tests (2026-11-14):** PC simulation with synthetic time (2 h, invalid gaps, a counter reset, a restart in between):
rows as expected (only the unfinished last interval at a stop is lost), invalid interval -> NULL, the delta after the
gap carries the whole increment, reset delta = new value, self-check difference 0, counters continue after the
restart, the open 15 min window of the first run is filled after the restart, agg SUM = raw SUM. 24.5 B per raw
row (estimate 25 B -> ~22 MB/day). On the Pi with `tools/fake_elecon.py` (separate out-dir and DB, production not
touched): 6010 rows per 10 min (85 x 60 + 91 x 10 = 6010), slowest write 150-330 ms, CPU 8.2 % / RSS 27 MB
(production 0.2.1: 8.1 % / 25 MB), long read transactions (like Grafana) next to it do not stop the writes.
Existing unit tests (72) pass, golden test against UhaGate6 included.

### States as events (0.4.0, 2026-11-15)
Task: `UHA_FW/UHA_COMMON/tasks/vars2_states_on_change.md`. Discrete states (lights, sunscreens; later relays,
modes, setpoints) are normal VARS2 variables in the YAML group `States` with `send: on_change` (the firmware sends
them on change + every 20 s as refresh) and `agg: event`. Pilot: IOBOARD_U ids 400–413.

- `vars_def.py`: `legacy` is optional (no `legacy` -> only in `uha2.json`, not in `uha.json`), `agg: event`
  (must not have `log_s`), `send` is read (inherited group -> subgroup -> variable) but not used.
- `db_log.py`: table `events(var_id, ts, value)` (WITHOUT ROWID, kept forever). A row when the value or valid differs
  from the last stored row of that variable (invalid -> `NULL`); refresh frames with the same value are dropped. After
  a gateway start the first value of each event variable is stored. `ts` = receive time (UTC s); two changes in one
  second: the last one is kept (`INSERT OR REPLACE`). Same writer thread, batches, NTP wait and size guard as `raw`.
  `vars.agg` = `event` for them.
- Journal: the 10-minute summary has `N events (M in the table)`; `uha_status.json` -> `DbLog.EventRows`.
- Check: `sudo sqlite3 /var/lib/uhalog/uha_log.db "select v.name, e.ts, e.value from events e join vars v on
  v.id = e.var_id order by e.ts desc limit 20;"`. Grafana: dashboard **UHA States** (`UHA/Grafana/README.md`).

**0.4.1 (2026-11-16):** `uha2.json` entries of `send: on_change` variables have `"on_change": true`. They are only
refreshed every 20 s, so `WS/js/uha-common.js` (`ageClass()`) no longer greys them out after 10 s; `valid` (timeout
60 s) still shows a missing node. Step 2c adds TECHM states (ids 440–464) and makes `EL_HEATER_STATUS` on_change.

### Still to do
1. Watch the 10-minute summaries in the journal for `OFFSET` (a warning is logged) for a few days.
