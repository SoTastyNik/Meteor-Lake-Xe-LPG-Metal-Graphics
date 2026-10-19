#!/bin/bash
set -euo pipefail
[ "$(id -u)" = 0 ] || { echo 'Run rollback with sudo on the Dell.' >&2; exit 2; }
BACKUP="${1:-$(cat /Library/NullMoth/latitude5350-last-backup.txt)}"
case "$BACKUP" in /Library/NullMoth/latitude5350-backups/*) ;; *) echo 'Unexpected backup path' >&2; exit 2 ;; esac
[ -d "$BACKUP/original" ] || { echo 'Backup not found' >&2; exit 2; }
nvram -d nullmoth-gpu-once 2>/dev/null || true
for path in /Library/Extensions/MyIntelGPU.kext /Library/Extensions/NMXGPU.kext /Library/Extensions/NMXAccel.kext \
 /Library/GPUBundles/NVMTLDriver.bundle /Library/GPUBundles/nvmtl /Library/GPUBundles/nvmtl-allow.txt \
 /Library/NullMoth/firmware/i915 /Library/KernelCollections/AuxiliaryKernelExtensions.kc; do
  rm -rf "$path"
  if [ -e "$BACKUP/original$path" ] || [ -L "$BACKUP/original$path" ]; then
    mkdir -p "$(dirname "$path")"; ditto "$BACKUP/original$path" "$path"
  fi
done
kcditto
printf 'Runtime restored from %s. Reboot to use the restored collection.\n' "$BACKUP"
echo 'USB security settings are separate; their previous config is backed up under iGPU-Port/backups on the USB.'
