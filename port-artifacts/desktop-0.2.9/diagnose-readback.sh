#!/bin/bash
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
PROFILE=${1:-fresh-pools}
case "$PROFILE" in retained|fresh-pools|fresh-staging) ;; *) echo 'Use retained, fresh-pools or fresh-staging.' >&2; exit 2 ;; esac
[ "$(id -u)" = 0 ] || { echo 'Run with sudo on the Dell.' >&2; exit 2; }
echo "Diagnostic comparison: $PROFILE. Same three warmup tests, then 1000 padded frames."
/bin/bash "$HERE/test-readback.sh" 1000 "$PROFILE"
result=$?
echo "COMPARISON profile=$PROFILE exit=$result"
echo 'Desktop remains disabled. Bring back the USB report before choosing the next profile.'
exit "$result"
