from pathlib import Path
import hashlib,json,subprocess,shutil
r=Path('/Users/ved/Documents/iGPU Port');p=r/'latitude-desktop';usb=Path('/Volumes/SEQOUIA/iGPU-Port');dest=usb/'Desktop'
# Preserve previous USB candidate files that will change; never copy target reports over local reports.
b=usb/'backups/desktop-0.2.6-before';b.mkdir(parents=True,exist_ok=True)
for rel in ['Desktop/Library/GPUBundles/NVMTLDriver.bundle','Desktop/Library/GPUBundles/nvmtl/libdrm.2.dylib','Desktop/install-runtime.sh','Desktop/README.md','Desktop/BUILD-MANIFEST.json','Desktop/SHA256SUMS.txt','PORT-STATUS.md','ROADMAP.md','install-desktop.sh']:
 src=usb/rel;dst=b/rel
 if dst.exists() or not src.exists():continue
 dst.parent.mkdir(parents=True,exist_ok=True)
 if src.is_dir():shutil.copytree(src,dst)
 else:shutil.copy2(src,dst)
for src in p.rglob('*'):
 rel=src.relative_to(p)
 if 'reports' in rel.parts or src.name.startswith('._'):continue
 dst=dest/rel
 if src.is_symlink():
  if dst.is_symlink() or dst.exists():continue
  dst.symlink_to(src.readlink());continue
 if src.is_dir():dst.mkdir(parents=True,exist_ok=True)
 else:
  dst.parent.mkdir(parents=True,exist_ok=True)
  if not dst.exists() or hashlib.sha256(src.read_bytes()).digest()!=hashlib.sha256(dst.read_bytes()).digest():shutil.copy2(src,dst)
for name,target,args,label in [('install-readback.sh','install-runtime.sh','--readback-only','READBACK INSTALL'),('test-readback.sh','test-readback.sh','"$@"','READBACK TEST')]:
 (usb/name).write_text('''#!/bin/bash
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
LOG="$HERE/'''+name[:-3]+'''-$(date +%Y%m%d-%H%M%S).txt"
echo "'''+label+''' — log: $LOG"
/bin/bash "$HERE/Desktop/'''+target+'" '+args+''' 2>&1 | tee "$LOG"
result=${PIPESTATUS[0]}
echo "'''+label+''' exit=$result" | tee -a "$LOG"
exit "$result"
''')
# Existing user-facing command also uses the safe default now.
f=usb/'install-desktop.sh';s=f.read_text().replace('LATITUDE DESKTOP INSTALL — using','LATITUDE CANDIDATE INSTALL — default readback-only, using');f.write_text(s)
validation=r/'port-artifacts/desktop-0.2.6';validation.mkdir(parents=True,exist_ok=True)
for f in ['test-readback.c','test-readback-recording.py','test-transport.py','package-0.2.6.py']:
 shutil.copy2(r/'desktop-sources'/f,validation/f)
for src,new in [(r/'NullMoth/plugin/nvmtl_readback.h','nvmtl_readback.h'),(r/'latitude-desktop/tools/latitude-readback-test.m','latitude-readback-test.m'),(p/'test-readback.sh','test-readback.sh'),(p/'BUILD-MANIFEST.json','BUILD-MANIFEST.json')]:shutil.copy2(src,validation/new)
for tool,out in [('test-readback','copy-plan.txt'),('test-readback-recording','recording.txt'),('test-transport','transport.txt')]:
 with (validation/out).open('w') as stream:subprocess.run([str(r/'desktop-build'/tool)],stdout=stream,stderr=subprocess.STDOUT,check=True)
shutil.copy2(r/'desktop-build/failure-regression-0.2.6.txt',validation/'failed-command-buffer.txt')
for opts,name in [(['--iterations','1000','--size','64x64','--threads','2','--shared-texture'],'native-handoff.txt'),(['--iterations','100','--size','1920x1080','--padding','64','--iosurface'],'native-iosurface.txt'),(['--iterations','5','--size','64x64','--raw','--threads','2','--fresh-textures'],'native-raw.txt')]:
 with (validation/name).open('w') as stream:subprocess.run([str(r/'desktop-build/latitude-readback-test-native'),'--allow-native',*opts],stdout=stream,stderr=subprocess.STDOUT,check=True)
