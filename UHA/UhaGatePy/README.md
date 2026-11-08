# UhaGatePy — findings and plan

Status (2026-11-01): **PRODUCTION runs UhaGatePy since 2026-11-01 09:32** (switched on Martin's request after test
window 1; UhaGate6 disabled, kept as backup, rollback: `sudo /home/pi/UhaGatePy/rollback_to_v6.sh`).
Implemented, reviewed, tested on the PC, on the Pi with a fake ELECON and in a 3-min window on the real link.
Martin approved the plan and the decisions in §6.
On the Pi: `python3-serial` + `python3-yaml` installed (apt), code in `/home/pi/UhaGatePy`,
`uhagatepy.service` enabled (production). Results in §7.
Task: `tasks/uhagatepy_python_gateway.md`. Contract with ELECON: `VARS2_spec.md` §7 (UHA_FW repo).

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
serial bytes ─► rpiserp.Parser ─► packet id? ─┬─ 0x221  ─► store.old[id]  = raw int16 + valid
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
| `vars_def.py` | loads `uha_vars.yaml`: defaults, producer inheritance, arrays, `timeout auto`; clear error + exit if invalid |
| `legacy_table.py` | **generated once** from UhaGate6 (`uha_json_body.inc`, `uha_vars.h`): the 256 `uha.json` keys in order with ids. Not invented, not hand-edited |
| `tunnel.py` | decode of a `0x18n` packet (id u16 LE, value 4 B LE as float32 / int32 / uint32, flags, seq) |
| `store.py` | old store + VARS2 store, freshness choice, legacy conversion, old-vs-new comparison |
| `outputs.py` | `uha.json`, `bms.json`, `uha2.json`, `uha_status.json`, atomic writes |
| `event_log.py` | `log.txt` line (same format as UhaGate6) |
| `rtc.py` | RTC sync payload (`0x051`) |
| `status.py` | content of `uha_status.json` |
| `gateway.py` | the event loop: serial link, packet handling, timers, summaries |

### Value selection (spec §7.5)

For each variable: use the VARS2 value if it has `VALID` and its age ≤ `timeout_ms`, converted back with
`round(value * legacy_scale)`; otherwise the last old `0x221` raw value (0 if never received, like UhaGate6).
Rounding is half away from zero like C `round()` (Python's `round` is banker's rounding); the result is
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
`producer` (from the packet id), `source` (`vars2` / `old` / `none`). Variables not in the YAML (ids 49, 142) are
only in `uha_status.json`.

### `uha_status.json`

All UhaGate6 fields (link, counters, vars, uptime, RSS) plus: packets per id class (old / tunnel / log),
tunnel packets per producer node with last-seen and rate, unknown VARS2 ids, wrong-producer count,
YAML version, and the old-vs-new comparison table.

### Old vs. new comparison (brief §2.6)

When a value arrives in one format and the other format arrived within `compare-window-ms` (default 2 s),
compare `round(v2 * legacy_scale)` with the old raw value, tolerance ±1. Counted per variable (compared / mismatched).
Journal: summary every 10 min (total, mismatch %, 5 worst variables); each mismatch only with `--verbose`.
Fast-changing powers will show some mismatches because of different sampling times; a systematic one
(wrong scale, wrong id) shows as ~100 % for that variable.

### Config (`uhagatepy.conf`, same style as `uhagate6.conf`)

`port` (default the by-id CP2102 path), `out-dir` (`/dev/shm` in production), `log-file`, `json-period-ms`,
`rtc-period-s`, `reopen-s`, `silence-warn-s`, `error-summary-s`, `compare-window-ms`, `vars-yaml`, `verbose`.

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
| `rollback_to_v6.sh` | Pi | `disable --now uhagatepy`, `enable --now uhagate6` |
| `tools/fake_elecon.py` | Pi (Linux) | optional: writes `0x221` + tunnel + `0x620` frames into a pseudo-terminal, so UhaGatePy can be run completely **without touching the production serial port** (output to `/tmp`) |

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

### Still to do
1. **Test window 2** (now: a comparison on the live production service, no stop needed — read the journal summary
   and `uha_status.json` `Comparison` after ELECON step 2 is flashed) after Martin flashes ELECON step 2: tunnel rates per node, mismatch summary ≈ 0.
