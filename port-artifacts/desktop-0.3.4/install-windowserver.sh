#!/bin/bash
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
[ "$(uname -m)" = x86_64 ] && [ "$(id -u)" = 0 ] || { echo 'Run with sudo on the Intel Dell fallback desktop.'; exit 2; }
[ "$(sw_vers -buildVersion)" = 24H32 ] || { echo 'This candidate targets Sequoia24H32.'; exit 2; }
REPORT="$HERE/reports/windowserver-install-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$REPORT"
ioreg -r -n GFX0 -l -w0 > "$REPORT/GFX0.txt"
grep -q '"device-id" = <457d0000>' "$REPORT/GFX0.txt" || { echo 'Expected8086:7D45 is not visible.'; exit 2; }
ioreg -r -c LatitudePanelClaim -l -w0 > "$REPORT/panel.txt"
if grep -q LatitudePanelClaim "$REPORT/panel.txt"; then echo 'Boot the fallback desktop before updating WindowServer.'; exit 2; fi
cd "$HERE"
shasum -a 256 -c SHA256SUMS.txt > "$REPORT/package-check.txt"
cd "$HERE/.."
shasum -a 256 -c "$HERE/WINDOWSERVER-BASELINE-SHA256SUMS.txt" > "$REPORT/baseline-check.txt"
echo 'Verified the saved22case/26000frame baseline. No GPU tests will run.'
kmutil showloaded > "$REPORT/loaded-kexts.txt" 2>&1
for spec in 'NMXGPU 1.0.8' 'NMXAccel 0.2.4'; do
  set -- $spec
  expected_uuid=$(cat "$HERE/$1-UUID.txt")
  grep -F "com.nullmoth.$1 ($2)" "$REPORT/loaded-kexts.txt" | grep -F "$expected_uuid" >/dev/null || { echo "Loaded $1 differs from the verified baseline; no changes made."; exit 2; }
  cmp -s "$HERE/Library/Extensions/$1.kext/Contents/MacOS/$1" "/Library/Extensions/$1.kext/Contents/MacOS/$1" || { echo "Installed $1 differs from baseline."; exit 2; }
done
grep -F 'com.dhinakg.AMFIPass' "$REPORT/loaded-kexts.txt" >/dev/null || { echo 'AMFIPass is not loaded; no changes made.'; exit 2; }
cmp -s "$HERE/Library/GPUBundles/nvmtl/libdrm.2.dylib" /Library/GPUBundles/nvmtl/libdrm.2.dylib || { echo 'Installed transport differs from baseline.'; exit 2; }
codesign --verify --strict "$HERE/Library/GPUBundles/NVMTLDriver.bundle"
codesign --verify --strict "$HERE/Library/NullMoth/latitude-desktop-journal"
/bin/bash -n "$HERE/Library/NullMoth/load-panel-framebuffer.sh"
DEST=/Library/GPUBundles/NVMTLDriver.bundle
HELPER=/Library/NullMoth/latitude-desktop-journal
LOADER=/Library/NullMoth/load-panel-framebuffer.sh
[ -d "$DEST" ] || { echo 'Existing runtime bundle missing; install the base runtime first.'; exit 2; }
BACKUP="/Library/NullMoth/latitude5350-backups/windowserver-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$BACKUP"
WORK=$(mktemp -d /Library/GPUBundles/.latitude-windowserver.XXXXXX)
# Capture every file before changing any runtime component.
for file in "$HELPER" "$LOADER"; do
  if [ -e "$file" ]; then cp -p "$file" "$BACKUP/$(basename "$file")"; else touch "$BACKUP/$(basename "$file").absent"; fi
done
changed=0
success=0
cleanup() {
  result=$?
  trap - EXIT
  if [ "$success" != 1 ] && [ "$changed" = 1 ]; then
    nvram -d nullmoth-panel-once 2>/dev/null || true
    nvram -d nullmoth-gpu-once 2>/dev/null || true
    for file in "$HELPER" "$LOADER"; do
      name=$(basename "$file")
      if [ -f "$BACKUP/$name.absent" ]; then rm -f "$file"; else cp -p "$BACKUP/$name" "$file"; fi
    done
    if [ -d "$WORK/previous.bundle" ]; then
      rm -rf "$DEST"
      mv "$WORK/previous.bundle" "$DEST"
      echo 'Desktop preparation failed; previous plugin and capture tools restored and both opt-ins cleared.'
    fi
  fi
  rm -rf "$WORK"
  exit "$result"
}
trap cleanup EXIT
ditto "$HERE/Library/GPUBundles/NVMTLDriver.bundle" "$WORK/new.bundle"
chown -R root:wheel "$WORK/new.bundle"
chmod -R a+rX,go-w "$WORK/new.bundle"
codesign --verify --strict "$WORK/new.bundle"
mv "$DEST" "$WORK/previous.bundle"
changed=1
mv "$WORK/new.bundle" "$DEST"
codesign --verify --strict "$DEST"
cmp -s "$HERE/Library/GPUBundles/NVMTLDriver.bundle/Contents/MacOS/NVMTLDriver" "$DEST/Contents/MacOS/NVMTLDriver"
ditto "$WORK/previous.bundle" "$BACKUP/NVMTLDriver.bundle"
for file in "$HELPER" "$LOADER"; do
  cp "$HERE/Library/NullMoth/$(basename "$file")" "$file.new"
  chown root:wheel "$file.new"
  chmod 755 "$file.new"
  mv -f "$file.new" "$file"
  cmp -s "$HERE/Library/NullMoth/$(basename "$file")" "$file"
done
codesign --verify --strict "$HELPER"
"$HELPER" prepare
"$HELPER" stage installer-ready candidate0.3.4 0
shasum -a 256 "$HELPER" "$LOADER" > "$REPORT/installed-capture-tools.txt"
shasum -a 256 "$DEST/Contents/MacOS/NVMTLDriver" > "$REPORT/installed-plugin.txt"
printf '%s\n' "$BACKUP" > "$REPORT/backup.txt"
date +%s > "$HERE/reports/windowserver-attempt-start.txt"
nvram nullmoth-gpu-once=1
nvram nullmoth-panel-once=1
nvram nullmoth-gpu-once > "$REPORT/armed-markers.txt"
nvram nullmoth-panel-once >> "$REPORT/armed-markers.txt"
success=1
echo "WindowServer candidate0.3.4 installed. Backup: $BACKUP"
echo 'ONE desktop boot armed. Reboot through this USB once when ready.'
echo 'No hardware suite was rerun. The installer has not rebooted the laptop.'
echo 'If the panel fails, power off and boot this USB again for fallback; run collect-desktop-failure.sh.'