(validation/'VALIDATION.md').write_text('''# Candidate 0.2.6 local validation

Copy-plan tests and the actual extracted readback/transport implementations passed ASan/UBSan. The readback test records producer dependency → copy → transfer/host dependency → subresource restoration → completion, then checks padded CPU output. Simulated timeout preserves output and retains memory; command-begin failure and noncoherent staging are rejected safely. Transport fixtures verify actual branch logic and fail-closed direct/IOKit routing. These tests mock Vulkan/IOKit calls and cannot validate GPU execution.

A native fault-injection build of the plugin passed 80 error command buffers with terminal encoders, completion callbacks and capacity release. The x86_64 release plugin contains no compile-time fault injection.

The native Apple M4 test harness passed 2,000 shared-texture handoff frames, 100 full-HD padded IOSurface frames, and independent raw/fresh-texture frames. These results validate the workload and exact-pixel checker on Apple hardware, not the Intel driver or Intel compiler.

x86_64 plugin, libdrm and isolated test executable built; signatures and USB package hashes verified separately. The installer and runner pass bash -n. Readback-only mode removes the panel one-shot and arms only the GPU one-shot.

Pending: Intel smoke test, 1,000-frame test matrix, driver allocation-growth analysis, synchronization-validation-layer proof, broader shared-image ownership, conditional kernel capture expansion and physical WindowServer acceptance. No desktop-success claim.
''')
new='''## Candidate 0.2.6 prepared — Intel tests pending

The readback correctness patch and isolated test matrix are on the USB. Local ASan/UBSan recording/error tests pass. Native Apple M4 exact-pixel tests validate the harness only. Default installation is now readback-only; physical panel ownership is disabled for the next GPU application test. Automatic WindowServer `INTEL_DEBUG=stall` was removed after its failed target result.

Run `sudo /bin/bash /Volumes/SEQOUIA/iGPU-Port/install-readback.sh` on the Dell. After exit=0, reboot USB once and run `sudo /bin/bash /Volumes/SEQOUIA/iGPU-Port/test-readback.sh`. Reports go to `Desktop/reports/readback-TIMESTAMP`. The 100-iteration smoke test comes before the 1,000-iteration gate and another desktop attempt.

Implemented: validated full/region readback, transfer-write/host-read dependency, copied-subresource layout restoration, coherent-memory verification, timeout retention, image/stage identities, dedicated-staging option, deterministic raw/render/IOSurface tests, controlled two-thread cases, verified direct/IOKit route counters.

Pending: target results, broader render/compute/blit image-state concurrency, synchronization validation, conditional kernel-request/GEM correlation, desktop stability and later display features. Artifacting and full acceleration are not confirmed fixed.

'''
f=r/'ROADMAP.md';s=f.read_text();s=s.replace('## Evidence and corrections',new+'## Evidence and corrections',1) if '## Evidence and corrections' in s else s.replace('\n## ', '\n'+new+'## ',1);f.write_text(s);shutil.copy2(f,usb/'ROADMAP.md');shutil.copy2(f,r/'research/desktop-roadmap-20261018.md')
f=usb/'PORT-STATUS.md';s=f.read_text();f.write_text('# Current: candidate 0.2.6 isolated readback test prepared\n\n'+new+'---\n\n'+s)
shutil.copy2(validation/'VALIDATION.md',usb/'desktop-0.2.6-validation.md')
for name in ['install-readback.sh','test-readback.sh','install-desktop.sh']:subprocess.run(['/bin/bash','-n',str(usb/name)],check=True)
for f in [dest/'Library/GPUBundles/NVMTLDriver.bundle',dest/'Library/GPUBundles/nvmtl/libdrm.2.dylib',dest/'tools/latitude-readback-test']:subprocess.run(['codesign','--verify','--strict',str(f)],check=True)
for line in (dest/'SHA256SUMS.txt').read_text().splitlines():
 digest,rel=line.split('  ',1);assert hashlib.sha256((dest/rel).read_bytes()).hexdigest()==digest,rel
f=usb/'SHA256SUMS.json';m=json.loads(f.read_text());m['PORT-STATUS.md']=hashlib.sha256((usb/'PORT-STATUS.md').read_bytes()).hexdigest()
for name in ['install-readback.sh','test-readback.sh','ROADMAP.md','desktop-0.2.6-validation.md']:m[name]=hashlib.sha256((usb/name).read_bytes()).hexdigest()
f.write_text(json.dumps(m,indent=2)+'\n')
print('USB candidate 0.2.6 verified; local tests archived at',validation)
