#!/bin/bash
# Run on the PC (Git Bash): copy UhaGate6 to the Pi, build it there, run the tests and install
# uhagate6.service. Nothing is enabled or started; UhaGate5 keeps running.
# Usage: ./deploy.sh            (SSH host alias "uharpi", override with UHA_HOST=...)
set -euo pipefail

HOST="${UHA_HOST:-uharpi}"
DIR="$(cd "$(dirname "$0")" && pwd)"

echo "== copy to $HOST:/home/pi/UHA6"
ssh "$HOST" "mkdir -p /home/pi/UHA6"
tar -C "$DIR" --exclude=README.md --exclude=deploy.sh -cf - . | ssh "$HOST" "tar -C /home/pi/UHA6 -xf - --no-same-owner"

echo "== build and test on $HOST"
ssh "$HOST" "bash -s" <<'EOF'
set -euo pipefail
cd /home/pi/UHA6
find . -path ./build -prune -o -type f \( -name '*.sh' -o -name '*.py' -o -name '*.service' -o -name '*.conf' \) \
    -exec sed -i 's/\r$//' {} +
chmod +x ./*.sh ./*.py src/tests/*.sh

cmake -S src -B build -DCMAKE_BUILD_TYPE=Release > /dev/null
cmake --build build -j2
(cd build && ctest --output-on-failure)
src/tests/compare_with_v5.sh /home/pi/UHA5/src 100

# install replaces the file (new inode), safe while UhaGate6 is running
install -m 755 build/UhaGate6 /home/pi/UHA6/UhaGate6
sudo install -m 644 uhagate6.service /lib/systemd/system/uhagate6.service
sudo systemctl daemon-reload
echo "uhagate6: $(systemctl is-enabled uhagate6 2>/dev/null || true) / $(systemctl is-active uhagate6 || true)"
echo "uhagate5: $(systemctl is-enabled uhagate5 2>/dev/null || true) / $(systemctl is-active uhagate5 || true)"
EOF
echo "== deploy done (if uhagate6 is running, restart it to load the new binary)"
