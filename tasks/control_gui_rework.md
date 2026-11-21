# Control GUI rework (ctrl.uha.mkresta.cz): pages, widgets, texts

Repo UHARPI (+ UHA_FW `UHA_COMMON/VarDefs/uha_vars.yaml`, only the UI keys `step:` — see below). Lightweight mode:
implement, deploy, check, short report. Branch `feature/control-gui`.

**Run after `tasks/monitoring_gui_rework.md` is merged**: it creates `WS/i18n/texts.json` (single text source from
Martin's dictionary), the unified colors and the hamburger menu; reuse them here, do not make a second copy of the
logic (shared JS/CSS where practical, e.g. `WS/js/uha-menu.js`, `WS/css/uha-colors.css`).

Keep what works: generic from `GET /api/commands` + `uha2.json` states, feedback "čekám na změnu…" / "stav se
nezměnil", command = request, state = truth (`CMD_spec.md`). No framework. UhaGatePy and the API are unchanged.

## 1. Pages (instead of one long page)

`WS/control/`:
- `index.html` — **Světla** (category `light`), the most used page, opens first.
- `heating.html` — **Topení a rekuperace** (categories `heating`, `ventilation`).
- `other.html` — **Ostatní**: Žaluzie (`blind`), Měniče (`inverter`), Vytěžování (placeholder, section 4), and any
  command without a known category.
- `history.html` — the command history table (today at the bottom of the page), reachable from the menu and a small
  link "Historie příkazů ›" on each page.
Page → categories mapping in one table in JS. One shared `control.js` (+ small per-page config), not four copies.

Menu: the same hamburger menu as monitoring, with the control pages, plus links to the monitoring pages
(`https://uha.mkresta.cz/uha.html` …) and Grafana (`https://uha.mkresta.cz/grafana/`), language switch CZ/EN.

## 2. Texts

All labels from `texts.json`: command names from the `cmds` section (Martin's dictionary sheet "Příkazy YAML"),
enum item names from `enums`, page/section titles from `ui` (`ctrl.*` keys). Section title "Měniče" (not
"Střídače"). Missing keys: add `ctrl.*` keys to the json and list them in the report for the dictionary.
The ctrl server root is `/home/pi/Web/control/`, so `/i18n/` is not reachable there: the deploy copies
`WS/i18n/texts.json` (and the shared js/css) into `/home/pi/Web/control/` — **no nginx change**. Repo keeps one copy.

## 3. Widgets

Compact rows (short names leave room): name | control | state, phone first (360 px wide).

- **Lights** (uint32 % 0..100): a **toggle switch** (small, CSS only) + to its right a **horizontal brightness
  slider**. State shown as **brightness in %**, on a grey background at 0 %, yellow (battery/light yellow of the
  unified colors) above 0. Toggle sends 0 / 100 as today. The slider is prepared but **disabled** for now
  (`DIMMING_ENABLED = false` in one place; it shows the current state value). When enabled later it sends the value
  on release (nodes and protocol do not dim yet).
- **Blinds** (enum BlindCmd): buttons **▲** (Up), **■** (Stop), **▼** (Down) as symbols (with `title`/aria label from
  the texts); **no button for `None`** (item 0). State = enum name from the texts.
- **Setpoints** (float, `heating`/`ventilation`): **− value +** stepper: big value in the middle, round − / +
  buttons. Each press changes the shown value by `step` (clamped to min..max, displayed as "pending" style); the
  command is sent **1.5 s after the last press** (debounce), then the usual feedback; current state below in small
  text when it differs from the pending value. Long press repeats. Same stepper for RECU (CO₂ setpoint, anti-dry).
  Steps (UI-only YAML key `step:`, not used by FW, no FW build needed): interior temperatures
  `CMD_UP_REQ_DAY/NIGHT`, `CMD_DOWN_REQ_DAY/NIGHT` → **0.1**; `CMD_EXHAUST_SET` → **1**; `CMD_AKUPACK_SET_DAY/NIGHT`
  → **1**; RECU unchanged (50 ppm, 1 %). Change the YAML in UHA_FW on a branch there (`feature/ui-steps`, YAML only,
  bump the YAML `version` if the validator requires it), deploy it to the Pi with the UhaGatePy `deploy.sh` way.
  Martin merges/pushes UHA_FW.
- **Inverters** (bool, state enum InverterState): the **same toggle switch** as lights; state text = enum item
  (Off / On / OnKeepSetting / KeepOn / AutoOff) from the texts.
- Any other type keeps a generic fallback (number input + "Nastavit").

## 4. Placeholders for later (GUI only, no protocol yet)

- **Vytěžování** section on `other.html`: rows **EVSE** (state `ST_EVSE_RELAY`), **Topení dílna** (state
  `ST_WS_HEATING_RELAY`), **El. ohřev** (state `EL_HEATER_STATUS`, enum text): toggle switch **disabled**, state
  shown live, small note "zatím nelze ovládat". Defined in a small JS list (no YAML commands exist).
- Later (do **not** build now, just keep the row layout open for an extra control): for inverters and these loads a
  "run for time" (e.g. 5 kW inverter on for 3 h, no auto-off) or "consume energy" (EVSE until 5 kWh) setting.

## 4b. Cross-links monitoring ↔ control

Small button "Ovládat ›" (text from the dictionary, `mon.*` key) on the monitoring pages, linking to the matching
control page **and section** (anchor per section id, e.g. `https://ctrl.uha.mkresta.cz/other.html#inverter`):
- Loads, inverter card → `other.html#inverter`; Energy scheme, inverter blocks → same.
- Heat page and heat scheme → `heating.html#heating`; Climate RECU card and RECU scheme → `heating.html#ventilation`.
- Battery page, workshop pack → `heating.html#heating` (akupack heater setpoints).
- Home: no button on the cards (cards are links already); the menu has the control pages.
And back: each control section has a small "Přehled ›" link to the matching monitoring page.
Mapping in one table (section → monitoring page). Note: without a client certificate the ctrl link answers 400 —
accepted (only family devices have certificates); no detection needed.

## 5. Look

Same dark theme and unified colors as monitoring (`uha.css` variables). Buttons/toggles at least 40 px touch height.
Cards per section like monitoring. No inline script/style in the pages (ctrl CSP is `default-src 'self'`).

## Deploy & check

- Backup `tar czf /home/pi/control-backup-<date>.tgz -C /home/pi/Web control`, copy `WS/control/*` + the shared
  js/css + `texts.json` to `/home/pi/Web/control/`. Do not touch nginx, UhaGatePy, the json files.
- Check on the phone-sized window (360 × 640) and Martin's real use later: lights toggle → state % and color, blinds
  ▲■▼, stepper with debounce sends once, clamped value shown (e.g. interior above 25 °C), inverter toggle, history
  page, menu, CZ/EN, no console/CSP errors. Live tests: **lights only** (on/off once, then back to the
  previous state). Do not send inverter, blind or setpoint commands — Martin tests those; for them check the UI
  with the commands not sent (e.g. a dry-run flag `?dry=1` that logs instead of POSTing).
- Report: per page what changed, new `ctrl.*` keys for the dictionary, YAML step change (branch/commit in UHA_FW).
