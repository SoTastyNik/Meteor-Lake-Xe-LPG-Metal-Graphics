#!/bin/bash
# Collect a report after an accelerated (or failed, then fallback) boot.  sudo /bin/bash collect.sh [--test]
# --test also runs the Vulkan and Metal smoke tests (only meaningful when NMXGPU is attached).
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
[ "$(id -u)" = 0 ] || { echo 'Run with sudo.' >&2; exit 2; }
OUT="$HERE/reports/collect-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$OUT"
b() { local s=$1; shift; "$@" & local c=$!; ( sleep "$s"; kill -KILL "$c" 2>/dev/null ) >/dev/null 2>&1 & local w=$!; wait "$c"; local r=$?; kill "$w" 2>/dev/null; return $r; }
sw_vers > "$OUT/sw_vers.txt"; sysctl kern.boottime kern.bootargs > "$OUT/boot.txt"
b 20 kmutil showloaded > "$OUT/loaded-kexts.txt" 2>&1
for c in IOPCIDevice LatitudePanelClaim NMXIntelVGAFB IOFramebuffer NMXAccel IODisplay; do
  b 10 ioreg -r -c "$c" -l -w0 > "$OUT/ioreg-$c.txt" 2>&1
done
b 10 ioreg -r -n GFX0 -l -w0 > "$OUT/ioreg-GFX0.txt" 2>&1
for v in nullmoth-gpu-once nullmoth-panel-once nullmoth-gpu-attaching csr-active-config boot-args; do nvram "$v" >> "$OUT/nvram.txt" 2>&1; done
b 120 log show --last boot --style compact --predicate 'process == "kernel" AND (eventMessage CONTAINS[c] "NMX" OR eventMessage CONTAINS[c] "i915" OR eventMessage CONTAINS[c] "drm" OR eventMessage CONTAINS[c] "Latitude" OR eventMessage CONTAINS[c] "GuC" OR eventMessage CONTAINS[c] "HuC")' > "$OUT/kernel-gpu.log" 2>&1
b 120 log show --last boot --style compact --predicate 'process == "WindowServer"' > "$OUT/windowserver.log" 2>&1
for f in /Library/Logs/HuaweiPanelLoad.log /Library/Logs/LatitudeDesktopLive.log /Library/Logs/LatitudeDesktopRegistry.log \
         /Library/Logs/LatitudeWindowServerSample.txt /Library/Logs/LatitudeWindowServerSample.stderr.txt; do
  [ -f "$f" ] && cp -p "$f" "$OUT/" ; [ -f "$f.previous" ] && cp -p "$f.previous" "$OUT/"
done
find /Library/Logs/DiagnosticReports -newer /Library/NullMoth/huawei-last-backup.txt \( -name '*.panic' -o -name 'WindowServer*' -o -name 'Kernel*' \) \
  -exec cp -p {} "$OUT/" \; 2>/dev/null
if [ "${1:-}" = --test ]; then
  b 60 "$HERE/tools/latitude-i915-info" > "$OUT/test-i915-info.txt" 2>&1
  # bare i915 submission (no Mesa), then the driver state dump into the kernel log
  b 60 "$HERE/tools/latitude-gpu-probe" > "$OUT/test-gpu-probe.txt" 2>&1
  b 120 "$HERE/tools/latitude-vulkan-test" "$HERE/tools/check.spv" > "$OUT/test-vulkan.txt" 2>&1
  b 120 "$HERE/tools/latitude-metal-test" > "$OUT/test-metal.txt" 2>&1
  sleep 3
  b 120 log show --last 15m --style compact --predicate 'process == "kernel" AND (eventMessage CONTAINS "i915 dump" OR eventMessage CONTAINS "state dump" OR eventMessage CONTAINS[c] "i915" OR eventMessage CONTAINS "NMX")' > "$OUT/kernel-after-tests.log" 2>&1
fi
grep -hE 'com.nullmoth|AMFIPass|LatitudePanelClaim' "$OUT/loaded-kexts.txt" | awk '{print $6, $7}'
echo "Report: $OUT"
