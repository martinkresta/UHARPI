#!/bin/bash
# Return production to UhaGate5 (also after reboot). The tmpfs links can stay, UhaGate5 writes
# through them; to undo them as well: sudo ./tmpfs_links.sh remove
set -euo pipefail
[ "$(id -u)" = 0 ] || { echo "run with sudo"; exit 2; }

systemctl disable --now uhagate6 || true
systemctl enable --now uhagate5
sleep 3
echo "uhagate5: $(systemctl is-enabled uhagate5) / $(systemctl is-active uhagate5)"
echo "uhagate6: $(systemctl is-enabled uhagate6 2>/dev/null || true) / $(systemctl is-active uhagate6 || true)"
