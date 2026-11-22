#!/usr/bin/env python3
"""Writes the Grafana dashboards (dashboards/*.json) from the panel lists below.

Edit this file, run `python make_dashboards.py`, commit both, deploy with deploy_grafana.sh.
(Dashboards edited in the Grafana UI cannot be saved over the provisioned files.)

The database (UhaGatePy db_log.py): vars(id, name, unit, log_s, agg), raw(var_id, ts, value) every 10 / 60 s,
kept 30 days, agg_15min(var_id, ts, value) kept forever; ts = UTC unix seconds, start of the interval.
agg_15min holds the mean for `agg: avg` variables and the increment for counters (`agg: delta`).

Which table a panel reads depends on the shown time range (one SQL per panel, see avg_sql / calc_sql):
  range <= 2 days   raw,       buckets of Grafana's $__interval (at least the variable's log_s)
  range <= 60 days  agg_15min, buckets of $__interval (at least 15 min)
  range > 60 days   agg_15min, one value per day; the day is the CET day (UTC+1, winter time) all year, because
                    converting every row to local time costs ~3x more on the Pi 3 (1 year of 16 cells: 8 s instead
                    of 2.4 s for the bare query); in summer the day starts at 01:00 local time - irrelevant for averages
Measured on the Pi 3 with a full-size database, one panel of 16 cells: 1 day ~1.3 s, 3 days ~0.4 s, 30 days
~0.6 s, 1 year ~4 s.
Energy bars (day_sql) always read agg_15min: SUM per exact local day (counters directly, powers integrated as
mean x 15 min). The last, unfinished 15 min are therefore missing from the bars (up to ~16 min behind).
Local time: SQLite 'localtime' = time zone of the Pi (Europe/Prague), also for summer time.

Labels: Grafana is English. Legends use the English short names of WS/i18n/texts.json (vars.<NAME>.en_short, then
en, then the name) unless a panel gives its own label; never the YAML names.

States dashboard (UhaGatePy 0.4.0): events(var_id, ts, value), one row per change of an `agg: event` variable
(invalid = NULL), kept forever. The panels are generated from uha_vars.yaml (env UHA_VARS_YAML, default the
UHA_FW checkout), grouped by category (YAML command `category:` of the state, STATE_CATEGORY for the rest).
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "UhaGatePy"))
from uhagatepy import vars_def  # noqa: E402  (the gateway's YAML reader)

YAML = os.environ.get("UHA_VARS_YAML", "C:/Martin/GIT/UHA_FW/UHA_COMMON/VarDefs/uha_vars.yaml")
TEXTS = os.path.join(HERE, "..", "..", "WS", "i18n", "texts.json")
DS = {"type": "frser-sqlite-datasource", "uid": "uhalog"}
RAW_MAX_S = 2 * 86400        # up to this range read raw (more rows would be slow on the Pi 3)
DAILY_MIN_S = 60 * 86400     # above this range one value per local day

# colours as on the web (WS/css/uha.css)
SOLAR, BATTERY, LOAD = "#28a745", "#ffc107", "#dc3545"

with open(TEXTS, encoding="utf-8") as f:
    _TEXTS = json.load(f)


def en(name):
    """English short name from the dictionary (en_short, en, else the name)."""
    v = _TEXTS["vars"].get(name, {})
    return v.get("en_short") or v.get("en") or name


def enum_text(enum, value, fallback):
    return _TEXTS["enums"].get(enum, {}).get(str(value), {}).get("en") or fallback


# Start of the local day of a unix time t (SQL expression), e.g. 2026-11-14 00:00 Prague as UTC seconds.
# Exact (summer time too) but slow per row: only for the energy bars (few rows).
LOCAL_DAY = "CAST(strftime('%s', date({t}, 'unixepoch', 'localtime'), 'utc') AS INTEGER)"
# "Nov 21" for the bar chart x axis (local date of the day start d)
DAY_LABEL = ("substr('JanFebMarAprMayJunJulAugSepOctNovDec', CAST(strftime('%m', {d}, 'unixepoch', 'localtime') "
             "AS INTEGER) * 3 - 2, 3) || ' ' || CAST(strftime('%d', {d}, 'unixepoch', 'localtime') AS INTEGER)")

RANGE_CTE = "WITH q AS (SELECT $__from / 1000 AS f, $__to / 1000 AS t, $__interval_ms / 1000 AS i)"


def q(s):
    """SQL string literal."""
    return "'" + s.replace("'", "''") + "'"


def names_sql(names):
    return ", ".join(q(n) for n in names)


def series(items):
    """[(label, name)] from a list of names, (label, name) pairs, or a {name: label} dict."""
    if isinstance(items, dict):
        return [(label, name) for name, label in items.items()]
    return [(en(i), i) if isinstance(i, str) else i for i in items]


def label_sql(pairs):
    """SQL label of v.name: CASE v.name WHEN 'X' THEN 'Label' ... END."""
    whens = " ".join(f"WHEN {q(n)} THEN {q(label)}" for label, n in pairs)
    return f"CASE v.name {whens} ELSE v.name END"


def src_cte(names, raw_bucket):
    """Rows of the variables in the range: raw up to RAW_MAX_S, agg_15min beyond; b = bucket size in s."""
    n = names_sql(names)
    return f"""src AS (
  SELECT v.name, x.ts, x.value, {raw_bucket} AS b
  FROM q, vars v CROSS JOIN raw x ON x.var_id = v.id AND x.ts >= q.f AND x.ts < q.t
  WHERE v.name IN ({n}) AND q.t - q.f <= {RAW_MAX_S}
  UNION ALL
  SELECT v.name, x.ts, x.value, CASE WHEN q.t - q.f > {DAILY_MIN_S} THEN 86400 ELSE max(q.i, 900) END
  FROM q, vars v CROSS JOIN agg_15min x ON x.var_id = v.id AND x.ts >= q.f AND x.ts < q.t
  WHERE v.name IN ({n}) AND q.t - q.f > {RAW_MAX_S}
)"""


BUCKET = "CASE WHEN b >= 86400 THEN ts - (ts + 3600) % 86400 ELSE ts - ts % b END"


def avg_sql(items, scale=1.0):
    """Mean of avg variables, one series per variable (column `name` = label)."""
    pairs = series(items)
    names = [n for _, n in pairs]
    factor = "" if scale == 1.0 else f" * {scale}"
    src = src_cte(names, "max(q.i, v.log_s)").replace("SELECT v.name,", f"SELECT {label_sql(pairs)} AS name,")
    return f"""-- raw up to {RAW_MAX_S // 86400} days, agg_15min beyond, one value per (CET) day beyond {DAILY_MIN_S // 86400} days
{RANGE_CTE},
{src}
SELECT {BUCKET} AS time, name, AVG(value){factor} AS value
FROM src
GROUP BY 1, 2
ORDER BY 1"""


def expr_vars(expr):
    """Variable names used as {NAME} in an expression."""
    import re
    return re.findall(r"\{([A-Z0-9_]+)\}", expr)


def sql_expr(expr):
    return expr.replace("{", '"').replace("}", '"')


def calc_sql(items):
    """Series computed from the bucket means of several variables, wide (one column per label).
    items = [(label, expr)], expr in SQL with {NAME} = mean of that variable in the bucket (NULL if it has no row
    there, so a computed value with a missing input is not drawn)."""
    names = sorted({n for _, e in items for n in expr_vars(e)})
    cols = ",\n    ".join(f"AVG(CASE WHEN name = {q(n)} THEN value END) AS \"{n}\"" for n in names)
    outs = ",\n       ".join(f"{sql_expr(e)} AS {q(label).replace(chr(39), chr(34))}" for label, e in items)
    return f"""-- computed from the bucket means (raw up to {RAW_MAX_S // 86400} days, agg_15min beyond)
{RANGE_CTE},
{src_cte(names, "max(q.i, 60)")},
p AS (
  SELECT {BUCKET} AS time,
    {cols}
  FROM src
  GROUP BY 1
)
SELECT time,
       {outs}
FROM p
ORDER BY 1"""


# Period buckets for the sums (key = SQL of the hour start `hr`, label = SQL of the key `k`). The 15 min rows are first
# summed per UTC hour (cheap integer grouping), only the hours are converted to local time: exact also across summer
# time (Prague offsets are whole hours) and ~4x fewer 'localtime' calls on the Pi 3.
MONTHS = "'JanFebMarAprMayJunJulAugSepOctNovDec'"
BUCKETS = {
    "day": (LOCAL_DAY.format(t="hr"), DAY_LABEL.format(d="k")),
    "month": ("strftime('%Y-%m', hr, 'unixepoch', 'localtime')",
              f"substr({MONTHS}, CAST(substr(k, 6, 2) AS INTEGER) * 3 - 2, 3) || ' ' || substr(k, 1, 4)"),
    "year": ("strftime('%Y', hr, 'unixepoch', 'localtime')", "k"),
    "total": ("0", "'total'"),
}
FULL_DAY_START = "CAST(strftime('%s', date(q.f, 'unixepoch', 'localtime', '+1 day'), 'utc') AS INTEGER)"


def sums_cte(items, bucket, full_days):
    """CTEs h (per variable and UTC hour) and p (one row per bucket, one column per variable = its energy / volume in
    the bucket): counters (agg: delta) summed, powers (name ending in _W) integrated from the 15 min means (Wh).
    full_days: start at the first full local day of the range (rolling "last 30 days"), else at the range start."""
    names = sorted({n for _, e in items for n in expr_vars(e)})
    start = FULL_DAY_START if full_days else "q.f"
    cols = []
    for n in names:
        c = f"COALESCE(SUM(CASE WHEN name = {q(n)} THEN s END), 0)"
        cols.append(f"{c} / 4.0 AS \"{n}\"" if n.endswith("_W") else f"{c} AS \"{n}\"")
    cols = ",\n    ".join(cols)
    return f"""{RANGE_CTE},
h AS (
  SELECT v.name AS name, x.ts - x.ts % 3600 AS hr, SUM(x.value) AS s
  FROM q, vars v CROSS JOIN agg_15min x ON x.var_id = v.id AND x.ts >= {start} AND x.ts < q.t
  WHERE v.name IN ({names_sql(names)})
  GROUP BY 1, 2
),
p AS (
  SELECT {BUCKETS[bucket][0]} AS k,
    {cols}
  FROM h
  GROUP BY 1
)"""


def period_sql(items, bucket="day", full_days=True, scale=1000.0, xcol="day"):
    """Sums per local day / month / year for the bar charts, wide: column xcol ("Nov 21", "Nov 2026", "2026") + one
    column per label. items = [(label, expr)], expr with {NAME} = the bucket sum of that variable; value / scale
    (Wh -> kWh by default, litres: scale 1 or 1000 for m3)."""
    outs = ",\n       ".join(f"({sql_expr(e)}) / {scale} AS \"{label}\"" for label, e in items)
    return f"""-- sums per local {bucket}: counters = SUM of the 15 min increments, powers (_W) = SUM of the 15 min means / 4
{sums_cte(items, bucket, full_days)}
SELECT {BUCKETS[bucket][1]} AS {xcol},
       {outs}
FROM p
ORDER BY k"""


def day_sql(items):
    """kWh per local day, the days of the range from its first full local day (rolling "last 30 days")."""
    return period_sql(items, "day", True)


def total_sql(items, scale=1000.0, share_of=None, name_col="Category", value_col="kWh"):
    """Sums over the whole range (time picker). Without share_of: one row, one column per label (Stat panel).
    With share_of (expr): one row per label + its share of share_of in %, largest first (Table panel)."""
    head = f"-- sums over the selected range\n{sums_cte([it[:2] for it in items], 'total', False)}\n"
    if share_of is None:      # an item may carry its own scale: (label, expr, scale)
        outs = ",\n       ".join(f"({sql_expr(it[1])}) / {it[2] if len(it) > 2 else scale} AS \"{it[0]}\"" for it in items)
        return head + f"SELECT {outs}\nFROM p"
    total = sql_expr(share_of)
    rows = "\n  UNION ALL\n".join(
        f"  SELECT {q(label)} AS \"{name_col}\", ({sql_expr(e)}) / {scale} AS \"{value_col}\", "
        f"({sql_expr(e)}) * 100.0 / NULLIF({total}, 0) AS \"Share\" FROM p" for label, e in items)
    return head + f"SELECT * FROM (\n{rows}\n) ORDER BY 2 DESC"


# ---- panels --------------------------------------------------------------------------------------------------

def fixed(color):
    return {"id": "color", "value": {"mode": "fixed", "fixedColor": color}}


def by_name(label, *props):
    return {"matcher": {"id": "byName", "options": label}, "properties": list(props)}


def color_overrides(colors):
    return [by_name(label, fixed(c)) for label, c in colors.items()]


def hidden_by_default(visible):
    """Grafana's own legend-click override: all series except `visible` hidden (a click in the legend shows them)."""
    return {"__systemRef": "hideSeriesFrom",
            "matcher": {"id": "byNames", "options": {"mode": "exclude", "names": visible, "prefix": "All except:",
                                                     "readOnly": True}},
            "properties": [{"id": "custom.hideFrom", "value": {"legend": False, "tooltip": False, "viz": True}}]}


def target(sql, kind="time series"):
    return {"refId": "A", "datasource": DS, "queryType": kind, "rawQueryText": sql, "queryText": sql,
            "timeColumns": ["time"] if kind == "time series" else []}


def panel(title, sql, unit, x, y, w=12, h=8, bars=False, stack=False, decimals=None, time_from=None, desc="",
          colors=None, wide=False, fill=0):
    """Time series panel. Long SQL (time, name, value) names the series by the label `name`; wide SQL (calc_sql)
    by its column names (wide=True)."""
    custom = {"drawStyle": "line", "lineWidth": 1, "fillOpacity": fill, "showPoints": "never", "spanNulls": False,
              "axisSoftMin": None}
    if bars:
        custom.update({"drawStyle": "bars", "fillOpacity": 80, "barAlignment": 1, "lineWidth": 1})
    if stack:
        custom["stacking"] = {"mode": "normal", "group": "A"}
    defaults = {"unit": unit, "custom": custom}
    if not wide:
        defaults["displayName"] = "${__field.labels.name}"
    if decimals is not None:
        defaults["decimals"] = decimals
    p = {
        "type": "timeseries", "title": title, "description": desc, "datasource": DS,
        "gridPos": {"x": x, "y": y, "w": w, "h": h},
        "fieldConfig": {"defaults": defaults, "overrides": color_overrides(colors or {})},
        "options": {"legend": {"displayMode": "list", "placement": "bottom", "showLegend": True},
                    "tooltip": {"mode": "multi", "sort": "none"}},
        "targets": [target(sql)],
    }
    if time_from:
        p["timeFrom"] = time_from
    return p


def barchart(title, sql, x, y, w=24, h=9, stack=False, colors=None, hidden=None, desc="", time_from="30d",
             unit="kwatth", decimals=1, xfield="day"):
    """Bar chart of period_sql (x = its text column xfield): bars side by side, or stacked.
    time_from None = the dashboard time picker, else a relative override ("30d", "2y")."""
    overrides = color_overrides(colors or {})
    if hidden:
        overrides.append(hidden_by_default([c for c in colors if c not in hidden]))
    return {
        "type": "barchart", "title": title, "description": desc, "datasource": DS,
        "gridPos": {"x": x, "y": y, "w": w, "h": h},
        "fieldConfig": {"defaults": {"unit": unit, "decimals": decimals, "color": {"mode": "palette-classic"},
                                     "custom": {"fillOpacity": 85, "lineWidth": 0, "gradientMode": "none",
                                                "axisPlacement": "auto", "axisSoftMin": 0}},
                        "overrides": overrides},
        "options": {"orientation": "vertical", "xField": xfield, "stacking": "normal" if stack else "none",
                    "groupWidth": 0.8, "barWidth": 0.9, "barRadius": 0, "showValue": "never",
                    "xTickLabelRotation": -45, "xTickLabelSpacing": 0, "fullHighlight": False,
                    "legend": {"displayMode": "list", "placement": "bottom", "showLegend": True},
                    "tooltip": {"mode": "multi", "sort": "none"}},
        "targets": [target(sql, "table")],
    } | ({"timeFrom": time_from} if time_from else {})


def stat(title, sql, x, y, w=12, h=5, unit="kwatth", decimals=1, colors=None, desc="", overrides=None):
    """Stat panel of a one-row total_sql: one big number per column."""
    return {
        "type": "stat", "title": title, "description": desc, "datasource": DS,
        "gridPos": {"x": x, "y": y, "w": w, "h": h},
        "fieldConfig": {"defaults": {"unit": unit, "decimals": decimals, "color": {"mode": "fixed", "fixedColor": "text"}},
                        "overrides": color_overrides(colors or {}) + (overrides or [])},
        "options": {"reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False},
                    "textMode": "value_and_name", "colorMode": "value", "graphMode": "none", "justifyMode": "auto",
                    "orientation": "auto", "wideLayout": True, "showPercentChange": False},
        "targets": [target(sql, "table")],
    }


def share_table(title, sql, x, y, w=12, h=10, desc="", name_col="Category"):
    """Table of a total_sql with share_of: name, kWh, share % (as a bar)."""
    return {
        "type": "table", "title": title, "description": desc, "datasource": DS,
        "gridPos": {"x": x, "y": y, "w": w, "h": h},
        "fieldConfig": {"defaults": {}, "overrides": [
            by_name("kWh", {"id": "unit", "value": "kwatth"}, {"id": "decimals", "value": 1}),
            by_name("Share", {"id": "unit", "value": "percent"}, {"id": "decimals", "value": 1},
                    {"id": "min", "value": 0}, {"id": "max", "value": 100},
                    {"id": "color", "value": {"mode": "fixed", "fixedColor": LOAD}},
                    {"id": "custom.cellOptions", "value": {"type": "gauge", "mode": "basic", "valueDisplayMode": "text"}})]},
        "options": {"showHeader": True, "cellHeight": "sm"},
        "targets": [target(sql, "table")],
    }


def dashboard(uid, title, panels, time_from="now-24h", time_to="now", refresh="1m"):
    for number, p in enumerate(panels, 1):
        p["id"] = number
    return {
        "uid": uid, "title": title, "tags": ["uha"], "timezone": "Europe/Prague", "editable": True,
        "schemaVersion": 39, "version": 1, "refresh": refresh, "graphTooltip": 1,
        "time": {"from": time_from, "to": time_to},
        "timepicker": {"refresh_intervals": ["1m", "5m", "15m", "1h"]},
        "panels": panels, "templating": {"list": []}, "annotations": {"list": []},
        "links": [{"title": "UHA dashboards", "type": "dashboards", "tags": ["uha"], "asDropdown": False}],
    }


# ---- Energy ---------------------------------------------------------------------------------------------------
# Two views, never mixed or summed (ENERGY_TOPOLOGY.md "Consumption breakdown"): loads/circuits vs. inverters.

CONSUMPTION_WH = "{LLOAD1_CONS_WH} + {LLOAD2_CONS_WH}"        # DC-side daily consumption, house + workshop
PRODUCTION_WH = "{LPV1_PROD_WH} + {LPV2_PROD_WH}"
CONSUMPTION_W = "{LOAD_W}"

# The consumption breakdown, in one place: (label, energy per day in Wh, power in W, colour).
# "Other" (the rest: lights, DC loads, inverter losses, kids room + office, errors) is added by the panels.
# Axpert losses: the Axpert DC input is integrated from AXPERT_LOAD_W (logged mean), not AXPERT_ENERGY_TODAY_WH
# (not monotonic, mangled by the logger's delta reset rule).
LOAD_CATEGORIES = [
    ("Fridge", "{CONS_FRIDGE_WH}", "{POW_FRIDGE_W}", "#73bf69"),
    ("Kitchen", "{CONS_KITCHEN_WH}", "{POW_KITCHEN_W}", "#ff9830"),
    ("Washing machine", "{CONS_WASCHMACHINE_WH}", "{POW_WASCHMACHINE_W}", "#5794f2"),
    ("Technical room", "{CONS_TECHM_WH}", "{POW_TECHM_W}", "#b877d9"),
    ("Other circuits", "{CONS_OTHER_WH}", "{POW_OTHER_W}", "#8ab8ff"),
    ("Workshop", "{CONS_AXPERT_WH} - {CONS_EVSE_WH}", "{POW_AXPERT_W} - {POW_EVSE_W}", "#c4a000"),
    ("EV charger", "{CONS_EVSE_WH}", "{POW_EVSE_W}", "#1f60c4"),
    ("Workshop air conditioner", "{CONS_WS_HEATING_WH}", "{POW_WS_HEATING_W}", "#37c2c2"),
    ("Water heater", "{EL_HEATER_CONS_WH}", "{EL_HEATER_CURRENT_A} * {STRG1_VOLTAGE_V}", "#f2495c"),
    ("Axpert losses", "{AXPERT_LOAD_W} - {CONS_AXPERT_WH}", "{AXPERT_LOAD_W} - {POW_AXPERT_W}", "#8f3bb8"),
]
OTHER_COLOR = "#9e9e9e"


def with_other(total, col):
    """The categories (column col: 1 = energy, 2 = power) + "Other" = total - all of them (not clamped)."""
    rest = " - ".join(f"({c[col]})" for c in LOAD_CATEGORIES)
    items = [(c[0], c[col]) for c in LOAD_CATEGORIES] + [("Other", f"({total}) - {rest}")]
    colors = dict({c[0]: c[3] for c in LOAD_CATEGORIES}, Other=OTHER_COLOR)
    return items, colors


INVERTERS = [("Inverter 300 W", "POW_AC300_W"), ("Inverter 3 kW", "POW_AC3KW_W"), ("Inverter 5 kW", "POW_AC5KW_W"),
             ("Axpert 8 kW", "POW_AXPERT_W"), ("Victron 2 kW", "POW_WS_HEATING_W")]

# LVDC link house -> workshop (estimate, positive = house -> workshop) from the workshop bus balance:
# pack + Victron DC input = Axpert battery current + link. Both currents are + when charging (checked on the data
# of 2026-11-20/21: sunny hours both +, night Axpert 0 and pack -). The Victron (air conditioner) takes up to ~1 kW
# from the workshop bus: without it the estimate was off by up to 20 A against the voltage difference of the two
# storages; with its AC power / 0.9 it matches (12:30: +1.7 A vs +2.6 A from (STRG1_V - STRG2_V) / 0.05 ohm).
LVDC_W = "({BMS1_CURRENT_A} - {AXPERT_BAT_CURRENT_A}) * {STRG2_VOLTAGE_V} + {POW_WS_HEATING_W} / 0.9"


def energy_dashboard():
    day_loads, load_colors = with_other(CONSUMPTION_WH, 1)
    pow_loads, _ = with_other(CONSUMPTION_W, 2)
    storages = [("House storage", "{STRG1_POWER_W}"), ("Workshop storage", "{STRG2_POWER_W}"),
                ("House PV", "{LPV1_POWER_W}"), ("Workshop PV", "{LPV2_POWER_W}"),
                ("House load", "{LLOAD1_POWER_W}"), ("Workshop load", "{LLOAD2_POWER_W}"),
                ("LVDC link ≈", LVDC_W)]
    soc = panel("State of charge", avg_sql([("Total", "BAT_SOC"), ("BMS1 251 Ah", "BMS1_SOC"),
                                            ("BMS2 220 Ah", "BMS2_SOC"), ("BMS3 80 Ah", "BMS3_SOC")]),
                "percent", 0, 9, 24, 8)
    soc["fieldConfig"]["overrides"].append(by_name("Total", fixed(BATTERY), {"id": "custom.lineWidth", "value": 3}))
    loads_power = panel("Loads power", calc_sql(pow_loads), "watt", 0, 44, 24, 10, stack=True, wide=True, fill=60,
                        colors=load_colors,
                        desc="Stacked: the top is the total load (LOAD_W). Same categories as Loads per day. "
                             "Other = load - all categories; noisy, the sources refresh at different rates.")
    return dashboard("uha-energy", "UHA Energy", [
        panel("Power", avg_sql([("Solar", "SOLAR_POWER_W"), ("Battery", "BAT_POWER_W"), ("Load", "LOAD_W")]),
              "watt", 0, 0, 24, 9, colors={"Solar": SOLAR, "Battery": BATTERY, "Load": LOAD},
              desc="Battery + = charging. Mean per bucket."),
        soc,
        barchart("Energy per day (last 30 days)",
                 day_sql([("Production", PRODUCTION_WH), ("Consumption", CONSUMPTION_WH),
                          ("Balance", f"({PRODUCTION_WH}) - ({CONSUMPTION_WH})")]), 0, 17, 24, 9,
                 colors={"Production": SOLAR, "Consumption": LOAD, "Balance": BATTERY}, hidden=["Balance"],
                 desc="Production = PV house + workshop, consumption = load house + workshop (DC side). "
                      "Balance (click it in the legend) = production - consumption. Today is incomplete."),
        barchart("Loads per day (last 30 days)", day_sql(day_loads), 0, 26, 24, 10, stack=True, colors=load_colors,
                 desc="Consumption split into loads; the stack adds up to the Consumption bar of Energy per day. "
                      "Workshop = Axpert output - EV charger. Axpert losses = Axpert DC input - AC output (rough). "
                      "Other = consumption - all of the above (lights, DC loads, inverter losses, kids room + "
                      "office, measurement errors; can be negative)."),
        panel("Inverters power", avg_sql(INVERTERS), "watt", 0, 36, 24, 8,
              desc="AC output of each inverter (overload view; not a consumption breakdown). Victron 2 kW = its "
                   "only load, the workshop air conditioner."),
        loads_power,
        panel("Storages power", calc_sql(storages), "watt", 0, 54, 24, 9, wide=True,
              colors={"House storage": BATTERY, "Workshop storage": "#e0752d", "House PV": SOLAR,
                      "Workshop PV": "#96d98d", "House load": LOAD, "Workshop load": "#ff7383",
                      "LVDC link ≈": "#5794f2"},
              desc="Storage + = charging. House = ELECON, workshop = ELECON_D. LVDC link ≈ = ESTIMATE of the "
                   "power house -> workshop (+) through the cable: (workshop pack current - Axpert battery "
                   "current) x workshop voltage + Victron AC power / 0.9; workshop DC lights and the pack heater "
                   "neglected (a few A), Axpert currents in 1 A steps."),
    ])


# ---- Water ---------------------------------------------------------------------------------------------------
# CONS_COLD_L = ALL water (dictionary "Voda celkem"), CONS_HOT_L = hot water, a PART of it: side by side, never stacked.
WATER = [("Total", "{CONS_COLD_L}"), ("Hot", "{CONS_HOT_L}")]
WATER_COLORS = {"Total": "#5794f2", "Hot": LOAD}


def water_per_day(x, y, w, h, rolling=True):
    """Litres per local day, total and hot side by side (rolling: last 30 full days, else the time picker)."""
    return barchart("Water per day (last 30 days)" if rolling else "Water per day",
                    period_sql(WATER, "day", rolling, scale=1.0), x, y, w, h, colors=WATER_COLORS,
                    time_from="30d" if rolling else None, unit="litre", decimals=0,
                    desc="Total = all water, hot = the part of it that is hot water (side by side, not stacked).")


# ---- Packs ----------------------------------------------------------------------------------------------------

def cells(pack):
    return [(str(i), f"BMS{pack}_CELL_V_{i}") for i in range(1, 17)]


PACKS = [("BMS1 251 Ah", 1), ("BMS2 220 Ah", 2), ("BMS3 80 Ah", 3)]

packs = dashboard("uha-packs", "UHA Packs", [
    panel("BMS1 Workshop 251 Ah - cells", avg_sql(cells(1)), "volt", 0, 0, 24, 8, decimals=3),
    panel("BMS2 House 220 Ah - cells", avg_sql(cells(2)), "volt", 0, 8, 24, 8, decimals=3),
    panel("BMS3 House 80 Ah - cells", avg_sql(cells(3)), "volt", 0, 16, 24, 8, decimals=3),
    panel("Pack voltage", avg_sql([(p, f"BMS{n}_VOLTAGE_V") for p, n in PACKS] + [("Battery", "BAT_VOLTAGE_V")]),
          "volt", 0, 24, 8, 8, decimals=2),
    panel("Pack current", avg_sql([(p, f"BMS{n}_CURRENT_A") for p, n in PACKS] + [("Battery", "BAT_CURRENT_A")]),
          "amp", 8, 24, 8, 8, decimals=1),
    panel("Pack SOC", avg_sql([(p, f"BMS{n}_SOC") for p, n in PACKS] + [("Total", "BAT_SOC")]),
          "percent", 16, 24, 8, 8),
])

# ---- Temperatures ---------------------------------------------------------------------------------------------

temperatures = dashboard("uha-temperatures", "UHA Temperatures", [
    panel("Indoor & outside", avg_sql(["TEMP_DOWNSTAIRS_C", ("Office", "TEMP_OFFICE_C"), "TEMP_KIDROOM_C",
                                       "TEMP_DILNA_C", "TEMP_KOLARNA_C", "TEMP_OUTSIDE_C"]),
          "celsius", 0, 0, 24, 9),
    panel("Tank", avg_sql([("Layer 1 (bottom)", "TEMP_TANK_1_C"), ("Layer 2", "TEMP_TANK_2_C"),
                           ("Layer 3", "TEMP_TANK_3_C"), ("Layer 4", "TEMP_TANK_4_C"), ("Layer 5", "TEMP_TANK_5_C"),
                           ("Layer 6 (top)", "TEMP_TANK_6_C")]), "celsius", 0, 9, 12, 9),
    panel("Boiler", avg_sql(["TEMP_BOILER_C", "TEMP_BOILER_IN_C", "TEMP_BOILER_OUT_C", "TEMP_BOILER_EXHAUST_C"]),
          "celsius", 12, 9, 12, 9),
    panel("Heating circuits", avg_sql(["TEMP_RAD_H_C", "TEMP_RAD_C_C", "TEMP_WALL_IN_C", "TEMP_WALL_OUT_C"]),
          "celsius", 0, 18, 12, 8),
    panel("Recuperation", avg_sql(["TEMP_RECU_FC_C", "TEMP_RECU_FH_C", "TEMP_RECU_WH_C", "TEMP_RECU_WC_C"]),
          "celsius", 12, 18, 12, 8),
    panel("CO₂", avg_sql(["CO2_RECU"]), "ppm", 0, 26, 12, 8, desc="Recuperation CO₂ sensor"),
    panel("Electronics", avg_sql(["TEMP_TECHM_BOARD_C", "TEMP_IOBOARD_D_C", "TEMP_IOBOARD_U_C", "TEMP_ELECON_BOARD_C",
                                  "TEMP_BOARD_ELECON_D_C", ("Axpert", "AXPERT_TEMP_C"), ("MPPT", "MPPT_TEMP_C"),
                                  "TEMP_AKUPACK1_C"]), "celsius", 12, 26, 12, 8),
    panel("Wind (mean)", avg_sql(["METEO_WIND_AVG"]), "velocityms", 0, 34, 12, 8),
    water_per_day(12, 34, 12, 8),
])

# ---- States (events table) -----------------------------------------------------------------------------------

def two_queries(p, sql_b):
    """Add a second query (refId B) to a panel, e.g. actual temperatures from raw next to setpoints from events."""
    t = dict(p["targets"][0])
    t.update({"refId": "B", "rawQueryText": sql_b, "queryText": sql_b})
    p["targets"].append(t)
    return p


def events_sql(items):
    """State changes in the range + the state at the range start (last row before it) + the same state again at the
    range end / now, so that the timeline draws the current state up to the right edge. One series per variable.
    Invalid (NULL) becomes -1 so that the timeline shows 'invalid' instead of continuing the previous state
    (the panel connects the nulls that come from merging the series). A silent node gets an invalid row from the
    gateway after timeout_ms, so its last state is not drawn on."""
    pairs = series(items)
    n = names_sql([x for _, x in pairs])
    label = label_sql(pairs)
    return f"""-- events: changes in the range + the state at its start + the state at its end (or now)
{RANGE_CTE},
e AS (SELECT q.f, q.t, MIN(q.t, CAST(strftime('%s', 'now') AS INTEGER)) AS te FROM q)
SELECT time, name, value FROM (
  SELECT x.ts AS time, {label} AS name, COALESCE(x.value, -1) AS value
  FROM e, vars v CROSS JOIN events x ON x.var_id = v.id AND x.ts >= e.f AND x.ts < e.t
  WHERE v.name IN ({n})
  UNION ALL
  SELECT e.f, {label}, COALESCE(x.value, -1)
  FROM e, vars v CROSS JOIN events x ON x.var_id = v.id
       AND x.ts = (SELECT MAX(y.ts) FROM events y WHERE y.var_id = v.id AND y.ts < e.f)
  WHERE v.name IN ({n})
  UNION ALL
  SELECT e.te, {label}, COALESCE(x.value, -1)
  FROM e, vars v CROSS JOIN events x ON x.var_id = v.id
       AND x.ts = (SELECT MAX(y.ts) FROM events y WHERE y.var_id = v.id AND y.ts <= e.te)
  WHERE v.name IN ({n}) AND x.ts < e.te     -- no extra point if the last change is exactly at the end
) ORDER BY time"""


def on_time_sql(items):
    """Hours per local day with value > 0: intervals between consecutive rows of one variable (the last one runs
    until now), clipped to the local days of the range."""
    pairs = series(items)
    n = names_sql([x for _, x in pairs])
    label = label_sql(pairs)
    next_day = "CAST(strftime('%s', date({t}, 'unixepoch', 'localtime', '+1 day'), 'utc') AS INTEGER)"
    return f"""-- hours on per local day, from events
{RANGE_CTE},
days(d0, d1) AS (
  SELECT s, {next_day.format(t="s")} FROM (SELECT {LOCAL_DAY.format(t="q.f")} AS s FROM q)
  UNION ALL
  SELECT d1, {next_day.format(t="d1")} FROM days, q WHERE d1 < q.t
),
ev AS (
  SELECT {label} AS name, x.ts, x.value, LEAD(x.ts) OVER (PARTITION BY x.var_id ORDER BY x.ts) AS te
  FROM q, vars v CROSS JOIN events x ON x.var_id = v.id AND x.ts < q.t
       AND x.ts >= COALESCE((SELECT MAX(e.ts) FROM events e WHERE e.var_id = v.id
                              AND e.ts <= (SELECT MIN(d0) FROM days)), 0)
  WHERE v.name IN ({n})
),
iv AS (
  SELECT name, ts, COALESCE(te, MIN(q.t, CAST(strftime('%s', 'now') AS INTEGER))) AS te FROM ev, q WHERE value > 0
)
SELECT d.d0 AS time, iv.name, SUM(MIN(iv.te, d.d1) - MAX(iv.ts, d.d0)) / 3600.0 AS value
FROM days d JOIN iv ON iv.ts < d.d1 AND iv.te > d.d0
GROUP BY 1, 2
ORDER BY 1"""


ENUM_COLORS = ["#8e8e8e", "green", "blue", "orange", "purple", "red", "yellow", "dark-green", "dark-blue",
               "dark-orange", "dark-purple", "dark-red"]
INVALID_MAP = {"-1": {"text": "invalid", "color": "#3a3a3a", "index": 99}}


def timeline(title, sql, mappings, x, y, w=24, h=8, unit="none", thresholds=None, desc="", legend=False):
    steps = thresholds or [{"color": "#8e8e8e", "value": None}]
    return {
        "type": "state-timeline", "title": title, "description": desc, "datasource": DS,
        "gridPos": {"x": x, "y": y, "w": w, "h": h},
        "fieldConfig": {"defaults": {
            "unit": unit, "displayName": "${__field.labels.name}", "mappings": mappings,
            "color": {"mode": "thresholds"}, "thresholds": {"mode": "absolute", "steps": steps},
            "custom": {"fillOpacity": 80, "lineWidth": 0, "spanNulls": True}}, "overrides": []},
        "options": {"mergeValues": True, "showValue": "auto", "alignValue": "left", "rowHeight": 0.85,
                    "legend": {"showLegend": legend, "displayMode": "list", "placement": "bottom"},
                    "tooltip": {"mode": "single", "sort": "none"}},
        "targets": [target(sql)],
    }


def row(title, y):
    return {"type": "row", "title": title, "collapsed": False, "gridPos": {"x": 0, "y": y, "w": 24, "h": 1},
            "panels": []}


def step_panel(title, sql, unit, x, y, w=24, h=7, desc=""):
    """Setpoints and other numeric states: a line that holds its value until the next event."""
    p = panel(title, sql, unit, x, y, w, h, desc=desc)
    p["fieldConfig"]["defaults"]["custom"].update({"lineInterpolation": "stepAfter", "spanNulls": True,
                                                   "showPoints": "always", "pointSize": 4})
    return p


# Row of each state by meaning (never by node). States with a YAML command take its `category:`; this table
# holds the rest. None = not shown (ST_RAD_ON / ST_WALL_ON follow the pumps).
CATEGORY_ROWS = [("light", "Lights"), ("blind", "Blinds"), ("inverter", "Inverters"), ("heating", "Heating"),
                 ("loads", "Loads / relays"), ("ventilation", "Ventilation"), ("other", "Other")]
STATE_CATEGORY = {
    "ST_LIGHT_EXTERIOR_HOUSE": "light", "ST_LIGHT_EXTERIOR_WS": "light",
    "ST_AC_300W": "inverter",
    "ST_UP_REQ_C": "heating", "ST_DOWN_REQ_C": "heating", "ST_PUMP_BOILER": "heating", "ST_PUMP_RAD": "heating",
    "ST_PUMP_WALL": "heating", "ST_BOILER_STATE": "heating", "ST_AKUPACK_HEATER": "heating",
    "ST_RAD_ON": None, "ST_WALL_ON": None,
    "ST_EVSE_RELAY": "loads", "ST_WS_HEATING_RELAY": "loads", "ST_SEWAGE_PUMP": "loads",
    "EL_HEATER_STATUS": "loads", "ST_EL_HEATER_COILS": "loads",
    "ST_RECU_REMOTE_MODE": "ventilation", "ST_RECU_LIMIT": "ventilation",
}
ENUM_TITLES = {"InverterState": "Inverters", "BoilerStatus": "Boiler", "ElHeaterState": "Electric heater",
               "BlindCmd": "Blinds", "RecuRemoteMode": "Recuperation mode", "RecuLimit": "Recuperation limitation"}
# not in "Light on-time per day": exterior outputs only feed the photocell-switched lamps, no lamp on the stair steps
ON_TIME_EXCLUDE = {"ST_LIGHT_EXTERIOR_HOUSE", "ST_LIGHT_EXTERIOR_WS", "ST_LIGHT_STAIR_STEPS"}
# TECHM: setpoints next to the actual values (own panels, not in the generic setpoint panel)
TECHM_OWN_PANELS = {"ST_UP_REQ_C", "ST_DOWN_REQ_C", "ST_EXHAUST_SET_C"}


def techm_panels(panels, y):
    rooms = two_queries(step_panel("Room request in effect vs room temperature",
                                   events_sql(["ST_UP_REQ_C", "ST_DOWN_REQ_C"]), "celsius", 0, y, 12, 8,
                                   desc="Upstairs = kids room, radiators; downstairs = walls"),
                        avg_sql(["TEMP_KIDROOM_C", "TEMP_DOWNSTAIRS_C"]))
    exhaust = two_queries(step_panel("Exhaust setpoint vs exhaust", events_sql(["ST_EXHAUST_SET_C"]),
                                     "celsius", 12, y, 12, 8, desc="Boiler air control setpoint"),
                          avg_sql(["TEMP_BOILER_EXHAUST_C"]))
    y += 8
    valves = panel("Valves (commanded %)", avg_sql(["TECHM_VALVE_WALL_PCT", "TECHM_VALVE_RAD_PCT",
                                                    "TECHM_AIR_VALVE_SIGNAL_PCT"]), "percent", 0, y, 12, 8,
                   desc="Mixing valves wall / radiators as commanded; air valve = servo signal (20..100 % = 2..10 V)")
    water = panel("Water required vs actual", avg_sql(["TECHM_REQ_WATER_RAD_C", "TEMP_RAD_H_C",
                                                       "TECHM_REQ_WATER_WALL_C", "TEMP_WALL_IN_C"]),
                  "celsius", 12, y, 12, 8, desc="Required water temperatures and the circuit inlets")
    panels += [rooms, exhaust, valves, water]
    return y + 8


def state_category(d, cmd_category):
    if d.name in STATE_CATEGORY:
        return STATE_CATEGORY[d.name]
    if d.name in cmd_category:
        return cmd_category[d.name]
    if d.unit == "%" and d.name.startswith("ST_LIGHT_"):
        return "light"
    print("warning: no category for", d.name, "-> row Other")
    return "other"


def states_dashboard(defs):
    """One row per category: lights (unit %), on/off states (bool), one timeline per enum, numeric states."""
    cmd_category = {c.state: c.category for c in defs.commands.values() if c.state and c.category}
    events = sorted((d for d in defs.by_id.values() if d.agg == "event"), key=lambda d: d.id)
    groups = {}                                 # category -> {"lights": [], "bools": [], "enums": {enum: []}, "nums": []}
    for d in events:
        cat = state_category(d, cmd_category)
        if cat is None:
            continue
        g = groups.setdefault(cat, {"lights": [], "bools": [], "enums": {}, "nums": []})
        if d.unit == "%" and d.type != "float":
            g["lights"].append(d.name)
        elif d.type == "bool":
            g["bools"].append(d.name)
        elif d.type == "enum":
            g["enums"].setdefault(d.enum, []).append(d.name)
        else:
            g["nums"].append(d)
    light_map = [{"type": "value", "options": dict({"0": {"text": "off", "color": "#555555", "index": 0}},
                                                   **INVALID_MAP)}]
    light_steps = [{"color": "#555555", "value": None}, {"color": "#e0b400", "value": 1}]
    bool_map = [{"type": "value", "options": dict({"0": {"text": "off", "color": "#555555", "index": 0},
                                                   "1": {"text": "on", "color": "green", "index": 1}}, **INVALID_MAP)}]
    panels, y = [], 0
    all_lights = []
    for cat, title in CATEGORY_ROWS:
        g = groups.get(cat)
        if not g:
            continue
        panels.append(row(title, y))
        y += 1
        if g["lights"]:
            all_lights += g["lights"]
            h = 2 + len(g["lights"])
            panels.append(timeline("Lights", events_sql(g["lights"]), light_map, 0, y, h=h,
                                   unit="percent", thresholds=light_steps,
                                   desc="Output really set: PWM %, relay lights 0 / 100"))
            y += h
        if g["bools"]:
            h = 2 + len(g["bools"])
            panels.append(timeline("On / off", events_sql(g["bools"]), bool_map, 0, y, h=h,
                                   thresholds=[{"color": "#3a3a3a", "value": None}, {"color": "#555555", "value": 0},
                                               {"color": "green", "value": 1}],
                                   desc="On / off outputs as really set"))
            y += h
        for enum, names in g["enums"].items():
            items = sorted(defs.enums[enum].items())
            color = {k: ENUM_COLORS[i % len(ENUM_COLORS)] for i, (k, _) in enumerate(items)}
            options = {str(k): {"text": enum_text(enum, k, v), "color": color[k], "index": i}
                       for i, (k, v) in enumerate(items)}
            options.update(INVALID_MAP)
            # the timeline colours come from the thresholds, the legend from the mappings: same colour in both;
            # -1 (invalid) stays dark
            steps = [{"color": INVALID_MAP["-1"]["color"], "value": None}] + \
                    [{"color": color[k], "value": k} for k, _ in items]
            h = 4 + 2 * len(names)
            panels.append(timeline(ENUM_TITLES.get(enum, enum), events_sql(names),
                                   [{"type": "value", "options": options}], 0, y, h=h, thresholds=steps,
                                   legend=True, desc="Colours: see the legend below the chart"))
            y += h
        units = {}
        for d in g["nums"]:
            if d.name not in TECHM_OWN_PANELS:
                units.setdefault(d.unit, []).append(d.name)
        for unit, names in units.items():
            grafana_unit = {"°C": "celsius", "%": "percent", "ppm": "ppm"}.get(unit, "none")
            sub = (f"Setpoints ({unit})" if unit in ("°C", "%", "ppm") else
                   " / ".join(en(n) for n in names))
            panels.append(step_panel(sub, events_sql(names), grafana_unit, 0, y,
                                     desc="Numeric states, one point per change"))
            y += 7
        if cat == "heating":
            y = techm_panels(panels, y)
        if cat == "light":
            on_time = [n for n in all_lights if n not in ON_TIME_EXCLUDE]
            panels.append(panel("Light on-time per day (hours)", on_time_sql(on_time), "h", 0, y, 24, 9,
                                bars=True, stack=True, decimals=1, time_from="30d",
                                desc="Intervals with value > 0 between consecutive event rows, per local day. "
                                     "Without the exterior outputs and the stair steps."))
            y += 9
    return dashboard("uha-states", "UHA States", panels)


# ---- Statistics ----------------------------------------------------------------------------------------------
# Period panels follow the time picker (default this month); monthly / yearly panels have a fixed relative range.

def statistics_dashboard():
    day_loads, load_colors = with_other(CONSUMPTION_WH, 1)
    energy_items = [("Production", PRODUCTION_WH), ("Consumption", CONSUMPTION_WH)]
    energy_colors = {"Production": SOLAR, "Consumption": LOAD, "Balance": BATTERY}
    balance = ("Balance", f"({PRODUCTION_WH}) - ({CONSUMPTION_WH})")
    inverters = [("Inverter 300 W", "{CONS_AC300_WH}"), ("Inverter 3 kW", "{CONS_AC3KW_WH}"),
                 ("Inverter 5 kW", "{CONS_AC5KW_WH}"), ("Axpert 8 kW", "{CONS_AXPERT_WH}"),
                 ("Victron 2 kW", "{CONS_WS_HEATING_WH}")]
    m3 = [("Total m³", "{CONS_COLD_L}"), ("Hot m³", "{CONS_HOT_L}")]
    p = [row("Period totals (time picker)", 0),
         stat("Energy", total_sql([("PV house", "{LPV1_PROD_WH}"), ("PV workshop", "{LPV2_PROD_WH}"),
                                   ("PV total", PRODUCTION_WH), ("Consumption", CONSUMPTION_WH), balance]),
              0, 1, 12, 5, colors={"PV house": SOLAR, "PV workshop": SOLAR, "PV total": SOLAR,
                                   "Consumption": LOAD, "Balance": BATTERY},
              desc="PV = local PV house / workshop, consumption = load house + workshop (DC side), balance = PV - consumption"),
         stat("Water", total_sql(WATER + [(n, e, 1000.0) for n, e in m3], scale=1.0),
              12, 1, 6, 5, unit="litre", decimals=0, colors={"Total": WATER_COLORS["Total"], "Hot": LOAD,
                                                            "Total m³": WATER_COLORS["Total"], "Hot m³": LOAD},
              overrides=[by_name(n, {"id": "unit", "value": "m3"}, {"id": "decimals", "value": 2}) for n, _ in m3],
              desc="Total = all water, hot = part of it"),
         stat("Heat", total_sql([("Boiler", "{BOILER_HEAT}"), ("Electric heater", "{EL_HEATER_CONS_WH}")]),
              18, 1, 6, 5, colors={"Boiler": "#ff9830", "Electric heater": LOAD},
              desc="Boiler heat (counter) and the electric heater's consumption in the tank"),
         share_table("Consumption breakdown", total_sql(day_loads, share_of=CONSUMPTION_WH), 0, 6, 12, 11,
                     desc="Same categories as Loads per day (UHA Energy); Other = consumption - all categories. "
                          "Share of the consumption total."),
         share_table("Inverters - AC output (not part of the breakdown)",
                     total_sql(inverters, share_of=" + ".join(e for _, e in inverters), name_col="Inverter"),
                     12, 6, 12, 8, name_col="Inverter",
                     desc="AC energy per inverter meter, share of all inverters. Overload / lifetime view - never "
                          "add it to the consumption breakdown."),
         row("Daily (time picker)", 17),
         barchart("Energy per day", period_sql(energy_items + [balance], "day", False), 0, 18, 12, 9,
                  colors=energy_colors, hidden=["Balance"], time_from=None,
                  desc="Balance (click it in the legend) = production - consumption"),
         water_per_day(12, 18, 12, 9, rolling=False),
         row("Monthly (last 24 months)", 27),
         barchart("Energy per month", period_sql(energy_items + [balance], "month", False, xcol="month"), 0, 28, 12, 9,
                  colors=energy_colors, hidden=["Balance"], time_from="2y", decimals=0, xfield="month"),
         barchart("Water per month", period_sql(WATER, "month", False, scale=1000.0, xcol="month"), 12, 28, 12, 9,
                  colors=WATER_COLORS, time_from="2y", unit="m3", decimals=1, xfield="month",
                  desc="Total = all water, hot = part of it"),
         barchart("Loads per month", period_sql(day_loads, "month", False, xcol="month"), 0, 37, 24, 10, stack=True,
                  colors=load_colors, time_from="2y", decimals=0, xfield="month",
                  desc="Same categories as Loads per day; the stack = consumption of the month"),
         row("Yearly (last 10 years)", 47),
         barchart("Energy per year", period_sql(energy_items, "year", False, xcol="year"), 0, 48, 12, 9,
                  colors=energy_colors, time_from="10y", decimals=0, xfield="year"),
         barchart("Water per year", period_sql([WATER[0]], "year", False, scale=1000.0, xcol="year"), 12, 48, 12, 9,
                  colors=WATER_COLORS, time_from="10y", unit="m3", decimals=1, xfield="year")]
    return dashboard("uha-statistics", "UHA Statistics", p, time_from="now/M", time_to="now/M", refresh="5m")


energy = energy_dashboard()
statistics = statistics_dashboard()
states = states_dashboard(vars_def.load(YAML))

if __name__ == "__main__":
    for name, board in (("energy", energy), ("packs", packs), ("temperatures", temperatures), ("states", states),
                        ("statistics", statistics)):
        path = os.path.join(HERE, "dashboards", name + ".json")
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            json.dump(board, f, indent=2, ensure_ascii=False)
            f.write("\n")
        print("written", path)
