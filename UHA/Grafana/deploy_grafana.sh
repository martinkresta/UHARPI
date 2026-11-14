#!/bin/bash
# Run on the PC (Git Bash): install the UHA Grafana configuration on the Pi and restart Grafana.
#   - folder of the log database (root writes, group grafana reads)
#   - datasource "UHA log" (the SQLite file, read only) and the dashboards from dashboards/*.json
#   - systemd drop-in with the Grafana settings (127.0.0.1:3000, served under /grafana/, no anonymous access)
#   - with --nginx also the nginx location /grafana/ (LAN only), after a backup and `nginx -t`
# Grafana and the plugin themselves are installed once by hand (README.md).
# Usage: ./deploy_grafana.sh [--nginx]
#        UHA_LOG_DB=/var/lib/uhalog/other.db ./deploy_grafana.sh     (another database file, e.g. for a test)
set -euo pipefail

HOST="${UHA_HOST:-uharpi}"
DIR="$(cd "$(dirname "$0")" && pwd)"
LOG_DB="${UHA_LOG_DB:-/var/lib/uhalog/uha_log.db}"
NGINX=0
[ "${1:-}" = "--nginx" ] && NGINX=1

cd "$DIR"
echo "== copy to $HOST:/tmp/uha-grafana"
tar -cf - provisioning dashboards systemd nginx | ssh "$HOST" "rm -rf /tmp/uha-grafana && mkdir /tmp/uha-grafana && tar -C /tmp/uha-grafana -xf - --no-same-owner"

echo "== install on $HOST (database $LOG_DB, nginx $NGINX)"
ssh "$HOST" "LOG_DB='$LOG_DB' NGINX=$NGINX bash -s" <<'EOF'
set -euo pipefail
cd /tmp/uha-grafana
find . -type f -exec sed -i 's/\r$//' {} +

# database folder: UhaGatePy (root) writes, Grafana (group grafana) reads; setgid = new files get the group
sudo install -d -o root -g grafana -m 2770 "$(dirname "$LOG_DB")"

# datasource and dashboards
sed "s|@LOG_DB@|$LOG_DB|" provisioning/datasources/uhalog.yaml > uhalog.yaml
sudo install -o root -g grafana -m 640 uhalog.yaml /etc/grafana/provisioning/datasources/uhalog.yaml
sudo install -o root -g grafana -m 640 provisioning/dashboards/uha.yaml /etc/grafana/provisioning/dashboards/uha.yaml
sudo install -d -o root -g grafana -m 755 /var/lib/grafana/dashboards/uha
sudo install -o root -g grafana -m 644 dashboards/*.json /var/lib/grafana/dashboards/uha/

# Grafana settings (systemd drop-in), start at boot
sudo install -d /etc/systemd/system/grafana-server.service.d
sudo install -m 644 systemd/grafana-uha.conf /etc/systemd/system/grafana-server.service.d/uha.conf
sudo systemctl daemon-reload
sudo systemctl enable grafana-server >/dev/null 2>&1
sudo systemctl restart grafana-server
echo "grafana-server: $(systemctl is-enabled grafana-server) / $(systemctl is-active grafana-server)"

if [ "$NGINX" = 1 ]; then
    SITE=/etc/nginx/sites-available/default
    BACKUP="/home/pi/nginx-default.bak-$(date +%Y%m%d-%H%M%S)"
    sudo cp -p "$SITE" "$BACKUP"
    echo "nginx: backup of $SITE in $BACKUP"
    sudo install -m 644 nginx/uha-grafana-map.conf /etc/nginx/conf.d/uha-grafana-map.conf
    sudo install -m 644 nginx/uha-grafana.conf /etc/nginx/snippets/uha-grafana.conf
    sudo install -m 644 nginx/uha-grafana-lan.conf /etc/nginx/snippets/uha-grafana-lan.conf
    if ! sudo grep -q "include snippets/uha-grafana.conf;" "$SITE"; then
        # after the (only, not commented) "server_name _;" line of the default server
        sudo sed -i 's|^\(\s*\)server_name _;$|&\n\1include snippets/uha-grafana.conf;|' "$SITE"
    fi
    if sudo /usr/sbin/nginx -t; then
        sudo systemctl reload nginx
        echo "nginx: reloaded"
    else
        echo "nginx: config test FAILED - restoring $SITE and removing the new files"
        sudo cp -p "$BACKUP" "$SITE"
        sudo rm -f /etc/nginx/conf.d/uha-grafana-map.conf /etc/nginx/snippets/uha-grafana.conf \
                   /etc/nginx/snippets/uha-grafana-lan.conf
        sudo /usr/sbin/nginx -t
        exit 1
    fi
fi
rm -rf /tmp/uha-grafana
EOF
echo "== done: http://192.168.1.10/grafana/ (first login admin / admin, Grafana asks for a new password)"
