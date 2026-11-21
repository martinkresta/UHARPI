# Monitoring GUI rework (uha.html pages) + UI texts + schematic pages

Repo UHARPI (read UHA_FW `UHA_COMMON/VarDefs/uha_vars.yaml` for names/units). Lightweight mode: implement, deploy,
check on the Pi and on a phone-sized browser window, short report. Branch `feature/monitoring-gui`.

Scope: the monitoring pages `WS/uha*.html`, `WS/js/uha-common.js`, `WS/css/uha.css` (served from `/home/pi/Web/`,
public at `https://uha.mkresta.cz/uha.html`). **Not** in scope: Grafana, the control page `WS/control/` (next
briefs), UhaGatePy. Do not delete `WS/index.html` and its assets (`js/uha.js`, `js/bms.js`, `vendor/`, `css/sb-admin*`)
— it goes away later; it is the reference for colors and the cell thresholds.

Before starting: `WS/uha-climate.html` has an uncommitted change by Martin ("Bike shed") — commit it on the branch
as his change first (or keep it), never overwrite it.

## 1. UI texts from the dictionary (single text source)

Martin's dictionary is a spreadsheet, exported to `WS/i18n/uha_ui_dict.xlsx` (Martin puts it there). Sheets:
- `UI texty`: Klíč | Aktuálně | CZ | EN | Kde | Poznámka — page/card/label texts, keys like `mon.nav.home`,
  `mon.energy.*`, `ctrl.*`, `graf.*`.
- `Proměnné YAML`: Klíč (YAML) | Aktuálně | CZ | EN | CZ krátce | EN krátce | Jednotka | Skupina YAML | Poznámka —
  per VARS2 variable. `{n}` in a name = array index (cells: "Článek {n}").
- `Příkazy YAML`, `Enumy YAML`: same idea for commands and enum items (used later by ctrl).

Do:
- `UHA/tools/dict_to_texts.py` (python3 + openpyxl; if openpyxl is missing on the PC, ask Martin — do not pip install
  silently): reads the xlsx by header names (not column letters), writes `WS/i18n/texts.json`:
  `{"ui": {key: {"cz","en"}}, "vars": {NAME: {"cz","en","cz_short","en_short"}}, "cmds": {...}, "enums": {...}}`.
  Empty cell → fall back to the other language, then to the key. Commit both the xlsx and the json; re-running the
  script after Martin edits the dictionary must be the whole update procedure (document it in `WS/i18n/README.md`).
- `uha-common.js`: load `i18n/texts.json` once; `U.t(key)` for UI texts, `U.vname(NAME, n)` full name,
  `U.vshort(NAME, n)` short name. **No user-visible string literal stays in the page files** — every label comes
  from `texts.json`. Missing key → show the key (so gaps are visible) and list missing keys once in the console.
  New texts the pages need: add rows to the json under new `mon.*` keys AND list them in the report so Martin adds
  them to the dictionary (the xlsx stays the source).
- Language: CZ default, EN switch in the menu, remembered in `localStorage` (wrapped in try/catch). Number format
  follows the language (cs: decimal comma).
- Use the **short** names inside a card/group whose title already says the measure or the area (e.g. the Loads
  table: "Kuchyň", not "Kuchyň – výkon"); full names only where the context is missing (All data page, tooltips).

## 2. General rules (all pages)

- **Group by meaning, never by board/node.** No IOBOARD_D / IOBOARD_U / ELECON split visible in the UI.
- **Colors**, unified in `uha.css` variables, taken from index.html (Bootstrap): production/solar green `#28a745`,
  consumption/load red `#dc3545`, battery yellow `#ffc107`. Keep the current amount of color (card top border, bars,
  chart fills) — only re-map: today's `--solar` (yellow) → green, `--bat` (green) → yellow, `--load` (blue) → red.
  Status colors ok/warn/bad stay separate from these meanings (they may share hues; keep them readable on yellow).
  Heat/climate colors free (keep). Charts on these pages use the same three colors where it makes sense.
- **Hamburger menu** instead of the scrolling top bar: the bar shows brand, the Status link, the feed dot/time and
  the ☰ button; the menu (overlay/drawer) lists all pages + Grafana (`/grafana/`) + Ovládání
  (`https://ctrl.uha.mkresta.cz/`) + the language switch. Works without any library.
- Cards that link to a detail page stay links (keep `U.card(..., {href})`).

## 3. Home (`uha.html`)

