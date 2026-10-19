#!/bin/bash
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
LOG="$HERE/desktop-install-$(date +%Y%m%d-%H%M%S).txt"
echo "LATITUDE DESKTOP INSTALL — using $HERE/Desktop/install-runtime.sh"
echo "Full terminal output will be saved to $LOG"
/bin/bash "$HERE/Desktop/install-runtime.sh" 2>&1 | tee "$LOG"
result=${PIPESTATUS[0]}
echo "DESKTOP INSTALL exit=$result" | tee -a "$LOG"
exit "$result"
