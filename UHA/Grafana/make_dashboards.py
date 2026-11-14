#!/usr/bin/env python3
"""Writes the Grafana dashboards (dashboards/*.json) from the panel lists below.

Edit this file, run `python make_dashboards.py`, commit both, deploy with deploy_grafana.sh.
(Dashboards edited in the Grafana UI cannot be saved over the provisioned files.)

The database (UhaGatePy db_log.py): vars(id, name, unit, log_s, agg), raw(var_id, ts, value) every 10 / 60 s,
kept 30 days, agg_15min(var_id, ts, value) kept forever; ts = UTC unix seconds, start of the interval.

Which table a panel reads depends on the shown time range (one SQL per panel, see avg_sql):
  range <= 2 days   raw,       buckets of Grafana's $__interval (at least the variable's log_s)
  range <= 60 days  agg_15min, buckets of $__interval (at least 15 min)
  range > 60 days   agg_15min, one value per day; the day is the CET day (UTC+1, winter time) all year, because
                    converting every row to local time costs ~3x more on the Pi 3 (1 year of 16 cells: 8 s instead
                    of 2.4 s for the bare query); in summer the day starts at 01:00 local time - irrelevant for averages
Measured on the Pi 3 with a full-size database, one panel of 16 cells: 1 day ~1.3 s, 3 days ~0.4 s, 30 days
~0.6 s, 1 year ~4 s.
Energy bars (counters, agg: delta) always read agg_15min: SUM per local hour / exact local day. The last, unfinished 15 min
are therefore missing from the bars (up to ~16 min behind).
Local time: SQLite 'localtime' = time zone of the Pi (Europe/Prague), also for summer time.
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
DS = {"type": "frser-sqlite-datasource", "uid": "uhalog"}
RAW_MAX_S = 2 * 86400        # up to this range read raw (more rows would be slow on the Pi 3)
DAILY_MIN_S = 60 * 86400     # above this range one value per local day

# Start of the local day of a unix time t (SQL expression), e.g. 2026-11-14 00:00 Prague as UTC seconds.
# Exact (summer time too) but slow per row: only for the energy bars (few rows).
LOCAL_DAY = "CAST(strftime('%s', date({t}, 'unixepoch', 'localtime'), 'utc') AS INTEGER)"

RANGE_CTE = "WITH q AS (SELECT $__from / 1000 AS f, $__to / 1000 AS t, $__interval_ms / 1000 AS i)"


def names_sql(names):
    return ", ".join(f"'{n}'" for n in names)


def avg_sql(names, scale=1.0):
    """Mean of avg variables, one series per variable (column `name`)."""
    n = names_sql(names)
    factor = "" if scale == 1.0 else f" * {scale}"
    return f"""-- raw up to {RAW_MAX_S // 86400} days, agg_15min beyond, one value per (CET) day beyond {DAILY_MIN_S // 86400} days
{RANGE_CTE},
src AS (
  SELECT v.name, x.ts, x.value, max(q.i, v.log_s) AS b
  FROM q, vars v CROSS JOIN raw x ON x.var_id = v.id AND x.ts >= q.f AND x.ts < q.t
  WHERE v.name IN ({n}) AND q.t - q.f <= {RAW_MAX_S}
  UNION ALL
  SELECT v.name, x.ts, x.value, CASE WHEN q.t - q.f > {DAILY_MIN_S} THEN 86400 ELSE max(q.i, 900) END
  FROM q, vars v CROSS JOIN agg_15min x ON x.var_id = v.id AND x.ts >= q.f AND x.ts < q.t
  WHERE v.name IN ({n}) AND q.t - q.f > {RAW_MAX_S}
)
SELECT CASE WHEN b >= 86400 THEN ts - (ts + 3600) % 86400 ELSE ts - ts % b END AS time,
       name, AVG(value){factor} AS value
FROM src
GROUP BY 1, 2
ORDER BY 1"""


def energy_sql(series, bucket):
    """kWh per local hour or day from counters (agg: delta). series = [(label, [names]), ...]: the label's bar is
    the sum of its counters. Daily bars start at the first full local day of the range."""
    if bucket == "day":
        time_expr = LOCAL_DAY.format(t="x.ts")
        # the next local midnight after the range start, so the first bar is a full day
        start = "CAST(strftime('%s', date(q.f, 'unixepoch', 'localtime', '+1 day'), 'utc') AS INTEGER)"
    else:
        time_expr = "x.ts - x.ts % 3600"
        start = "q.f - q.f % 3600 + 3600"
    parts = []
    for label, names in series:
        parts.append(f"""  SELECT {time_expr} AS time, '{label}' AS name, SUM(x.value) / 1000.0 AS value
  FROM q, vars v CROSS JOIN agg_15min x ON x.var_id = v.id AND x.ts >= {start} AND x.ts < q.t
  WHERE v.name IN ({names_sql(names)})
  GROUP BY 1""")
    return (f"-- kWh per local {bucket}: SUM of the 15 min increments of the counters\n{RANGE_CTE}\n"
            + "SELECT * FROM (\n" + "\n  UNION ALL\n".join(parts) + "\n) ORDER BY 1")


# ---- panels --------------------------------------------------------------------------------------------------

def panel(title, sql, unit, x, y, w=12, h=8, bars=False, stack=False, decimals=None, time_from=None, desc=""):
    custom = {"drawStyle": "line", "lineWidth": 1, "fillOpacity": 0, "showPoints": "never", "spanNulls": False,
              "axisSoftMin": None}
    if bars:
        custom.update({"drawStyle": "bars", "fillOpacity": 80, "barAlignment": 1, "lineWidth": 1})
    if stack:
        custom["stacking"] = {"mode": "normal", "group": "A"}
    defaults = {"unit": unit, "custom": custom, "displayName": "${__field.labels.name}"}
    if decimals is not None:
        defaults["decimals"] = decimals
    p = {
        "type": "timeseries", "title": title, "description": desc, "datasource": DS,
        "gridPos": {"x": x, "y": y, "w": w, "h": h},
        "fieldConfig": {"defaults": defaults, "overrides": []},
        "options": {"legend": {"displayMode": "list", "placement": "bottom", "showLegend": True},
                    "tooltip": {"mode": "multi", "sort": "none"}},
        "targets": [{"refId": "A", "datasource": DS, "queryType": "time series", "rawQueryText": sql,
                     "queryText": sql, "timeColumns": ["time"]}],
    }
    if time_from:
        p["timeFrom"] = time_from
    return p


def dashboard(uid, title, panels, time_from="now-24h"):
    for number, p in enumerate(panels, 1):
        p["id"] = number
    return {
        "uid": uid, "title": title, "tags": ["uha"], "timezone": "Europe/Prague", "editable": True,
        "schemaVersion": 39, "version": 1, "refresh": "1m", "graphTooltip": 1,
        "time": {"from": time_from, "to": "now"},
        "timepicker": {"refresh_intervals": ["1m", "5m", "15m", "1h"]},
        "panels": panels, "templating": {"list": []}, "annotations": {"list": []},
        "links": [{"title": "UHA dashboards", "type": "dashboards", "tags": ["uha"], "asDropdown": False}],
    }


def cells(pack):
    return [f"BMS{pack}_CELL_V_{i}" for i in range(1, 17)]


METERS = ["CONS_AC300_WH", "CONS_AC3KW_WH", "CONS_AC5KW_WH", "CONS_FRIDGE_WH", "CONS_KITCHEN_WH",
          "CONS_WASCHMACHINE_WH", "CONS_OTHER_WH", "CONS_TECHM_WH", "CONS_AXPERT_WH", "CONS_EVSE_WH",
          "CONS_WS_HEATING_WH", "EL_HEATER_CONS_WH"]
TOTALS = [("Consumption (LLOAD1+2)", ["LLOAD1_CONS_WH", "LLOAD2_CONS_WH"]),
          ("PV production (LPV1+2)", ["LPV1_PROD_WH", "LPV2_PROD_WH"])]

energy = dashboard("uha-energy", "UHA Energy", [
    panel("Power", avg_sql(["BAT_POWER_W", "SOLAR_POWER_W", "LOAD_W"]), "watt", 0, 0, 24, 9,
          desc="BAT_POWER_W (+ charging), SOLAR_POWER_W, LOAD_W - mean per bucket"),
    panel("State of charge", avg_sql(["BAT_SOC", "BMS1_SOC", "BMS2_SOC", "BMS3_SOC"]), "percent", 0, 9, 12, 8),
    panel("Storages power", avg_sql(["STRG1_POWER_W", "STRG2_POWER_W", "LPV1_POWER_W", "LPV2_POWER_W",
                                     "LLOAD1_POWER_W", "LLOAD2_POWER_W"]), "watt", 12, 9, 12, 8,
          desc="1 = house (ELECON), 2 = workshop (ELECON_D)"),
    panel("Energy per hour", energy_sql(TOTALS, "hour"), "kwatth", 0, 17, 24, 8, bars=True, decimals=2,
          desc="From agg_15min (the current 15 min are not in yet)"),
    panel("Energy per day (last 30 days)", energy_sql(TOTALS, "day"), "kwatth", 0, 25, 12, 9, bars=True,
          decimals=1, time_from="30d"),
    panel("Meters per day (last 30 days)", energy_sql([(m.replace("CONS_", "").replace("_WH", ""), [m])
                                                       for m in METERS], "day"),
          "kwatth", 12, 25, 12, 9, bars=True, stack=True, decimals=1, time_from="30d"),
    panel("Meters power", avg_sql(["POW_AC300_W", "POW_AC3KW_W", "POW_AC5KW_W", "POW_FRIDGE_W", "POW_KITCHEN_W",
                                   "POW_WASCHMACHINE_W", "POW_OTHER_W", "POW_TECHM_W", "POW_AXPERT_W", "POW_EVSE_W",
                                   "POW_WS_HEATING_W"]), "watt", 0, 34, 24, 9),
])

packs = dashboard("uha-packs", "UHA Packs", [
    panel("BMS1 Workshop 251 Ah - cells", avg_sql(cells(1)), "volt", 0, 0, 24, 8, decimals=3),
    panel("BMS2 House 220 Ah - cells", avg_sql(cells(2)), "volt", 0, 8, 24, 8, decimals=3),
    panel("BMS3 House 80 Ah - cells", avg_sql(cells(3)), "volt", 0, 16, 24, 8, decimals=3),
    panel("Pack voltage", avg_sql(["BMS1_VOLTAGE_V", "BMS2_VOLTAGE_V", "BMS3_VOLTAGE_V", "BAT_VOLTAGE_V"]),
          "volt", 0, 24, 8, 8, decimals=2),
    panel("Pack current", avg_sql(["BMS1_CURRENT_A", "BMS2_CURRENT_A", "BMS3_CURRENT_A", "BAT_CURRENT_A"]),
          "amp", 8, 24, 8, 8, decimals=1),
    panel("Pack SOC", avg_sql(["BMS1_SOC", "BMS2_SOC", "BMS3_SOC", "BAT_SOC"]), "percent", 16, 24, 8, 8),
])

temperatures = dashboard("uha-temperatures", "UHA Temperatures", [
    panel("House", avg_sql(["TEMP_OFFICE_C", "TEMP_KIDROOM_C", "TEMP_DOWNSTAIRS_C"]), "celsius", 0, 0, 12, 8),
    panel("Outside", avg_sql(["TEMP_OUTSIDE_C"]), "celsius", 12, 0, 12, 8),
    panel("Tank", avg_sql(["TEMP_TANK_1_C", "TEMP_TANK_2_C", "TEMP_TANK_3_C", "TEMP_TANK_4_C", "TEMP_TANK_5_C",
                           "TEMP_TANK_6_C", "TEMP_TANK_IN_H_C", "TEMP_TANK_OUT_H_C", "TEMP_TANK_IN_C_C",
                           "TEMP_TANK_OUT_C_C"]), "celsius", 0, 8, 12, 9, desc="TANK_1..6 = tank layers"),
    panel("Boiler and heating circuits", avg_sql(["TEMP_BOILER_C", "TEMP_BOILER_IN_C", "TEMP_BOILER_OUT_C",
                                                  "TEMP_BOILER_EXHAUST_C", "TEMP_RAD_H_C", "TEMP_RAD_C_C",
                                                  "TEMP_WALL_IN_C", "TEMP_WALL_OUT_C"]), "celsius", 12, 8, 12, 9),
    panel("Workshop", avg_sql(["TEMP_DILNA_C", "TEMP_AKUPACK1_C", "TEMP_KOLARNA_C"]), "celsius", 0, 17, 12, 8),
    panel("Recuperation", avg_sql(["TEMP_RECU_FC_C", "TEMP_RECU_FH_C", "TEMP_RECU_WH_C", "TEMP_RECU_WC_C"]),
          "celsius", 12, 17, 12, 8, desc="FC fresh cold, FH fresh hot, WH waste hot, WC waste cold"),
    panel("Boards and converters", avg_sql(["TEMP_TECHM_BOARD_C", "TEMP_IOBOARD_D_C", "TEMP_IOBOARD_U_C",
                                            "TEMP_ELECON_BOARD_C", "TEMP_BOARD_ELECON_D_C", "AXPERT_TEMP_C",
                                            "MPPT_TEMP_C"]), "celsius", 0, 25, 12, 8),
    panel("Wind (mean)", avg_sql(["METEO_WIND_AVG"]), "velocityms", 12, 25, 12, 8),
])

if __name__ == "__main__":
    for name, board in (("energy", energy), ("packs", packs), ("temperatures", temperatures)):
        path = os.path.join(HERE, "dashboards", name + ".json")
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            json.dump(board, f, indent=2)
            f.write("\n")
        print("written", path)
