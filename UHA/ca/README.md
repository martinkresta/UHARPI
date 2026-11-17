# UHA CA — client certificates for https://ctrl.uha.mkresta.cz

The control page and the command API accept **only devices with a certificate of this CA** (nginx
`ssl_verify_client on`, `UHA/nginx/uha-public`). The CN of the certificate is the user name in the journal and in the
DB table `commands`.

- The CA lives **on the PC, outside the repo**: `~/uha-ca/` (`UHA_CA_DIR` to change it). The scripts refuse a folder
  inside the repo; `.gitignore` here blocks keys and certificates as a second guard.
- Only `ca.crt` and `crl.pem` go to the Pi (`/etc/nginx/uha-ca/`, `deploy_ca.sh`). The CA key never leaves the PC.
- Keys: EC P-256. CA 10 years, client certificates 3 years, CRL 10 years (nginx rejects *all* client certificates once
  the CRL has expired, so it must not run out; `revoke.sh` writes a new one anyway).
- The CA key has no passphrase (same protection level as the SSH key of the Pi on this PC). Back up `~/uha-ca/`
  (e.g. on an encrypted USB stick): without it no new certificates and no revocations.

## Scripts (Git Bash on the PC, in `UHA/ca/`)

| Script | What |
|--------|------|
| `./ca_init.sh [folder]` | create the CA (once; done 2026-11-17 in `~/uha-ca`) |
| `./client_cert.sh <name>` | key + certificate + `<name>.p12` for one device; asks for the `.p12` export password |
| `./client_cert.sh <name> --no-p12` | key + certificate only (PEM), e.g. for `curl` tests |
| `./revoke.sh <name>` | revoke + new CRL (folder renamed to `<name>.revoked-<date>`, the name can be reissued) |
| `./deploy_ca.sh` | copy `ca.crt` + `crl.pem` to the Pi, `nginx -t`, reload. **After every `revoke.sh`.** |

Names: one per device, lower case, e.g. `martin-pc`, `martin-telefon`, `zena-telefon`. Files land in
`~/uha-ca/clients/<name>/`.

The `.p12` uses the 3DES format that every Android / Firefox / Windows version imports, and contains **only** the
device certificate, not the CA: the phone must not trust the home CA for web sites.

## Install the `.p12`

The export password is the one typed in `client_cert.sh`. Copy the file to the device over a private way (USB cable,
not e-mail / chat), delete the copy afterwards.

**Android (Chrome):** Settings → Security (and privacy) → More security settings → Encryption & credentials →
Install a certificate → **VPN & app user certificate** (older Androids: "Install from storage") → pick
`<name>.p12` → enter the export password → give it a name. Chrome then offers the certificate when
`https://ctrl.uha.mkresta.cz` asks; allow it (Chrome remembers the choice).

**Firefox (desktop):** Settings → Privacy & Security → Certificates → View Certificates… → **Your Certificates** →
Import… → `<name>.p12` → export password. Opening `https://ctrl.uha.mkresta.cz` then asks which certificate to send;
tick "Remember this decision".

**Chrome / Edge on Windows:** double-click the `.p12` → Current User → next → password → "Automatically select the
certificate store" → finish. Restart the browser.

Without a (valid) certificate the page shows `400 No required SSL certificate was sent` or `400 The SSL certificate
error` (revoked / expired / other CA).

## Lost or replaced device

```bash
./revoke.sh martin-telefon && ./deploy_ca.sh
./client_cert.sh martin-telefon          # new certificate for the new phone
```

Check on the Pi which CRL nginx has: `openssl crl -in /etc/nginx/uha-ca/crl.pem -noout -text | grep -A1 Serial`.
Serial numbers of issued certificates: `~/uha-ca/index.txt` (`V` valid, `R` revoked).