- Must fit **360 × 640 CSS px** without scrolling (Martin's Moto G54 ≈ 412 × ~800 usable; most phones are 360–414
  wide). Today only 4 of 5 cards fit: make cards denser (smaller paddings/gaps, compact tiles, 2-column grid of small
  cards on narrow screens if needed). Desktop may stay roomy.
- Content equivalent to index.html's top cards:
  - **Solar** (title "Solar", not "Solar production"): power, today kWh; small line PV voltage (`MPPT_SOLAR_VOLTAGE_V`)
    and charging current (`CHARGING_A`). Optional vertical bargraph of power vs installed peak (constant in one
    place, ask Martin for the value in the report; until then 5000 W).
  - **Battery**: no SOC ring. SOC % big + a simple vertical battery symbol filled by SOC (or a vertical bar) in
    yellow (fill turns warn/bad below 40/20 % as today); stored kWh, today diff (`BAT_*`: use the closest existing
    variable, say which one), voltage, current, charging/discharging/idle.
  - **Load** (title "Load", not "Consumption"): power, today kWh; small line current. No bargraph.
  - **Heat**: tank max, heat energy, and **water consumption** (cold + hot, `CONS_COLD_L`, `CONS_HOT_L`; no flow).
  - **House**: outside, downstairs, kids room, CO₂ **+ workshop temperature** (`TEMP_DILNA_C`).

## 4. Detail pages

- **Status**: as is. Prepare (hidden while no data) columns **Uptime** and **FW version** per node, read from
  `uha_status.json` `Nodes.<X>.UptimeS` / `Nodes.<X>.FwVersion` when present — the gateway does not send them yet
  (separate later task).
- **All data**: keep; names from `texts.json` (full names), raw YAML name small below as today.
- **Climate**: remove the "Electronics temperature" card and the workshop battery pack temperature row. RECU card:
  only CO₂ and fans (temperatures/humidity/pressure move to the RECU schematic, section 5).
- **Loads**: add the **Victron 2 kW inverter** to the inverter list (rated 2000 W). It has no own meter yet: show
  the values of the meter `POW_WS_HEATING_W` / `CONS_WS_HEATING_WH` there as well — the meter **stays** in the circuit
  table under its dictionary name ("Topení dílna"), the value is just duplicated. Later the Victron gets its own meter:
  make the inverter list data-driven (one array, variable names per inverter) so it is a one-line change. Optional, low priority: horizontal
  bargraph of today's consumption per circuit below the table (Grafana has it, skip if it costs time).
- **Battery**: cell bars colored by **fixed thresholds** like index.html: `< 3.000 V` or `> 3.600 V` red,
  `≥ 3.500 V` yellow, otherwise green (constants in one place). Vertical range **2.8–3.8 V** (not from 0), chart
  noticeably taller (e.g. 160–200 px) so differences are visible. Min/max marking may stay as an outline, not as fill.
- **Energy**: remove the "Shunts" card (values are in the storage cards).
- **Heat**: remove the "Water" card (water consumption is on Home). Tank card: a graphic of the tank — vertical
  rounded rectangle, 6 evenly spaced levels (6 top … 1 bottom) with the temperature text on each level, fill a
  vertical gradient between the level colors; color scale **blue → red** (no green; e.g. 20 °C blue … 70 °C red,
  constants in one place). Remove the heating-circuit temperatures from the tank card (they are in the schematic).

## 5. Schematic pages (new, SCADA style)

Three new pages, linked from the menu and from the related detail page ("Schéma ›"):
`uha-energy-scheme.html`, `uha-heat-scheme.html`, `uha-recu-scheme.html`. Inline SVG generated by JS, live values
every 2 s like the other pages, same colors (green production, red consumption, yellow battery; heat lines by
temperature color). Must be readable on a phone in portrait (scale to width; text ≥ 11 px at 360 px width; allow
pinch zoom), nicer on desktop.

**Data-driven**: each page defines its topology in one JS array of blocks (id, label key, x, y, variables shown) and
links (from, to, variable for flow/direction) — so Martin can correct the topology without touching drawing code.
Invalid/stale values grey like elsewhere. Flow direction shown by a small arrow (or animated dash) only when the
power/flow is above a threshold. This is a **first proposal: Martin will review the topology**; list your
assumptions in the report.

