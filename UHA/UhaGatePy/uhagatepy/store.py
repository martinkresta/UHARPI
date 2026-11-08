"""Holds the last received values of both formats and decides which one to publish.

Old format (RPISERP 0x221):   int16 raw value + a valid flag, one id space.
VARS2 (tunnel 0x180..0x18F):  physical value (float/int) + valid flag + producer node.

Publishing rule (VARS2 spec section 7.5): use the VARS2 value while it is fresh, otherwise the old one.
  fresh = VALID flag set and age <= timeout_ms of the variable
The old-format outputs need the old raw int16 back:  raw = round(value * legacy_scale).
"""
import math
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from .legacy_table import NAME_TO_ID
from .tunnel import TunnelValue
from .vars_def import VarDef, VarsFile

INT16_MIN, INT16_MAX = -32768, 32767
TOLERANCE = 1            # old-vs-VARS2 comparison: allowed difference of the raw values

# Verdict thresholds (see CompareStats.verdict)
MIN_SAMPLES = 20         # fewer comparisons than this: no verdict yet
OK_MISMATCH_RATE = 0.05  # up to 5 % of the pairs beyond TOLERANCE is still "ok"
CLOSE_RELATIVE = 0.02    # mean difference below 2 % of the value: the sampling time explains it
OFFSET_BIAS = 0.8        # |mean difference| >= 80 % of the mean |difference|: nearly always the same sign


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
class OldValue:
    raw: int
    valid: bool
    mono: float      # monotonic receive time [s]
    unix: int
    count: int


@dataclass
class V2Value:
    value: float
    valid: bool
    producer: int
    mono: float
    unix: int
    count: int


@dataclass
class CompareStats:
    """Old-vs-VARS2 comparison of one variable, in old raw units (VARS2 value converted back minus old value).

    Counting only "beyond +-1" is too crude for values that change quickly: the two formats are sampled at
    different moments, so a noisy signal differs by more than 1 almost every time. These sums tell noise from
    a real error: noise has a mean difference near zero and small compared to the value, a wrong scale, unit
    or id gives a large difference that nearly always has the same sign.
    """
    compared: int = 0
    mismatched: int = 0        # pairs with |difference| > TOLERANCE
    sum_diff: int = 0          # sum of (VARS2 - old): the bias
    sum_abs_diff: int = 0
    max_abs_diff: int = 0
    sum_abs_old: int = 0       # to put the difference into proportion to the value
    sum_gap_s: float = 0.0     # time between the two samples [s]
    last_v2: int = 0
    last_old: int = 0

    def add(self, v2_raw: int, old_raw: int, gap_s: float) -> None:
        diff = v2_raw - old_raw
        self.compared += 1
        if abs(diff) > TOLERANCE:
            self.mismatched += 1
        self.sum_diff += diff
        self.sum_abs_diff += abs(diff)
        self.max_abs_diff = max(self.max_abs_diff, abs(diff))
        self.sum_abs_old += abs(old_raw)
        self.sum_gap_s += gap_s
        self.last_v2, self.last_old = v2_raw, old_raw

    @property
    def mean_diff(self) -> float:
        return self.sum_diff / self.compared if self.compared else 0.0

    @property
    def mean_abs_diff(self) -> float:
        return self.sum_abs_diff / self.compared if self.compared else 0.0

    @property
    def relative(self) -> float:
        """Mean |difference| as a fraction of the mean |old value| (at least 1 raw unit)."""
        return self.mean_abs_diff / max(self.sum_abs_old / self.compared, 1.0) if self.compared else 0.0

    @property
    def mean_gap_s(self) -> float:
        return self.sum_gap_s / self.compared if self.compared else 0.0

    def verdict(self) -> str:
        """few | ok | close | offset | noisy"""
        if self.compared < MIN_SAMPLES:
            return "few"
        if self.mismatched <= OK_MISMATCH_RATE * self.compared:
            return "ok"
        if self.relative <= CLOSE_RELATIVE:
            return "close"        # differs by some raw units but only a tiny part of the value
        if abs(self.mean_diff) >= OFFSET_BIAS * self.mean_abs_diff:
            return "offset"       # always the same direction: look for a scale / unit / id problem
        return "noisy"            # large but random: a fast signal sampled at different times


@dataclass
class Reading:
    """What is published for one variable (used by uha2.json)."""
    value: object                # physical value (float / int / bool) or None
    source: str                  # "vars2" fresh, "old", "stale" (last VARS2 value, no old one), "none"
    valid: bool
    age_s: Optional[float]
    producer: Optional[int]      # node id from the VARS2 packet, None for old values


