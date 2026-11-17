# Control page: enum and float commands, grouping (for steps 3b/3c)

Repo UHARPI (+ read UHA_FW YAML). Lightweight mode, deploy and check, short report. Branch `feature/control-ui-types`.
The FW side adds new commands in `uha_vars.yaml` (`UHA_COMMON/tasks/cmd_lights_blinds_setpoints.md`, later
`cmd_inverters_recu.md`); the gateway and the page must handle them **generically** from the YAML, no per-command code.

## UhaGatePy

- `vars_def.py`: read the new optional `step:` key of commands; for `type: enum` include the enum items
  (from `enums:`) in `GET /api/commands`.
- `POST /api/cmd`: accept the value for every type: `uint32`/`int32` integers, `float` numbers, `bool` 0/1 or
  true/false, `enum` the item number **or** its name. No clamping in the gateway (the node clamps), but return 400
  for a value of the wrong type or an unknown enum name.
- Deploy the new YAML (`deploy.sh`) whenever the FW agent changed it.

## Control page (`WS/control/`)

- Group rows by **category**, not by node: the new optional YAML key `category:` of each command (added by the FW
  agent: `light`, `blind`, `heating`, `inverter`, `ventilation`). Section titles: Světla, Žaluzie, Topení,
  Střídače, Rekuperace; commands without a category go to "Ostatní". Pass `category` through `GET /api/commands`.
- Function over looks: Martin will simplify the page (short names etc.) later — do not spend time on design.
- Widgets by type: `uint32` with `unit: %` and range 0..100 → on/off buttons (as today); `float` → number input
  with min/max/step from the API + "Nastavit" button, current state next to it; `enum` → one button per item,
  the current one highlighted; `bool` → on/off.
- Same feedback as today ("čekám na změnu…", "stav se nezměnil" after 10 s).
- Keep it plain HTML/JS, no framework; Martin refines the look later.

## Check

With the 3b FW not yet flashed the new rows show "no state" — fine. After Martin flashed: set a TECHM setpoint to a
value outside the range (e.g. 30 °C) — the page sends it, the state shows the clamped value (25 °C).
