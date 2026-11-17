# nginx: HTTPS for uha.mkresta.cz + ctrl.uha.mkresta.cz (step 1c, 2026-11-17)

Brief: `tasks/https_letsencrypt.md`. DNS (Hukot.cz): both names AAAA → `2a00:1028:83d2:4216::10`, IPv6 only.

| URL | Content |
|-----|---------|
| `https://uha.mkresta.cz/` | dashboard (`/home/pi/Web/`) + `/grafana/` (password login, from anywhere) |
| `https://ctrl.uha.mkresta.cz/` | control page (`WS/control/` → `/home/pi/Web/control/`) + `/uha2.json` + `/api/commands`, `/api/cmd` → UhaGatePy `127.0.0.1:8091`; **client certificate of the UHA CA required** (`UHA/ca/`), else 400 |
| `http://<name>/` | `301` → https (ACME challenges for renewal also on 80) |
| `https://<IP or other name>` | TLS handshake rejected (`ssl_reject_handshake`) |
| `http://192.168.1.10/` | unchanged `sites-available/default`, Grafana LAN only (`UHA/Grafana/nginx/`) |

## Files (repo → Pi)

| Repo | Pi |
|------|----|
| `uha-public` | `/etc/nginx/sites-available/uha-public` + symlink in `sites-enabled/` |
| `uha-tls.conf` | `/etc/nginx/snippets/uha-tls.conf` (TLS 1.2/1.3, Mozilla intermediate) |
| `uha-grafana-public.conf` | `/etc/nginx/snippets/uha-grafana-public.conf` (`/grafana/` proxy without LAN restriction) |
| `uha-security.conf` | `/etc/nginx/conf.d/uha-security.conf` (`server_tokens off`) |
| `uha-ctrl-api.conf` | `/etc/nginx/snippets/uha-ctrl-api.conf` (proxy to the API, sets `X-Client-DN` from the verified certificate) |
| — | `/etc/nginx/uha-ca/ca.crt`, `crl.pem` (`UHA/ca/deploy_ca.sh`; without them nginx -t fails) |

Grafana settings for the public name are in `UHA/Grafana/systemd/grafana-uha.conf` (`GF_SERVER_DOMAIN`,
`GF_SERVER_ROOT_URL=https://uha.mkresta.cz/grafana/`, `GF_SECURITY_COOKIE_SECURE=true`); `grafana.ini` is untouched.

## Certificate

- Let's Encrypt, one certificate `--cert-name uha.mkresta.cz` with both names, ECDSA, 90 days.
- Obtained with `certbot certonly --nginx` (the nginx plugin only answers the challenge; it does not edit the files
  above), `--deploy-hook "systemctl reload nginx"` (stored as `renew_hook` in `/etc/letsencrypt/renewal/uha.mkresta.cz.conf`).
- Account without e-mail (`--register-unsafely-without-email`): no expiry warnings by mail. Add one later with
  `sudo certbot update_account -m <address>`.
- Renewal: `certbot.timer` (twice a day), renews 30 days before expiry. Test: `sudo certbot renew --dry-run`.
- Private key only on the Pi (`/etc/letsencrypt/`), never in the repo.

## Install / change

```bash
scp UHA/nginx/uha-public UHA/nginx/*.conf uharpi:/tmp/            # CA files first: UHA/ca/deploy_ca.sh
ssh uharpi 'cd /tmp && sed -i "s/\r$//" uha-public *.conf \
  && sudo install -m 644 uha-public /etc/nginx/sites-available/uha-public \
  && sudo install -m 644 uha-tls.conf uha-grafana-public.conf uha-ctrl-api.conf /etc/nginx/snippets/ \
  && sudo install -m 644 uha-security.conf /etc/nginx/conf.d/ \
  && sudo nginx -t && sudo systemctl reload nginx'
```

On a fresh Pi (no certificate yet) nginx refuses the 443 blocks: first install only the port-80 server block, run
certbot, then the full file.

## Undo

```bash
sudo tar -xzf /home/pi/nginx-backup-20261117-https.tgz -C /     # /etc/nginx as before (new files stay: remove them)
sudo rm /etc/nginx/sites-enabled/uha-public /etc/nginx/sites-available/uha-public \
        /etc/nginx/snippets/uha-tls.conf /etc/nginx/snippets/uha-grafana-public.conf /etc/nginx/conf.d/uha-security.conf
sudo nginx -t && sudo systemctl reload nginx
sudo certbot delete --cert-name uha.mkresta.cz
# Grafana back to the LAN URL:
sudo cp /home/pi/grafana-uha.conf.bak-20261117 /etc/systemd/system/grafana-server.service.d/uha.conf
sudo systemctl daemon-reload && sudo systemctl restart grafana-server
```

## Control site (step 3a, 2026-11-17)

- `ssl_verify_client on`, `ssl_verify_depth 1`, `ssl_crl`. nginx completes the TLS handshake also without a client
  certificate and answers HTTP 400 (it does not abort the handshake); nothing else is reachable.
- `X-Client-DN` is always set by nginx from `$ssl_client_s_dn` (a header sent by the client is overwritten — checked).
- Only `GET /api/commands` and `POST /api/cmd` are proxied (`limit_except`), other `/api/` paths 404.
- Headers: `Cache-Control: no-store`, `X-Frame-Options: DENY`, CSP `default-src 'self'; frame-ancestors 'none'`
  (the page has no inline script or style).
- The page files are in `/home/pi/Web/control/`, so `https://uha.mkresta.cz/control/` also serves the static page
  (harmless: the API is only on the ctrl name).
- Both names share one certificate and one IP: a browser may reuse an HTTP/2 connection of `uha.mkresta.cz` for
  `ctrl.uha.mkresta.cz`; nginx then answers 421 and the browser opens a new connection with the client certificate.
- Backup before the change: `/home/pi/nginx-backup-20261117-ctrl.tgz`.
- Undo (back to the 403 placeholder): restore that backup, `sudo nginx -t && sudo systemctl reload nginx`.

## Open

- **HSTS**: not yet. After HTTPS has run well for a while, uncomment the `Strict-Transport-Security` line in `uha-public`.
- **Grafana by IP** (`http://192.168.1.10/grafana/`): the page loads, but the session cookie is `Secure`, so login over
  plain HTTP does not hold. Use `https://uha.mkresta.cz/grafana/` (also works from the LAN over IPv6).
