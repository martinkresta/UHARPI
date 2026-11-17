#!/bin/bash
# Create the small UHA CA for the control web client certificates (UHA/ca/README.md).
# Usage: ./ca_init.sh [folder]        default folder: $UHA_CA_DIR or ~/uha-ca (outside the repo!)
# The CA key stays in <folder>/private/ca.key on this PC and never goes to the Pi or into the repo.
[ $# -ge 1 ] && export UHA_CA_DIR="$1"
source "$(dirname "$0")/common.sh"

[ -e "$CA/private/ca.key" ] && die "$CA already has a CA (delete the folder by hand to start over)"
case "$(mkdir -p "$CA" && cd "$CA" && pwd)/" in
    "$REPO_DIR"/*) die "the CA folder $CA is inside the repo - choose a folder outside it" ;;
esac
mkdir -p "$CA/private" "$CA/newcerts" "$CA/clients"
chmod 700 "$CA" "$CA/private" 2>/dev/null || true
: > "$CA/index.txt"
echo "unique_subject = no" > "$CA/index.txt.attr"     # a name can get a new cert after revoking the old one
echo 1000 > "$CA/serial"
echo 1000 > "$CA/crlnumber"

cat > "$CA/openssl.cnf" <<'EOF'
# UHA CA (created by UHARPI/UHA/ca/ca_init.sh). Paths are relative: openssl runs inside this folder.
[ ca ]
default_ca = uha_ca

[ uha_ca ]
dir              = .
database         = $dir/index.txt
new_certs_dir    = $dir/newcerts
certificate      = $dir/ca.crt
private_key      = $dir/private/ca.key
serial           = $dir/serial
crlnumber        = $dir/crlnumber
default_md       = sha256
default_days     = 1095            # client certificates: 3 years
# nginx refuses EVERY client certificate once the CRL has expired, so it is valid as long as the CA.
# revoke.sh writes a new one anyway.
default_crl_days = 3650
policy           = policy_any
copy_extensions  = none
unique_subject   = no

[ policy_any ]
organizationName = optional
commonName       = supplied

[ req ]
distinguished_name = req_dn
prompt             = no

[ req_dn ]
O  = UHA
CN = UHA home CA

[ ca_ext ]
basicConstraints     = critical, CA:true, pathlen:0
keyUsage             = critical, keyCertSign, cRLSign
subjectKeyIdentifier = hash

[ client_ext ]
basicConstraints       = critical, CA:false
keyUsage               = critical, digitalSignature
extendedKeyUsage       = clientAuth
subjectKeyIdentifier   = hash
authorityKeyIdentifier = keyid
EOF

ca_openssl genpkey -algorithm EC -pkeyopt ec_paramgen_curve:P-256 -out private/ca.key 2>/dev/null
chmod 600 "$CA/private/ca.key" 2>/dev/null || true
ca_openssl req -x509 -new -config openssl.cnf -extensions ca_ext -key private/ca.key -days 3650 \
    -subj "/O=UHA/CN=UHA home CA" -out ca.crt
gen_crl
echo "CA created in $CA:"
ca_openssl x509 -in ca.crt -noout -subject -dates
echo "Next: ./client_cert.sh <name>, then ./deploy_ca.sh"
