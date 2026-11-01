#!/bin/bash
# Test window: run UhaGatePy instead of the production gateway for N minutes (1..15),
# then ALWAYS bring the production gateway back (the one that was running when the window started).
# Usage: sudo /home/pi/UhaGatePy/test_window.sh [minutes]      (default 10)
#
# Safety:
#  - runs detached as the transient unit "uhapy-test", so an SSH disconnect cannot stop the restore
#  - the restore (stop uhagatepy, start production) runs from a trap on every exit of the script
#  - a backstop timer "uhapy-backstop" starts the production gateway 2 minutes after the window even
#    if the script itself was killed
# Results: /home/pi/UhaGatePy/test/<timestamp>/  (summary.txt, JSON snapshots, journal, memory samples)
set -u

MIN="${1:-10}"
[[ "$MIN" =~ ^[0-9]+$ ]] && (( MIN >= 1 && MIN <= 15 )) || { echo "minutes must be 1..15"; exit 2; }
[ "$(id -u)" = 0 ] || { echo "run with sudo"; exit 2; }

DIR=/home/pi/UhaGatePy
WEB=/home/pi/Web

if [ -z "${UHAPY_TW_INNER:-}" ]; then
    if systemctl is-active -q uhapy-test; then echo "a test window is already running"; exit 1; fi
    [ -f /lib/systemd/system/uhagatepy.service ] || { echo "uhagatepy.service not installed, run deploy.sh"; exit 1; }
    if grep -Eq '^\s*out-dir\s*=\s*/dev/shm' $DIR/uhagatepy.conf; then
        for f in uha.json bms.json uha2.json uha_status.json; do
            [ -L "$WEB/$f" ] || { echo "$WEB/$f is not a link to /dev/shm: run sudo $DIR/tmpfs_links.sh install"; exit 1; }
        done
    fi
    PROD=""
    for u in uhagate6 uhagate5; do systemctl is-active -q $u && PROD=$u && break; done
    [ -n "$PROD" ] || { echo "no production gateway is running - not starting a test"; exit 1; }
    systemd-run --quiet --unit=uhapy-test --collect --setenv=UHAPY_TW_INNER=1 --setenv=UHAPY_PROD=$PROD \
        /bin/bash "$(readlink -f "$0")" "$MIN"
    echo "Test window started for $MIN min (production $PROD is restored afterwards)."
    echo "Follow with: journalctl -f -u uhapy-test -u uhagatepy"
    exit 0
fi

PROD="${UHAPY_PROD:-uhagate6}"
OUT="$DIR/test/$(date +%Y%m%d-%H%M%S)"
mkdir -p "$OUT"
exec > >(tee -a "$OUT/summary.txt") 2>&1

restore() {
    trap - EXIT INT TERM
    echo "== restoring $PROD"
    systemctl stop uhagatepy
    systemctl start "$PROD"
    sleep 3
    systemctl stop uhapy-backstop.timer 2>/dev/null
    echo "$PROD: $(systemctl is-active "$PROD"), uhagatepy: $(systemctl is-active uhagatepy)"
    chown -R pi:pi "$DIR/test"
}
trap restore EXIT INT TERM

systemd-run --quiet --unit=uhapy-backstop --on-active="$((MIN + 2))min" /bin/systemctl start "$PROD"

echo "== test window $MIN min, production $PROD, $(date)"
for f in uha.json bms.json uha_status.json; do cp -L "$WEB/$f" "$OUT/prod_$f"; done
PROD_PID=$(systemctl show -p MainPID --value "$PROD")
ps -o pid,pcpu,rss,etime,cmd -p "$PROD_PID" > "$OUT/prod_ps.txt" 2>&1

START=$(date '+%Y-%m-%d %H:%M:%S')
systemctl start uhagatepy      # Conflicts= stops the production gateway
sleep 4
systemctl is-active -q uhagatepy || { echo "UhaGatePy did not start"; journalctl -u uhagatepy --since "$START" --no-pager | tail -20; exit 1; }
PID=$(systemctl show -p MainPID --value uhagatepy)
TICKS=$(getconf CLK_TCK)
cpu_ticks() { awk '{print $14 + $15}' "/proc/$PID/stat"; }

# atomic write check: parse all four files 20x/s during the whole window
python3 "$DIR/uhatest.py" reader $((MIN * 60 - 30)) "$WEB/uha.json" "$WEB/bms.json" "$WEB/uha2.json" "$WEB/uha_status.json" \
    > "$OUT/reader.txt" 2>&1 &
READER=$!

T0=$(date +%s); C0=$(cpu_ticks)
END=$((T0 + MIN * 60 - 10))
while [ "$(date +%s)" -lt "$END" ]; do
    systemctl is-active -q uhagatepy || { echo "UhaGatePy stopped unexpectedly"; break; }
    echo "$(date +%T) rss_kb=$(awk '/VmRSS/{print $2}' "/proc/$PID/status")" >> "$OUT/py_samples.txt"
    sleep 30
done
T1=$(date +%s); C1=$(cpu_ticks)

for f in uha.json bms.json uha2.json uha_status.json; do cp -L "$WEB/$f" "$OUT/py_$f"; done
journalctl -u uhagatepy --since "$START" --no-pager > "$OUT/py_journal.txt"

# production back first, evaluation afterwards. Wait only for the reader: a plain "wait" would
# also wait for the tee process substitution above and hang forever.
restore
wait "$READER"

echo "== results"
awk -v c=$((C1 - C0)) -v t=$((T1 - T0)) -v hz="$TICKS" 'BEGIN{printf "UhaGatePy CPU: %.2f %% of one core over %d s\n", 100*c/hz/t, t}'
echo "production before: $(tail -n 1 "$OUT/prod_ps.txt")"
echo "UhaGatePy RSS samples [kB]: $(awk '{print $2}' "$OUT/py_samples.txt" | sed 's/rss_kb=//' | tr '\n' ' ')"
echo "journal lines from UhaGatePy: $(wc -l < "$OUT/py_journal.txt")"
cat "$OUT/reader.txt"
python3 "$DIR/uhatest.py" compare "$OUT/prod_uha.json" "$OUT/py_uha.json"
python3 "$DIR/uhatest.py" compare "$OUT/prod_bms.json" "$OUT/py_bms.json"
python3 - "$OUT/py_uha_status.json" <<'PY'
import json, sys
s = json.load(open(sys.argv[1]))
print("link:", s["Link"])
print("counters:", s["Counters"])
print("comparison:", s["Comparison"])
print("nodes:", {n: (v["TunnelPackets"], v["TunnelAvgPerS"], v["LogMessages"]) for n, v in s["Nodes"].items()})
PY
echo "== journal (without the one-line RTC messages)"
grep -v "RTC sync sent" "$OUT/py_journal.txt" | cut -c1-260
echo "results in $OUT"
