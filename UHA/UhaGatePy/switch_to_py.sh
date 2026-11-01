#!/bin/bash
# Switch production to UhaGatePy (it also starts after a reboot).  Undo: sudo ./rollback_to_v6.sh
# If UhaGatePy does not come up with fresh data, UhaGate6 is restored automatically.
set -euo pipefail
[ "$(id -u)" = 0 ] || { echo "run with sudo"; exit 2; }
DIR=/home/pi/UhaGatePy
[ -f /lib/systemd/system/uhagatepy.service ] && [ -f "$DIR/uha_vars.yaml" ] \
    || { echo "UhaGatePy not installed, run deploy.sh first"; exit 1; }

"$DIR/tmpfs_links.sh" install            # the JSON files must be links to RAM (adds uha2.json)

restore_v6() {
    echo "UhaGatePy is not working - restoring UhaGate6"
    systemctl disable --now uhagatepy || true
    systemctl enable --now uhagate6
}

systemctl enable --now uhagatepy         # Conflicts= stops uhagate6 / uhagate5
sleep 8
if ! systemctl is-active -q uhagatepy; then restore_v6; exit 1; fi
# fresh data? uha.json is written every second, UnixTime must be current
AGE=$(python3 -c "import json,time; print(int(time.time()-json.load(open('/home/pi/Web/uha.json'))['UnixTime']))" || echo 999)
if [ "$AGE" -gt 5 ]; then echo "uha.json is $AGE s old"; restore_v6; exit 1; fi

systemctl disable uhagate6 || true
echo "uhagatepy: $(systemctl is-enabled uhagatepy) / $(systemctl is-active uhagatepy)"
echo "uhagate6:  $(systemctl is-enabled uhagate6 || true) / $(systemctl is-active uhagate6 || true)"
journalctl -u uhagatepy -n 12 --no-pager | cut -c1-200
