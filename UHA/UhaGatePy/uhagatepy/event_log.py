"""Node log messages (RPISERP 0x620) -> one text line in log.txt.

Packet data (8 bytes): node id, event type, then 6 free data bytes. Line format, same as UhaGate6:

    dd.mm.yyyy hh:mm:ss NODE EVENT d2 d3 d4 d5 d6 d7
"""
import time
from typing import Dict

EVENT_NAMES = {0: "STARTUP", 1: "ERROR", 2: "LOG", 3: "STATUS"}


def format_line(data: bytes, node_names: Dict[int, str], when: time.struct_time) -> str:
    data = data.ljust(8, b"\x00")[:8]                 # a short packet is padded with zeros
    return "{:02d}.{:02d}.{} {:02d}:{:02d}:{:02d} {} {} {}\n".format(
        when.tm_mday, when.tm_mon, when.tm_year, when.tm_hour, when.tm_min, when.tm_sec,
        node_names.get(data[0], "UNKNOWN"), EVENT_NAMES.get(data[1], "UNKNOWN_EVENT"),
        " ".join(str(b) for b in data[2:8]))


def append(path: str, line: str) -> None:
    with open(path, "a", encoding="utf-8") as f:
        f.write(line)
