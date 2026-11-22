# Grafana: water per day + new "UHA Statistics" dashboard

Repo UHARPI, `UHA/Grafana/make_dashboards.py` only (regenerate, `deploy_grafana.sh`). Lightweight mode, short
report. Branch `feature/grafana-statistics`. English, short names from `WS/i18n/texts.json`, the unified colors
(production green, battery yellow, consumption red). Consumption rules from UHA_FW
`UHA_COMMON/VarDefs/ENERGY_TOPOLOGY.md`: the consumption breakdown and the inverters are never summed together.

Data: counters (`agg: delta`) are in `agg_15min` as increments; agg_15min is kept forever (only raw rows expire),
so long-term sums come from agg_15min. Water: `CONS_COLD_L` = **total** water (dictionary "Voda celkem"),
`CONS_HOT_L` = hot water, which is **part of** the total — never stack hot on top of total. Local time
(Europe/Prague) for days, months, years. The DB is only a few days old: panels must work with partial periods.

## 1. Water per day

New panel **Water per day (last 30 days)**: Bar chart (like "Energy per day"), per local day **Total** and **Hot**
side by side, unit litres (show m³ only if the axis gets large — your choice, say which). Put it in the new
Statistics dashboard (below) and also at the bottom of "UHA Temperatures" next to the heating panels (it is the
closest existing place); if you think one place is enough, say why.

## 2. New dashboard "UHA Statistics"

Default time range **This month** (`now/M`), the time picker selects the period for the period panels (Grafana
quick ranges: this/last month, this/last year, or any custom range).

Rows:
1. **Period totals** (follow the time picker) — Stat or Table panels:
   - Energy: PV house (`LPV1_PROD_WH`), PV workshop (`LPV2_PROD_WH`), PV total, consumption total
     (`LLOAD1_CONS_WH + LLOAD2_CONS_WH`), balance.
   - **Consumption breakdown**: one table with the same categories as "Loads per day" in UHA Energy (reuse the same
     category list from one place in the generator — no copy), kWh and share of total in %, sorted by size. "Other"
     included.
   - **Inverters** (separate table, clearly titled, not part of the breakdown): AC energy per inverter (300 W, 3 kW,
     5 kW, Axpert, Victron).
   - Water: total, hot (litres and m³).
   - Heat: boiler heat (`BOILER_HEAT`, counter), electric heater (`EL_HEATER_CONS_WH`).
2. **Daily** (follow the time picker; one bar per local day): Energy per day (production / consumption side by side,
   balance hidden by default — same as UHA Energy), Water per day.
3. **Monthly** (fixed range: last 24 months via the panel's relative time override): bars per local month —
   production vs consumption side by side; loads per month stacked by category; water total and hot side by side.
4. **Yearly** (fixed range: last 10 years): bars per year — production, consumption, water total.

SQL: group the agg_15min increments by local day / month / year (`strftime(..., 'localtime')`); keep the helpers
small and commented. Check speed on the Pi for a 1-year range (synthetic is not needed — just measure the query on
the existing data and estimate). No UhaGatePy change.

## Check

- All panels on "This month", "Last 7 days", a custom range of 2 days: no errors, totals = sum of the daily bars.
- Consumption breakdown total = consumption total for the same range.
- Water: hot ≤ total every day.
- Report: panels, the speed check, anything that needs Martin's eye (he checks visually in the browser).
