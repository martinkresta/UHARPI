"""Loads the variable definitions from uha_vars.yaml (single source of truth, lives in UHA_FW).

Only what the gateway needs is read: ids, names, types, scales, timeouts and producers.
Rules (see VARS2_spec.md section 3):
  - a variable inherits `producer` from its group and the other missing keys from `defaults:`
  - `timeout_ms: auto` means 3 x period_ms
  - `count: n` makes an array: ids id .. id+n-1, names NAME_1 .. NAME_n and the legacy
    name 'VAR_BMS1_CELL{1..16}_MV' becomes VAR_BMS1_CELL1_MV .. VAR_BMS1_CELL16_MV
A broken file raises VarsDefError with the reason - the gateway then refuses to start.
"""
import hashlib
import re
from dataclasses import dataclass, field
from typing import Dict, List

import yaml

from .legacy_table import NAME_TO_ID

_ID_TO_NAME = {var_id: name for name, var_id in NAME_TO_ID.items()}

TYPES = ("float", "int32", "uint32", "bool", "enum")
_RANGE = re.compile(r"\{(\d+)\.\.(\d+)\}")


class VarsDefError(Exception):
    pass


@dataclass(frozen=True)
class VarDef:
    id: int
    name: str            # YAML name, e.g. BAT_SOC or BMS1_CELL_V_3
    legacy: str          # old define, e.g. VAR_BAT_SOC
    type: str            # float | int32 | uint32 | bool | enum
    enum: str            # enum name when type is enum, else ""
    unit: str
    legacy_scale: float  # old raw int16 = physical value * legacy_scale
    producer: str        # node name
    period_ms: int
    timeout_ms: int
    on_can: bool         # False: only forwarded over the serial link


@dataclass
class VarsFile:
    version: int
    sha: str                          # first 8 hex digits of the file hash, to see which file runs
    nodes: Dict[str, int]             # name -> node id
    node_names: Dict[int, str]        # node id -> name
    enums: Dict[str, Dict[int, str]]  # enum name -> {number: name}
    by_id: Dict[int, VarDef]          # VARS2 id == old variable id
    warnings: List[str] = field(default_factory=list)   # harmless differences to the old table, to be logged


def _fail(message: str) -> None:
    raise VarsDefError(message)


def load(path: str) -> VarsFile:
    try:
        with open(path, "rb") as f:
            raw = f.read()
        data = yaml.safe_load(raw)
    except (OSError, yaml.YAMLError) as e:
        raise VarsDefError(f"{path}: {e}")
    if not isinstance(data, dict):
        _fail(f"{path}: top level must be a mapping")
    try:
        return _build(data, hashlib.sha256(raw).hexdigest()[:8])
    except (KeyError, TypeError, ValueError, AttributeError) as e:
        raise VarsDefError(f"{path}: malformed definition ({type(e).__name__}: {e})")


def _build(data: dict, sha: str) -> VarsFile:
    nodes = {str(name): int(number) for name, number in data["nodes"].items()}
    enums = {name: {int(k): str(v) for k, v in entries.items()} for name, entries in (data.get("enums") or {}).items()}
    defaults = data.get("defaults") or {}
    by_id: Dict[int, VarDef] = {}
    names = set()
    warnings: List[str] = []

    for group_name, group in data["groups"].items():
        for entry in group["vars"]:
            item = dict(defaults)
            item.update(entry)
            producer = entry.get("producer", group.get("producer"))
            if producer not in nodes:
                _fail(f"variable {entry.get('name')}: producer '{producer}' is not in nodes")
            vtype = item.get("type", "float")
            if vtype not in TYPES:
                _fail(f"variable {entry['name']}: unknown type '{vtype}'")
            if vtype == "enum" and item.get("enum") not in enums:
                _fail(f"variable {entry['name']}: unknown enum '{item.get('enum')}'")
            scale = item.get("legacy_scale", 1)
            if not isinstance(scale, (int, float)) or isinstance(scale, bool) or scale <= 0:
                _fail(f"variable {entry['name']}: legacy_scale must be a positive number")
            period = int(item["period_ms"])
            timeout = 3 * period if item.get("timeout_ms", "auto") == "auto" else int(item["timeout_ms"])
            count = int(item.get("count") or 1)
            is_array = "count" in entry

            for index in range(count):
                name = f"{entry['name']}_{index + 1}" if is_array else entry["name"]
                legacy = _expand_legacy(item["legacy"], index)
                var_id = int(entry["id"]) + index
                if var_id in by_id:
                    _fail(f"duplicate id {var_id} ({name})")
                if name in names:
                    _fail(f"duplicate name {name}")
                known_id = NAME_TO_ID.get(legacy)
                if known_id is not None and known_id != var_id:
                    _fail(f"{name}: id {var_id} does not match the old variable {legacy} "
                          f"(id {known_id}) - VARS2 and old ids must be equal")
                if known_id is None:
                    # The id is what counts. Only the label differs, e.g. the gateway's old table calls
                    # id 49 VAR_MPPT_ENERGY_TODAY_WH but the firmware VAR_MPPT_TEMP_C.
                    warnings.append(f"{name} (id {var_id}): old name {legacy} is not in the gateway's table"
                                    + (f", it calls this id {_ID_TO_NAME[var_id]}" if var_id in _ID_TO_NAME else ""))
                names.add(name)
                by_id[var_id] = VarDef(
                    id=var_id, name=name, legacy=legacy, type=vtype, enum=item.get("enum") or "",
                    unit=str(item.get("unit", "")), legacy_scale=float(scale), producer=producer,
                    period_ms=period, timeout_ms=timeout, on_can=bool(item.get("on_can", True)))

    return VarsFile(version=int(data.get("version", 0)), sha=sha, nodes=nodes,
                    node_names={number: name for name, number in nodes.items()}, enums=enums, by_id=by_id,
                    warnings=warnings)


def _expand_legacy(legacy: str, index: int) -> str:
    """'VAR_BMS1_CELL{1..16}_MV', 2 -> 'VAR_BMS1_CELL3_MV'."""
    match = _RANGE.search(legacy)
    if not match:
        return legacy
    return legacy[:match.start()] + str(int(match.group(1)) + index) + legacy[match.end():]
