#!/bin/bash
set -uo pipefail
if [ "$(uname -m)" != x86_64 ]; then
  echo 'Run this on the Dell laptop after booting macOS, not on the Apple Silicon build Mac.' >&2
  exit 2
fi
OUT="${1:-$HOME/Desktop/latitude5350-$(date +%Y%m%d-%H%M%S)}"
mkdir -p "$OUT" || exit 1
sw_vers > "$OUT/macos.txt" 2>&1
sysctl machdep.cpu.brand_string >> "$OUT/macos.txt" 2>&1
ioreg -r -c LatitudeMTLProbe -l -w0 > "$OUT/probe-ioreg.txt" 2>&1
ioreg -r -n IGPU -l -w0 > "$OUT/igpu-ioreg.txt" 2>&1
ioreg -r -n GFX0 -l -w0 > "$OUT/gfx0-ioreg.txt" 2>&1
ioreg -r -c NMXGPU -l -w0 > "$OUT/nmxgpu-ioreg.txt" 2>&1
system_profiler SPDisplaysDataType > "$OUT/displays.txt" 2>&1
kmutil showloaded > "$OUT/loaded-kexts.txt" 2>&1
log show --last boot --style compact --predicate 'eventMessage CONTAINS "LatitudeMTLProbe" OR eventMessage CONTAINS "NullMoth GPU" OR eventMessage CONTAINS "MyIntelGPU"' > "$OUT/gpu-log.txt" 2>&1
if grep -q 'ActualDeviceID' "$OUT/probe-ioreg.txt"; then
  echo 'PCI probe attached. This does not establish GPU acceleration.'
else
  echo 'PCI probe did not publish; inspect loaded-kexts.txt and gpu-log.txt.'
fi
printf 'Saved locally: %s\n' "$OUT"