class Store:
    def __init__(self, defs: VarsFile, compare_window_s: float) -> None:
        self.defs = defs
        self.compare_window_s = compare_window_s
        self.old: Dict[int, OldValue] = {}
        self.v2: Dict[int, V2Value] = {}
        self.compared: Dict[int, CompareStats] = {}   # since start, for the status file
        self.window: Dict[int, CompareStats] = {}     # since the last summary, for the journal
        self.clamped = 0                              # values that did not fit into int16

    # ---- receiving -------------------------------------------------------------------------

    def set_old(self, var_id: int, raw: int, valid: bool, mono: float, unix: int) -> None:
        previous = self.old.get(var_id)
        self.old[var_id] = OldValue(raw, valid, mono, unix, previous.count + 1 if previous else 1)

    def set_v2(self, tv: TunnelValue, mono: float, unix: int) -> Optional[Tuple[int, int]]:
        """Store a VARS2 value. Returns (expected_raw, old_raw) if it disagrees with the old value."""
        definition = self.defs.by_id[tv.var_id]
        previous = self.v2.get(tv.var_id)
        self.v2[tv.var_id] = V2Value(tv.value, tv.valid, tv.producer, mono, unix,
                                     previous.count + 1 if previous else 1)
        raw, clamped = to_legacy_raw(tv.value, definition.legacy_scale)
        if clamped:
            self.clamped += 1                     # counted once per received value, not per output
        return self._compare(definition, tv, raw, mono)

    def _compare(self, definition: VarDef, tv: TunnelValue, expected: int, mono: float) -> Optional[Tuple[int, int]]:
        """Old and VARS2 are both sent by the nodes, so they must agree (this checks the migration).

        The old value may be at most one publish period old: slow variables (3 s, 5 s) would never be
        compared within the short default window, and they change slowly anyway.
        """
        old = self.old.get(tv.var_id)
        window = max(self.compare_window_s, definition.period_ms / 1000)
        if old is None or not (tv.valid and old.valid) or mono - old.mono > window:
            return None
        gap = mono - old.mono
        self.compared.setdefault(tv.var_id, CompareStats()).add(expected, old.raw, gap)
        self.window.setdefault(tv.var_id, CompareStats()).add(expected, old.raw, gap)
        return (expected, old.raw) if abs(expected - old.raw) > TOLERANCE else None

    def take_window(self) -> Dict[int, CompareStats]:
        """The comparison statistics since the previous call (they start again from zero)."""
        window, self.window = self.window, {}
        return window

    # ---- health of the VARS2 stream --------------------------------------------------------

    def vars2_health(self, mono: float) -> Dict[str, List[str]]:
        """YAML variables by state: fresh | invalid (producer says so) | stale (too old) | never received."""
        health: Dict[str, List[str]] = {"fresh": [], "invalid": [], "stale": [], "never": []}
        for var_id, definition in self.defs.by_id.items():
            v2 = self.v2.get(var_id)
            if v2 is None:
                state = "never"
            elif not v2.valid:
                state = "invalid"
            elif (mono - v2.mono) * 1000 > definition.timeout_ms:
                state = "stale"
            else:
                state = "fresh"
            health[state].append(definition.name)
        return health

    # ---- publishing ------------------------------------------------------------------------

    def _fresh(self, v2: V2Value, definition: VarDef, mono: float) -> bool:
        return v2.valid and (mono - v2.mono) * 1000 <= definition.timeout_ms

    def legacy_raw(self, var_id: int, mono: float) -> int:
        """Old-format raw value to publish in uha.json / bms.json (0 if nothing was ever received)."""
        old = self.old.get(var_id)
        definition = self.defs.by_id.get(var_id)
        v2 = self.v2.get(var_id)
        if definition is not None and v2 is not None and self._fresh(v2, definition, mono):
            return to_legacy_raw(v2.value, definition.legacy_scale)[0]
        if old is not None:
            return old.raw
        if definition is not None and v2 is not None:
            return to_legacy_raw(v2.value, definition.legacy_scale)[0]       # stale, but better than 0
        return 0

    def snapshot(self, mono: float) -> Dict[str, int]:
        """All old variables by define name, for the old-format outputs."""
        return {name: self.legacy_raw(var_id, mono) for name, var_id in NAME_TO_ID.items()}

    def reading(self, definition: VarDef, mono: float) -> Reading:
        """Physical value + where it comes from, for uha2.json."""
        v2 = self.v2.get(definition.id)
        old = self.old.get(definition.id)
        if v2 is not None and self._fresh(v2, definition, mono):
            return Reading(self._physical(v2.value, definition), "vars2", True, mono - v2.mono, v2.producer)
        if old is not None:
            age = mono - old.mono
            valid = old.valid and age * 1000 <= definition.timeout_ms
            return Reading(self._physical(old.raw / definition.legacy_scale, definition), "old", valid, age, None)
        if v2 is not None:
            return Reading(self._physical(v2.value, definition), "stale", False, mono - v2.mono, v2.producer)
        return Reading(None, "none", False, None, None)

    @staticmethod
    def _physical(value: float, definition: VarDef) -> object:
        if definition.type == "bool":
            return bool(round_half_away(value))
        if definition.type in ("int32", "uint32", "enum"):
            return round_half_away(value)
        return float(f"{value:.7g}")        # float32 has ~7 digits; hides 3.3050000667572021
