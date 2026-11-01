"""VARS2 tunnel packets from ELECON (VARS2 spec section 7.2).

RPISERP packet id 0x180 + n (n = producer node id, 0..15), data = the 8 bytes of a VARS2 CAN frame:

    byte 0..1   variable id    uint16 LITTLE-endian   (the RPISERP packet id itself is big-endian!)
    byte 2..5   value          4 bytes LITTLE-endian: float32 | int32 | uint32, chosen by the YAML type
    byte 6      flags          bit0 = VALID
    byte 7      sequence       reserved

The value type is not sent - it comes from the YAML definition of the variable id.
"""
import math
import struct
from dataclasses import dataclass
from typing import Union

from .rpiserp import Packet
from .vars_def import VarsFile

FIRST_ID = 0x180
LAST_ID = 0x18F
FLAG_VALID = 0x01


def is_tunnel(packet_id: int) -> bool:
    return FIRST_ID <= packet_id <= LAST_ID


class TunnelDrop(Exception):
    """The packet is not usable. `reason` is one of: length, unknown_id, bad_value."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass
class TunnelValue:
    var_id: int
    value: Union[float, int]   # float for type float, otherwise int (bool: 0 or 1)
    valid: bool                # VALID flag of the frame
    producer: int              # node id taken from the packet id (id & 0x0F)


def decode(packet: Packet, defs: VarsFile) -> TunnelValue:
    if len(packet.data) != 8:
        raise TunnelDrop("length")
    var_id, raw, flags, _sequence = struct.unpack("<H4sBB", packet.data)
    definition = defs.by_id.get(var_id)
    if definition is None:
        raise TunnelDrop("unknown_id")       # a newer YAML on the nodes than here, or garbage

    if definition.type == "float":
        value: Union[float, int] = struct.unpack("<f", raw)[0]
        if not math.isfinite(value):
            raise TunnelDrop("bad_value")
    elif definition.type == "int32":
        value = struct.unpack("<i", raw)[0]
    else:                                    # uint32; bool and enum are stored as uint32 as well
        value = struct.unpack("<I", raw)[0]
        if definition.type == "bool":
            value = 1 if value else 0
    return TunnelValue(var_id, value, bool(flags & FLAG_VALID), packet.id & 0x0F)
