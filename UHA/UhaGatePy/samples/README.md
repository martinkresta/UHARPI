# Sample outputs of UhaGatePy

Downloaded from the production Pi on 2026-11-01 (about 4.5 h after the switch to UhaGatePy).
They only show the **format**. The real files are written compact (one line) to `/dev/shm` and are served
as `/home/pi/Web/uha2.json` and `/home/pi/Web/uha_status.json`; here they are pretty-printed for reading.

At the time of the capture ELECON did not send the VARS2 tunnel yet, so:
- in `uha2.json` every `source` is `old` (it becomes `vars2` once the tunnel arrives; `stale` / `none` also exist),
- in `uha_status.json` `TunnelPackets` are 0 and `Comparison` is empty.

`uha.json` and `bms.json` are unchanged compared to UhaGate6; a sample of the old `uha.json` is `WS/uha.json`.
