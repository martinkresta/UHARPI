# Command channel — RPi part: certificates, nginx mTLS, UhaGatePy API, control page (step 3a)

Spec: **`UHA_FW/UHA_COMMON/VarDefs/CMD_spec.md`** (read it first; it wins if this brief is unclear).
Runs in parallel with the FW brief `UHA_FW/UHA_COMMON/tasks/cmd_channel_fw.md` (other agent), which owns the YAML
`commands:` section. Until that is committed, work against the example in spec section 5 in a test fixture;
switch to the real YAML before the end.

Repos: UHARPI (+ read UHA_FW). Branch `feature/control-web`. Lightweight mode (deploy, run, debug from the journal,
short report). Pi rules as before: backup + `nginx -t` + reload; no reboot; apt only if really needed (ask);
**never put private keys or passwords into the repo or into files the agent writes outside the CA folder.**

## Part 1 — Own CA and client certificates

- Scripts in `UHARPI/UHA/ca/` (scripts + README only; **no keys in the repo**, add a `.gitignore`):
  - `ca_init.sh` — creates a small CA with `openssl ca` (index/serial/crl), key **on Martin's PC** in a folder
    outside the repo (default `~/uha-ca/`, path as a parameter), long validity (e.g. 10 years).
  - `client_cert.sh <name>` — key + cert for one device (CN = name, e.g. `martin-telefon`, `martin-pc`,
    `zena-telefon`), 3 years, exports a `.p12` for Android/Firefox; Martin types the export password himself.
  - `revoke.sh <name>` — revoke + regenerate the CRL.
  - `deploy_ca.sh` — copies only the CA certificate and the CRL to the Pi (`/etc/nginx/uha-ca/`).
- README: how Martin installs the `.p12` on Android (Settings → Security → Install certificate → user certificate;
  Chrome then offers it) and in desktop Firefox (Settings → Privacy & Security → Certificates → View → Your
  Certificates → Import). Create the first cert `martin-pc` together with Martin at the end (he enters the password).

## Part 2 — nginx `ctrl.uha.mkresta.cz`

Replace the step-1c placeholder (`return 403`) in the 443 server block:
- `ssl_client_certificate /etc/nginx/uha-ca/ca.crt; ssl_verify_client on; ssl_verify_depth 1; ssl_crl /etc/nginx/uha-ca/crl.pem;`
- `/` → static control page `/home/pi/Web/control/` (from `UHARPI/WS/control/`).
- `/uha2.json` → same file as on the monitoring site (read only).
- `/api/` → `proxy_pass http://127.0.0.1:<port>/api/`; `proxy_set_header X-Client-DN $ssl_client_s_dn;`
  (overwrite any incoming header of that name). Only `GET /api/commands` and `POST /api/cmd`.
- Monitoring site `uha.mkresta.cz`: add a menu link "Ovládání" → `https://ctrl.uha.mkresta.cz/` in `WS/index.html`.
- Checks: without a cert the TLS handshake fails (`curl -sI https://ctrl.uha.mkresta.cz/` → error); with the
  `martin-pc` cert (`curl --cert ... --key ...`) → 200; `uha.mkresta.cz` unchanged.

## Part 3 — UhaGatePy

- `vars_def.py`: read `commands:` (id, name, target, type, min, max, state, unit, desc); a broken section refuses
  to start like the rest of the YAML.
- HTTP API on `127.0.0.1` only (config key `api-port`, e.g. 8091). Keep it simple: Python stdlib
  (`http.server.ThreadingHTTPServer` in its own thread, handing commands to the asyncio loop with
  `loop.call_soon_threadsafe`, or an equally simple asyncio solution — choose and explain). No web framework.
  Endpoints and errors as spec section 1. Reject requests without `X-Client-DN` (403).
- Send: RPISERP packet `0x52` exactly as spec section 2 (value packed by the command's `type`), seq counter.
  Gateway-side rate limit matching ELECON (10/s, 20/min) → 429, so the UI gets a clear answer.
- Log every command: journal line (user CN, command, value, seq) and DB table
  `CREATE TABLE IF NOT EXISTS commands (ts INTEGER, user TEXT, cmd_id INTEGER, value REAL, seq INTEGER)` (kept forever).
- The serial link down → 503. API errors must never stop the gateway (same rule as the DB logger).
- Bump `VERSION`, README section.

## Part 4 — Minimal control page (`UHARPI/WS/control/`)

Plain HTML + JS like the existing dashboard, no framework, look refined later by Martin:
- Loads `/api/commands`, shows one row per command: name/desc, current state from `/uha2.json` (polled every
  3 s), on/off button for the lights (sends 0 / 100).
- After sending: "čekám na změnu…" → state changed → normal; no change within 10 s → "stav se nezměnil".
  Show API errors (429, 503) as text.
- Link back to `https://uha.mkresta.cz/`.

## End-to-end check (after Martin flashed ELECON + IOBOARD_U from the FW brief)

Martin installs `martin-pc.p12` in Firefox, opens `https://ctrl.uha.mkresta.cz`, switches one loft light:
the light reacts, the state in the page changes within a few seconds, journal + `commands` table have the entry
with `martin-pc`. Phone: same with `martin-telefon` in Chrome on mobile data.

## Report and stop

What changed (files, nginx config copy in `UHA/nginx/`), API port, versions, check results, open points.
