"""Holds the last received VARS2 value of every variable (tunnel packets 0x180..0x18F).

The YAML (uha_vars.yaml) is the only definition of the variables. The old 0x221 format is not used any more.

  fresh = VALID flag set and age <= timeout_ms of the variable (only shown in uha2.json / uha_status.json)
The old-format outputs (uha.json, bms.json) get the last received value, converted back to the old raw int16:
  raw = round(value * legacy_scale); 0 for ids that are not in the YAML or were never received.
"""
import math
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from .legacy_table import NAME_TO_ID
from .tunnel import TunnelValue
from .vars_def import VarDef, VarsFile

INT16_MIN, INT16_MAX = -32768, 32767


def round_half_away(x: float) -> int:
    """Like C round(): 2.5 -> 3, -2.5 -> -3 (Python's round() would give 2 and -2)."""
    return int(math.floor(abs(x) + 0.5)) * (1 if x >= 0 else -1)


def to_legacy_raw(value: float, scale: float) -> Tuple[int, bool]:
    """Physical value -> old int16 raw value. Second result: True if it had to be clamped to int16."""
    raw = round_half_away(value * scale)
    if raw > INT16_MAX:
        return INT16_MAX, True
    if raw < INT16_MIN:
        return INT16_MIN, True
    return raw, False


@dataclass
class V2Value:
    value: float
    valid: bool
    producer: int
    mono: float
    unix: int
    count: int


@dataclass
class Reading:
    """What is published for one variable (used by uha2.json)."""
    value: object                # physical value (float / int / bool), None if never received
    valid: bool                  # fresh: VALID flag and not older than timeout_ms
    age_s: Optional[float]
    producer: Optional[int]      # node id from the VARS2 packet


class Store:
    def __init__(self, defs: VarsFile) -> None:
        self.defs = defs
        self.v2: Dict[int, V2Value] = {}
        self.clamped = 0                              # values that did not fit into int16

    def set_v2(self, tv: TunnelValue, mono: float, unix: int) -> bool:
        """Store a VARS2 value. Returns True if the value differs from the previous one (for the frozen watch)."""
        definition = self.defs.by_id[tv.var_id]
        previous = self.v2.get(tv.var_id)
        self.v2[tv.var_id] = V2Value(tv.value, tv.valid, tv.producer, mono, unix,
                                     previous.count + 1 if previous else 1)
        if to_legacy_raw(tv.value, definition.legacy_scale)[1]:
            self.clamped += 1                     # counted once per received value, not per output
        return previous is not None and previous.value != tv.value

    def fresh(self, v2: V2Value, definition: VarDef, mono: float) -> bool:
        return v2.valid and (mono - v2.mono) * 1000 <= definition.timeout_ms

    def vars2_health(self, mono: float) -> Dict[str, List[str]]:
        """YAML variables by state: fresh | invalid (producer says so) | stale (too old) | never received."""
        health: Dict[str, List[str]] = {"fresh": [], "invalid": [], "stale": [], "never": []}
        for var_id, definition in self.defs.by_id.items():
            v2 = self.v2.get(var_id)
            if v2 is None:
                state = "never"
            elif not v2.valid:
                state = "invalid"
            elif not self.fresh(v2, definition, mono):
                state = "stale"
            else:
                state = "fresh"
            health[state].append(definition.name)
        return health

    # ---- publishing ------------------------------------------------------------------------

    def legacy_raw(self, var_id: int) -> int:
        """Old-format raw value for uha.json / bms.json: the last VARS2 value of any age, 0 if none."""
        definition = self.defs.by_id.get(var_id)
        v2 = self.v2.get(var_id)
        if definition is None or v2 is None:
            return 0
        return to_legacy_raw(v2.value, definition.legacy_scale)[0]

    def snapshot(self) -> Dict[str, int]:
        """All old variables by define name, for the old-format outputs."""
        return {name: self.legacy_raw(var_id) for name, var_id in NAME_TO_ID.items()}

    def reading(self, definition: VarDef, mono: float) -> Reading:
        """Physical value + validity, for uha2.json."""
        v2 = self.v2.get(definition.id)
        if v2 is None:
            return Reading(None, False, None, None)
        return Reading(self._physical(v2.value, definition), self.fresh(v2, definition, mono), mono - v2.mono,
                       v2.producer)

    @staticmethod
    def _physical(value: float, definition: VarDef) -> object:
        if definition.type == "bool":
            return bool(round_half_away(value))
        if definition.type in ("int32", "uint32", "enum"):
            return round_half_away(value)
        return float(f"{value:.7g}")        # float32 has ~7 digits; hides 3.3050000667572021
