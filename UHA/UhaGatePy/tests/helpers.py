"""Shared helpers for the tests."""
import os
import struct

from uhagatepy import vars_def
from uhagatepy.rpiserp import Packet

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")
REAL_YAML = os.environ.get("UHA_VARS_YAML", r"C:\Martin\GIT\UHA_FW\UHA_COMMON\VarDefs\uha_vars.yaml")


def mini_defs():
    return vars_def.load(os.path.join(FIXTURES, "mini_vars.yaml"))


def tunnel_packet(node: int, var_id: int, raw4: bytes, flags: int = 1) -> Packet:
    """A VARS2 tunnel packet as ELECON sends it: packet id 0x180+node, CAN data bytes unchanged."""
    return Packet(0x180 + node, struct.pack("<H", var_id) + raw4 + bytes([flags, 0]))


def float_packet(node: int, var_id: int, value: float, flags: int = 1) -> Packet:
    return tunnel_packet(node, var_id, struct.pack("<f", value), flags)


def old_packet(var_id: int, raw: int, valid: int = 1) -> Packet:
    """Old 0x221 packet: id, int16 value, valid - all big-endian."""
    return Packet(0x221, struct.pack(">HhH", var_id, raw, valid))
