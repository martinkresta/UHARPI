# RPi hardening before HTTPS (step 3.0)

Repo: **UHARPI** (this brief, plus a short `UHA/hardening/README.md` with what was set and how to undo it).
Pi: `pi@192.168.1.10`, SSH alias `uharpi` (key `~/.ssh/id_ed25519_uharpi`), from Martin's PC in the LAN.

## Why now

Step 1c will publish `uha.mkresta.cz` (DNS AAAA + Let's Encrypt certificate → Certificate Transparency logs).
After that, bots will find and probe the Pi within hours. Today SSH (22) and nginx (80) are reachable from the
internet on the public IPv6. Goal: only what must be public is public, nothing guessable, automatic security updates.

## Working mode

Lightweight: check, change, verify, short report. Allowed in this task (exception to the usual Pi rules):
editing sshd config, adding a host firewall, installing `nftables` and `unattended-upgrades` via apt.
Not allowed: reboot, changes of network interfaces/addresses/DHCP, touching UHA5/UHA6, dist-upgrade, disabling
services other than the ones listed below without asking Martin. Never write passwords into files.

## ⚠️ Never lock yourself out — mandatory procedure

The Pi has no screen/keyboard access during this task. Losing SSH from the LAN = Martin must fix it by hand.

1. Keep **one SSH session open the whole time** (a second terminal). Never close it until the end.
2. Test every change from a **new** SSH session before relying on it. Existing sessions survive `reload`.
3. sshd: `sudo sshd -t` before every `sudo systemctl reload ssh`. Use reload, never restart/stop.
4. Before turning password login off: prove key login works with
   `ssh -o PasswordAuthentication=no -o PubkeyAuthentication=yes uharpi true`.
5. Firewall: **apply with an automatic undo**. Before loading the new ruleset, schedule a revert
   (e.g. `sudo systemd-run --on-active=5min --unit=fw-revert nft flush ruleset` or restoring the saved previous
   ruleset). Load the rules, open a new SSH session from the PC; only if it works, `systemctl stop fw-revert.timer`
   and make the rules persistent. If anything fails, wait 5 minutes and the old state is back.
6. If something goes wrong anyway: stop, do not try clever recovery, tell Martin exactly what state it is in.

## 1. Inventory (report, change nothing yet)

- OS: `cat /etc/os-release`, `uname -a`. Is this Debian/Raspberry Pi OS release still supported with security
  updates? If it is end-of-life: report and stop after part 1 (no upgrade in this task).
- Listening sockets: `sudo ss -tulpn` (expect sshd 22, nginx 80, Grafana 127.0.0.1:3000, others?).
- Existing firewall: `sudo nft list ruleset`, `sudo iptables -S`, `sudo ip6tables -S`, `ufw status` if present.
  Do not stack a second firewall on top of an existing one — if one exists, report and extend that one.
- sshd effective config: `sudo sshd -T | grep -Ei 'passwordauth|permitroot|pubkeyauth|listenaddress|port'`.
- Users with a login shell and with a password set (`sudo awk -F: '$2!~/^[!*]/' /etc/shadow` → names only, never
  print hashes). Is the `pi` password still a default? (Ask Martin, do not test it.)
- How does the alias `uharpi` connect (IPv4 192.168.1.10 or IPv6)? From `~/.ssh/config` on the PC.
- Public IPv6 address of the Pi (`ip -6 addr show scope global`): report whether it is EUI-64 (MAC-based,
  `ff:fe` in the middle), stable-privacy or other — this only tells how guessable it is.

## 2. SSH: key only, LAN only

- `PasswordAuthentication no`, `KbdInteractiveAuthentication no`, `PermitRootLogin no` (in a drop-in file
  `/etc/ssh/sshd_config.d/10-uha-hardening.conf`, so the main file stays untouched).
- LAN-only access is done by the firewall (part 3), not by `ListenAddress` (simpler to undo, no risk with
  changing addresses).
- Procedure from the lock-out section: `sshd -t`, reload, new session with key, keep the old session.

## 3. Host firewall (nftables)

Policy: **incoming drop by default**, outgoing allowed. Allow incoming:
- loopback; `ct state established,related`
- **ICMPv6** needed for IPv6 to work (neighbor discovery, router advertisements, echo) and ICMP echo for IPv4
- DHCPv6 client replies (udp 546) and DHCPv4 client replies (udp 68) if the Pi uses DHCP
- **TCP 22 only from the LAN**: `192.168.1.0/24` and IPv6 link-local `fe80::/10` (plus the LAN's IPv6 ULA prefix
  if one exists). Not from the global IPv6 prefix (it can change and is "the internet" from the Pi's view).
- TCP 80 and 443 from anywhere (443 for step 1c; nothing listens there yet).
- Grafana stays on `127.0.0.1:3000` (check), nothing else from outside.

Apply with the 5-minute automatic undo, test from the PC: new SSH session, web dashboard `http://192.168.1.10/`,
Grafana `/grafana/`. Then persist (`/etc/nftables.conf`, `systemctl enable nftables`) and keep the file also in
the repo (`UHA/hardening/nftables.conf`).

## 4. Automatic security updates

- `unattended-upgrades` with the Debian security origin, the Raspberry Pi archive and the Grafana repo
  (Grafana is internet-facing). `Automatic-Reboot "false"` (no reboots). Check with
  `sudo unattended-upgrade --dry-run -d` (tail of the output in the report).
- Do not run a full upgrade now; only report how many packages are pending (`apt list --upgradable | wc -l`).

## 5. Check from outside (Martin)

The agent cannot test from outside (the PC is in the LAN). Write Martin a 3-line instruction for his phone on
**mobile data, Wi-Fi off**: open an online IPv6 port scanner (any site that scans a given IPv6 address) with the
Pi's public IPv6, ports 22, 80, 443, 3000. Expected: 22 closed/filtered, 80 open, 443 closed (nothing listens
yet), 3000 closed/filtered.

## Not in this task (later)

UhaGatePy under its own user instead of root; nginx TLS config (step 1c); certificates for control (step 3).

## Report

Inventory results, what was changed (files, values), how to undo each change, test results from the PC, the
instruction for the outside check, pending updates count, anything that needs Martin's decision.
