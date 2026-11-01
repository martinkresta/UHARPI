"""The JSON files written every second.

uha.json, bms.json   same keys, key order and values as UhaGate6 (the web and the FTP upload read them).
                     Ported from UHA/UHA6/src/outputs.cpp - quirks included, do not "fix" them here.
uha2.json            new: every VARS2 variable by YAML name in physical units.
"""
import json
import math
import os
import time
from typing import Dict

from .legacy_table import UHA_JSON_ITEMS
from .store import Store
from .vars_def import VarsFile


def _plain(node):
    """Whole-number floats become ints (cJSON prints 3.0 as 3), like UhaGate6."""
    if isinstance(node, dict):
        return {key: _plain(value) for key, value in node.items()}
    if isinstance(node, list):
        return [_plain(value) for value in node]
    if isinstance(node, float) and node.is_integer():
        return int(node)
    return node


def to_json(data: dict) -> str:
    """Tab indentation like cJSON; the key order of `data` is kept. For the small old-format files."""
    return json.dumps(_plain(data), indent="\t")


def to_json_compact(data: dict) -> str:
    """One line. Used for the big diagnostic files: with `indent` Python cannot use its fast C encoder
    and the Pi spent 7 % of a core on it. View them with a browser or `python3 -m json.tool`."""
    return json.dumps(data, separators=(",", ":"))


def write_atomic(path: str, text: str) -> None:
    """Write a temp file next to the target and rename it over the target.

    A reader (nginx, the FTP upload) sees either the old or the new file, never a half-written one.
    If `path` is a symlink (the tmpfs setup) the file it points to is replaced, not the link.
    """
    target = os.path.realpath(path)
    temp = target + ".tmp"
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.chmod(temp, 0o644)
        os.replace(temp, target)
    except BaseException:
        try:
            os.unlink(temp)
        except OSError:
            pass
        raise


def build_uha_json(raw: Dict[str, int], unix_time: int) -> str:
    """`raw` = old raw value by define name (Store.snapshot)."""
    data = {key: raw[name] * factor for key, name, factor in UHA_JSON_ITEMS}
    data["UnixTime"] = unix_time
    return to_json(data)


def _c_div(a: int, b: int) -> int:
    """Integer division like C (truncates towards zero)."""
    return int(a / b)


def build_bms_json(raw: Dict[str, int], unix_time: int) -> str:
    """Legacy battery format, BMS1 cells. Formulas copied from UhaGate6 / UHA5."""
    sun_power_w = raw["VAR_SOLAR_POWER_W"]
    sun_power_pct = _c_div(sun_power_w, 11200) * 100             # integer division: always 0 below 11.2 kW
    load_power_w = raw["VAR_LOAD_W"]
    load_power_pct = _c_div(load_power_w, 8000) * 100
    today_diff_wh = raw["VAR_SOLAR_ENERGY_TODAY_10WH"] * 10 - raw["VAR_CONS_TODAY_10WH"] * 10   # Wh, name says Kwh
    total_charging_a = raw["VAR_AXPERT_BAT_CHARGING_A"] + raw["VAR_MPPT_BAT_CURRENT_A10"] / 10.0

    # UhaGate5 also "added" TotalChargingKwh, TotalDischargingKwh and a 2nd DischargingA with an empty
    # item, which cJSON ignores - so these keys never appeared and must not appear now.
    live = {
        "SunPowerW": sun_power_w,
        "TotalVoltageV": raw["VAR_BAT_VOLTAGE_V10"] / 10.0,
        "ChargingA": total_charging_a,
        "DischargingA": raw["VAR_LOAD_A100"] / 100.0,
        "TodayChargingKwh": raw["VAR_SOLAR_ENERGY_TODAY_10WH"] / 100.0,
        "TodayDischargingKwh": raw["VAR_CONS_TODAY_10WH"] / 100.0,
        "AvailableEnergyKwh": raw["VAR_BAT_ENERGY_WH"] / 1000.0,
        "SocPct": raw["VAR_BAT_SOC"],
        "TemperatureC": raw["VAR_BMS2_CELL4_C"],
        "SunPowerPct": sun_power_pct,
        "BattCurrentA": raw["VAR_BAT_CURRENT_A10"] / 10.0,
        "LoadCurrentA": raw["VAR_LOAD_A100"] / 100.0,
        "LoadPowerW": load_power_w,
        "LoadPowerPct": load_power_pct,
        "TodayDiffKwh": today_diff_wh,
        "UnixTime": unix_time,
    }
    cells = [{"VoltageV": raw[f"VAR_BMS1_CELL{n}_MV"] / 1000.0, "TemperatureC": raw[f"VAR_BMS1_CELL{n}_C"]}
             for n in range(1, 17)]
    return to_json({
        "BatteryPackInfo": {"CapacityKwh": 16, "MinCellVoltageV": 3, "MaxCellVoltageV": 3.6,
                            "BalanceCellVoltageV": 3.5, "NumOfCells": 16},
        "LiveData": live,
        "Cells": cells,
    })


def build_uha2_json(store: Store, defs: VarsFile, mono: float, unix_time: int) -> str:
    """Every VARS2 variable by its YAML name: value in physical units and where it came from."""
    variables = {}
    for var_id in sorted(defs.by_id):
        d = defs.by_id[var_id]
        reading = store.reading(d, mono)
        entry = {"id": d.id, "value": reading.value, "unit": d.unit, "valid": reading.valid,
                 "age_s": None if reading.age_s is None else round(reading.age_s, 1),
                 "producer": defs.node_names.get(reading.producer, d.producer) if reading.producer is not None
                 else d.producer,
                 "source": reading.source}
        if d.type == "enum":
            entry["enum_name"] = defs.enums[d.enum].get(reading.value) if reading.value is not None else None
        variables[d.name] = entry
    return to_json_compact({"UnixTime": unix_time, "YamlVersion": defs.version, "Vars": variables})
