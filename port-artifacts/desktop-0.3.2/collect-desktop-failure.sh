#!/bin/bash
set -uo pipefail
[ "$(uname -m)" = x86_64 ] || { echo 'Run this on the Dell, from its working fallback desktop.' >&2; exit 2; }
HERE="$(cd "$(dirname "$0")" && pwd)"
if [ "$#" -ge 1 ]; then
  START=$1
else
  boot_epoch=''
  for report in "$HERE"/Desktop/reports/readback-[0-9]*; do
    [ ! -f "$report/boot.txt" ] || boot_epoch=$(sed -n 's/.*sec = \([0-9]*\),.*/\1/p' "$report/boot.txt")
  done
  case "$boot_epoch" in ''|*[!0-9]*) boot_epoch=$(($(date +%s)-1200));; esac
  attempt_epoch=$(cat "$HERE/Desktop/reports/windowserver-attempt-start.txt" 2>/dev/null || true)
  case "$attempt_epoch" in ''|*[!0-9]*) ;; *) [ "$attempt_epoch" -le "$boot_epoch" ] || boot_epoch=$attempt_epoch;; esac
  START=$(date -r "$((boot_epoch-5))" '+%Y-%m-%d %H:%M:%S')
fi
END=${2:-$(date '+%Y-%m-%d %H:%M:%S')}
OUT="$HERE/Desktop/reports/failure-detail-$(date +%Y%m%d-%H%M%S)"
mkdir "$OUT" || exit 2
printf 'Reading retained logs from %s to %s. No GPU tests or system changes.\n' "$START" "$END"
printf 'This search has a 90-second limit. Partial output is retained.\n'
{ date; sysctl kern.boottime; sw_vers; } > "$OUT/collection-context.txt" 2>&1

# Preserve full crash reports before the bounded historical search.
mkdir -p "$OUT/WindowServer-crashes" || exit 2
crash_count=0
crash_failures=0
user_home=${HOME:-/var/root}
if [ -n "${SUDO_USER:-}" ] && [ "$SUDO_USER" != root ]; then
  resolved_home=$(/usr/bin/dscl . -read "/Users/$SUDO_USER" NFSHomeDirectory 2>/dev/null | sed 's/^NFSHomeDirectory: //')
  [ -z "$resolved_home" ] || user_home=$resolved_home
fi
for source in system user; do
  if [ "$source" = system ]; then crash_root=/Library/Logs/DiagnosticReports; else crash_root="$user_home/Library/Logs/DiagnosticReports"; fi
  [ -d "$crash_root" ] || continue
  mkdir -p "$OUT/WindowServer-crashes/$source" || exit 2
  while IFS= read -r -d '' crash; do
    if cp -p "$crash" "$OUT/WindowServer-crashes/$source/$(basename "$crash")" 2>> "$OUT/crash-copy-errors.txt"; then
      crash_count=$((crash_count+1))
      printf '%s\n' "$crash" >> "$OUT/crash-sources.txt"
    else
      crash_failures=$((crash_failures+1))
    fi
  done < <(find "$crash_root" -type f -name 'WindowServer*' -mtime -2 -print0 2>> "$OUT/crash-copy-errors.txt")
done
printf 'WindowServer crash reports from last 48 hours: copied=%s failed=%s\n' "$crash_count" "$crash_failures" | tee "$OUT/crash-status.txt"
if [ "$crash_count" = 0 ]; then
  echo 'No recent WindowServer crash report found; retained boot logs will still be collected.' | tee -a "$OUT/crash-status.txt"
fi

/usr/bin/log show --start "$START" --end "$END" --style compact --info --debug --predicate 'process == "kernel" OR process == "WindowServer" OR process == "ReportCrash" OR process == "kernelmanagerd" OR process == "kernelmanager_helper" OR eventMessage CONTAINS[c] "NVMTL" OR eventMessage CONTAINS[c] "NMX" OR eventMessage CONTAINS[c] "Latitude"' > "$OUT/failed-boot.txt" 2>&1 &
child=$!
( sleep 90; echo 'Search time limit reached; partial output retained.' >> "$OUT/status.txt"; kill -TERM "$child" 2>/dev/null; sleep 2; kill -KILL "$child" 2>/dev/null ) >/dev/null 2>&1 &
watcher=$!
wait "$child"; result=$?
kill "$watcher" 2>/dev/null
wait "$watcher" 2>/dev/null
printf 'log search exit=%s\n' "$result" >> "$OUT/status.txt"
wc -lc "$OUT/failed-boot.txt" | tee -a "$OUT/status.txt"
printf 'Saved: %s\n' "$OUT"
exit "$result"
