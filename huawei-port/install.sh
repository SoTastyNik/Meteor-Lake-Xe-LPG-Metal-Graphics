#!/bin/bash
# Install the HUAWEI MateBook 14 (8086:7D55) graphics runtime and arm ONE accelerated boot.
# Run from the package folder:  sudo /bin/bash install.sh
# Nothing is rebooted. If the accelerated boot fails, power off and boot again: the one-shot
# opt-ins are consumed, so the next start uses the firmware framebuffer.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
[ "$(id -u)" = 0 ] || { echo 'Run with sudo.' >&2; exit 2; }
[ "$(uname -m)" = x86_64 ] || { echo 'Intel x86_64 macOS only.' >&2; exit 2; }
[ "$(sw_vers -productVersion | cut -d. -f1)" = 15 ] || { echo 'This build targets macOS Sequoia 15.' >&2; exit 2; }
REPORT="$HERE/reports/install-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$REPORT"
sw_vers > "$REPORT/sw_vers.txt"
[ "$(sw_vers -buildVersion)" = 24H32 ] || echo "Note: upstream evidence is 15.8.1 (24H32); this Mac runs $(sw_vers -buildVersion)."

cpu=$(sysctl -n machdep.cpu.brand_string)
case "$cpu" in *'Ultra 5 125H'*) ;; *) echo "CPU '$cpu' is not the MateBook 14 profile." >&2; exit 2 ;; esac
ioreg -r -n GFX0 -l -w0 > "$REPORT/GFX0.txt"
grep -q '"device-id" = <557d0000>' "$REPORT/GFX0.txt" || { echo 'GFX0 8086:7D55 not visible.' >&2; exit 2; }
grep -q '"subsystem-vendor-id" = <e5190000>' "$REPORT/GFX0.txt" && grep -q '"subsystem-id" = <713e0000>' "$REPORT/GFX0.txt" \
  || { echo 'GFX0 subsystem is not HUAWEI 19E5:3E71.' >&2; exit 2; }
csrutil status > "$REPORT/csrutil.txt" 2>&1 || true
grep -qE 'status: disabled|Kext Signing: disabled' "$REPORT/csrutil.txt" \
  || { echo 'Unsigned kexts are still blocked: boot through the graphics EFI (csr-active-config 0x0A43).' >&2; exit 2; }
kmutil showloaded > "$REPORT/loaded-kexts.txt" 2>&1
grep -Fq 'com.dhinakg.AMFIPass' "$REPORT/loaded-kexts.txt" || { echo 'AMFIPass is not loaded: boot through the graphics EFI.' >&2; exit 2; }
grep -Fq 'com.nullmoth.LatitudePanelClaim' "$REPORT/loaded-kexts.txt" \
  || echo 'Note: LatitudePanelClaim is not loaded yet; it attaches only on a boot with nullmoth-panel-once set.'

