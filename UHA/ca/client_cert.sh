#!/bin/bash
# Key + certificate for one device (CN = name, 3 years) and a .p12 to import into Android / Firefox.
# Usage: ./client_cert.sh <name> [--no-p12]
#   name: e.g. martin-pc, martin-telefon, zena-telefon
#   The .p12 export password is typed here (twice); it is passed to openssl in an environment variable and
#   never written to a file. --no-p12: only key + certificate (PEM), e.g. for a curl test.
# Output: <CA>/clients/<name>/<name>.key .crt [.p12]
source "$(dirname "$0")/common.sh"
[ $# -ge 1 ] || die "usage: $0 <name> [--no-p12]"
NAME="$1"
P12=1
[ "${2:-}" = "--no-p12" ] && P12=0
check_name "$NAME"
need_ca

DIR="clients/$NAME"
[ -e "$CA/$DIR" ] && die "$CA/$DIR exists already (revoke.sh $NAME first to issue a new one)"

if [ "$P12" = 1 ]; then
    read -r -s -p "Export password for $NAME.p12 (asked by the phone / Firefox on import): " PASS1; echo
    read -r -s -p "Again: " PASS2; echo
    [ "$PASS1" = "$PASS2" ] || die "the passwords differ"
    [ ${#PASS1} -ge 6 ] || die "use at least 6 characters"
fi

mkdir -p "$CA/$DIR"
ca_openssl genpkey -algorithm EC -pkeyopt ec_paramgen_curve:P-256 -out "$DIR/$NAME.key" 2>/dev/null
chmod 600 "$CA/$DIR/$NAME.key" 2>/dev/null || true
ca_openssl req -new -key "$DIR/$NAME.key" -subj "/O=UHA/CN=$NAME" -out "$DIR/$NAME.csr"
ca_openssl ca -batch -config openssl.cnf -extensions client_ext -in "$DIR/$NAME.csr" -out "$DIR/$NAME.crt" \
    -notext 2>&1 | grep -vE "^(Using configuration|Check that the request|Signature ok|The Subject|organizationName|commonName|Certificate is to be|Write out database|Data Base Updated)" || true
rm -f "$CA/$DIR/$NAME.csr"
[ -s "$CA/$DIR/$NAME.crt" ] || die "signing failed"

if [ "$P12" = 1 ]; then
    # PBE-SHA1-3DES: the format every Android / Firefox / Windows version imports (OpenSSL 3 would otherwise
    # use AES, which older Androids reject as "wrong password"). No CA certificate inside: the phone must not
    # install the home CA as a trusted authority for web sites.
    UHA_P12_PASS="$PASS1" ca_openssl pkcs12 -export -inkey "$DIR/$NAME.key" -in "$DIR/$NAME.crt" \
        -name "UHA $NAME" -keypbe PBE-SHA1-3DES -certpbe PBE-SHA1-3DES -macalg sha1 \
        -passout env:UHA_P12_PASS -out "$DIR/$NAME.p12"
    unset PASS1 PASS2
fi

echo "Certificate for $NAME:"
ca_openssl x509 -in "$DIR/$NAME.crt" -noout -subject -serial -enddate
ls -1 "$CA/$DIR"
