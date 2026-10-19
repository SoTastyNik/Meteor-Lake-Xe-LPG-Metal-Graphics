#!/bin/bash
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
[ "$(uname -m)" = x86_64 ] || { echo 'Run on the Dell.' >&2; exit 2; }
OUT="$HERE/reports/$(date +%Y%m%d-%H%M%S)"
mkdir -p "$OUT" || exit 2
sw_vers > "$OUT/macos.txt" 2>&1
sysctl machdep.cpu.brand_string >> "$OUT/macos.txt" 2>&1
csrutil status > "$OUT/sip.txt" 2>&1
kmutil showloaded > "$OUT/loaded-kexts.txt" 2>&1
for class in NMXGPU NMXAccel NMXGPUFB LatitudeMTLProbe; do
  ioreg -r -c "$class" -l -w0 > "$OUT/$class-ioreg.txt" 2>&1
done
ioreg -r -n GFX0 -l -w0 > "$OUT/GFX0-ioreg.txt" 2>&1
stat -f '%Sp %Su:%Sg %N' /Library/GPUBundles /Library/GPUBundles/nvmtl /Library/GPUBundles/nvmtl/libvulkan_intel.dylib /Library/GPUBundles/nvmtl/libdrm.2.dylib /Library/GPUBundles/NVMTLDriver.bundle > "$OUT/runtime-permissions.txt" 2>&1
for marker in nullmoth-gpu-once nullmoth-gpu-attaching; do nvram "$marker"; done > "$OUT/gpu-boot-markers.txt" 2>&1
system_profiler SPDisplaysDataType > "$OUT/displays.txt" 2>&1
dmesg > "$OUT/dmesg.txt" 2>&1
log show --last boot --style compact --predicate 'eventMessage CONTAINS[c] "NullMoth" OR eventMessage CONTAINS[c] "NMX" OR eventMessage CONTAINS[c] "i915" OR eventMessage CONTAINS[c] "drmn" OR eventMessage CONTAINS[c] "GuC"' > "$OUT/driver-log.txt" 2>&1
run_bounded() {
  local name=$1; shift
  "$@" > "$OUT/$name.txt" 2>&1 &
  local child=$!
  ( sleep 45; echo 'TIMEOUT after 45 seconds' >> "$OUT/$name.txt"; kill -TERM "$child" 2>/dev/null; sleep 2; kill -KILL "$child" 2>/dev/null ) &
  local watcher=$!
  wait "$child"; local result=$?
  kill "$watcher" 2>/dev/null; wait "$watcher" 2>/dev/null
  printf '%s exit=%s\n' "$name" "$result" | tee -a "$OUT/results.txt"
}
# Run GPU clients as the logged-in user if the collector was started with sudo.
USERCMD=()
if [ "$(id -u)" = 0 ] && [ -n "${SUDO_USER:-}" ] && [ "$SUDO_USER" != root ]; then USERCMD=(sudo -u "$SUDO_USER"); fi
run_bounded i915-info "${USERCMD[@]}" "$HERE/tools/latitude-i915-info"
run_bounded vulkan "${USERCMD[@]}" "$HERE/tools/latitude-vulkan-test" "$HERE/tools/check.spv"
if grep -q '^PASS Vulkan hardware execution:' "$OUT/vulkan.txt"; then
  run_bounded metal "${USERCMD[@]}" env NVMTL_ENABLE=1 "$HERE/tools/latitude-metal-test"
else
  echo 'Metal test skipped until Vulkan GPU output is correct.' | tee "$OUT/metal.txt"
fi
if [ -f /Library/NullMoth/latitude5350-last-backup.txt ]; then
  backup=$(cat /Library/NullMoth/latitude5350-last-backup.txt)
  case "$backup" in /Library/NullMoth/latitude5350-backups/*)
    for file in kmutil-preflight.log kmutil-installed.log kcditto.log; do
      [ ! -f "$backup/$file" ] || cp "$backup/$file" "$OUT/$file"
    done ;;
  esac
fi
cat "$OUT/vulkan.txt" "$OUT/metal.txt"
printf 'Reports saved on USB: %s\n' "$OUT"
