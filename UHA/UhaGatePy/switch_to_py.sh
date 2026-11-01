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
    systemctl enable --now uhagate6 || systemctl start uhagate5
}

systemctl enable --now uhagatepy || { restore_v6; exit 1; }   # Conflicts= stops uhagate6 / uhagate5
sleep 10
if ! systemctl is-active -q uhagatepy; then restore_v6; exit 1; fi
# Is it really working? uha.json is rewritten every second even without a serial link, so check the
# status file: link up, packets arriving, and the file itself current.
if ! python3 - <<'PY'
import json, sys, time
s = json.load(open("/home/pi/Web/uha_status.json"))
ok = s["Link"]["State"] == "up" and s["Counters"]["RxPackets"] > 0 and time.time() - s["UnixTime"] < 5
print("status: link", s["Link"]["State"], "packets", s["Counters"]["RxPackets"], "age", int(time.time() - s["UnixTime"]), "s")
sys.exit(0 if ok else 1)
PY
then restore_v6; exit 1; fi

systemctl disable uhagate6 || true
echo "uhagatepy: $(systemctl is-enabled uhagatepy) / $(systemctl is-active uhagatepy)"
echo "uhagate6:  $(systemctl is-enabled uhagate6 || true) / $(systemctl is-active uhagate6 || true)"
journalctl -u uhagatepy -n 12 --no-pager | cut -c1-200
