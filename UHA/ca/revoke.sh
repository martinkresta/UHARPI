#!/bin/bash
# Revoke the certificate of one device and write a new CRL. Then run ./deploy_ca.sh so nginx knows it.
# Usage: ./revoke.sh <name>
# The device folder is renamed to <name>.revoked-<date>, so the name can get a new certificate.
source "$(dirname "$0")/common.sh"
[ $# -eq 1 ] || die "usage: $0 <name>"
NAME="$1"
check_name "$NAME"
need_ca
DIR="clients/$NAME"
[ -f "$CA/$DIR/$NAME.crt" ] || die "no certificate $CA/$DIR/$NAME.crt"

ca_openssl ca -config openssl.cnf -revoke "$DIR/$NAME.crt" -crl_reason superseded
gen_crl
mv "$CA/$DIR" "$CA/$DIR.revoked-$(date +%Y%m%d-%H%M%S)"
echo "revoked $NAME. Now: ./deploy_ca.sh (until then nginx still accepts the certificate)"
