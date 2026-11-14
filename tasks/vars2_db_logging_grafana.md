# VARS2 logging to a database + Grafana charts

Repos: **UHARPI** (UhaGatePy, Grafana files, this brief) and **UHA_FW** (only `UHA_COMMON/VarDefs/uha_vars.yaml`).
RPi only — no firmware change. Monitoring only, nothing on the Pi controls the house.

## Goal

UhaGatePy stores selected VARS2 values in a local SQLite database. Grafana (on the same Pi, behind the existing
nginx) shows them as charts: a day in detail, a year as daily values, energy consumption per day/hour.

## Working mode (lightweight)

- This is non-critical monitoring: implement, deploy to the Pi, run, read the logs, fix. No new unit tests, no
  separate reviewer agent. The existing UhaGatePy tests must keep passing (`deploy.sh` runs them).
- Good logging in the new code is the main debugging tool (journal: `journalctl -u uhagatepy`).
- Python stays simple and readable, a few comments (Martin is not fluent in Python).
- Short final report: what was done, versions, DB size after a few hours, open problems.

## Rules on the Pi (`pi@192.168.1.10`, SSH alias `uharpi`)

- Allowed: deploy and restart UhaGatePy directly in production (no test window needed for this task); configure
  nginx (back up the config first, `nginx -t` before every reload); basic system checks (disks, NTP, free space).
- apt: only what this brief needs (`grafana` from the Grafana apt repo, `sqlite3` CLI, `certbot` +
  `python3-certbot-nginx` in phase C). Anything else: ask Martin first.
- Not allowed: reboot, network changes, touching UHA5/UHA6 installs. Never write passwords or keys into files or
  the repo (Grafana admin password: Martin sets it himself).
- Quick rollback must stay possible: previous UhaGatePy version = git + `deploy.sh`.
- Git: feature branch `feature/vars2-logging` in UHARPI and in UHA_FW. Commit, Martin pushes.

## Decisions (already agreed, do not redesign)

| Topic | Decision |
|---|---|
| Where | Logger = new module in UhaGatePy, DB on the Pi (SD card now, SSD later — path is a config value) |
| DB | SQLite (Python `sqlite3`, WAL mode), one file |
| Charts | Grafana OSS + SQLite datasource plugin `frser-sqlite-datasource`, behind nginx at `/grafana/` |
| What to log | per variable in the YAML: `log_s` (10 or 60) and `agg` (`avg` default, `delta` for counters) |
| Tiers | `raw` (per `log_s`) kept `log-raw-days` (30 now on SD, 60 later on SSD); `agg_15min` kept forever |
| Invalid | invalid / missing value → `NULL` (gap in the chart) |
| Time | UTC unix seconds; Grafana shows local time (Europe/Prague) |
| Size limit | DB max 2 GB on the SD card; stop writing (and log a warning) when over the limit or when disk free < 1 GB |

## Part 1 — YAML (UHA_FW, `UHA_COMMON/VarDefs/uha_vars.yaml`)

Add two optional keys to variables (document them in the header comment, next to the other conventions):

```yaml
log_s: 10        # log period in s (10 or 60); missing = not logged
agg: delta       # avg (default) | delta: daily/total counter, store the increment (see Part 2)
```

On an array (`count: 16`) the keys apply to every element. Set them exactly for this list (176 values):

**`log_s: 10`, avg (85 values)**
BAT_CURRENT_A, BAT_POWER_W, SOLAR_POWER_W, LOAD_W, LOAD_A,
BMS1_CURRENT_A, BMS2_CURRENT_A, BMS3_CURRENT_A, BMS1_CELL_V, BMS2_CELL_V, BMS3_CELL_V (arrays, 48 values),
MPPT_SOLAR_POWER_W, SHUNT_PCK2_CURRENT_A,
STRG1_POWER_W, STRG2_POWER_W, STRG1_CURRENT_A, STRG2_CURRENT_A, LLOAD1_POWER_W, LLOAD2_POWER_W,
LPV1_POWER_W, LPV2_POWER_W,
AXPERT_AC_POWER_W, AXPERT_LOAD_W, AXPERT_SOLAR_W, AXPERT_PVS1_W, AXPERT_PVS2_W, AXPERT_BAT_POWER_W,
AXPERT_BAT_CURRENT_A,
POW_AC300_W, POW_AC3KW_W, POW_AC5KW_W, POW_FRIDGE_W, POW_KITCHEN_W, POW_WASCHMACHINE_W, POW_OTHER_W,
POW_TECHM_W, POW_AXPERT_W, POW_EVSE_W, POW_WS_HEATING_W,
EL_HEATER_CURRENT_A

