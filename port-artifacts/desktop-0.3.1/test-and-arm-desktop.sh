#!/bin/bash
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
[ "$(uname -m)" = x86_64 ] && [ "$(id -u)" = 0 ] || { echo 'Run with sudo on the Intel Dell.'; exit 2; }
GATE=$(mktemp -t latitude-fresh-gate)
EXPECTED=$(mktemp -t latitude-fresh-expected)
armed=0
cleanup() {
  rm -f "$GATE" "$EXPECTED"
  if [ "$armed" = 1 ]; then nvram -d nullmoth-panel-once 2>/dev/null || true; nvram -d nullmoth-gpu-once 2>/dev/null || true; fi
}
trap cleanup EXIT
READBACK_GATE_FILE="$GATE" /bin/bash "$HERE/test-readback.sh" 1000 full
{ printf 'candidate=0.3.1 cases=22 iterations=1000 boot=%s\n' "$(sysctl -n kern.bootsessionuuid)"; shasum -a 256 /Library/GPUBundles/NVMTLDriver.bundle/Contents/MacOS/NVMTLDriver /Library/GPUBundles/nvmtl/libdrm.2.dylib /Library/Extensions/NMXGPU.kext/Contents/MacOS/NMXGPU; } > "$EXPECTED"
cmp -s "$GATE" "$EXPECTED" || { echo 'FAIL missing/stale hardware gate or changed installed binaries; desktop not armed.'; exit 2; }
for relative in NVMTLDriver.bundle/Contents/MacOS/NVMTLDriver nvmtl/libdrm.2.dylib; do
  cmp -s "$HERE/Library/GPUBundles/$relative" "/Library/GPUBundles/$relative" || { echo 'FAIL candidate binary changed during testing'; exit 2; }
done
cmp -s "$HERE/Library/Extensions/NMXGPU.kext/Contents/MacOS/NMXGPU" /Library/Extensions/NMXGPU.kext/Contents/MacOS/NMXGPU || { echo 'GPU kernel binary changed during testing'; exit 2; }
armed=1
nvram nullmoth-gpu-once=1
nvram nullmoth-panel-once=1
armed=0
echo 'Full 22-case gate passed. One desktop boot armed. Reboot through this USB when ready.'
echo 'If the display fails, power off and boot this USB again for the firmware-display fallback.'
