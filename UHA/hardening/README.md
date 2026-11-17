# RPi hardening (step 3.0, 2026-11-17)

Before `uha.mkresta.cz` is published (step 1c). Brief: `tasks/rpi_hardening.md`.
Pi: Debian 12 bookworm (oldstable, security updates via Debian LTS until mid-2028), arm64, wlan0, NetworkManager.

## What was set

| Area | File on the Pi | Content |
|------|----------------|---------|
| SSH | `/etc/ssh/sshd_config.d/10-uha-hardening.conf` | `PasswordAuthentication no`, `KbdInteractiveAuthentication no`, `PermitRootLogin no` (main `sshd_config` untouched) |
| Firewall | `/etc/nftables.conf` (= `nftables.conf` here), `nftables.service` enabled | input policy drop, forward drop, output accept (details below) |
| Updates | `unattended-upgrades` package (apt), `/etc/apt/apt.conf.d/52uha-unattended-upgrades` (= file here) | Debian security, Raspberry Pi archive, Grafana repo; `Automatic-Reboot "false"` |

`/etc/apt/apt.conf.d/20auto-upgrades` (daily update + unattended-upgrade) was created by the package itself.
Backups on the Pi: `/root/nftables.conf.orig-debian` (Debian's empty default), `/root/nft-before-hardening.conf`
(the ruleset before: empty).

### Firewall (incoming)

- allowed: loopback; `established,related`; ICMPv6 (errors, PMTU, ND, RA, MLD, echo); ICMP echo + errors
- DHCP client replies: udp 67→68, udp 547→546 from `fe80::/10`
- mDNS udp 5353 (avahi, `raspberrypi.local`) from the LAN only (not in the brief, added so `.local` keeps working)
- TCP 22 from `192.168.1.0/24`, `fe80::/10`, ULA `fd6a:5888:3c1::/64` only (not from the global prefix)
- TCP 80, 443 from anywhere
- everything else dropped (counter: `sudo nft list chain inet filter input`)
- Grafana listens on `127.0.0.1:3000` only and is reached through nginx `/grafana/`

If the router's ULA prefix ever changes, edit `define LAN6` (IPv4 LAN still works for SSH meanwhile).

## Undo

```bash
# SSH (passwords back on):
sudo rm /etc/ssh/sshd_config.d/10-uha-hardening.conf && sudo sshd -t && sudo systemctl reload ssh

# Firewall off (now and at boot):
sudo nft flush ruleset
sudo systemctl disable nftables
sudo cp /root/nftables.conf.orig-debian /etc/nftables.conf     # optional

# Automatic updates off:
sudo rm /etc/apt/apt.conf.d/52uha-unattended-upgrades
sudo apt-get remove unattended-upgrades                         # or: set APT::Periodic::Unattended-Upgrade "0" in 20auto-upgrades
```

## Changing the firewall safely

```bash
scp UHA/hardening/nftables.conf uharpi:/tmp/nftables.uha.conf
ssh uharpi 'sudo nft -c -f /tmp/nftables.uha.conf'                       # syntax check
ssh uharpi 'sudo systemd-run --on-active=5min --unit=fw-revert nft -f /etc/nftables.conf && sudo nft -f /tmp/nftables.uha.conf'
ssh uharpi true                                                          # NEW session must work
ssh uharpi 'sudo systemctl stop fw-revert.timer && sudo install -m 755 /tmp/nftables.uha.conf /etc/nftables.conf'
```

If the new session fails: wait 5 minutes, the previous `/etc/nftables.conf` is loaded again.

## Logs

- unattended-upgrades: `/var/log/unattended-upgrades/`, `journalctl -u apt-daily-upgrade`
- No automatic reboot: kernel/firmware updates from the Raspberry Pi archive take effect only after a manual reboot
  (`/var/run/reboot-required` shows when one is needed).

## Not tested

A reboot (not allowed in this task). `nftables.service` is enabled and loads `/etc/nftables.conf` early at boot;
check after the next reboot: `sudo nft list ruleset | head`, SSH, dashboard.
