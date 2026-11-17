#!/bin/bash
# Copy ONLY the CA certificate and the CRL to the Pi (/etc/nginx/uha-ca/) and reload nginx after nginx -t.
# Usage: ./deploy_ca.sh            (SSH host alias "uharpi", override with UHA_HOST=...)
source "$(dirname "$0")/common.sh"
need_ca
HOST="${UHA_HOST:-uharpi}"

ca_openssl crl -in crl.pem -noout >/dev/null || die "crl.pem is not valid"
echo "== copy ca.crt + crl.pem to $HOST:/etc/nginx/uha-ca/"
tar -C "$CA" -cf - ca.crt crl.pem | ssh "$HOST" 'set -e
rm -rf /tmp/uha-ca && mkdir /tmp/uha-ca && tar -C /tmp/uha-ca -xf - --no-same-owner
sudo install -d -o root -g root -m 755 /etc/nginx/uha-ca
sudo install -o root -g root -m 644 /tmp/uha-ca/ca.crt /tmp/uha-ca/crl.pem /etc/nginx/uha-ca/
rm -rf /tmp/uha-ca
if sudo /usr/sbin/nginx -t 2>/dev/null; then
    sudo systemctl reload nginx && echo "nginx reloaded"
else
    sudo /usr/sbin/nginx -t; echo "nginx -t FAILED: not reloaded"; exit 1
fi'
echo "CRL on the Pi: $(ca_openssl crl -in crl.pem -noout -lastupdate -nextupdate | tr '\n' ' ')"
