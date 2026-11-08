# Sample outputs of UhaGatePy

Downloaded from the production Pi on 2026-11-08, about 10 minutes after the restart with the improved comparison,
with ELECON sending the VARS2 tunnel. They only show the **format**. The real files are written compact (one line)
to `/dev/shm` and are served as `/home/pi/Web/uha2.json` and `/home/pi/Web/uha_status.json`; here they are
pretty-printed for reading.

- `uha2.json`: every YAML variable with `source` = `vars2` (fresh tunnel value), `old` (VARS2 invalid or timed out, the
  old value is used) or `none` (never received).
- `uha_status.json`: `Comparison.Vars` holds, per variable, the old-vs-VARS2 statistics (differences in old raw units,
  `Verdict` ok / close / noisy / offset / few); `Vars2` lists invalid, stale and never received variables;
  `Nodes` shows the tunnel packets per producer.

`uha.json` and `bms.json` are unchanged compared to UhaGate6; a sample of the old `uha.json` is `WS/uha.json`.
