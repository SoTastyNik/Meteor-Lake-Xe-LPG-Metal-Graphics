#!/bin/bash
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
[ "$(uname -m)" = x86_64 ] || { echo 'Run on the Intel Dell.'; exit 2; }
COUNT=${1:-100}
case "$COUNT" in ''|*[!0-9]*) echo 'Iteration count must be 1..10000'; exit 2 ;; esac
[ "$COUNT" -ge 1 ] && [ "$COUNT" -le 10000 ] || exit 2
OUT="$HERE/reports/readback-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$OUT"
# Refuse this suite if the custom framebuffer owns the physical display.
ioreg -r -c LatitudePanelClaim -l -w0 > "$OUT/panel-before.txt"
if grep -q 'LatitudePanelClaim' "$OUT/panel-before.txt"; then
  echo "Custom panel is present. Reinstall in readback-only mode and reboot first. Report: $OUT"; exit 2
fi
sysctl kern.boottime > "$OUT/boot.txt"
kmutil showloaded > "$OUT/loaded-kexts.txt" 2>&1
USERCMD=()
if [ "$(id -u)" = 0 ] && [ -n "${SUDO_USER:-}" ] && [ "$SUDO_USER" != root ]; then USERCMD=(sudo -u "$SUDO_USER"); fi
cp /Library/GPUBundles/NVMTLDriver.bundle/Contents/Info.plist "$OUT/plugin.plist" || exit 2
version=$(/usr/libexec/PlistBuddy -c 'Print :CFBundleVersion' "$OUT/plugin.plist")
[ "$version" = 0.2.7 ] || { echo "Expected plugin 0.2.7, found $version"; exit 2; }
shasum -a 256 /Library/GPUBundles/NVMTLDriver.bundle/Contents/MacOS/NVMTLDriver /Library/GPUBundles/nvmtl/libdrm.2.dylib > "$OUT/binaries.txt"
for relative in NVMTLDriver.bundle/Contents/MacOS/NVMTLDriver nvmtl/libdrm.2.dylib; do
  cmp -s "$HERE/Library/GPUBundles/$relative" "/Library/GPUBundles/$relative" || { echo "Installed binary differs from this candidate: $relative"; exit 2; }
done
echo 'Waiting up to 75 seconds for the Metal plugin registration...'
ready=0
for ((attempt=0; attempt<=37; attempt++)); do
  ioreg -r -c NMXAccel -l -w0 > "$OUT/accelerator-before.txt"
  if grep -Eq '"MetalPluginName" = "([^"[:space:]]*/)?NVMTLDriver"' "$OUT/accelerator-before.txt"; then ready=1; break; fi
  [ "$attempt" = 37 ] || sleep 2
