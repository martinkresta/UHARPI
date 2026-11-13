# Task: UhaGatePy — VARS2 only (remove the old 0x221 path)

Part of VARS2 migration step 6b. Both protocols run in parallel today; the old-vs-VARS2 comparison has done its
job (the values match). Now UhaGatePy uses **only VARS2**, and the code that existed only to run and compare two
protocols is removed, so the gateway is simple again. The YAML (`uha_vars.yaml`) is the only definition of the
variables. This must be in production before the firmware stops the old format
(`UHA_FW/UHA_COMMON/tasks/vars2_stop_legacy_tx.md`).

## Context

Read first: this repo's `CLAUDE.md`, `UHA/UhaGatePy/README.md`, `C:\Martin\GIT\UHA_FW\UHA_COMMON\VarDefs\VARS2_spec.md` §7,
`C:\Martin\GIT\UHA_FW\UHA_COMMON\VarDefs\uha_vars.yaml`.

## Rules

As in the earlier UhaGatePy tasks (`tasks/uhagatepy_python_gateway.md`): Pi `pi@192.168.1.10`, never modify
UHA5/UHA6 installs, nginx, system; no apt without asking; test windows ≤ 15 min with automatic restore of the
production gateway; never write passwords/keys into files. Simple, readable, commented Python.
Feature branch `feature/uhagatepy_vars2_only` from `main`. Do not merge.

## What to do

1. **Values only from VARS2.**
   - `0x221` packets are ignored (only counted, so we can see when the firmware stops sending them).
   - `store.py` keeps only the VARS2 values. Remove `OldValue`, `set_old`, `CompareStats`, `_compare`,
     `take_window` and the fallback logic.
   - `uha.json` / `bms.json` keep all their keys (the dashboard uses them): value = last received VARS2 value,
     converted with `round(value * legacy_scale)`; keys whose id is not in the YAML, or never received, are 0.
   - `uha2.json`: value, valid (VALID and age ≤ `timeout_ms`), age, producer. Drop the `source` field.
2. **Remove the comparison code**: journal summary (`_compare_summary`), config keys `compare_window_ms` /
   `compare_summary_s`, `uha_status.json` `Comparison`, `Count` (old) and `OldPackets` (replace it with an
   ignored-packets counter). Update `WS/uha-status.html`, `WS/uha-detail.html`, `WS/js/uha-common.js` to match.
3. Frozen-node watch: fed only by VARS2 value changes (it stays — it catches dead producers).
4. `rollback_to_v6.sh`: print a warning that UhaGate6 reads only `0x221` and shows no live data once the
   nodes stop the old format. Same note in the README. Update the README (design section) to describe the
   VARS2-only gateway.
5. Tests: remove the comparison/fallback tests, keep the golden test (output format vs UhaGate6), add a test
   that a `0x221` packet does not change any output.
6. Short live check in a test window: gateway runs, `uha.json` / `bms.json` have the same keys as production,
   the dashboard shows data; list the YAML variables in `Vars2.NeverReceived` (report, do not fix).
7. Independent reviewer subagent. Report to Martin: changes, test results, and his steps: `deploy.sh`, restart
   `uhagatepy`.
