#!/bin/bash
set -uo pipefail
date
sysctl kern.boottime
echo 'Latitude panel boot loader: waiting briefly for an opted-in reservation.'
CLAIM_FILE=$(mktemp /private/var/tmp/latitude-panel-claim.XXXXXX) || exit 2
stream_child=''
snapshot_child=''
cleanup() {
  [ -z "$stream_child" ] || kill "$stream_child" 2>/dev/null
  [ -z "$snapshot_child" ] || kill "$snapshot_child" 2>/dev/null
  rm -f "$CLAIM_FILE"
}
trap cleanup EXIT
claim_ready=0
for ((attempt=0; attempt<10; attempt++)); do
  ioreg -r -c LatitudePanelClaim -l -w0 > "$CLAIM_FILE" 2>&1
  if grep -Fq 'class LatitudePanelClaim' "$CLAIM_FILE"; then claim_ready=1; break; fi
  sleep 1
done
if [ "$claim_ready" = 0 ]; then echo 'No panel reservation active; skipping framebuffer load.'; exit 0; fi
echo 'Panel reservation active; requesting framebuffer start and matching.'
# Capture before loading: fallback boots skip this block and preserve the failed attempt.
umask 077
LIVE=/Library/Logs/LatitudeDesktopLive.log
SNAP=/Library/Logs/LatitudeDesktopRegistry.log
[ ! -f "$LIVE" ] || mv -f "$LIVE" "$LIVE.previous"
[ ! -f "$SNAP" ] || mv -f "$SNAP" "$SNAP.previous"
{ date; sysctl kern.boottime; } > "$LIVE"
/usr/bin/log stream --style compact --level debug --timeout 120 --predicate 'process == "WindowServer" OR (process == "kernel" AND (eventMessage CONTAINS[c] "NMX" OR eventMessage CONTAINS[c] "Latitude" OR eventMessage CONTAINS[c] "drmn" OR eventMessage CONTAINS[c] "i915"))' >> "$LIVE" 2>&1 &
stream_child=$!
(
  for delay in 2 8 20; do
    sleep "$delay"
    date
    for class in IOFramebuffer NMXAccel LatitudePanelClaim; do ioreg -r -c "$class" -l -w0; done
    ps -axo pid,uid,pcpu,comm | awk 'NR==1 || /WindowServer/'
  done
) > "$SNAP" 2>&1 &
snapshot_child=$!
kmutil load --load-style start-and-match -b com.nullmoth.LatitudeMTLFB &
child=$!
( sleep 60; echo 'Framebuffer load exceeded 60 seconds.'; kill -TERM "$child" 2>/dev/null ) &
watcher=$!
wait "$child"; result=$?
kill "$watcher" 2>/dev/null; wait "$watcher" 2>/dev/null
echo "Framebuffer boot-load exit=$result"
date
# RunAtLoad is asynchronous; keeping this job alive preserves its diagnostic children.
wait "$stream_child"; stream_result=$?
echo "Desktop live-log exit=$stream_result"
stream_child=''
wait "$snapshot_child" 2>/dev/null
snapshot_child=''
exit "$result"
