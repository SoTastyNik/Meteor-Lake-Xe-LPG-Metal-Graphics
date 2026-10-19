#!/bin/bash
# Compile check only: does not link, install, load, or rebuild kernel collections.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/NullMoth"
mkdir -p "$ROOT/port-artifacts/logs"
for source in gpu-port/xkpi/xnu/*.cpp; do
  case "$source" in */nmx_npu_kext.cpp) continue ;; esac
  ./gpu-port/xkpi/ccxx.sh "$source" > "$ROOT/port-artifacts/logs/$(basename "$source").log" 2>&1
  echo "OK $(basename "$source")"
done
echo 'IOKit compile check passed. This is not a linked or boot-tested NMXGPU build.'
