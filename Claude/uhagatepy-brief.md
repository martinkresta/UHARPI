# Task: VARS2 step 3 — UhaGatePy, new RPi gateway in Python

## 1. Context

Read first: this repo's `CLAUDE.md`, `UHA/UHA6/README.md` (how the current
gateway UhaGate6 works, exact output formats, Pi details, test-window
approach) and the VARS2 specification
`C:\Martin\GIT\UHA_FW\UHA_COMMON\VarDefs\VARS2_spec.md` — **§7 (ELECON → RPi
tunnel) is the contract with the ELECON side**; §2 frame, §3 YAML schema.
Variables: `C:\Martin\GIT\UHA_FW\UHA_COMMON\VarDefs\uha_vars.yaml`.

Production runs **UhaGate6 (C++)**. It stays as the backup. The new gateway
**UhaGatePy** replaces it later and is the base for future features
(database, two-way communication, more logging) — not in this task.

**Martin does not know Python well. Keep the code simple and readable:**
small modules, plain functions/classes, no frameworks, type hints, a short
comment for every non-obvious piece (protocol details, why something is done).
Readability over cleverness.

## 2. What UhaGatePy does

Same as UhaGate6 (see its README for exact behaviour), plus VARS2:

1. **Serial link** (pyserial): port from config (default the stable
   `/dev/serial/by-id/...CP2102...`), 115200 8N1, reconnect on loss
   (retry every 5 s, logged).
2. **RPISERP parser** (spec §7.1): split frames across reads, checksum and
   length checks, counters.
3. **Packets** (spec §7.2):
   - `0x221` old variable (int16 BE, valid) → old store,
   - `0x180..0x18F` VARS2 tunnel → decode with YAML (type, enum) → VARS2
     store: value, valid flag, receive time, producer node,
   - `0x620` node log message → `log.txt` (same line format as UhaGate6) +
     journal.
4. **RTC sync** `0x051` exactly as UhaGate6 (format and timing in its
   README: unix time + 3600 (+3600 DST), 4 B big-endian, every minute change
   and at start-up).
5. **Outputs** (atomic write: temp file + `os.replace`), every second, to
   the configured folder (production: `/dev/shm`, symlinks in `/home/pi/Web`):
   - `uha.json`, `bms.json`: **same keys, key order, value types and values**
     as UhaGate6 (web `WS/js/*.js` and the FTP upload read them). Whitespace
     may differ. Value per variable: VARS2 value while fresh
     (age ≤ `timeout_ms`), converted back `round(value * legacy_scale)`;
     otherwise the old `0x221` value (spec §7.5). Port the key list and the
     special computed fields from UhaGate6 (`uha_json_body.inc`,
     `outputs.cpp`) — do not invent them.
   - `uha_status.json`: like UhaGate6, plus per-node last seen from the
     tunnel (producer is now known).
   - **new `uha2.json`**: per variable (YAML name): value in physical units,
     unit, valid, age_s, producer, source (`vars2` / `old`).
6. **Old vs new comparison**: for variables received in both formats, count
   and log mismatches (`round(v2 * legacy_scale)` vs old raw, tolerance ±1;
   allow for different sampling times). Summary in the journal every 10 min,
   details with `--verbose`. This is the main correctness check of the
   migration.
7. **Logging** to the journal with levels, no per-second spam (follow
   UhaGate6's logging rules in its README).
8. **Config**: file + command-line options, defaults as UhaGate6, plus YAML
   path. Load YAML at start; invalid YAML → clear error, exit.

Single-threaded `asyncio` (or selectors) event loop. Memory and CPU must stay
flat (check RSS over a test window). Python version on the Pi: Debian 12 →
3.11.

## 3. Constraints and the Pi

- Repo `UHARPI`: `git status` first; branch `uhagatepy`; code in
  `UHA/UhaGatePy/`. UhaGate5 and UhaGate6 sources untouched.
- Pi: `pi@192.168.1.10` (SSH as for UhaGate6). Install to
  `/home/pi/UhaGatePy`, unit `uhagatepy.service` (`Conflicts=` with
  uhagate5/uhagate6, `Restart=always`, `MemoryMax=`), **not enabled**.
- Packages: needs `python3-serial`, `python3-yaml` (apt). **Ask Martin before
  installing anything.** No pip into the system Python.
- All rules from the UhaGate6 task stay: never modify UHA5/UHA6 installs,
  nginx, system settings; test windows max 15 minutes with **automatic
  restore of UhaGate6** (production is now `uhagate6`, adapt
  `test_window.sh`); never leave the Pi without a running gateway.
  Do not switch production — Martin decides.
- Scripts: `deploy.sh`, `test_window.sh`, `switch_to_py.sh`,
  `rollback_to_v6.sh`.

## 4. Testing

- Unit tests (stdlib `unittest`, run on PC and Pi): parser (split frames,
  bad checksum, garbage), tunnel decoding (float / int / bool / enum, LE
  payload inside BE packet id), legacy conversion, freshness selection,
  JSON key order.
- **Before ELECON has step 2**, only `0x221` arrives — UhaGatePy must work
  on that alone (this is also the fallback path). Test window: compare
  `uha.json` / `bms.json` with UhaGate6 snapshots (same keys/order/types,
  values equal within sampling difference) — reuse `compare_json.py`.
- **After ELECON step 2 is flashed** (Martin tells you): second test window
  — tunnel rates per node, `uha2.json` plausible, old vs new mismatch
  summary ≈ 0.

## 5. Work plan

1. Study + plan into `UHA/UhaGatePy/README.md`, **stop for Martin's approval**
   (incl. the apt packages).
2. Implement; you may use subagents (e.g. serial + parser + RTC; outputs
   + YAML + comparison), then an **independent reviewer subagent** checking
   output compatibility with UhaGate6, spec §7, readability, Pi rules.
3. Test windows as in §4. Small commits on `uhagatepy`. Do not merge.

## 6. Report to Martin

Plan decisions, test results (CPU, RSS, JSON compare, mismatch counts),
how to switch and roll back.