**Energy** (toggle in the page: Výkon / Proud / Obojí, remembered in localStorage). Proposed topology (verify
against `uha_vars.yaml` groups and descriptions, ask nothing, write assumptions):
- House: PV → MPPT (`MPPT_SOLAR_*`, `MPPT_BAT_*`) → house storage `STRG1_*` = packs BMS2 220 Ah + BMS3 80 Ah
  (`BMS2_*`, `BMS3_*`) → inverters 300 W / 3 kW / 5 kW (`POW_AC300_W` …, states `ST_AC_300W` … on/off) → house
  circuits (fridge, kitchen, washing machine, technical room, other) and local load/PV (`LLOAD1_*`, `LPV1_*`).
- Workshop: PV1 / PV2 (`AXPERT_PVS1_*`, `AXPERT_PVS2_*`) → Axpert 8 kW (`AXPERT_*`, `ST_AC_AXPERT`) ↔ workshop
  storage `STRG2_*` = pack BMS1 251 Ah; Axpert AC out → EV charger (`POW_EVSE_W`), meter `POW_AXPERT_W`; Victron
  2 kW (`ST_AC_VICTRON`, value from meter `POW_WS_HEATING_W` = workshop heating, the only load on it today); local load/PV `LLOAD2_*`, `LPV2_*`.
- Totals block: `SOLAR_POWER_W`, `LOAD_W`, `BAT_*` (global).
Current mode shows A where a current variable exists, else "–"; power mode W.

**Heat** (TECHM): boiler (`TEMP_BOILER_C`, in/out, exhaust + set `ST_EXHAUST_SET_C`, power, `ST_BOILER_STATE`,
air valve `TECHM_AIR_VALVE_SIGNAL_PCT`, pump `ST_PUMP_BOILER`) → tank hot side in/out (`TEMP_TANK_IN_H_C`,
`TEMP_TANK_OUT_H_C`) → tank with 6 levels (same graphic as the Heat page) + electric heater in the tank
(`EL_HEATER_*`, `ST_EL_HEATER_COILS`) → tank cold side in/out (`TEMP_TANK_IN_C_C`, `TEMP_TANK_OUT_C_C`) → two
circuits: radiators (`TEMP_RAD_H_C` / `TEMP_RAD_C_C`, pump `ST_PUMP_RAD`, mixing valve `TECHM_VALVE_RAD_PCT`, target
`TECHM_REQ_WATER_RAD_C`, `ST_RAD_ON`) and wall heating (`TEMP_WALL_IN_C` / `TEMP_WALL_OUT_C`, `ST_PUMP_WALL`,
`TECHM_VALVE_WALL_PCT`, `TECHM_REQ_WATER_WALL_C`, `ST_WALL_ON`); rooms upstairs/downstairs with target now
(`ST_UP_REQ_C`, `ST_DOWN_REQ_C`) vs actual (`TEMP_DOWNSTAIRS_C`, upstairs: use the closest existing sensor, say which).
Pumps as circle symbols, filled when on; valves as bow-tie symbols with %. Pipe color = temperature color.

**RECU** (classic heat-recovery unit drawing): a cross-flow exchanger in the middle; outdoor air in
(`TEMP_RECU_FC_C`) → exchanger → supply to the house (`TEMP_RECU_FH_C`, `RH_RECU_FH`, supply fan `RECU_FAN_F` %,
pressure `DP_RECU_F`); extract from the house (`TEMP_RECU_WH_C`, `RH_RECU_WASTE`, `CO2_RECU`) → exchanger → exhaust
out (`TEMP_RECU_WC_C`, fan `RECU_FAN_WASTE`, `DP_RECU_WASTE`). Mode/limit states (`ST_RECU_REMOTE_MODE`,
`ST_RECU_LIMIT`) as text. Optionally the heat-recovery efficiency (FH−FC)/(WH−FC) in %, shown only when
|WH−FC| > 5 K.

## Deploy & check

- No deploy script exists for `WS/`: copy the changed/new files with `scp` to `pi@uharpi:/home/pi/Web/` (keep the
  folder layout; **never** touch `/home/pi/Web/control/`, the json files or their `/dev/shm` symlinks). Backup first:
  `tar czf /home/pi/web-backup-<date>-gui.tgz -C /home/pi Web --exclude='*.json'`.
- Check every page live (`https://uha.mkresta.cz/uha.html`) and locally with `python -m http.server` (sample data) in
  a 360 × 640 and a 412 × 800 window: Home without scrolling, menu works, EN/CZ switch, no console errors, no
  missing-key warnings (or list them).
- Report: what changed per page, missing dictionary keys added, assumptions for the schematics, the solar peak
  constant, screenshots of Home and the three schematics if you can.
