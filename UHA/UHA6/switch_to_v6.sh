#!/bin/bash
# Switch production to UhaGate6 (also after reboot). Undo: sudo ./rollback_to_v5.sh
# If UhaGate6 does not come up, UhaGate5 is restored automatically.
set -euo pipefail
[ "$(id -u)" = 0 ] || { echo "run with sudo"; exit 2; }
[ -x /home/pi/UHA6/UhaGate6 ] && [ -f /lib/systemd/system/uhagate6.service ] \
    || { echo "UhaGate6 not installed, run deploy.sh first"; exit 1; }

systemctl enable --now uhagate6     # Conflicts= stops uhagate5
sleep 5
if ! systemctl is-active -q uhagate6; then
    echo "UhaGate6 did not start - restoring UhaGate5"
    systemctl disable --now uhagate6 || true
    systemctl enable --now uhagate5
    exit 1
fi
systemctl disable uhagate5
echo "uhagate6: $(systemctl is-enabled uhagate6) / $(systemctl is-active uhagate6)"
echo "uhagate5: $(systemctl is-enabled uhagate5 || true) / $(systemctl is-active uhagate5 || true)"
journalctl -u uhagate6 -n 10 --no-pager