cd "$HERE"
shasum -a 256 -c SHA256SUMS.txt > "$REPORT/package-check.txt" || { tail "$REPORT/package-check.txt"; echo 'Package is damaged.' >&2; exit 2; }
for k in Library/Extensions/*.kext EFI-Kexts/*.kext Library/GPUBundles/NVMTLDriver.bundle; do codesign --verify --strict "$k"; done

BKC=/System/Library/KernelCollections/BootKernelExtensions.kc
SKC=/System/Library/KernelCollections/SystemKernelExtensions.kc
AUX=/Library/KernelCollections/AuxiliaryKernelExtensions.kc
[ -f "$BKC" ] && [ -f "$SKC" ] || { echo 'System kernel collections not found.' >&2; exit 2; }
OURS="NMXGPU.kext NMXAccel.kext LatitudeMTLFB.kext"
WORK=$(mktemp -d /private/var/tmp/huawei-mtl.XXXXXX)
ditto "$HERE/Library/Extensions" "$WORK/Extensions"
chown -R root:wheel "$WORK/Extensions"; chmod -R a+rX,go-w "$WORK/Extensions"
args=()
for kext in /Library/Extensions/*.kext; do
  [ -d "$kext" ] || continue
  case " $OURS " in *" $(basename "$kext") "*) continue ;; esac
  args+=( -p "$kext" )
done
for k in $OURS; do args+=( -p "$WORK/Extensions/$k" ); done
echo 'Preflight: linking the candidate against this Mac kernel collections...'
if ! kmutil create -n aux -B "$BKC" -S "$SKC" -A "$WORK/preflight.kc" "${args[@]}" -M --allow-missing-kdk > "$REPORT/kmutil-preflight.txt" 2>&1; then
  tail -40 "$REPORT/kmutil-preflight.txt"; echo "Preflight failed; nothing installed. Report: $REPORT" >&2; rm -rf "$WORK"; exit 1
fi

BACKUP="/Library/NullMoth/huawei-backups/$(date +%Y%m%d-%H%M%S)"
mkdir -p "$BACKUP/original"
PATHS=( /Library/Extensions/NMXGPU.kext /Library/Extensions/NMXAccel.kext /Library/Extensions/LatitudeMTLFB.kext
  /Library/GPUBundles/NVMTLDriver.bundle /Library/GPUBundles/nvmtl /Library/GPUBundles/nvmtl-allow.txt
  /Library/NullMoth/firmware/i915 /Library/NullMoth/load-panel-framebuffer.sh /Library/NullMoth/latitude-desktop-journal
  /Library/NullMoth/latitude-gpu-identity /Library/LaunchDaemons/com.huawei-mtl.panel-load.plist "$AUX" )
: > "$BACKUP/paths.txt"
for p in "${PATHS[@]}"; do
  if [ -e "$p" ]; then mkdir -p "$BACKUP/original$(dirname "$p")"; ditto "$p" "$BACKUP/original$p"; echo "saved $p" >> "$BACKUP/paths.txt"
  else echo "absent $p" >> "$BACKUP/paths.txt"; fi
done
cp "$HERE/uninstall.sh" "$BACKUP/uninstall.sh"
printf '%s\n' "$BACKUP" > /Library/NullMoth/huawei-last-backup.txt
rollback() { trap - ERR; echo "Install failed; restoring $BACKUP" >&2; /bin/bash "$BACKUP/uninstall.sh" "$BACKUP" || echo "Rollback needs attention: $BACKUP" >&2; exit 1; }
trap rollback ERR

install_tree() {  # install_tree <package-relative path> <destination>
  rm -rf "$2"; mkdir -p "$(dirname "$2")"; ditto "$HERE/$1" "$2"; chown -R root:wheel "$2"; chmod -R a+rX,go-w "$2"
}
for k in $OURS; do install_tree "Library/Extensions/$k" "/Library/Extensions/$k"; done
mkdir -p /Library/GPUBundles && chmod 755 /Library/GPUBundles
install_tree Library/GPUBundles/NVMTLDriver.bundle /Library/GPUBundles/NVMTLDriver.bundle
install_tree Library/GPUBundles/nvmtl /Library/GPUBundles/nvmtl
install_tree Library/GPUBundles/nvmtl-allow.txt /Library/GPUBundles/nvmtl-allow.txt
install_tree Library/NullMoth/firmware/i915 /Library/NullMoth/firmware/i915
for f in load-panel-framebuffer.sh latitude-desktop-journal latitude-gpu-identity; do
  install_tree "Library/NullMoth/$f" "/Library/NullMoth/$f"; chmod 755 "/Library/NullMoth/$f"
done
install_tree Library/LaunchDaemons/com.huawei-mtl.panel-load.plist /Library/LaunchDaemons/com.huawei-mtl.panel-load.plist
chmod 644 /Library/LaunchDaemons/com.huawei-mtl.panel-load.plist
plutil -lint /Library/LaunchDaemons/com.huawei-mtl.panel-load.plist > /dev/null

args=()
for kext in /Library/Extensions/*.kext; do if [ -d "$kext" ]; then args+=( -p "$kext" ); fi; done
kmutil create -n aux -B "$BKC" -S "$SKC" -A "$WORK/installed.kc" "${args[@]}" -M --allow-missing-kdk > "$REPORT/kmutil-final.txt" 2>&1
kmutil inspect -B "$BKC" -S "$SKC" -A "$WORK/installed.kc" --show-prelink-info > "$REPORT/prelink-info.txt" 2>&1
V="$HERE/tools/validate-kernel-prelink"
"$V" "$REPORT/prelink-info.txt" "$(cat "$HERE/NMXGPU-UUID.txt")" /Library/Extensions/NMXGPU.kext "$(cat "$HERE/NMXGPU-VERSION.txt")" > "$REPORT/validate.txt"
"$V" "$REPORT/prelink-info.txt" "$(cat "$HERE/NMXAccel-UUID.txt")" /Library/Extensions/NMXAccel.kext "$(cat "$HERE/NMXAccel-VERSION.txt")" com.nullmoth.NMXAccel NMXAccel >> "$REPORT/validate.txt"
"$V" "$REPORT/prelink-info.txt" "$(cat "$HERE/LatitudeMTLFB-UUID.txt")" /Library/Extensions/LatitudeMTLFB.kext "$(cat "$HERE/LatitudeMTLFB-VERSION.txt")" com.nullmoth.LatitudeMTLFB LatitudeMTLFB >> "$REPORT/validate.txt"
mkdir -p /Library/KernelCollections
cp "$WORK/installed.kc" "$AUX.huawei-tmp"; chown root:wheel "$AUX.huawei-tmp"; chmod 644 "$AUX.huawei-tmp"; mv -f "$AUX.huawei-tmp" "$AUX"
kcditto > "$REPORT/kcditto.txt" 2>&1
trap - ERR
rm -rf "$WORK"

# Arm one accelerated boot. The kernel's attach guard (nullmoth-gpu-attaching) parks the driver after a failed attach;
# an explicit install is the only place that clears it.
nvram -d nullmoth-gpu-attaching 2>/dev/null || true
nvram nullmoth-gpu-once=1
nvram nullmoth-panel-once=1
{ nvram nullmoth-gpu-once; nvram nullmoth-panel-once; } > "$REPORT/armed.txt"
cat "$REPORT/validate.txt"
echo "Installed. Backup: $BACKUP"
echo 'ONE accelerated boot is armed. Reboot through the USB (no NVRAM reset).'
echo 'After the boot, run: sudo /bin/bash collect.sh   (also after a failed boot, from the fallback desktop)'
