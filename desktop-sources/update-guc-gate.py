from pathlib import Path
r=Path(__file__).resolve().parent.parent;p=r/'latitude-desktop'
f=p/'test-readback.sh';s=f.read_text();needle='kmutil showloaded > "$OUT/loaded-kexts.txt" 2>&1';s=s.replace(needle,needle+'''
expected_gpu_uuid=$(cat "$HERE/NMXGPU-UUID.txt") || exit 2
[ -n "$expected_gpu_uuid" ] || exit 2
if ! grep -F 'com.nullmoth.NMXGPU (1.0.8)' "$OUT/loaded-kexts.txt" | grep -Fq "$expected_gpu_uuid"; then
  echo 'Expected newly loaded NMXGPU 1.0.8 UUID; install this candidate and reboot through USB first.'; exit 2
fi
cmp -s "$HERE/Library/Extensions/NMXGPU.kext/Contents/MacOS/NMXGPU" /Library/Extensions/NMXGPU.kext/Contents/MacOS/NMXGPU || { echo 'Installed GPU kernel binary differs from candidate'; exit 2; }
# Match kernel event records, excluding log-filter headers and log command metadata.
kernel_faults() {
  grep -hE '^[0-9]{4}-.* kernel\\[' "$@" | grep -Ei 'GPU HANG|Resetting (chip|rcs|engine)|GT[0-9 ]* reset|TLB invalidation response timed out|TLB invalidation did not complete'
}''');s=s.replace('  echo "$name exit=$result" | tee', '''  if kernel_faults "$OUT/kernel-live.txt" > "$OUT/$name-kernel-faults.txt"; then
    echo 'FAIL kernel GPU/TLB fault detected; stopping before another workload'; result=1
  fi
  echo "$name exit=$result" | tee''');s=s.replace("if grep -Ei 'GPU HANG|Resetting (chip|rcs|engine)|GT[0-9 ]* reset'",'if kernel_faults');s=s.replace('FAIL GPU hang/reset recorded during suite','FAIL kernel GPU hang/reset/TLB fault recorded during suite');s=s.replace('shasum -a 256 /Library/GPUBundles/NVMTLDriver.bundle/Contents/MacOS/NVMTLDriver /Library/GPUBundles/nvmtl/libdrm.2.dylib > "$OUT/passing-binaries.txt"','shasum -a 256 /Library/GPUBundles/NVMTLDriver.bundle/Contents/MacOS/NVMTLDriver /Library/GPUBundles/nvmtl/libdrm.2.dylib /Library/Extensions/NMXGPU.kext/Contents/MacOS/NMXGPU > "$OUT/passing-binaries.txt"');s=s.replace('candidate=0.3.0 cases=22','candidate=0.3.1 cases=22');f.write_text(s)
f=p/'test-and-arm-desktop.sh';s=f.read_text().replace('candidate=0.3.0 cases=22','candidate=0.3.1 cases=22').replace('/Library/GPUBundles/nvmtl/libdrm.2.dylib;','/Library/GPUBundles/nvmtl/libdrm.2.dylib /Library/Extensions/NMXGPU.kext/Contents/MacOS/NMXGPU;');s=s.replace('armed=1\nnvram', '''cmp -s "$HERE/Library/Extensions/NMXGPU.kext/Contents/MacOS/NMXGPU" /Library/Extensions/NMXGPU.kext/Contents/MacOS/NMXGPU || { echo 'GPU kernel binary changed during testing'; exit 2; }
armed=1
nvram''');f.write_text(s)
f=p/'install-runtime.sh';s=f.read_text().replace('0.3.0','0.3.1');f.write_text(s)
