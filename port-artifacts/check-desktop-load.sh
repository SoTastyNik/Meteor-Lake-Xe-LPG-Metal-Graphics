#!/bin/bash
set -uo pipefail
[ "$(id -u)" = 0 ] || { echo 'Run with sudo on the Dell.'; exit 2; }
[ "$(uname -m)" = x86_64 ] || { echo 'Run on the Intel Dell.'; exit 2; }
HERE="$(cd "$(dirname "$0")" && pwd)"
OUT="$HERE/Desktop/reports/load-check-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$OUT" || exit 2
ioreg -r -c LatitudePanelClaim -l -w0 > "$OUT/panel-claim-before.txt" 2>&1
if grep -Fq 'class LatitudePanelClaim' "$OUT/panel-claim-before.txt"; then echo 'Panel claim is active; load-only check cancelled.'; exit 2; fi
kmutil load --help > "$OUT/kmutil-load-help.txt" 2>&1
if ! grep -q -- '--load-style' "$OUT/kmutil-load-help.txt"; then echo 'This kmutil lacks the required start-only option; no load attempted.'; exit 2; fi
kmutil showloaded > "$OUT/loaded-before.txt" 2>&1
cp /Library/Extensions/LatitudeMTLFB.kext/Contents/Info.plist "$OUT/installed-framebuffer-Info.plist" 2>/dev/null || true
echo 'Checking framebuffer code loading only. Panel reservation stays disabled; no reboot or hardware matching requested.'
kmutil load --load-style start-only -b com.nullmoth.LatitudeMTLFB > "$OUT/framebuffer-load.txt" 2>&1 &
child=$!
( sleep 90; echo 'Load check reached 90-second limit.' >> "$OUT/status.txt"; kill -TERM "$child" 2>/dev/null ) &
watcher=$!
wait "$child"; result=$?
kill "$watcher" 2>/dev/null; wait "$watcher" 2>/dev/null
printf 'kmutil start-only exit=%s\n' "$result" | tee -a "$OUT/status.txt"
cat "$OUT/framebuffer-load.txt"
kmutil showloaded > "$OUT/loaded-after.txt" 2>&1
log show --last 3m --style compact --predicate 'process == "kernelmanagerd" OR process == "kernelmanager_helper" OR (process == "kernel" AND eventMessage CONTAINS[c] "Latitude")' > "$OUT/load-log.txt" 2>&1
printf 'Load-only check saved: %s\n' "$OUT"
exit "$result"
