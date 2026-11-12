# Task: UhaGatePy — publish from VARS2 only (old 0x221 off)

Part of VARS2 migration step 6b. The firmware side (`UHA_FW/UHA_COMMON/tasks/vars2_stop_legacy_tx.md`)
stops the old format node by node; **this task must be in production first**, so that the order of the
firmware changes does not matter.

## Context

Read first: this repo's `CLAUDE.md`, `UHA/UhaGatePy/README.md` (design, §2 value selection, frozen-node
watch), `C:\Martin\GIT\UHA_FW\UHA_COMMON\VarDefs\VARS2_spec.md` §7,
`C:\Martin\GIT\UHA_FW\UHA_COMMON\VarDefs\uha_vars.yaml`.

Facts checked in the code:
- `store.py` `legacy_raw()` returns the **last old value of any age** before the stale VARS2 value. When the
  old format stops, a VARS2 timeout would publish a frozen old value. This must not happen.
- ELECON's `0x221` scan list (`ASW_ELECON/Core/Src/SCOM.c`, 271 entries) sends 19 variables that are not
  in the YAML, so they can never come through VARS2:
  `VAR_AXPERT_DISCHARGING_W`, `VAR_LPV1_S1/S2_*`, `VAR_LPV2_S1/S2_*`, `VAR_LVDC_*` (5), `VAR_CURR_RECU_A`.
  No firmware sets them any more (`VAR_SetVariable` commented out in `LEMON.c`, `COM_AddStreamedVariable`
  commented out in RECU `APP.c:164`), so they should be constant today. Their `uha.json` keys stay
  (compatibility) with value 0.
- `VAR_NETWORK_STATUS` (id 1, a `uha.json` key) is sent by ELECON only on `0x221` (`SCOM.c:85-92`, every
  5 s) and is not in the YAML. The firmware task adds it to the YAML and to the tunnel; until ELECON has
  that version it exists only on the old path.
- `rollback_to_v6.sh`: UhaGate6 reads only `0x221`. After the firmware part of 6b it shows no live data.

## Rules

As in the earlier UhaGatePy tasks (`tasks/uhagatepy_python_gateway.md`): Pi `pi@192.168.1.10`, never modify
UHA5/UHA6 installs, nginx, system; no apt without asking; test windows ≤ 15 min with automatic restore of the
production gateway; never write passwords/keys into files. Simple, readable, commented Python.
Feature branch `feature/uhagatepy_vars2_only` from `main`. Do not merge.

## What to do

1. **New value selection in `store.py`**, per variable (no config switch, so the firmware can change in any
   order):
   - **Once any VARS2 value of the variable has been received, the old value is never used again** (until the
     gateway restarts): fresh → VARS2, stale → last VARS2 value. Reason: when a producer is dead, ELECON
     keeps re-sending its frozen `Vars[]` on `0x221`, which looks fresh (incident 2026-11-12).
   - Never received over VARS2: the old value, only while fresh (variable's `timeout_ms` from the YAML, or
     9 s for variables not in the YAML); otherwise the last old value is kept (dead keys stay as today).
   - The old-vs-VARS2 comparison stays as it is.
2. **Coverage check tool** (`tools/`): reads `uha_status.json` / `uha2.json` from the live gateway and
   lists every `uha.json` key with its current source (`vars2` / `old` / `stale` / `none`). Expected: all keys
   `vars2`, except the 19 above + `VAR_CONS_TODAY_WH` (computed). Anything else is a finding.
3. `rollback_to_v6.sh`: print a clear warning that UhaGate6 has no live data once the nodes stop the old
   format (no other change). Same note in the README.
4. Unit tests: VARS2-received variable never falls back to old (also when old is fresh and VARS2 stale),
   old-only variable with expiry, never received at all, startup order (old first, then VARS2).
5. **Live check in a test window**: run the coverage tool; compare `uha.json` and `bms.json` with production
   (same keys; values equal within the existing comparison tolerance). If any of the 19 dead keys is not
   constant, stop and report.
6. Independent reviewer subagent. Report to Martin: changes, test results, coverage table, and the steps for
   him: `deploy.sh`, restart `uhagatepy`.
