# UhaGate6 — findings and plan

Status (2026-11-01): **implemented and tested in a 10-min window; production still runs UhaGate5.**
Plan approved by Martin on 2026-10-31 incl. tmpfs. Installed on the Pi: `/home/pi/UHA6`,
`uhagate6.service` (disabled), tmpfs symlinks in `/home/pi/Web`. Results in §5.

---

## 1. Pi inspection (2026-10-31, read-only)

### How UhaGate5 really runs

| Item | Finding |
|------|---------|
| Unit | `/lib/systemd/system/uhagate5.service` — `ExecStart=/home/pi/UHA5/UhaGate5`, `Restart=always`, runs as root, enabled. Identical to `UHA/service/uhagate5.service` and `/home/pi/UHA5/uhagate5.service`. |
| Binary | `/home/pi/UHA5/UhaGate5`, built 9 May 2026 in `/home/pi/UHA5` (in-tree CMake build of `src/`). |
| Source on Pi | `/home/pi/UHA5/src/` — **identical to `UHA/UHA5/` in the repo** (md5 of all 10 files match, both CRLF). |
| Serial | `/dev/ttyUSB0` = CP2102, stable alias `/dev/serial/by-id/usb-Silicon_Labs_CP2102_USB_to_UART_Bridge_Controller_0001-if00-port0`. |
| Web | nginx active, `root /home/pi/Web`, `try_files $uri $uri/ =404`, default symlink handling. |
| Outputs | `uha.json`, `bms.json` (rewritten every second), `log.txt` (196 lines, owned root). |
| Other consumer | **cron (user pi) every minute: `/home/pi/Web/ftpupload.sh` uploads `bms.json` by plain FTP to an external host.** So `bms.json` has a second reader besides the web. |
| System | Pi OS (Debian 12), kernel 6.6.74 aarch64, 907 MB RAM, **no swap**, SD 14 GB, 30 % used. NTP synced, TZ Europe/Prague. |
| Tools | cmake 3.25.1, g++ 12.2.0. `libsystemd-dev` **not** installed (not needed, see §3). |

### Problems confirmed

1. **Memory leak → OOM kill every ~2–3 days.** `cJSON_Print()` result is never freed
   (`UHA.cpp:202`, `UHA.cpp:627`). RSS grows ~23 MB/h (290 MB after 9.7 h today).
   Previous boot (16 Sep – 31 Oct): kernel OOM killer killed UhaGate5 at ~800 MB RSS
   (e.g. 27 Oct 00:13, 29 Oct 07:42; also 15, 17, 20 Oct), systemd restart counter
   reached 82. After every restart all values are 0 until nodes resend them.
2. **100 % of one CPU core** — busy loop in `Main.cpp` (`ps`: 100 % CPU, load avg ≈ 1.0).
3. **Journal spam / 1.3 GB journal** — `TimeMS` line every second + 3 lines per RTC sync.
   Persistent journal in `/var/log/journal` is 1.3 GB.
4. JSON files written in place (`fopen "w"`) — web *and* the FTP upload can read a
   truncated file.
5. `fprintf(fh, json)` uses JSON text as a format string; `bms.json` `fopen` not checked for NULL.
6. Receiver ring buffer: no overflow detection, no synchronisation between threads.
   Parser drops a trailing `0x7F` that is split across two reads (occasional lost packet).
7. No recovery if the USB-serial adapter disappears (fd stays dead, `read` returns errors forever).
8. Values have no timestamp — stale values look current.

### Compatibility details UhaGate6 must reproduce exactly

- `bms.json`: `cJSON_AddItemToObject(..., 0)` with a NULL item adds **nothing**, so the keys
  `TotalChargingKwh`, `TotalDischargingKwh` and the 2nd `DischargingA` are **absent** today.
  UhaGate6 keeps them absent.
- `uha.json`: same 270+ keys, same order, same scaling, `cJSON_Print` formatting (tabs).
- RTC packet `0x51`: 4 bytes big-endian = `unix_time + 3600 (+3600 if DST)`. There is no
  separate TZ byte (the description in CLAUDE.md is inaccurate). Sent on every minute change,
  and once at start-up.
- `log.txt` line format `dd.mm.yyyy hh:mm:ss NODE EVENT d2 d3 d4 d5 d6 d7`, append.
- Variable value = int16 from bytes 2..3, var id < 400 accepted, others ignored.

---

## 2. Design of UhaGate6

