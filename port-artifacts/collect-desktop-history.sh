#!/bin/bash
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
OUT="$HERE/Desktop/reports/failure-history-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$OUT" || exit 2
echo 'Collecting only the failed boot window: 15:50–15:56 on 18 October 2026.'
echo 'This search has a 90-second limit; partial output is retained.'
log show --start '2026-10-18 15:50:00' --end '2026-10-18 15:56:00' --style compact --predicate 'process == "kernel" OR process == "kernelmanagerd" OR process == "kernelmanager_helper" OR process == "WindowServer"' > "$OUT/failed-boot.txt" 2>&1 &
child=$!
( sleep 90; echo 'Search time limit reached; partial output retained.' >> "$OUT/status.txt"; kill -TERM "$child" 2>/dev/null ) &
watcher=$!
wait "$child"; result=$?
kill "$watcher" 2>/dev/null; wait "$watcher" 2>/dev/null
printf 'log search exit=%s\n' "$result" >> "$OUT/status.txt"
wc -lc "$OUT/failed-boot.txt" | tee -a "$OUT/status.txt"
printf 'Historical logs saved: %s\n' "$OUT"
