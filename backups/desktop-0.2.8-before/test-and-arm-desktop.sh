#!/bin/bash
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
[ "$(id -u)" = 0 ] && [ "$(uname -m)" = x86_64 ] || { echo 'Run with sudo on the Dell.' >&2; exit 2; }
echo 'Running the 1000-iteration IOKit/direct suite before enabling the next desktop boot.'
/bin/bash "$HERE/test-readback.sh" 1000
# test-readback fails closed on any case/pixel/backing/route failure. No boot
# opt-in is touched until its entire current-binary test has completed.
armed=0
cleanup() {
  if [ "$armed" != 1 ]; then
    nvram -d nullmoth-panel-once 2>/dev/null || true
    nvram -d nullmoth-gpu-once 2>/dev/null || true
  fi
}
trap cleanup EXIT
nvram nullmoth-gpu-once=1
nvram nullmoth-panel-once=1
armed=1
trap - EXIT
echo 'All 22 cases passed. The experimental accelerated desktop is enabled for ONE boot.'
echo 'Reboot through this USB. This script has not rebooted the laptop.'
echo 'If black/artifacting, power off and boot USB again without reinstalling, then collect-desktop.sh.'
echo 'If usable, run collect-desktop.sh after testing window movement and resizing.'
