"""RPISERP framing between ELECON and the RPi (VARS2 spec section 7.1).

    0x7F 0xAA | len | id_hi id_lo | data (len - 2 bytes, 0..8) | checksum

`len` counts the id and the data (2..10). The checksum is the 8-bit sum of all bytes of the frame
before it (starting with 0x7F). The packet id is big-endian.

The parser keeps an incomplete frame between two reads, so a frame split anywhere is still found.
Bytes that do not belong to a valid frame are skipped one by one and counted.
"""
from dataclasses import dataclass
from typing import List

START_1 = 0x7F
START_2 = 0xAA
ID_LENGTH = 2
MAX_DATA_LENGTH = 8
MAX_LEN = ID_LENGTH + MAX_DATA_LENGTH       # largest allowed value of the len byte


@dataclass
class Packet:
    id: int          # RPISERP packet id, e.g. 0x221
    data: bytes      # 0..8 bytes


def checksum(frame_part: bytes) -> int:
    """8-bit sum of the bytes."""
    return sum(frame_part) & 0xFF


def encode(packet_id: int, data: bytes) -> bytes:
    """Build a complete frame to send."""
    if len(data) > MAX_DATA_LENGTH:
        raise ValueError("RPISERP data is limited to 8 bytes")
    body = bytes([START_1, START_2, len(data) + ID_LENGTH, (packet_id >> 8) & 0xFF, packet_id & 0xFF]) + data
    return body + bytes([checksum(body)])


class Parser:
    """Feed it the received bytes, get the complete valid packets back."""

    def __init__(self) -> None:
        self._buf = bytearray()
        self.rx_bytes = 0
        self.packets = 0
        self.checksum_errors = 0
        self.length_errors = 0        # len byte outside 2..10
        self.discarded_bytes = 0      # bytes skipped because they are not part of a valid frame

    def reset(self) -> None:
        """Forget an incomplete frame (after the serial link was reopened)."""
        self._buf.clear()

    def feed(self, chunk: bytes) -> List[Packet]:
        self.rx_bytes += len(chunk)
        buf = self._buf
        buf += chunk
        end_of_data = len(buf)
        packets: List[Packet] = []
        i = 0                                   # everything before i has been handled
        while True:
            start = buf.find(b"\x7f\xaa", i)
            if start < 0:
                # no start sequence; a single 0x7F at the very end may be its first half - keep it
                keep_from = end_of_data - 1 if (end_of_data > i and buf[-1] == START_1) else end_of_data
                self.discarded_bytes += keep_from - i
                i = keep_from
                break
            self.discarded_bytes += start - i
            i = start
            if i + 3 > end_of_data:
                break                           # the len byte has not arrived yet
            length = buf[i + 2]
            if length < ID_LENGTH or length > MAX_LEN:
                self.length_errors += 1
                self.discarded_bytes += 1
                i += 1                          # not a real frame start, look further
                continue
            frame_end = i + length + 4          # 3 header bytes + len bytes + checksum
            if frame_end > end_of_data:
                break                           # wait for the rest of the frame
            if checksum(buf[i:frame_end - 1]) != buf[frame_end - 1]:
                self.checksum_errors += 1
                self.discarded_bytes += 1
                i += 1
                continue
            packets.append(Packet((buf[i + 3] << 8) | buf[i + 4], bytes(buf[i + 5:frame_end - 1])))
            self.packets += 1
            i = frame_end
        del buf[:i]
        return packets
