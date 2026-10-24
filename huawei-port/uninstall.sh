#!/bin/bash
# Restore the state saved by install.sh.  sudo /bin/bash uninstall.sh [backup dir]
# Default: the last backup recorded in /Library/NullMoth/huawei-last-backup.txt.
set -uo pipefail
[ "$(id -u)" = 0 ] || { echo 'Run with sudo.' >&2; exit 2; }
BACKUP=${1:-$(cat /Library/NullMoth/huawei-last-backup.txt 2>/dev/null)}
[ -n "$BACKUP" ] && [ -f "$BACKUP/paths.txt" ] || { echo "No backup found: '$BACKUP'" >&2; exit 2; }
nvram -d nullmoth-gpu-once 2>/dev/null; nvram -d nullmoth-panel-once 2>/dev/null
fail=0
while read -r state p; do
  case "$state" in
    absent) rm -rf "$p" || fail=1 ;;
    saved) rm -rf "$p"; mkdir -p "$(dirname "$p")"; ditto "$BACKUP/original$p" "$p" || fail=1 ;;
  esac
done < "$BACKUP/paths.txt"
kcditto > /dev/null 2>&1 || fail=1
if [ "$fail" = 0 ]; then echo "Restored from $BACKUP; opt-ins cleared. Reboot to use the restored state."
else echo "Restore incomplete; inspect $BACKUP" >&2; exit 1; fi