**Single-threaded event loop** (`poll()` on serial fd + `timerfd` 1 s tick + `signalfd`
for SIGTERM/SIGINT). No receiver thread → no races, idle CPU ≈ 0 %.

| Module | Content |
|--------|---------|
| `serial_link` | open/configure (115200 raw, non-blocking), detect disconnect (`POLLHUP`/`POLLERR`/`EIO`/`ENODEV`), reopen every 5 s, link up/down logged. |
| `rpiserp_parser` | Same framing and acceptance rules as `rpiserp.c` (len ≤ 10, 8-bit sum checksum), but correct handling of split headers. Counters: packets, checksum errors, length errors, discarded bytes. Pure function, unit-tested. |
| `var_store` | `int16 value`, `last_rx` (realtime + monotonic), `rx_count` per variable. |
| `outputs` | `uha.json` / `bms.json` built by the **same cJSON code as UhaGate5** (copied, only memory freed); `uha_status.json` new. All written atomically: `name.tmp` in the same dir → `rename()`. Permissions 0644. |
| `event_log` | `log.txt` append, same format; each node log message also goes to journald (info). |
| `logging` | stdout with syslog prefixes `<3>`…`<7>` (journald parses them, no library needed). Levels: error, warning, info, debug (`--verbose`). |
| `config` | CLI options + optional `key=value` config file. Defaults = UhaGate5 values. |

### Logging (no per-second spam)

- info: start-up + effective config, link up / down / reopen attempts (rate-limited),
  first packet after link up, RTC sync sent (1 line/min), node log messages.
- warning: checksum/length errors **summarised** every 10 min (only if > 0), output write failures (rate-limited).
- info hourly summary: packets, errors, vars seen, RSS.
- debug (`--verbose` only): individual packets.

### `uha_status.json` (new)

```json
{
  "UnixTime": 1793472000,
  "UptimeS": 3600,
  "Link": { "Port": "/dev/ttyUSB0", "State": "up", "SinceUnix": 1793468400, "Reconnects": 0 },
  "Counters": { "RxBytes": 0, "RxPackets": 0, "VarPackets": 0, "LogPackets": 0,
                "ChecksumErrors": 0, "LengthErrors": 0, "UnknownIds": 0 },
  "Vars":  { "VAR_BAT_SOC": { "AgeS": 2, "LastRxUnix": 1793471998, "Count": 1800 }, ... },
  "Nodes": { "ELECON": { "LastSeenUnix": ..., "AgeS": ... }, ... }
}
```
Vars never received are listed with `"AgeS": null`.

**Limitation:** packet `0x221` does not carry the node id. "Node last seen" can only come from
`0x620` log messages (they have node id in byte 0). A var→node mapping would make it exact;
that belongs to the YAML task (out of scope). Proposal: node last-seen from log messages
only for now.

### Configuration

```
UhaGate6 [-c /home/pi/UHA6/uhagate6.conf] [--port PATH] [--out-dir DIR]
         [--log-file PATH] [--json-period-ms 1000] [--rtc-period-s 60] [--verbose]
```
Defaults: `/dev/ttyUSB0`, `/home/pi/Web`, `/home/pi/Web/log.txt`, 1000 ms, 60 s.

### Service `uhagate6.service` (installed, **not enabled**)

```
[Unit]
Description=UhaGate_v6
Conflicts=uhagate5.service        # starting v6 stops v5 (serial port is single-user)
[Service]
ExecStart=/home/pi/UHA6/build/UhaGate6 -c /home/pi/UHA6/uhagate6.conf
Restart=always
RestartSec=2
MemoryMax=64M                     # safety net against any future leak
[Install]
WantedBy=multi-user.target
```
Runs as root like v5 (`log.txt` is root-owned; changing users is a later step).

---

## 3. Scripts (in `UHA/UHA6/`)

| Script | Runs on | What it does |
|--------|---------|--------------|
| `deploy.sh` | PC (Git Bash) | `scp` sources to `uharpi:/home/pi/UHA6/src`, build in `/home/pi/UHA6/build`, copy unit to `/lib/systemd/system/uhagate6.service`, `daemon-reload`. Does **not** enable or start anything. |
| `test_window.sh [minutes≤15]` | Pi | Starts as a transient unit (`systemd-run`) so it survives an SSH drop. Arms a backstop timer (`systemd-run --on-active=16min systemctl start uhagate5`), stops v5, runs v6, on exit/`trap` always stops v6 and starts v5, then cancels the backstop. Saves v5 + v6 JSON snapshots for comparison. |
| `switch_to_v6.sh` | Pi | `disable --now uhagate5`, `enable --now uhagate6`, show status. |
| `rollback_to_v5.sh` | Pi | `disable --now uhagate6`, `enable --now uhagate5`, show status. |
| `compare_json.py` | Pi/PC | Compare key sets/structure of v5 vs v6 JSON and list value differences. |

