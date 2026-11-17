"""Commands from the control web to the nodes (CMD_spec.md, UHA_FW/UHA_COMMON/VarDefs).

Pure logic, no I/O (tested without a serial port):
  user_from_dn   the user name = CN of the client certificate DN that nginx passes in X-Client-DN
  check_value    the JSON value -> number for the command's type (400 if it does not fit the type)
  packet_data    the 8 data bytes of RPISERP packet 0x52 CMD_RPI_COMMAND (spec section 2):
                     0 target node id | 1-2 command id u16 LE | 3-6 value LE (float32 / int32 / uint32) | 7 seq
  RateLimit      at most 10 per second and 20 per minute, like ELECON (spec section 3), so the web gets a
                 clear 429 instead of commands silently dropped by ELECON. Sliding windows: never more than
                 ELECON's fixed windows allow.

The value is not checked against min / max (nor an enum number against the items): the target node clamps it
(spec "Principles"). Only the type is checked: integers for uint32 / int32, numbers for float, 0 / 1 / true / false
for bool, the item number or name for enum.
"""
import collections
import math
import re
import struct
from typing import Deque, Dict, Optional, Union

from .vars_def import CmdDef

PACKET_COMMAND = 0x52
RATE_PER_S = 10
RATE_PER_MIN = 20

_CN = re.compile(r"(?:^|,|/)\s*CN\s*=\s*((?:\\.|[^,/+])+)")


class BadValue(Exception):
    pass


def user_from_dn(dn: Optional[str]) -> Optional[str]:
    """'CN=martin-pc,O=UHA' (RFC 2253, nginx $ssl_client_s_dn) -> 'martin-pc'; None if there is no CN."""
    if not dn:
        return None
    match = _CN.search(dn)
    if not match:
        return None
    name = re.sub(r"\\(.)", r"\1", match.group(1)).strip()
    return name or None


def check_value(cmd: CmdDef, value, enums: Optional[Dict[str, Dict[int, str]]] = None) -> Union[int, float]:
    """The value from the request as the number that will be sent. Raises BadValue.

    bool: 0 / 1 or true / false. enum: the item number or its name (names from `enums`, VarsFile.enums).
    """
    if cmd.type == "bool" and isinstance(value, bool):
        return int(value)
    if cmd.type == "enum" and isinstance(value, str):
        items = (enums or {}).get(cmd.enum, {})
        for number, name in items.items():
            if name == value:
                return number
        raise BadValue(f"unknown item '{value}' of enum {cmd.enum}")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise BadValue("value must be a number" + (" or an item name" if cmd.type == "enum" else
                                                   " or true / false" if cmd.type == "bool" else ""))
    if not math.isfinite(value):
        raise BadValue("value must be finite")
    if cmd.type == "float":
        number = float(value)
        if abs(number) > 3.4e38:
            raise BadValue("value does not fit float32")
        return number
    if value != int(value):
        raise BadValue(f"value must be a whole number for type {cmd.type}")
    number = int(value)
    low, high = (0, 2 ** 32 - 1) if cmd.type == "uint32" else (-2 ** 31, 2 ** 31 - 1)
    if cmd.type == "bool":
        low, high = 0, 1
    if not low <= number <= high:
        raise BadValue(f"value out of range for type {cmd.type} ({low}..{high})")
    return number


def packet_data(cmd: CmdDef, value: Union[int, float], seq: int) -> bytes:
    if cmd.type == "float":
        raw = struct.pack("<f", value)
    elif cmd.type == "uint32":
        raw = struct.pack("<I", value)
    else:                                         # int32, bool, enum: int32 (spec section 2)
        raw = struct.pack("<i", value)
    return struct.pack("<BH", cmd.target_id & 0x0F, cmd.id) + raw + bytes([seq & 0xFF])


class RateLimit:
    """Times of the commands sent in the last minute (monotonic seconds)."""

    def __init__(self, per_s: int = RATE_PER_S, per_min: int = RATE_PER_MIN) -> None:
        self.per_s = per_s
        self.per_min = per_min
        self._sent: Deque[float] = collections.deque()

    def allowed(self, now: float) -> bool:
        while self._sent and self._sent[0] <= now - 60:
            self._sent.popleft()
        last_second = sum(1 for t in self._sent if t > now - 1)
        return len(self._sent) < self.per_min and last_second < self.per_s

    def sent(self, now: float) -> None:
        self._sent.append(now)
