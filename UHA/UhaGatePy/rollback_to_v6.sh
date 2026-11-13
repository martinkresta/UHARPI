#!/bin/bash
# Return production to UhaGate6 (also after a reboot). The tmpfs links can stay, UhaGate6 writes through them.
set -euo pipefail
[ "$(id -u)" = 0 ] || { echo "run with sudo"; exit 2; }

# UhaGate6 reads only the old 0x221 format. Once the nodes send only VARS2 (migration step 6b) it gets no data.
echo "WARNING: UhaGate6 reads only the old 0x221 format. If the nodes no longer send it (VARS2 only),"
echo "         the dashboard will show no live data (all values 0 / frozen)."

systemctl disable --now uhagatepy || true
if ! systemctl enable --now uhagate6; then
    echo "uhagate6 did not start - starting uhagate5"
    systemctl start uhagate5
fi
sleep 3
echo "uhagate6:  $(systemctl is-enabled uhagate6) / $(systemctl is-active uhagate6)"
echo "uhagatepy: $(systemctl is-enabled uhagatepy 2>/dev/null || true) / $(systemctl is-active uhagatepy || true)"