**`log_s: 60`, avg (70 values)**
BAT_SOC, BAT_VOLTAGE_V, BAT_ENERGY_WH,
BMS1_SOC, BMS2_SOC, BMS3_SOC, BMS1_VOLTAGE_V, BMS2_VOLTAGE_V, BMS3_VOLTAGE_V,
BMS1_ENERGY_STORED_WH, BMS2_ENERGY_STORED_WH, BMS3_ENERGY_STORED_WH,
MPPT_TEMP_C,
STRG1_SOC, STRG2_SOC, STRG1_VOLTAGE_V, STRG2_VOLTAGE_V, STRG1_ENERGY_WH, STRG2_ENERGY_WH,
STRG1_OPT_CHARGING_A, STRG2_OPT_CHARGING_A,
AXPERT_PVS1_V, AXPERT_PVS2_V, AXPERT_BAT_VOLTAGE_V, AXPERT_TEMP_C,
HEAT_TOTAL_WH, HEAT_HEATING_WH, BOILER_POWER_W,
FLOW_COLD_LPM, FLOW_HOT_LPM,
TEMP_RECU_FC_C, TEMP_RECU_FH_C, TEMP_RECU_WH_C, TEMP_RECU_WC_C, RH_RECU_FH, RH_RECU_WASTE, CO2_RECU,
RECU_FAN_F, RECU_FAN_WASTE,
all 30 variables of group `Temperatures` (Techm 19, IoboardD 2, IoboardU 1, Elecon 4, EleconD 4),
METEO_WIND_AVG

**`log_s: 60`, `agg: delta` (21 values)**
MPPT_YIELD_TODAY_WH, LLOAD1_CONS_WH, LLOAD2_CONS_WH, LPV1_PROD_WH, LPV2_PROD_WH, AXPERT_ENERGY_TODAY_WH,
CONS_AC300_WH, CONS_AC3KW_WH, CONS_AC5KW_WH, CONS_FRIDGE_WH, CONS_KITCHEN_WH, CONS_WASCHMACHINE_WH,
CONS_OTHER_WH, CONS_TECHM_WH, CONS_AXPERT_WH, CONS_EVSE_WH, CONS_WS_HEATING_WH,
EL_HEATER_CONS_WH, BOILER_HEAT, CONS_COLD_L, CONS_HOT_L

Deliberately **not** logged (do not add): CONS_TODAY_WH and SOLAR_ENERGY_TODAY_WH (sums of two nodes' counters —
a reset of one node breaks the delta; the totals come from LLOAD1+2 / LPV1+2 in the query), BMSx_TODAY_ENERGY_WH
(net balance, can go down), cell temperatures, daily maxima, NETWORK_STATUS, statuses/enums, DP_RECU_*,
SHUNT_PCK1 (broken shunt), POW/CONS_KITCHEN_A/B (not delivered).

Checks: `tools/gen_all.py` / `vars_validate.py` accept the new keys (`tests/fixtures/pass_unknown_keys.yaml`
suggests unknown keys pass — verify) and the **generated FW files are byte-identical** → no FW build, no
`ASW_VERSION` bump. If the validator needs a change to accept them, keep it minimal (allowed values: `log_s`
10 or 60, `agg` avg|delta). If `ASW_RECU_NUCLEO/UhaCommon/` holds a copy of the YAML, keep it identical.
Do not touch UhaCanMaster (only note in the report if its YAML reader could choke on new keys).

## Part 2 — Logger in UhaGatePy

### Structure

- New module `uhagatepy/db_log.py` (+ YAML fields `log_s`, `agg` in `vars_def.VarDef`).
- Hook: `Gateway._on_tunnel()` after `store.set_v2(...)` passes (var_id, value, valid, mono) to the logger.
  Accumulating is cheap and stays in the asyncio loop.
- **All SQLite work runs in one separate writer thread** (queue from the loop). The serial link must never wait
  for the disk.
- **The logger must not be able to stop the gateway**: every exception inside it is caught and logged
  (rate-limited), the gateway runs on. If the DB cannot be opened, the gateway runs without logging.
- New config keys (in `uhagatepy.conf` + `config.py`, with defaults): `log-db` (e.g.
  `/home/pi/uhalog/uha_log.db`), `log-raw-days = 30`, `log-max-mb = 2048`, `log-min-free-mb = 1024`.
  Logging is enabled when `log-db` is set.
- Bump `VERSION` (0.3.0), update `README.md` (short section: what is logged, schema, config, how to check).

### Schema

```sql
CREATE TABLE vars (id INTEGER PRIMARY KEY, name TEXT, unit TEXT, log_s INTEGER, agg TEXT);  -- from the YAML at start
CREATE TABLE raw       (var_id INTEGER, ts INTEGER, value REAL, PRIMARY KEY (var_id, ts)) WITHOUT ROWID;
CREATE TABLE agg_15min (var_id INTEGER, ts INTEGER, value REAL, PRIMARY KEY (var_id, ts)) WITHOUT ROWID;
CREATE TABLE counter_state (var_id INTEGER PRIMARY KEY, ts INTEGER, value REAL);  -- last counter value, survives restarts
```

`ts` = start of the interval, UTC seconds, aligned to a multiple of the interval length. `vars` is refreshed from
the YAML at every start (so Grafana queries can use names and units).

