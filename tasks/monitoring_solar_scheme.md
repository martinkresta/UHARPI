# Monitoring: unified PV cards + high-level energy scheme

Repo UHARPI, `WS/` only. Lightweight mode: implement, deploy (backup first, bump the css/js version as before),
check on 360 px portrait and desktop, short report. Branch `feature/monitoring-solar-scheme`. Reference:
UHA_FW `UHA_COMMON/VarDefs/ENERGY_TOPOLOGY.md`. Texts via `texts.json`; new `mon.*` keys go to `texts_pending.json`
and into the report.

## 1. Solar page: MPPT (house) and Axpert PV (workshop) cards look the same

Both cards use **one shared render function** with the same layout (the compact style of today's Axpert PV card):
- Big tiles: **PV power now**, **PV today**.
- One row per string: name, power · voltage · current. MPPT: one row "String" (`MPPT_SOLAR_POWER_W`,
  `MPPT_SOLAR_VOLTAGE_V`, `MPPT_SOLAR_CURRENT_A`); Axpert: "String 1", "String 2" (`AXPERT_PVS1_*`, `AXPERT_PVS2_*`).
- Rows: **battery voltage** (`MPPT_BAT_VOLTAGE_V`, `AXPERT_BAT_VOLTAGE_V`), **max power today**
  (`MPPT_MAX_TODAY_W`; Axpert has none yet → "–", the FW will add it later), **temperature** of the charger
  (`MPPT_TEMP_C`, `AXPERT_TEMP_C`) as a small last row.
- PV today: MPPT `MPPT_YIELD_TODAY_WH`, Axpert `LPV2_PROD_WH`.
Everything else (MPPT battery current, max battery current, max PV voltage …) leaves the card.

## 2. Energy scheme (`uha-energy-scheme.html`): high level only

Replace the detailed scheme by **6 modules in 2 columns** — left house, right workshop — readable on a phone in
portrait (360 px wide) without zoom; columns narrow, stacked vertically:

```
   House                 Workshop
 [ PV house ]          [ PV workshop ]
      │                      │
 [ Storage house ] ◄─LVDC─► [ Storage workshop ]
      │                      │
 [ Load house ]        [ Load workshop ]
```

- **PV**: power now (`MPPT_SOLAR_POWER_W` / `AXPERT_SOLAR_W`), today (`MPPT_YIELD_TODAY_WH` / `LPV2_PROD_WH`).
- **Storage**: SOC (`STRG1_SOC` / `STRG2_SOC`) big, charging / discharging power (`STRG1/2_POWER_W`).
- **LVDC**: the existing estimate from `uha-common.js` (same function as the Storage page), "≈ … W", arrow direction.
- **Load** (one value per site, no split into AC/DC/heater): local load corrected for the link:
  house = `LPV1_POWER_W − STRG1_POWER_W − P_link`, workshop = `LPV2_POWER_W − STRG2_POWER_W + P_link`
  (P_link positive house → workshop; verify the sign convention of `STRGx_POWER_W` — positive = charging — and say
  in the report). Show also today's consumption: `LLOAD1/2_CONS_WH` are not link-corrected, so show "today" only if
  you can do it correctly, otherwise power only (say which).
- Colors: PV green, storage yellow, load red (the unified palette); LVDC dashed yellow.
- **Flow animation**: every link (PV → storage, storage ↔ load, storage ↔ storage) is a line with a moving dash
  pattern (`stroke-dasharray` + animated `stroke-dashoffset`, CSS or requestAnimationFrame), moving **in the direction
  of the energy flow**, speed growing with the power (e.g. log scale, capped), still below a threshold (constant,
  e.g. 20 W). Line width may grow with power. Respect `prefers-reduced-motion` (then static arrows). The flow
  directions follow the signs: PV → storage only when PV > threshold; storage → load / load ← storage by the sign of
  the storage power vs. load (keep it simple: PV→storage when producing, storage→load always when load > threshold,
  LVDC by its sign).
- Each module is a link: PV → Solar page, Storage → Storage page, Load → Loads page.
- Invalid / stale values grey as elsewhere. Remove the old detailed blocks and their unused texts.

## Check

- 360 × 640 portrait: whole scheme visible with at most a little scrolling, no horizontal scroll; desktop centred.
- Animation direction matches reality at the time of the check (day: PV → storage; LVDC by the voltage difference).
- Report: what changed, sign convention check, screenshots of the Solar page and the scheme if possible.
