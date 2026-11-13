# Sample outputs of UhaGatePy

Downloaded from the production Pi on 2026-11-13 07:18, one minute after the start of version 0.2.0 (VARS2 only).
They only show the **format**. The real files are written compact (one line) to `/dev/shm` and are served as
`/home/pi/Web/uha2.json` and `/home/pi/Web/uha_status.json`; here they are pretty-printed for reading.

- `uha2.json`: every YAML variable with `value` (physical units, `null` if never received), `valid` (VALID flag and
  age <= `timeout_ms`), `age_s`, `producer`.
- `uha_status.json`: `Counters` (incl. `IgnoredOldPackets`, the old 0x221 packets still sent by the firmware);
  `Vars2` lists invalid, stale and never received variables; `Nodes` shows the tunnel packets and frozen state
  per producer; `Vars` the value and age of every `uha.json` variable.

`uha.json` and `bms.json` are unchanged compared to UhaGate6; a sample of the old `uha.json` is `WS/uha.json`.