### Values

- **avg:** `raw.value` = mean of the valid values received in `[ts, ts+log_s)`. No valid value (invalid flag or
  nothing received) → `NULL`.
- **delta:** at the end of each 60 s interval take the last valid counter value `new` and compare with the
  previous one `prev` (from memory, after a restart from `counter_state`):
  - `new < 0.5 * prev` → reset (midnight or node restart): `delta = new`
  - otherwise `delta = new - prev` (**may be slightly negative** — LEMON's `Cons_Wh` integrates a computed
    power and can drop a little; keep the negative value, the sum stays right)
  - no valid value in the interval → `NULL`, `prev` stays; the next valid value gives the whole increment
  - `raw.value` = delta (energy/water in that interval), so any consumption = `SUM(value)`
  - very first value ever (no `prev`): store nothing, it is only the baseline
- **Self-check for counters:** when a reset is detected, log one line per counter: sum of deltas since the last
  reset vs. the counter value just before the reset. Shows bugs in the delta logic without tests.
- **agg_15min:** when a 15-min window is complete, compute it from `raw` in SQL: `AVG(value)` for avg,
  `SUM(value)` for delta (NULLs ignored by both; all NULL → NULL). Also fill missing windows after a restart.

### Writing, retention, safety

- Batch writes: one transaction about every 60 s (SD card wear). WAL mode.
- **Start writing only after NTP sync** (`timedatectl show -p NTPSynchronized --value` = `yes`); log while waiting.
  The Pi 3 has no RTC and boots with the last saved time.
- Once a day: delete `raw` older than `log-raw-days`, then `PRAGMA incremental_vacuum` or similar so the file
  does not only grow (choose a simple working way; `auto_vacuum=INCREMENTAL` must be set before the tables exist).
- Size guard: before each write batch check DB file size (incl. WAL) and free disk space; over the limit → skip
  writing, one warning per hour in the journal. Resume by itself when space is back.
- Journal summary every 10 min (like the VARS2 summary): rows written, DB size, free space, skipped batches.

### Check on the Pi

After a few hours: row counts per table, DB size vs. the estimate (~22 MB/day raw, ~25 B per row), a few values
against `uha2.json`, the reset self-check after the first midnight.

## Part 3 — Grafana (phase B)

- Install Grafana OSS from the official Grafana apt repo (arm64 or armhf to match the Pi OS), plugin
  `frser-sqlite-datasource` via `grafana-cli`. Listen only on `127.0.0.1:3000`.
- Grafana config: `root_url = %(protocol)s://%(domain)s/grafana/`, `serve_from_sub_path = true`, anonymous access
  off, sign-up off. Ask Martin to set the admin password at first login (never in files).
- nginx: `location /grafana/ { proxy_pass http://127.0.0.1:3000; ... }` incl. the websocket headers Grafana needs
  (`/grafana/api/live/`). The existing dashboard (`/home/pi/Web/`) must keep working unchanged.
- **Until HTTPS exists (phase C), allow `/grafana/` only from the LAN** in nginx (`192.168.1.0/24` + local IPv6
  ranges, `deny all`), so the password never goes over plain HTTP from outside.
- Datasource: the SQLite file, read only. Grafana must be able to read the DB file and the WAL/SHM files (group
  permissions); check it does not lock the writer.
- Dashboards as provisioned JSON files in the repo (`UHARPI/UHA/Grafana/`, deployed by a small script), so they
  are versioned. Start with three, kept simple:
  1. **Energy** — battery power, PV power, load power, SOC; daily consumption/production bars (kWh) from the
     delta counters (`LLOAD1+LLOAD2`, `LPV1+LPV2`, meters).
  2. **Packs** — 16 cell voltages per pack (one panel per pack), pack voltage/current/SOC.
  3. **Temperatures** — house, technical room / tank, workshop, outside.
- Queries pick the table by the shown range: from `raw` when the range is within the raw retention (grouped to
  Grafana's `$__interval`), otherwise from `agg_15min` (grouped to days for long ranges). Day boundaries in local
  time (`'localtime'` in SQLite date functions, Pi timezone Europe/Prague — verify). Keep it simple; if one query
  cannot do both cleanly, use the agg table for ranges > 7 days.
- Link from the existing web dashboard to `/grafana/` (one link in `WS/index.html` is enough for now).

## Part 4 — HTTPS (phase C, only when Martin has created the DNS record)

Martin adds a subdomain of mkresta.cz (AAAA record → the Pi's public IPv6). Then: `certbot --nginx` for that
name, automatic renewal check (`certbot renew --dry-run`), HTTP → HTTPS redirect, then remove the LAN-only
restriction on `/grafana/`. Stop and ask Martin before this phase.

## Order and stop points

1. Part 1 (YAML) + Part 2 (logger) → deploy, run, fix from logs → **short report to Martin, wait.**
2. Part 3 (Grafana, LAN only) → **report, wait.**
3. Part 4 (HTTPS) only after Martin's go.
