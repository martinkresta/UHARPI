#!/usr/bin/env python3
"""Fake ELECON: lets UhaGatePy be tested without the real serial link (Linux only, uses a pseudo-terminal).

    python3 tools/fake_elecon.py --seconds 120 &
    python3 -m uhagatepy --port /tmp/fake_elecon --out-dir /tmp/out --log-file /tmp/out/log.txt --vars-yaml uha_vars.yaml

It creates a pseudo-terminal, links it to /tmp/fake_elecon (--link) and then sends, like ELECON does:
  - every YAML variable in the old format (packet 0x221) at its period,
  - the same variable in the VARS2 tunnel (packet 0x180 + producer) unless --no-tunnel,
  - a node log message (0x620) every 20 s,
and prints the RTC sync packets (0x051) it receives from the gateway.

--break NAME makes the tunnel value of that variable 10 % wrong, to check the old-vs-VARS2 comparison.
The frames are built here with plain struct calls (not with the gateway's tunnel module), so the test
does not simply repeat the gateway's own mistakes.
"""
import argparse
import os
import pty
import random
import select
import struct
import sys
import time
import tty

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, APP_DIR)

from uhagatepy import rpiserp, vars_def           # noqa: E402  (needs the path above)
from uhagatepy.store import to_legacy_raw          # noqa: E402


def start_value(rng, d):
    """A start value that fits the old int16 range: up to 3000 steps of one old raw unit."""
    if d.type == "bool":
        return rng.randint(0, 1)
    if d.type == "enum":
        return 0
    return rng.uniform(0, 3000) / d.legacy_scale


def next_value(rng, d, value, enums):
    """Random walk of a few old raw units per update (booleans and enums change rarely)."""
    if d.type == "bool":
        return value if rng.random() < 0.95 else 1 - value
    if d.type == "enum":
        return value if rng.random() < 0.9 else rng.choice(list(enums[d.enum]))
    return value + rng.uniform(-2, 2) / d.legacy_scale


def old_frame(d, value):
    raw, _ = to_legacy_raw(value, d.legacy_scale)
    return rpiserp.encode(0x221, struct.pack(">HhH", d.id, raw, 1))


def tunnel_frame(defs, d, value, wrong):
    if wrong:
        value = value * 1.1 + 5
    if d.type == "float":
        payload = struct.pack("<f", value)
    else:
        payload = struct.pack("<I", int(value))
    node = defs.nodes[d.producer]
    return rpiserp.encode(0x180 + node, struct.pack("<H", d.id) + payload + bytes([1, 0]))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--yaml", default=os.path.join(APP_DIR, "uha_vars.yaml"))
    parser.add_argument("--link", default="/tmp/fake_elecon", help="symlink to the pseudo-terminal")
    parser.add_argument("--seconds", type=float, default=0, help="stop after this time (0 = run until Ctrl-C)")
    parser.add_argument("--no-tunnel", action="store_true", help="old format only (ELECON before step 2)")
    parser.add_argument("--break", dest="broken", default="", help="variable name whose tunnel value is wrong")
    args = parser.parse_args()

    defs = vars_def.load(args.yaml)
    rng = random.Random(1)
    master, slave = pty.openpty()
    tty.setraw(slave)
    os.set_blocking(master, False)       # nobody reading (gateway stopped): drop frames like a real UART, do not hang
    if os.path.lexists(args.link):
        os.unlink(args.link)
    os.symlink(os.ttyname(slave), args.link)
    print(f"fake ELECON on {args.link} -> {os.ttyname(slave)}, {len(defs.by_id)} variables", flush=True)

    values = {i: start_value(rng, d) for i, d in defs.by_id.items()}
    now = time.monotonic()
    due = {i: now + rng.uniform(0, d.period_ms / 1000) for i, d in defs.by_id.items()}
    sent = {"old": 0, "tunnel": 0, "log": 0, "dropped": 0}
    rtc_seen = 0
    next_log = now + 5
    end = now + args.seconds if args.seconds else None
    parser_rx = rpiserp.Parser()
    try:
        while end is None or time.monotonic() < end:
            now = time.monotonic()
            frames = []
            for var_id, when in due.items():
                if when <= now:
                    d = defs.by_id[var_id]
                    values[var_id] = next_value(rng, d, values[var_id], defs.enums)
                    frames.append(old_frame(d, values[var_id]))
                    sent["old"] += 1
                    if not args.no_tunnel:
                        frames.append(tunnel_frame(defs, d, values[var_id], d.name == args.broken))
                        sent["tunnel"] += 1
                    due[var_id] = when + d.period_ms / 1000
            if now >= next_log:
                frames.append(rpiserp.encode(0x620, bytes([4, 2, 1, 2, 3, 4, 5, 6])))
                sent["log"] += 1
                next_log = now + 20
            for frame in frames:
                try:
                    os.write(master, frame)
                except BlockingIOError:
                    sent["dropped"] += 1
                time.sleep(0.001)                        # ~115200 Bd: about one 14-byte frame per millisecond
            readable, _, _ = select.select([master], [], [], 0.005)
            if readable:
                for packet in parser_rx.feed(os.read(master, 1024)):
                    if packet.id == 0x051:
                        rtc_seen += 1
                        print(f"RTC sync received: {int.from_bytes(packet.data, 'big')}", flush=True)
    except KeyboardInterrupt:
        pass
    finally:
        os.unlink(args.link)
        print(f"fake ELECON done: sent {sent}, RTC syncs received {rtc_seen}", flush=True)


if __name__ == "__main__":
    main()
