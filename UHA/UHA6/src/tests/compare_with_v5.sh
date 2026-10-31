#!/bin/bash
# Byte-compare uha.json / bms.json of the original UHA5 code with UhaGate6 for random values.
# Usage: compare_with_v5.sh [UHA5 source dir] [rounds]
#   repo:  UHA/UHA6/src/tests/compare_with_v5.sh            (uses UHA/UHA5)
#   Pi:    /home/pi/UHA6/src/tests/compare_with_v5.sh /home/pi/UHA5/src
set -euo pipefail

SRC="$(cd "$(dirname "$0")/.." && pwd)"
V5="${1:-$SRC/../../UHA5}"
ROUNDS="${2:-200}"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

# UHA5 writes to /home/pi/Web/...; redirect to the work folder (relative paths, run inside it)
for f in UHA.cpp UHA.h LOG.cpp LOG.h rpiserp.h; do
    tr -d '\r' < "$V5/$f" | sed -e 's#/home/pi/Web/#v5_#g' > "$WORK/$f"
done

cd "$WORK"
gcc -c -O1 -w -I"$SRC" "$SRC/cJSON.c" -o cJSON.o
g++ -std=c++17 -O1 -w -I"$WORK" -I"$SRC" \
    "$SRC/tests/compare_v5.cpp" UHA.cpp LOG.cpp "$SRC/outputs.cpp" cJSON.o -o compare_v5
./compare_v5 "$ROUNDS"
