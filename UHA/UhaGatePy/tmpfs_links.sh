#!/bin/bash
# Keep the JSON outputs in RAM: /dev/shm/<file>, with a symlink in /home/pi/Web (nginx and the FTP upload
# keep using /home/pi/Web/<file>). Same as UHA/UHA6/tmpfs_links.sh, plus the new uha2.json.
# Files that already are links are left alone, so it is safe to run again.
# Usage: sudo ./tmpfs_links.sh install | remove | status
set -euo pipefail

WEB=/home/pi/Web
SHM=/dev/shm
FILES="uha.json bms.json uha2.json uha_status.json"

[ "$(id -u)" = 0 ] || { echo "run with sudo"; exit 2; }

case "${1:-status}" in
install)
    for f in $FILES; do
        if [ -L "$WEB/$f" ]; then echo "$f: already a link -> $(readlink "$WEB/$f")"; continue; fi
        # the tmpfs copy must be owned by root: with fs.protected_regular=2 the kernel refuses
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