---

## 4. Test plan

1. Parser unit test (`ctest` on Pi): split frames, bad checksum, garbage, overlong length, frame across 2+ reads.
2. Test window #1 (10 min): CPU (`pidstat`/`ps`), RSS stable, journal volume, JSON compare
   v5 snapshot vs v6 (same keys, values within 1 s sampling difference), `log.txt` format,
   RTC packets sent each minute.
3. Atomic writes: reader loop parsing `uha.json`/`bms.json` 20×/s during the window → 0 parse errors.
4. Serial unplug/replug — **only if Martin agrees and is at the Pi**.
5. v5 restored automatically after each window, verified by `systemctl is-active uhagate5`.

---

## 5. Test results

### Before the Pi (deploy.sh)
- Unit tests (parser: split frames, `0x7F` at chunk end, bad checksum, len 0/1/11, start sequence
  inside data, all dlc 0..8; JSON; log line format): pass.
- Golden test `src/tests/compare_with_v5.sh`: UHA5 `UHA.cpp` compiled with redirected paths vs
  UhaGate6 builders, 100 random variable sets: **uha.json and bms.json byte-identical**.

### Test window 2026-10-31 20:19:30 – 20:31:34 (v6 on production data)

| Check | UhaGate5 | UhaGate6 |
|-------|----------|----------|
| CPU | 100 % of one core | 18.0 s CPU in 724 s = **2.5 %** at ~79 packets/s |
| RSS | 309 MB after 10.4 h, growing | 3.3 → 3.8 MB, flat from minute 5 |
| Journal | ~3,700 lines/h | 24 lines in 12 min (12 of them RTC sync) |
| Atomic writes | – | 30,138 parses of uha/bms/status JSON during the window, **0 errors** |
| Serial | – | 682 kB, 56,863 packets, **0 checksum / length errors**, 0 discarded bytes |
| RTC sync | every minute | at link-up + every minute (11 sent), 0 TX errors |
| JSON compare (v5 snapshot 20:19 vs v6 20:29) | | same 256 / 53 keys, same order, same types; differing values are real changes over 10 min (load, temperatures, cells) |
| Variables | | 272 of 276 received, max age 3 s; never sent: `VAR_CONS_KITCHEN_A/B_WH`, `VAR_POW_KITCHEN_A/B_W` |

Not covered yet: node log messages (none arrived in the window; format covered by unit test),
serial unplug/replug.

Incident: `test_window.sh` hung in a plain `wait` (it also waited for the `tee` process
substitution), so its restore did not run. The backstop timer started UhaGate5 at 20:31:33
as designed (v6 was stopped by `Conflicts=`), the gateway was never down. Fixed: wait only for
the reader, restore v5 before the evaluation.

Possible improvement: most of the 2.5 % CPU is probably the per-packet wake-ups and the 34 kB
status JSON every second; status every 5 s or reading in batches would lower it further.

---

## 6. Decisions

| Topic | Decision (Martin, 2026-10-31 / 11-01) |
|-------|---------------------------------------|
| Plan | approved; fix all serious bugs in UhaGate6 (UhaGate5 untouched) |
| tmpfs | approved; JSON in `/dev/shm` (directly, not a subfolder, so the links also work for UhaGate5 after a reboot), symlinks in `/home/pi/Web` |
| Serial port | `/dev/serial/by-id/...CP2102...` in `uhagate6.conf` (survives replug as ttyUSB1) |
| Node last seen | from log messages only |
| USB unplug test | not now; later only if link problems appear |
| FTP upload (`ftpupload.sh`) | hosting ends soon; upload will be removed and moved to another hosting later. Change the password regardless (it was exposed in a session log) |
| Switch to UhaGate6 | open: Martin decides (`switch_to_v6.sh`) |

Open, outside this task (Martin's decision):
- UhaGate5 is OOM-killed every 2–3 days; until the switch, v5 keeps restarting itself.
- Journal is 1.3 GB; can be trimmed with `sudo journalctl --vacuum-size=200M`
  and/or `SystemMaxUse=` in journald.conf.
