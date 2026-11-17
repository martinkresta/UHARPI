# Shared by the UHA CA scripts (sourced). The CA lives OUTSIDE the repo: $UHA_CA_DIR, default ~/uha-ca.
set -euo pipefail
export MSYS_NO_PATHCONV=1                      # Git Bash: do not turn "/O=UHA/CN=x" into a Windows path
CA="${UHA_CA_DIR:-$HOME/uha-ca}"
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

die() { echo "ERROR: $*" >&2; exit 1; }

need_ca() {
    [ -f "$CA/ca.crt" ] && [ -f "$CA/private/ca.key" ] && [ -f "$CA/openssl.cnf" ] \
        || die "no CA in $CA (run ca_init.sh first, or set UHA_CA_DIR)"
    case "$(cd "$CA" && pwd)/" in
        "$REPO_DIR"/*) die "the CA folder $CA is inside the repo - keys must never be there" ;;
    esac
}

# the CA's own openssl calls run inside the CA folder (relative paths in openssl.cnf)
ca_openssl() { (cd "$CA" && openssl "$@"); }

check_name() {
    [[ "$1" =~ ^[a-z0-9][a-z0-9-]{0,62}$ ]] || die "name '$1': use lower-case letters, digits and '-' (e.g. martin-telefon)"
}

gen_crl() {
    ca_openssl ca -batch -config openssl.cnf -gencrl -out crl.pem
    echo "CRL: $CA/crl.pem ($(ca_openssl crl -in crl.pem -noout -nextupdate))"
}
