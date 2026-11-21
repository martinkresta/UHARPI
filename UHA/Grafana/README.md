# UHA Grafana — charts of the VARS2 log

Grafana OSS on the Pi shows the SQLite log written by UhaGatePy 0.3.0 (`db_log.py`, see `UHA/UhaGatePy/README.md`
"VARS2 DB log"). Task: `tasks/vars2_db_logging_grafana.md`. Monitoring only.

URL: **https://uha.mkresta.cz/grafana/** (public, since 2026-11-17, `UHA/nginx/README.md`).
`http://192.168.1.10/grafana/` still loads (LAN only), but login does not hold there (`cookie_secure`).
First login `admin` / `admin`, Grafana then asks for a new password (Martin sets it; never written to a file).

## Files

| Path | What | Installed to |
|------|------|--------------|
| `make_dashboards.py` | generates `dashboards/*.json`: panel lists + the SQL (read its header for the query rules) | — |
| `dashboards/energy.json` `packs.json` `temperatures.json` `states.json` | the dashboards (generated, commit them too) | `/var/lib/grafana/dashboards/uha/` |
| `provisioning/datasources/uhalog.yaml` | datasource "UHA log" (uid `uhalog`), the SQLite file, read only | `/etc/grafana/provisioning/datasources/` |
| `provisioning/dashboards/uha.yaml` | dashboard provider, folder "UHA" | `/etc/grafana/provisioning/dashboards/` |
| `systemd/grafana-uha.conf` | Grafana settings as `GF_*` variables (the packaged `grafana.ini` is untouched) | `/etc/systemd/system/grafana-server.service.d/uha.conf` |
| `nginx/uha-grafana.conf` | `location /grafana/` + websocket `/grafana/api/live/` | `/etc/nginx/snippets/`, included in `sites-available/default` |
| `nginx/uha-grafana-lan.conf` | allow LAN (192.168.1.0/24, IPv6 ULA / link-local), deny the rest | `/etc/nginx/snippets/` |
| `nginx/uha-grafana-map.conf` | `$connection_upgrade` map | `/etc/nginx/conf.d/` |
| `deploy_grafana.sh` | PC (Git Bash): copies and installs all of the above, restarts Grafana; `--nginx` also nginx | — |

Change a dashboard: edit `make_dashboards.py`, `python make_dashboards.py`, `./deploy_grafana.sh`. A dashboard
changed in the UI cannot be saved over the provisioned file (use "Save as" for experiments).

## Settings (systemd drop-in)

Listen `127.0.0.1:3000` only (reached through nginx), `domain = uha.mkresta.cz`,
`root_url = https://uha.mkresta.cz/grafana/`, `cookie_secure = true`, brute-force login protection on (default),
`serve_from_sub_path = true`, anonymous access off, sign-up off, no usage reporting / update checks / news feed,
no automatic download of "preinstalled" plugins, unused bundled datasources disabled (`GF_PLUGINS_DISABLE_PLUGINS`:
each one started a backend process, ~190 MB RAM together). Grafana 13.3.1 + `frser-sqlite-datasource` 4.0.6 then
use ~400 MB RSS; the Pi keeps ~520 MB available.

The database is `/var/lib/uhalog/uha_log.db`, not under `/home`: the packaged Grafana unit has `ProtectHome=true`.
Folder `root:grafana 2770` (setgid: new files get the group), files 0660 — Grafana needs write access to the `-shm`
file of a WAL database even when it only reads. The plugin opens it with `mode=ro` and adds `query_only` itself.
WAL readers do not block the writer (checked: long read transactions next to the running logger).

## Dashboards

Folder **UHA**, linked to each other (tag `uha`). Time zone Europe/Prague. Grafana is English; legends use the
English short names of `WS/i18n/texts.json` (no YAML names). Task `tasks/grafana_energy_views.md`.

1. **UHA Energy** — power (solar / battery / load), SOC (total thick + packs), energy per day (bar chart:
   production, consumption, balance hidden by default), loads per day (stacked: the consumption breakdown of
   `LOAD_CATEGORIES` + "Other" = consumption − categories, adds up to the consumption bar), inverters power
   (overload view, never summed with the loads), loads power (stacked area, same categories), storages power with
   the **LVDC link estimate** `(BMS1_CURRENT_A − AXPERT_BAT_CURRENT_A) × STRG2_VOLTAGE_V + POW_WS_HEATING_W / 0.9`
   (+ = house → workshop; the Victron term is needed, checked on data 2026-11-21).
2. **UHA Packs** — 16 cell voltages per pack (legend = cell number), pack voltage / current / SOC.
3. **UHA Temperatures** — indoor & outside, tank layers, boiler, heating circuits, recuperation, CO₂, electronics, wind.
4. **UHA States** (table `events`) — rows by category (YAML command `category:`, `STATE_CATEGORY` for the rest):
   lights (+ light on-time per day without the exterior outputs and the stair steps), blinds, inverters, heating
   (3 pumps, boiler, setpoints, TECHM panels), loads / relays, ventilation. Enum timelines have a colour legend.
   Invalid is shown as "invalid" (the query writes it as -1).

Which table a panel reads: raw up to 2 days, agg_15min beyond, one value per day beyond 60 days (CET day for
averages, exact local day for the energy bars). Speed on the Pi 3 with a full-size database (3 days raw + 1 year
agg, 207 MB): one panel of 16 cells takes ~1.3 s for 1 day, ~0.6 s for 30 days, ~4 s for 1 year.
Energy bars come from agg_15min, so the current unfinished 15 min are not in them yet.

## Install (done 2026-11-14)

```bash
# Pi: Grafana apt repo (arm64), packages, plugin
sudo mkdir -p /etc/apt/keyrings
wget -q -O - https://apt.grafana.com/gpg.key | gpg --dearmor | sudo tee /etc/apt/keyrings/grafana.gpg > /dev/null
echo "deb [signed-by=/etc/apt/keyrings/grafana.gpg] https://apt.grafana.com stable main" | sudo tee /etc/apt/sources.list.d/grafana.list
sudo apt-get update && sudo apt-get install -y grafana sqlite3
sudo grafana cli plugins install frser-sqlite-datasource
sudo chown -R grafana:grafana /var/lib/grafana/plugins

# PC (Git Bash)
./UHA/Grafana/deploy_grafana.sh --nginx
```

`sqlite3` pulled in a patch update of `libsqlite3-0` (3.40.1-2+deb12u1 -> deb12u2, Debian security update), nothing
else. nginx backup before the change: `/home/pi/nginx-default.bak-<date>`; the only change in
`sites-available/default` is the line `include snippets/uha-grafana.conf;` after `server_name _;`.

## Phase C (HTTPS) — done 2026-11-17

Done as a separate site `uha-public` (see `UHA/nginx/README.md`): `https://uha.mkresta.cz/grafana/` uses
`snippets/uha-grafana-public.conf` (no LAN restriction). The plain-HTTP default site keeps `uha-grafana.conf` with
the LAN-only include, so `deploy_grafana.sh --nginx` still applies to the LAN site only.
