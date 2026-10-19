#!/bin/bash
set -uo pipefail
[ "$(uname -m)" = x86_64 ] || { echo 'Run this on the Dell, from its working fallback desktop.' >&2; exit 2; }
HERE="$(cd "$(dirname "$0")" && pwd)"
START=${1:-'2026-10-18 18:38:00'}
END=${2:-'2026-10-18 18:39:50'}
OUT="$HERE/Desktop/reports/failure-detail-$(date +%Y%m%d-%H%M%S)"
mkdir "$OUT" || exit 2
printf 'Reading retained logs from %s to %s. No GPU tests or system changes.\n' "$START" "$END"
printf 'This search has a 90-second limit. Partial output is retained.\n'
{ date; sysctl kern.boottime; sw_vers; } > "$OUT/collection-context.txt" 2>&1
/usr/bin/log show --start "$START" --end "$END" --style compact --info --debug --predicate 'process == "kernel" OR process == "WindowServer" OR process == "kernelmanagerd" OR process == "kernelmanager_helper" OR eventMessage CONTAINS[c] "NVMTL" OR eventMessage CONTAINS[c] "NMX" OR eventMessage CONTAINS[c] "Latitude"' > "$OUT/failed-boot.txt" 2>&1 &
child=$!
( sleep 90; echo 'Search time limit reached; partial output retained.' >> "$OUT/status.txt"; kill -TERM "$child" 2>/dev/null; sleep 2; kill -KILL "$child" 2>/dev/null ) &
watcher=$!
wait "$child"; result=$?
kill "$watcher" 2>/dev/null
wait "$watcher" 2>/dev/null
printf 'log search exit=%s\n' "$result" >> "$OUT/status.txt"
wc -lc "$OUT/failed-boot.txt" | tee -a "$OUT/status.txt"
printf 'Saved: %s\n' "$OUT"
exit "$result"
