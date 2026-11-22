# Monitoring pages tuning: Solar / Storage / Packs split, Heat cards, RECU scheme colors

Repo UHARPI, `WS/` only. Lightweight mode: implement, deploy (as in `tasks/monitoring_gui_rework.md`), check on
360 px and desktop, short report. Branch `feature/monitoring-tuning`.

**Run after `tasks/grafana_energy_views.md` is merged** — it adds things to the Energy page (storage balances,
Axpert PV/DC/AC/losses) that this task moves. Reference for the energy data: UHA_FW
`UHA_COMMON/VarDefs/ENERGY_TOPOLOGY.md`. All texts via `texts.json` (`U.t`, `U.vshort`, `U.vmeasure`); list new
`mon.*` keys in the report for the dictionary.

## 1. Split the Energy page by meaning (Home cards keep linking to them)

- **Solar** page (`uha-solar.html`, target of the green Home card **Solar**): production only.
  - Totals: `SOLAR_POWER_W`, `SOLAR_ENERGY_TODAY_WH`.
  - Card **MPPT (house)**: as now on the Energy page.
  - Card **Axpert PV (workshop)**: only the PV side, the equivalent of the MPPT card: PV power total
    (`AXPERT_SOLAR_W`), PV1 and PV2 (W / V / A), PV today (`LPV2_PROD_WH`). **No** AC power, load, battery or losses
    here.
- **Storage** page (`uha-storage.html`, target of the yellow Home card **Battery**): global balance (battery part:
  SOC, stored energy, voltage, current, power, balance today), Storage 1 (house), Storage 2 (workshop) with their
  balances today, the LVDC link estimate (if the Grafana task added a formula for it, reuse the same; mark "≈").
  Link to the Packs page.
- **Packs** page (today's `uha-battery.html`, title "Akupacky"/"Battery packs"): BMS data per pack as now.
- **Axpert inverter part** (AC power, load, DC input / AC output / losses today): move to the **Loads** page
  (inverter section), next to the other inverters.
- Remove `uha-energy.html` (or redirect it to `uha-solar.html`); update the menu (Solar, Storage, Packs, Loads, …,
  schemes) and every link to it. The energy scheme stays and is linked from Solar and Storage.
- **Check every value** on Storage and Packs: remove what is meaningless — at least the per-pack "today" values
  (`BMSx_TODAY_ENERGY_WH`: BMS "charged today" only, empty for the JK-BMS). If something else looks wrong or
  doubtful (e.g. optimal charging current, capacity, balanced today), do not guess: list it in the report with the
  current value and why, Martin decides.

## 2. Heat page

- **Accumulation tank** card (replaces the big tank graphic card and the "Electric heater" card): a **compact** tank
  — a narrow vertical tank (about 70–90 px wide, ~150 px high) with 6 bands colored blue → red and the temperature
  written in each band, placed **beside** the rows, not above them — so the card is no taller than the other cards.
  Rows: heat energy (`HEAT_TOTAL_WH`), and the electric heater: status (`EL_HEATER_STATUS`), current or power,
  coils on (`ST_EL_HEATER_COILS`), consumption today (`EL_HEATER_CONS_WH`). If you find a better compact layout,
  fine — keep the information density high.
- **Boiler** card: labels **without the word "Kotel"/"Boiler"** (the card title says it; use `U.vmeasure` or a
  local label: "Vstup", "Výstup", "Spaliny", "Klapka vzduchu"…). Remove the row "nastavené spaliny"
  (`ST_EXHAUST_SET_C`). Swap heat and temperature: **heat (`BOILER_HEAT`) as the first big tile**, the boiler
  temperature as a normal row; power and state stay tiles.
- Heat energy / heating circuits card: unchanged (apart from short labels).

## 3. Climate page

- RECU card stays minimal: CO₂, fans, and the current mode (`ST_RECU_REMOTE_MODE`) if it fits; everything else is
  on the RECU scheme (link as now).

## 4. RECU scheme (`uha-recu-scheme.html`)

- Color the four air ducts by temperature on a **0–25 °C** blue → red scale (below 0 °C full blue, above 25 °C full
  red; constants in one place, separate from the tank scale). Cold and warm air must be obvious at a glance.
- Write the **heat-recovery efficiency** and the **mode** (`ST_RECU_REMOTE_MODE`, enum text) **inside the exchanger
  symbol**; shrink the font if needed, efficiency hidden when |WH − FC| ≤ 5 K as now.

## Check

- Home: Solar → Solar page, Battery → Storage page, Load → Loads; all menu links work; no link to the removed page.
- Heat page: tank card about as tall as the boiler card on desktop and phone.
- RECU scheme: in cold weather the outdoor/exhaust ducts are blue, supply/extract warm.
- Report: pages changed, values removed or questioned, new dictionary keys, screenshots of Solar, Storage, Heat and
  the RECU scheme if possible.
