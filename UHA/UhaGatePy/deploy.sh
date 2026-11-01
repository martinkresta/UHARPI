#!/bin/bash
# Run on the PC (Git Bash): copy UhaGatePy to the Pi, run the unit tests there and install uhagatepy.service.
# Nothing is enabled or started and the running gateway is not touched.
# Usage: ./deploy.sh            (SSH host alias "uharpi", override with UHA_HOST=...)
#        UHA_VARS_YAML=<path to uha_vars.yaml> ./deploy.sh
set -euo pipefail

HOST="${UHA_HOST:-uharpi}"
DIR="$(cd "$(dirname "$0")" && pwd)"
YAML="${UHA_VARS_YAML:-/c/Martin/GIT/UHA_FW/UHA_COMMON/VarDefs/uha_vars.yaml}"
[ -f "$YAML" ] || { echo "uha_vars.yaml not found: $YAML (set UHA_VARS_YAML)"; exit 1; }

echo "== copy to $HOST:/home/pi/UhaGatePy"
ssh "$HOST" "mkdir -p /home/pi/UhaGatePy"
tar -C "$DIR" --exclude=__pycache__ --exclude=README.md --exclude=deploy.sh \
    -cf - uhagatepy tests tools ./*.sh ./*.py ./*.service ./*.conf | ssh "$HOST" "tar -C /home/pi/UhaGatePy -xf - --no-same-owner"
cat "$YAML" | ssh "$HOST" "cat > /home/pi/UhaGatePy/uha_vars.yaml"

echo "== test and install on $HOST"
ssh "$HOST" "bash -s" <<'EOF'
set -euo pipefail
cd /home/pi/UhaGatePy
find . -type f \( -name '*.sh' -o -name '*.py' -o -name '*.service' -o -name '*.conf' -o -name '*.yaml' \) \
    -exec sed -i 's/\r$//' {} +
chmod +x ./*.sh tools/*.py

# the golden test compares with the UhaGate6 builders (needs /home/pi/UHA6/src and g++)
UHA_VARS_YAML=/home/pi/UhaGatePy/uha_vars.yaml PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -t . 2>&1 | tail -5

sudo install -m 644 uhagatepy.service /lib/systemd/system/uhagatepy.service
sudo systemctl daemon-reload
for u in uhagate5 uhagate6 uhagatepy; do
    echo "$u: $(systemctl is-enabled $u 2>/dev/null || true) / $(systemctl is-active $u || true)"
done
EOF
echo "== deploy done (if uhagatepy is running, restart it to load the new code)"
