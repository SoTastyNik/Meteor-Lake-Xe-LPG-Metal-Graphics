from pathlib import Path
r=Path('/Users/ved/Documents/iGPU Port');f=r/'latitude-desktop/test-readback.sh';s=f.read_text().replace('local envargs=(NMX_DRM_TEST_TRANSPORT=', 'local envargs=(NVMTL_ENABLE=1 NMX_DRM_TEST_TRANSPORT=',1)
needle='echo "Readback suite: $COUNT iterations per worker/case. Progress every 50 frames. Logs: $OUT"'
replacement='''for relative in NVMTLDriver.bundle/Contents/MacOS/NVMTLDriver nvmtl/libdrm.2.dylib; do
  cmp -s "$HERE/Library/GPUBundles/$relative" "/Library/GPUBundles/$relative" || { echo "Installed binary differs from this candidate: $relative"; exit 2; }
done
echo 'Waiting up to 75 seconds for the Metal plugin registration...'
ready=0
for ((attempt=0; attempt<=37; attempt++)); do
  ioreg -r -c NMXAccel -l -w0 > "$OUT/accelerator-before.txt"
  if grep -Eq '\"MetalPluginName\" = \"([^\"[:space:]]*/)?NVMTLDriver\"' "$OUT/accelerator-before.txt"; then ready=1; break; fi
  [ "$attempt" = 37 ] || sleep 2
done
[ "$ready" = 1 ] || { echo 'NMXAccel Metal plugin did not register. No GPU tests run.'; exit 2; }
''' + needle
assert needle in s;s=s.replace(needle,replacement,1);f.write_text(s)
f=r/'NullMoth/plugin/nvmtl_vk.c';s=f.read_text().replace('if (nvmtl_desktop_stall_policy(vendor, g_pci_device, getprogname(), getenv("INTEL_DEBUG"))) {','if (getenv("NVMTL_DESKTOP_STALL") && nvmtl_desktop_stall_policy(vendor, g_pci_device, getprogname(), getenv("INTEL_DEBUG"))) {',1);f.write_text(s)
