"""Detects a node whose data is frozen.

Why: on 2026-11-12 ELECON_D stopped sending on CAN. ELECON kept repeating its last stored values over the serial
link, marked valid and "fresh", so the web showed 6.5 hours old BMS data as current. The age of a value cannot show
that, but a value that never changes can: a live node always has some variable that moves.

Rule: a node is "frozen" when none of its variables has changed its value for a while. "A while" starts at
`frozen_after_s` and grows by itself for nodes that are legitimately quiet for longer (a node with few, slow
variables): three times the longest quiet gap seen so far, at most MAX_THRESHOLD_S. A frozen gap that ended
with the node waking up again is not learned, otherwise one outage would switch the detection off.
"""
from dataclasses import dataclass
from typing import Dict, List, Tuple

LEARN_FACTOR = 3          # threshold = 3 x the longest normal quiet gap seen
MAX_THRESHOLD_S = 1800    # never wait longer than 30 min
REMINDER_S = 1800         # repeat the warning every 30 min while the node stays frozen


@dataclass
class NodeActivity:
    last_change_mono: float          # last time a variable of this node changed (or first value seen)
    longest_gap_s: float = 0.0       # longest quiet time that ended with a change, without alerts
    alerted: bool = False
    next_report_mono: float = 0.0


class NodeWatch:
    def __init__(self, frozen_after_s: float) -> None:
        self.frozen_after_s = frozen_after_s
        self.nodes: Dict[str, NodeActivity] = {}

    def seen(self, node: str, mono: float) -> None:
        """A value of this node arrived (changed or not). The first one starts the clock."""
        if node not in self.nodes:
            self.nodes[node] = NodeActivity(last_change_mono=mono)

    def changed(self, node: str, mono: float) -> float:
        """A variable of this node changed its value. Returns the quiet time if the node had been reported
        frozen (so the caller can log that it is back), otherwise 0."""
        activity = self.nodes.setdefault(node, NodeActivity(last_change_mono=mono))
        gap = mono - activity.last_change_mono
        activity.last_change_mono = mono
        if activity.alerted:
            activity.alerted = False
            return gap
        activity.longest_gap_s = max(activity.longest_gap_s, gap)
        return 0.0

    def threshold_s(self, node: str) -> float:
        activity = self.nodes.get(node)
        learned = LEARN_FACTOR * activity.longest_gap_s if activity else 0.0
        return min(max(self.frozen_after_s, learned), MAX_THRESHOLD_S)

    def quiet_s(self, node: str, mono: float) -> float:
        activity = self.nodes.get(node)
        return mono - activity.last_change_mono if activity else 0.0

    def is_frozen(self, node: str, mono: float) -> bool:
        return node in self.nodes and self.quiet_s(node, mono) > self.threshold_s(node)

    def check(self, mono: float) -> List[Tuple[str, float]]:
        """Nodes to report now: (name, quiet seconds). A frozen node is reported when it becomes frozen and
        then every REMINDER_S."""
        report = []
        for node, activity in self.nodes.items():
            if not self.is_frozen(node, mono):
                continue
            if not activity.alerted or mono >= activity.next_report_mono:
                activity.alerted = True
                activity.next_report_mono = mono + REMINDER_S
                report.append((node, mono - activity.last_change_mono))
        return report
