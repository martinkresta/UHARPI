"""Content of uha_status.json: link state, counters, age of every variable, nodes, old-vs-VARS2 check.

Similar to UhaGate6's status file, but not identical: VarPackets is now OldPackets, a node's LastEvent is
LastLogEvent, and variables without a name in the old table are not listed. Plus the VARS2 parts.
"""
import os
from typing import TYPE_CHECKING

from . import VERSION
from .legacy_table import NAME_TO_ID

if TYPE_CHECKING:                      # only for the type hint, avoids a circular import
    from .gateway import Gateway


def _age(now: float, then: float) -> int:
    return int(now - then)


def rss_kb() -> int:
    """Current resident memory of this process [kB], -1 where /proc is not available (PC tests)."""
    try:
        with open("/proc/self/statm") as f:
            return int(f.read().split()[1]) * os.sysconf("SC_PAGE_SIZE") // 1024
    except (OSError, ValueError, IndexError, AttributeError):
        return -1


def build(g: "Gateway", unix_time: int, mono: float, raw: dict) -> dict:
    """`raw` = Store.snapshot(), the values just published (so they are not computed twice)."""
    store = g.store
    parser = g.parser
    c = g.counters
    uptime = mono - g.start_mono

    # ---- link ----
    link = {
        "Port": g.link.path,
        "State": "down" if not g.link.is_open else ("up" if g.receiving else "silent"),
        "SinceUnix": g.link_change_unix,
        "Reconnects": g.reconnects,
        "LastPacketAgeS": None if g.last_packet_mono < 0 else _age(mono, g.last_packet_mono),
    }
    if not g.link.is_open and g.last_open_error:
        link["LastError"] = g.last_open_error

    counters = {
        "RxBytes": parser.rx_bytes, "RxPackets": parser.packets,
        "OldPackets": c.old_packets, "TunnelPackets": c.tunnel_packets, "LogPackets": c.log_packets,
        "UnknownIds": c.unknown_packets, "Malformed": c.malformed, "OutOfRangeVarIds": c.out_of_range_vars,
        "TunnelDropped": dict(c.tunnel_drops), "WrongProducer": c.wrong_producer,
        "ChecksumErrors": parser.checksum_errors, "LengthErrors": parser.length_errors,
        "DiscardedBytes": parser.discarded_bytes, "ClampedToInt16": store.clamped,
        "TxPackets": c.tx_packets, "TxErrors": c.tx_errors, "RtcSyncSent": c.rtc_sent,
        "WriteErrors": c.write_errors, "EventLogErrors": c.event_log_errors,
        "RssKb": rss_kb(),
    }

    # ---- every old variable (as in UhaGate6) ----
    variables = {}
    for name, var_id in NAME_TO_ID.items():
        old = store.old.get(var_id)
        v2 = store.v2.get(var_id)
        last = max((x.mono for x in (old, v2) if x is not None), default=None)
        last_unix = max((x.unix for x in (old, v2) if x is not None), default=None)
        variables[name] = {
            "Id": var_id, "Value": raw[name],
            "AgeS": None if last is None else _age(mono, last), "LastRxUnix": last_unix,
            "Count": old.count if old else 0, "Count2": v2.count if v2 else 0,
        }

    # ---- nodes: the VARS2 tunnel names the producer, log messages carry the node id ----
    nodes = {}
    for node_id, name in sorted(g.defs.node_names.items()):
        tunnel = g.tunnel_nodes.get(node_id)
        logs = g.log_nodes.get(node_id)
        seen = [x for x in (tunnel, logs) if x is not None]
        last = max((x.last_mono for x in seen), default=None)
        nodes[name] = {
            "Id": node_id,
            "LastSeenUnix": max((x.last_unix for x in seen), default=None),
            "AgeS": None if last is None else _age(mono, last),
            "TunnelPackets": tunnel.packets if tunnel else 0,
            "TunnelAvgPerS": round(tunnel.packets / uptime, 2) if tunnel and uptime > 0 else 0,
            "LogMessages": logs.packets if logs else 0,
            "LastLogEvent": logs.last_event if logs else None,
        }

    # ---- old vs VARS2 ----
    total = sum(s[0] for s in store.compared.values())
    mismatched = sum(s[1] for s in store.compared.values())
    worst = sorted(((s[1], var_id) for var_id, s in store.compared.items() if s[1]), reverse=True)[:10]
    comparison = {
        "VariablesCompared": len(store.compared), "Compared": total, "Mismatched": mismatched,
        "Worst": {g.defs.by_id[var_id].name: {"Mismatched": n, "Compared": store.compared[var_id][0]}
                  for n, var_id in worst},
    }

    return {
        "Version": VERSION, "UnixTime": unix_time, "StartUnix": g.start_unix, "UptimeS": int(uptime),
        "Yaml": {"Version": g.defs.version, "Sha": g.defs.sha, "Variables": len(g.defs.by_id)},
        "Link": link, "Counters": counters, "Comparison": comparison, "Nodes": nodes, "Vars": variables,
    }