done
[ "$ready" = 1 ] || { echo 'NMXAccel Metal plugin did not register. No GPU tests run.'; exit 2; }
echo "Readback suite: $COUNT iterations per worker/case. Progress every 50 frames. Logs: $OUT"
echo 'Each case stops after at most 600 seconds. The suite stops on the first failure.'
run_case() {
  local name=$1 route=$2 pools=$3 stages=$4; shift 4
  local log="$OUT/$name.txt"
  echo "START $name"
  local envargs=(NVMTL_ENABLE=1 NMX_DRM_TEST_TRANSPORT="$route" NVMTL_POOL_REUSE="$pools" NVMTL_READBACK_TRACE=1)
  [ "$stages" = retained ] || envargs+=(NVMTL_READBACK_STAGE_FRESH=1)
  "${USERCMD[@]}" /usr/bin/env -u NVMTL_READBACK_STAGE_FRESH -u NVMTL_NO_POOL_REUSE -u INTEL_DEBUG -u VK_INSTANCE_LAYERS -u NVMTL_ASYNC_TEX_UPLOAD "${envargs[@]}" "$HERE/tools/latitude-readback-test" --iterations "$COUNT" "$@" > "$log" 2>&1 &
  local child=$!
  ( sleep 600; echo 'FAIL watchdog: case exceeded 600 seconds' >> "$log"; kill -TERM "$child" 2>/dev/null; sleep 2; kill -KILL "$child" 2>/dev/null ) &
  local watcher=$!
  wait "$child"; local result=$?
  kill "$watcher" 2>/dev/null; wait "$watcher" 2>/dev/null
  tail -n 5 "$log"
  if [ "$result" = 0 ]; then
    grep -q '^PASS exact readback:' "$log" || result=1
    if [ "$route" = direct ]; then
      grep -Eq 'NMX transport counters: requested=direct direct=[1-9][0-9]* iokit=0$' "$log" || result=1
    else
      grep -Eq 'NMX transport counters: requested=iokit direct=0 iokit=[1-9][0-9]*$' "$log" || result=1
    fi
  fi
  case "$name" in *-iosurface|*-bgra-surface)
    grep -q '^PASS IOSurface backing:' "$log" || result=1 ;;
  esac
  echo "$name exit=$result" | tee -a "$OUT/results.txt"
  return "$result"
}
result=0
for route in iokit direct; do
  echo "Checking $route device discovery before Metal enumeration..."
  "${USERCMD[@]}" env NMX_DRM_TEST_TRANSPORT="$route" "$HERE/tools/latitude-drm-route-test" > "$OUT/$route-discovery.txt" 2>&1 &
  probe_child=$!
  ( sleep 60; echo 'FAIL discovery watchdog' >> "$OUT/$route-discovery.txt"; kill -TERM "$probe_child" 2>/dev/null; sleep 2; kill -KILL "$probe_child" 2>/dev/null ) &
  probe_watcher=$!
  wait "$probe_child"; probe=$?
  kill "$probe_watcher" 2>/dev/null; wait "$probe_watcher" 2>/dev/null
  cat "$OUT/$route-discovery.txt"
  if [ "$probe" != 0 ]; then echo "$route-discovery exit=$probe" >> "$OUT/results.txt"; result=1; break; fi
  run_case "$route-small-raw" "$route" 1 retained --size 64x64 --raw || { result=1; break; }
  run_case "$route-small-render" "$route" 1 retained --size 64x64 || { result=1; break; }
  run_case "$route-full-render" "$route" 1 retained --size 1920x1080 || { result=1; break; }
  run_case "$route-padded" "$route" 1 retained --size 1920x1080 --padding 64 || { result=1; break; }
  run_case "$route-fresh-pools" "$route" 0 retained --size 1920x1080 --padding 64 || { result=1; break; }
  run_case "$route-fresh-staging" "$route" 1 fresh --size 1920x1080 --padding 64 || { result=1; break; }
  run_case "$route-fresh-textures" "$route" 1 retained --size 1920x1080 --padding 64 --fresh-textures || { result=1; break; }
  run_case "$route-two-independent" "$route" 1 retained --size 1920x1080 --padding 64 --threads 2 || { result=1; break; }
  run_case "$route-two-handoff" "$route" 1 retained --size 1920x1080 --padding 64 --threads 2 --shared-texture || { result=1; break; }
  run_case "$route-iosurface" "$route" 1 retained --size 1920x1080 --padding 64 --iosurface || { result=1; break; }
  run_case "$route-bgra-surface" "$route" 1 retained --size 1920x1080 --padding 64 --iosurface --bgra || { result=1; break; }
done
# Bounded historical capture, without issuing more GPU work after a failure.
log show --last 20m --style compact --predicate 'eventMessage CONTAINS[c] "i915" OR eventMessage CONTAINS[c] "GPU HANG" OR eventMessage CONTAINS[c] "first-submit" OR subsystem == "org.nullmoth.libdrm" OR process == "latitude-readback-test" OR process == "latitude-drm-route-test"' > "$OUT/gpu-history.txt" 2>&1 &
child=$!
( sleep 30; kill -TERM "$child" 2>/dev/null; sleep 2; kill -KILL "$child" 2>/dev/null ) &
watcher=$!
wait "$child"; kill "$watcher" 2>/dev/null; wait "$watcher" 2>/dev/null
printf 'READBACK SUITE exit=%s iterations=%s\n' "$result" "$COUNT" | tee -a "$OUT/results.txt"
if [ "$result" = 0 ]; then
  shasum -a 256 /Library/GPUBundles/NVMTLDriver.bundle/Contents/MacOS/NVMTLDriver /Library/GPUBundles/nvmtl/libdrm.2.dylib > "$OUT/passing-binaries.txt"
  if [ "$COUNT" -ge 1000 ]; then echo "0.2.7 iterations=$COUNT all-22-cases-pass" > "$OUT/desktop-gate.txt"; fi
fi
echo "Saved report: $OUT"
[ "$COUNT" -ge 1000 ] || echo 'This was a smoke test; the 1000-iteration gate remains pending.'
exit "$result"
