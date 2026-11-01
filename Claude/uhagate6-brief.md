# Task: UhaGate6 — new version of the Raspberry Pi gateway (UHARPI)

## 1. Context

Read `CLAUDE.md` in this repo first. UHA is the home automation system of an
off-grid house (STM32 nodes on CAN). The Raspberry Pi runs **UhaGate5**
(`UHA/UHA5/`, C++), connected to the ELECON node over a USB-serial link:

- `/dev/ttyUSB0`, 115200 Bd, RPISERP framing `7F AA | len | id(2) | dlc | data | checksum`
  (`rpiserp.c`, receiver thread, 200-packet buffer).
- RX `0x221` variable value (id + int16), `0x620` log message from nodes.
- TX `0x51` **RTC sync every minute** — the Pi is the time source for all
  nodes (heater summer/winter mode, midnight resets …). Pi time is NTP synced.
- Every second writes `uha.json` and `bms.json` to `/home/pi/Web/`
  (served by nginx, read by `WS/js/uha.js`, `bms.js`); node log messages
  appended to `/home/pi/Web/log.txt`.
- Service: `uhagate5.service` (`ExecStart=/home/pi/UHA5/UhaGate5`,
  `Restart=always`, runs as root).

Weak points found in the code (verify):

1. Main loop busy-waits: `while(1)` calls `UHA_ProcessMessage()` with no
   sleep/blocking → one CPU core at 100 %.
2. `cout << "TimeMS"` every second → journal spam; no real logging.
3. `mVars` is `short[]` without validity or receive time → the web shows
   stale values as current when data stops.
4. JSON files are written in place every second → the web can read a
   half-written file; constant SD-card writes.
5. No recovery if the USB-serial adapter disconnects / reappears.
6. ~270 hard-coded `cJSON_AddItemToObject` lines (names later from
   `uha_vars.yaml`, not in this task).

## 2. Goal

Create **UhaGate6** in `UHA/UHA6/` — same protocol and same outputs as
UhaGate5, but robust, efficient and with proper logging. **UhaGate5 stays
untouched as the backup** (source in the repo and binary/service on the Pi).

Not in scope now: the new VARS2 protocol, YAML-driven variable names, any
change of ELECON firmware or the web dashboard.

## 3. Requirements

- **Output compatibility:** `uha.json`, `bms.json`, `log.txt` keep the exact
  same keys, structure and value scaling, so `WS/js/*.js` works unchanged.
  Write them atomically (temp file + `rename`). Writing to tmpfs with a
  symlink is allowed only if nginx keeps serving the same URLs — propose it,
  do not change nginx config without Martin's OK.
- **Additional output** (new file, e.g. `uha_status.json`): per variable
  last receive time / age; per node last seen; serial link state; RX packet
  and checksum-error counters; process uptime.
- **No busy-wait:** blocking/poll-based serial handling; idle CPU near 0 %.
- **Logging:** to journald with levels (startup, config, link up/down,
  checksum errors summarised, RTC sync sent); no per-second spam.
- **Serial robustness:** detect disconnect, retry open periodically, log it.
- **RTC sync:** identical behaviour to UhaGate5 (every minute, same packet).
- **Config:** serial port, output folder, periods via a small config file or
  command-line options; defaults = current values.
- Build with CMake on the Pi (as today, target `UhaGate6`). C++ (keep cJSON).
  Do not install packages on the Pi without asking Martin.

## 4. Raspberry Pi access (SSH)

- Host `192.168.1.10`, user `pi`. Use the SSH key / credentials available on
  this PC; **never write passwords or keys into the repo or any file**.
  If you cannot log in, ask Martin.
- **First step on the Pi (read-only):** inspect how UhaGate5 really runs —
  service file, binary location, source on the Pi (`/home/pi/UHA5`, maybe a
  `src/` subfolder) and **diff it against `UHA/UHA5` in the repo**; check
  nginx serving `/home/pi/Web`, journal of `uhagate5`, CPU usage, free disk.
  Report differences before changing anything.

### Rules on the Pi

- Allowed: create `/home/pi/UHA6/`, build there, create
  `uhagate6.service` (disabled by default), read logs, `systemctl
  stop/start/status` of `uhagate5` / `uhagate6` for tests.
- **Never modify** `/home/pi/UHA5/`, `uhagate5.service`, nginx, system
  settings, other services; no `apt`, no reboot, no network changes —
  ask Martin first.
- The serial port can be used by **one process only**: testing UhaGate6
  means stopping UhaGate5. Test windows max **15 minutes**, run the test so
  that UhaGate5 is **always restored automatically** (e.g. a wrapper script
  with `trap`/`timeout` that restarts `uhagate5` on exit). Never leave the Pi
  without a running gateway.
- Provide scripts in `UHA/UHA6/`: `deploy.sh` (copy/build on Pi),
  `switch_to_v6.sh`, `rollback_to_v5.sh` (one command each), and document them.

## 5. Workflow

1. **Git** (repo `UHARPI`): `git status`; if there are uncommitted changes,
   ask Martin. Branch `uhagate6`.
2. **Study + Pi inspection (read-only)** → write findings and the plan to
   `UHA/UHA6/README.md`. **Stop and wait for Martin's approval.**
3. **Implement** UhaGate6 (you may use subagents, e.g. one for the serial /
   RPISERP layer, one for JSON outputs + status, then an independent
   reviewer subagent checking output compatibility with UhaGate5 and the
   rules in §4).
4. **Compatibility test:** run UhaGate6 in a test window; compare its
   `uha.json` / `bms.json` with UhaGate5 output (same keys; values equal
   within the 1 s sampling difference). Check CPU, journal, atomic writes,
   serial unplug/replug if Martin agrees to unplug.
5. Commit in small logical commits on `uhagate6`; update `CLAUDE.md`.
   **Do not switch production to UhaGate6** — Martin decides.

## 6. Report to Martin

Pi inspection findings (incl. repo vs. Pi source differences), what was
built, test results (CPU, compatibility diff, link recovery), how to switch
and roll back.
