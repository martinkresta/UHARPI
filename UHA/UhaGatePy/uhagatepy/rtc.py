"""RTC sync packet for the nodes, identical to UhaGate6 / UHA5.

RPISERP packet 0x051, 4 bytes big-endian: local time as a unix timestamp
= UTC unix time + 3600 (time zone, winter) + another 3600 in summer time.
The nodes have no time zone of their own; the Raspberry Pi is their time source (NTP synchronised).
"""
import struct
import time
from typing import Tuple

PACKET_ID = 0x051


def payload(now: float) -> Tuple[bytes, bool]:
    """(4 data bytes, summer_time) for the unix time `now`."""
    summer = time.localtime(now).tm_isdst > 0
    local = int(now) + 3600 + (3600 if summer else 0)
    return struct.pack(">I", local & 0xFFFFFFFF), summer
