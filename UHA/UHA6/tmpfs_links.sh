#!/bin/bash
# Move the JSON outputs to RAM: /dev/shm/{uha,bms,uha_status}.json, with symlinks in /home/pi/Web.
# nginx and ftpupload.sh keep using /home/pi/Web/... (symlinks are followed). Works with UhaGate5
# too: it opens /home/pi/Web/uha.json for writing and so writes through the link into /dev/shm.
# After a reboot /dev/shm is empty and the links dangle until the gateway writes (within 1 s).
# Usage: sudo ./tmpfs_links.sh install | remove | status
set -euo pipefail

WEB=/home/pi/Web
SHM=/dev/shm
FILES="uha.json bms.json uha_status.json"

[ "$(id -u)" = 0 ] || { echo "run with sudo"; exit 2; }

case "${1:-status}" in
install)
    for f in $FILES; do
        if [ -L "$WEB/$f" ]; then echo "$f: already a link -> $(readlink "$WEB/$f")"; continue; fi
        # the tmpfs copy must be owned by root: with fs.protected_regular the kernel refuses
        # O_CREAT opens of files owned by someone else in the sticky /dev/shm, even for root
        if [ -f "$WEB/$f" ]; then
            install -o root -g root -m 644 "$WEB/$f" "$SHM/$f"
        elif [ ! -e "$SHM/$f" ]; then
            echo '{}' | install -o root -g root -m 644 /dev/stdin "$SHM/$f"
        fi
        ln -sfn "$SHM/$f" "$WEB/.$f.link"
        chown -h pi:pi "$WEB/.$f.link"
        mv -Tf "$WEB/.$f.link" "$WEB/$f"    # atomic replace of the file by the link
        echo "$f: -> $SHM/$f"
    done
    ;;
remove)
    for f in $FILES; do
        [ -L "$WEB/$f" ] || { echo "$f: not a link"; continue; }
        if [ -f "$SHM/$f" ]; then
            install -o pi -g pi -m 644 "$SHM/$f" "$WEB/.$f.copy"
            mv -Tf "$WEB/.$f.copy" "$WEB/$f"
        else
            rm -f "$WEB/$f"
        fi
        echo "$f: regular file again"
    done
    ;;
status)
    ls -la $(for f in $FILES; do echo "$WEB/$f"; done) 2>&1 || true
    ls -la $(for f in $FILES; do echo "$SHM/$f"; done) 2>&1 || true
    ;;
*)
    echo "Usage: $0 install | remove | status"; exit 2 ;;
esac
