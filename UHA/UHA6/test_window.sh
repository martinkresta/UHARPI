#!/bin/bash
# Test window: run UhaGate6 instead of UhaGate5 for N minutes (1..15), then ALWAYS restore UhaGate5.
# Usage: sudo /home/pi/UHA6/test_window.sh [minutes]      (default 10)
#
# Safety:
#  - runs detached as transient unit "uha6-test", so an SSH disconnect cannot stop the restore
#  - restore (stop v6, start v5) runs from a trap on every exit of the script
#  - backstop timer "uha6-backstop" starts uhagate5 2 minutes after the window even if the
#    script itself was killed
# Results: /home/pi/UHA6/test/<timestamp>/  (summary.txt, JSON snapshots, journal, CPU samples)
set -u

MIN="${1:-10}"
[[ "$MIN" =~ ^[0-9]+$ ]] && (( MIN >= 1 && MIN <= 15 )) || { echo "minutes must be 1..15"; exit 2; }
[ "$(id -u)" = 0 ] || { echo "run with sudo"; exit 2; }

if [ -z "${UHA6_TW_INNER:-}" ]; then
    if systemctl is-active -q uha6-test; then echo "a test window is already running"; exit 1; fi
    [ -x /home/pi/UHA6/UhaGate6 ] || { echo "UhaGate6 not installed, run deploy.sh"; exit 1; }
    if grep -Eq '^\s*out-dir\s*=\s*/dev/shm' /home/pi/UHA6/uhagate6.conf && [ ! -L /home/pi/Web/uha.json ]; then
        echo "UhaGate6 writes to /dev/shm but /home/pi/Web/uha.json is not a link: run tmpfs_links.sh install"
        exit 1
    fi
    systemd-run --quiet --unit=uha6-test --collect --setenv=UHA6_TW_INNER=1 \
        /bin/bash "$(readlink -f "$0")" "$MIN"
    echo "Test window started for $MIN min. Follow with: journalctl -f -u uha6-test -u uhagate6"
    exit 0
fi

DIR=/home/pi/UHA6
OUT="$DIR/test/$(date +%Y%m%d-%H%M%S)"
WEB=/home/pi/Web
mkdir -p "$OUT"
exec > >(tee -a "$OUT/summary.txt") 2>&1

restore() {
    trap - EXIT INT TERM
    echo "== restoring UhaGate5"
    systemctl stop uhagate6
    systemctl start uhagate5
    sleep 3
    systemctl stop uha6-backstop.timer 2>/dev/null
    echo "uhagate5: $(systemctl is-active uhagate5), uhagate6: $(systemctl is-active uhagate6)"
    chown -R pi:pi "$DIR/test"
}
trap restore EXIT INT TERM

systemd-run --quiet --unit=uha6-backstop --on-active="$((MIN + 2))min" /bin/systemctl start uhagate5

echo "== test window $MIN min, $(date)"
cp -L "$WEB/uha.json" "$OUT/v5_uha.json"
cp -L "$WEB/bms.json" "$OUT/v5_bms.json"
V5PID=$(systemctl show -p MainPID --value uhagate5)
ps -o pid,pcpu,rss,etime,cmd -p "$V5PID" > "$OUT/v5_ps.txt" 2>&1

START=$(date '+%Y-%m-%d %H:%M:%S')
systemctl start uhagate6      # Conflicts= stops uhagate5
sleep 3
systemctl is-active -q uhagate6 || { echo "UhaGate6 did not start"; exit 1; }
PID=$(systemctl show -p MainPID --value uhagate6)
TICKS=$(getconf CLK_TCK)
cpu_ticks() { awk '{print $14 + $15}' "/proc/$PID/stat"; }

# atomic write check: parse the files 20x/s during the whole window
python3 "$DIR/uhatest.py" reader $((MIN * 60 - 30)) "$WEB/uha.json" "$WEB/bms.json" "$WEB/uha_status.json" \
    > "$OUT/reader.txt" 2>&1 &

T0=$(date +%s); C0=$(cpu_ticks)
END=$((T0 + MIN * 60 - 10))
while [ "$(date +%s)" -lt "$END" ]; do
    systemctl is-active -q uhagate6 || { echo "UhaGate6 stopped unexpectedly"; break; }
    echo "$(date +%T) rss_kb=$(awk '/VmRSS/{print $2}' "/proc/$PID/status")" >> "$OUT/v6_samples.txt"
    sleep 30
done
T1=$(date +%s); C1=$(cpu_ticks)

cp -L "$WEB/uha.json" "$OUT/v6_uha.json"
cp -L "$WEB/bms.json" "$OUT/v6_bms.json"
cp -L "$WEB/uha_status.json" "$OUT/v6_status.json"
wait
journalctl -u uhagate6 --since "$START" --no-pager > "$OUT/v6_journal.txt"

echo "== results"
awk -v c=$((C1 - C0)) -v t=$((T1 - T0)) -v hz="$TICKS" 'BEGIN{printf "UhaGate6 CPU: %.2f %% of one core over %d s\n", 100*c/hz/t, t}'
echo "UhaGate5 before: $(tail -n 1 "$OUT/v5_ps.txt")"
echo "UhaGate6 RSS samples: $(awk '{print $2}' "$OUT/v6_samples.txt" | tr '\n' ' ')"
echo "journal lines from UhaGate6: $(wc -l < "$OUT/v6_journal.txt")"
cat "$OUT/reader.txt"
python3 "$DIR/uhatest.py" compare "$OUT/v5_uha.json" "$OUT/v6_uha.json"
python3 "$DIR/uhatest.py" compare "$OUT/v5_bms.json" "$OUT/v6_bms.json"
python3 -c "import json,sys; s=json.load(open(sys.argv[1])); print('status:', s['Link'], s['Counters'])" "$OUT/v6_status.json"
echo "results in $OUT"
