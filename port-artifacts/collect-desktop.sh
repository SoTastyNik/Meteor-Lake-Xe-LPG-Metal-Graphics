#!/bin/bash
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
LOG="$HERE/desktop-collect-$(date +%Y%m%d-%H%M%S).txt"
echo "LATITUDE DESKTOP COLLECT — using $HERE/Desktop/collect-runtime.sh"
echo "Full terminal output will be saved to $LOG"
/bin/bash "$HERE/Desktop/collect-runtime.sh" 2>&1 | tee "$LOG"
result=${PIPESTATUS[0]}
echo "DESKTOP COLLECT exit=$result" | tee -a "$LOG"
exit "$result"
