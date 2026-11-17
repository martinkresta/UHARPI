# HTTPS with Let's Encrypt for uha.mkresta.cz + ctrl.uha.mkresta.cz (step 1c)

Repo: **UHARPI** (nginx config copies in `UHA/nginx/`, short notes in `UHA/Grafana/README.md` or a new
`UHA/nginx/README.md`). Replaces part 4 of `tasks/vars2_db_logging_grafana.md` (that one assumed one name).

## Precondition — check first, stop if not met

- `tasks/rpi_hardening.md` is finished: SSH key-only + LAN-only, nftables active.
- The firewall allows incoming TCP **80 and 443** from anywhere (`sudo nft list ruleset`).
- DNS (done by Martin, Hukot.cz, 2026-11-17): `uha.mkresta.cz` and `ctrl.uha.mkresta.cz` AAAA →
  `2a00:1028:83d2:4216::10` (TTL 3600). Verify from the Pi: `dig +short AAAA uha.mkresta.cz` (or `getent ahosts`).
- No public IPv4: both names are IPv6-only. Let's Encrypt validates over IPv6 — fine.

## Goal

| Name | Content | Access |
|---|---|---|
| `https://uha.mkresta.cz` | existing web dashboard (`/home/pi/Web/`) + Grafana `/grafana/` (password login) | public, no client certificate |
| `https://ctrl.uha.mkresta.cz` | **placeholder only** — returns 403 now; step 3 adds the control UI with mandatory client certificates (mTLS) | nothing usable yet |
| `http://192.168.1.10/` (LAN, by IP) | unchanged, keeps working over HTTP | LAN |

## Working mode and rules

Lightweight. apt allowed: `certbot`, `python3-certbot-nginx`. nginx: back up `/etc/nginx` before changes,
`sudo nginx -t` before every reload, reload (not restart). No reboot, no network changes, do not touch UHA5/UHA6,
UhaGatePy only if a path needs it (should not). Never write passwords or private keys into the repo.

## Steps

1. **nginx server blocks** (keep the existing default site for LAN/IP access as it is):
   - `server_name uha.mkresta.cz;` on 80 → after the certificate exists: 301 redirect to https (but keep
     `/.well-known/acme-challenge/` served on 80 for renewals — certbot's nginx plugin handles that).
   - `server_name uha.mkresta.cz;` on 443: same root and same `/grafana/` proxy (incl. websocket headers) as the
     existing site. **Remove the LAN-only restriction on `/grafana/` here** (Grafana login is now protected by TLS).
     Keep the LAN-only restriction on the plain-HTTP default site.
   - `server_name ctrl.uha.mkresta.cz;` on 80 (ACME + redirect) and 443: `return 403;` with a comment
     `# step 3: ssl_verify_client on; control UI + /api/` — nothing else.
   - `server_tokens off;`. No HSTS yet (added after it has run well for a while — note it in the report).
2. **Certificate:** `sudo certbot --nginx -d uha.mkresta.cz -d ctrl.uha.mkresta.cz` (one certificate with both
   names, non-interactive flags, Martin's e-mail only if he gives it — otherwise
   `--register-unsafely-without-email` and say so in the report). Then `sudo certbot renew --dry-run` and check the
   systemd timer (`systemctl list-timers | grep certbot`).
3. **Grafana:** in `grafana.ini` set `domain = uha.mkresta.cz`, `root_url = https://uha.mkresta.cz/grafana/`,
   `serve_from_sub_path = true`, `cookie_secure = true`; keep anonymous access and sign-up off; brute-force login
   protection on (default — verify it is not disabled). Restart grafana-server (allowed).
   Check what happens with LAN access by IP (`http://192.168.1.10/grafana/`): if Grafana now redirects to the
   https name, that is acceptable — report it. Do not add hacks to keep both working.
4. **Web dashboard:** links to Grafana must be relative (`/grafana/...`) so they work on both names — check.
5. Copy the final nginx site files into `UHA/nginx/` in the repo (no keys/certs, only config).

## Checks

- From the Pi: `curl -sI https://uha.mkresta.cz/` (200), `curl -sI https://uha.mkresta.cz/grafana/login` (200),
  `curl -sI http://uha.mkresta.cz/` (301 → https), `curl -sI https://ctrl.uha.mkresta.cz/` (403).
- `openssl s_client -connect uha.mkresta.cz:443 -servername uha.mkresta.cz </dev/null | openssl x509 -noout -subject -issuer -dates -ext subjectAltName`
- LAN: `http://192.168.1.10/` still shows the dashboard.
- **Martin (phone on mobile data, Wi-Fi off):** open `https://uha.mkresta.cz` (dashboard, padlock), then
  `https://uha.mkresta.cz/grafana/` (login page), `https://ctrl.uha.mkresta.cz` (403). Write him these three lines.

## Report

What changed (files), certificate names and expiry, renewal dry-run result, check results, how to undo
(restore `/etc/nginx` backup, `certbot delete --cert-name ...`), open points (HSTS later, LAN-by-IP Grafana behaviour).
