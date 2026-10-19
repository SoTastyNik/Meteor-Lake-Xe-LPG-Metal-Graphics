from pathlib import Path
import hashlib,json,plistlib,shutil,subprocess,difflib
r=Path(__file__).resolve().parent.parent;p=r/'latitude-desktop';u=Path('/Volumes/SEQOUIA/iGPU-Port');v=r/'port-artifacts/desktop-0.3.2';v.mkdir(parents=True,exist_ok=True)
assert u.is_dir()
backup=u/'backups/desktop-0.3.2-before'
for rel in ['Desktop/Library/GPUBundles/NVMTLDriver.bundle','Desktop/BUILD-MANIFEST.json','Desktop/README.md','Desktop/install-runtime.sh','Desktop/test-and-arm-desktop.sh','Desktop/SHA256SUMS.txt','collect-desktop-failure.sh','PORT-STATUS.md','ROADMAP.md']:
 src=u/rel;dst=backup/rel
 if not src.exists() or dst.exists():continue
 dst.parent.mkdir(parents=True,exist_ok=True)
 if src.is_dir():shutil.copytree(src,dst)
 else:shutil.copy2(src,dst)
base=u/'Desktop/reports/readback-20261019-114424';cases=[]
for line in (base/'results.txt').read_text().splitlines():
 if line.endswith(' exit=0'):cases.append(line[:-7])
assert len(cases)==22 and 'READBACK SUITE exit=0 iterations=1000' in (base/'results.txt').read_text()
proof=[base/'results.txt',base/'desktop-gate.txt',base/'passing-binaries.txt',base/'loaded-kexts.txt']+[base/(case+'.txt') for case in cases]
(p/'WINDOWSERVER-BASELINE-SHA256SUMS.txt').write_text(''.join(hashlib.sha256(f.read_bytes()).hexdigest()+'  '+str(f.relative_to(u))+'\n' for f in proof))
for name in ['NMXGPU','NMXAccel']:
 a=p/f'Library/Extensions/{name}.kext/Contents/MacOS/{name}';b=u/f'Desktop/Library/Extensions/{name}.kext/Contents/MacOS/{name}';assert a.read_bytes()==b.read_bytes(),name
 uuid=subprocess.check_output(['xcrun','dwarfdump','--uuid',str(a)],text=True).split()[1];(p/(name+'-UUID.txt')).write_text(uuid+'\n')
b=p/'Library/GPUBundles/NVMTLDriver.bundle';f=b/'Contents/Info.plist';info=plistlib.loads(f.read_bytes());info.update(CFBundleVersion='0.3.2',CFBundleShortVersionString='0.3.2');f.write_bytes(plistlib.dumps(info));shutil.copy2(r/'desktop-build/NVMTLDriver-0.3.2',b/'Contents/MacOS/NVMTLDriver');subprocess.run(['codesign','--force','--sign','-',str(b)],check=True);subprocess.run(['codesign','--verify','--strict',str(b)],check=True)
(p/'test-and-arm-desktop.sh').write_text('''#!/bin/bash
printf '%s\\n' 'The 22-case baseline is already verified. This WindowServer-only candidate does not rerun it.' 'Use: sudo /bin/bash /Volumes/SEQOUIA/iGPU-Port/install-windowserver.sh'
exit 2
''')
for name in ['test-windowserver-serial.py','test-windowserver-publication.py','test-windowserver-installer.py','test-pool-lifetime.py','test-pool-completion.py','test-readback-recording.py','test-desktop-crash-collector.py']:
 with (v/(name[:-3]+'.txt')).open('w') as out:subprocess.run(['/usr/bin/python3',str(r/'desktop-sources'/name)],stdout=out,stderr=subprocess.STDOUT,check=True)
 shutil.copy2(r/'desktop-sources'/name,v/name)
with (v/'release-policy.txt').open('w') as out:subprocess.run(['/usr/bin/python3',str(r/'desktop-sources/test-release-probe-controls.py'),str(r/'desktop-build/NVMTLDriver-release-policy-test-0.3.2')],stdout=out,stderr=subprocess.STDOUT,check=True)
with (v/'failure-regression.txt').open('w') as out:subprocess.run([str(r/'desktop-build/test-failed-command-buffer'),str(r/'desktop-build/NVMTLDriver-fault-test-0.3.2')],stdout=out,stderr=subprocess.STDOUT,check=True)
for f in p.glob('*.sh'):subprocess.run(['/bin/bash','-n',str(f)],check=True)
research='''# WindowServer candidate 0.3.2 — serial completion and surface scheduling

## Verified evidence

The preserved 0.3.1 hardware baseline is readback-20261019-114424: 22 cases, 26,000 frames, IOKit and direct access, exact pixels/padding and IOSurface backing checked, 80,020 command pools created/destroyed, no recorded hang/TLB timeout. It remains the verified application baseline; the user explicitly asked not to repeat the suite.

The failed physical desktop boot is captured in failure-detail-20261019-121101, including both current WindowServer .ips reports. Initial surface upload #1, render #2, readback #3 and render/event segment #4 completed. Second readback #5 was submitted at12:00:45.626. At the same time, the display pipe mapped the IOSurface and copied a blank frame to the panel. A second surface upload #6 was submitted at12:00:45.705 while #5 was still incomplete. Both fence waits hit the existing5-second budget. CoreDisplay then threw std::runtime_error from DisplaySurface::GetMTLTexture after the backend had shut down. The restarted WindowServer also failed; kernel later reported GPUHANG12:1:00dfffff.

Those observations establish failure ordering, not an exact GPU hang cause. External host-pointer imports were refused and fell back to copies; the fallback's first upload/readback succeeded, so import refusal alone is not established as the trigger. No physical overlap between scanout memory and command buffers has been demonstrated; this candidate does not rewrite GGTT, stolen-memory mappings, plane registers or firmware.

## Source and API research

Vulkan queue submission order is not a substitute for every resource dependency or host completion. Apple requires GPU-to-CPU synchronization of managed resources before consuming their CPU copy. The driver implements that through IOSurface copy-out after its Vulkan fence. Its submit-ahead worker previously allowed more than one WindowServer submission to be live while another thread issued synchronous surface copies. Scheduled notifications were ordinarily emitted before the corresponding IOSurface CPU publication, allowing the display consumer to observe the previous/blank backing.

Mesa's ANV debugging guidance recommends serialized submissions to investigate inter-command-buffer synchronization. Rather than enabling its debug sync path, which can block inside the ICD, this candidate uses the plugin's existing bounded wait and a recursive lock around its normal submit-begin/finish pair. The application path is unchanged. No INTEL_DEBUG flags or cache/compression settings are added.

Primary references:
- [Vulkan synchronization and submission order](https://docs.vulkan.org/spec/latest/chapters/synchronization.html)
- [Apple managed-resource synchronization](https://developer.apple.com/documentation/metal/synchronizing-a-managed-resource-in-macos)
- [Mesa ANV debugging guidance](https://docs.mesa3d.org/drivers/anv.html#debugging-tips)

## Implemented change

Only WindowServer on vendor8086/device7d45 gets the new policy. The normal synchronous render/upload/readback wrapper holds a process-wide recursive mutex from submission begin through fence completion/retirement. WindowServer's submit-ahead method is disabled, keeping its event worker but preventing unfinished ahead submissions from escaping that bounded wrapper. One-time dummy-image initialization retains its separate descriptor-safe path; it has no new blocking lock order. Applications keep submit-ahead and normal concurrency.

For WindowServer command buffers that write IOSurfaces, the scheduled notification is deferred until their surface parts have completed and copied out. The execution finish routine now drains outstanding parts before releasing deferred scheduling, and error completion does not advertise successful publication. This fixes that early notification contract. It is not proof that every private display-transaction route honors scheduling or that the GPU hang is cured.

Fresh pools, their fence/witness checks and quarantine on uncertain completion remain intact. The5-second WindowServer budget is unchanged. The CoreDisplay exception is not hidden with fake textures or successful status after GPU failure.

## Validation and next hardware step

The x86_64 release plugin compiles and is ad-hoc signed. Local ASan/UBSan fixtures extract the actual submit wrapper and event methods:3,000 serialized submissions across3threads, application concurrency, recursion/error unlocking, two-part surface publication order, failed-copy/GPU completion and remaining-work drain. Pool lifetime/completion/readback tests pass; actual native release-constructor policy checks and80failed-command-buffer regression pass. These are local tests, not successful WindowServer operation on the Dell.

Only the Metal plugin changes in runtime. NMXGPU1.0.8, NMXAccel0.2.4, framebuffer/claim, libdrm and firmware remain byte-identical to the verified baseline. New install-windowserver.sh verifies saved baseline evidence, loaded kernel/accelerator UUIDs, installed kernel/accelerator/libdrm bytes and package signatures/hashes. It backs up/replaces only the plugin, verifies it and arms one GPU+panel boot. Partial failure restores the old plugin and clears both opt-ins. It runs no GPU tests, no full suite and no automatic reboot.

The failure collector now selects the latest desktop attempt window and includes full recent WindowServer crash reports. Next: run install-windowserver.sh on the fallback Dell desktop, then reboot through USB once. If unsuccessful, power off and boot USB again for fallback and collect-desktop-failure.sh. Candidate0.3.2 target desktop correctness and stability remain pending.
'''
(v/'RESEARCH.md').write_text(research);(r/'research/windowserver-0.3.2-research.md').write_text(research);(u/'windowserver-0.3.2-research.md').write_text(research)
f=p/'BUILD-MANIFEST.json';m=json.loads(f.read_text());m['runtime_revision']='desktop-0.3.2-windowserver-serial';m['stage']='WindowServer-only candidate compiled; retained 0.3.1 application baseline; physical desktop validation pending';m['built']['metal_plugin']='NVMTLDriver0.3.2: scoped WindowServer serial completion and schedule-after-IOSurface-publication; apps retain concurrency'
m['candidate_0_3_1']['on_target']='Full22case/26000frame gate passed 2026-10-19;80020pools reclaimed. Physical WindowServer attempt then failed on second readback, concurrent upload, backend timeout and CoreDisplay texture exception.'
m['candidate_0_3_2']={'scope':'Only WindowServer8086:7d45; normal synchronous submissions serialized through completion, submit-ahead disabled, IOSurface writers scheduled after copy-out; no false publication on failure','preserved':'Kernel1.0.8/Accel0.2.4/framebuffer/libdrm/firmware bytes, fresh pools, witness/quarantine and5sec desktop timeout unchanged; normal apps retain original submission concurrency','validation':['Actual wrapper concurrency/recursion/error cleanup under ASan+UBSan','Actual event advance/finish/scheduling methods: successful two-part copy-out ordering, copy/GPU errors, outstanding drain','Actual installer with system mocks: immutable baseline guards, kernel/version checks, plugin replacement/backup, partial failure rollback; no suite invocation','Pool allocator/lifetime, fence/witness completion, readback, release constructor and80failed buffers regressions','Release x86_64 compile, ad-hoc signature and package hashes'],'installer':'install-windowserver.sh replaces plugin only and arms one desktop boot against preserved baseline; no full GPU suite or automatic reboot','pending':'A single targeted Dell WindowServer boot; synchronization mitigation is not a proven hardware hang cure'}
f.write_text(json.dumps(m,indent=2)+'\n')
intro='''# Candidate 0.3.2 — WindowServer-only update

The verified0.3.1 baseline remains22cases/26,000frames passed with80,020command pools reclaimed. No full-suite rerun is required. The failed desktop boot exposed a second readback stalling alongside another surface upload, then a CoreDisplay texture exception after backend failure.

This plugin serializes WindowServer's normal submissions through completion, disables its submit-ahead path, and defers surface-writing scheduling notifications until copy-out finishes. The5-second timeout and quarantine behavior remain intact. Other applications retain normal concurrency. GPU kernel, accelerator, framebuffer, firmware and libdrm remain unchanged. Local build, sanitizer/order/error/installer tests pass; hardware desktop success is still pending.

On the Dell's fallback desktop, run only:

```sh
sudo /bin/bash /Volumes/SEQOUIA/iGPU-Port/install-windowserver.sh
```

It verifies the saved hardware baseline and loaded kernel/accelerator, replaces only the Metal plugin with backup/rollback, and arms one desktop boot. It does not run GPU tests or reboot. After exit=0 and ONE desktop boot armed, reboot through this USB once. Check the laptop panel and window movement.

If black/artifacting/frozen: power off, boot through this USB again for fallback, then:

```sh
sudo /bin/bash /Volumes/SEQOUIA/iGPU-Port/collect-desktop-failure.sh
```

That saves the latest desktop attempt's boot logs and recent full WindowServer crash reports. If the desktop works, use the same read-only collector after a few minutes; avoid the old collect-desktop.sh, which also runs GPU probes. Bring back the USB after the targeted attempt.

[Evidence, primary references and implementation limits](../windowserver-0.3.2-research.md).

---

Historical instructions below are superseded by this desktop-only workflow.

'''
f=p/'README.md';f.write_text(intro+f.read_text())
status='''## Candidate 0.3.2 prepared — WindowServer-only trial

The22case/26,000frame application baseline is retained. Latest physical desktop failed: second readback and another surface upload timed out, then CoreDisplay threw while creating a texture after backend shutdown. Candidate0.3.2 serializes normal WindowServer submissions, disables submit-ahead and defers IOSurface-writer scheduling until successful copy-out. Scoped to8086:7d45 WindowServer; applications keep normal concurrency. No kernel, framebuffer, firmware or security changes. Local compile/sanitizer/order/error/installer regressions pass; target desktop success pending.

Next on fallback Dell: install-windowserver.sh, then after exit0 reboot through USB once. Installer changes only the Metal plugin and arms one desktop boot using the saved hardware baseline; no GPU suite rerun or auto-reboot. After failure, poweroff/USBfallback then collect-desktop-failure.sh; full crash reports and latest attempt window included.

'''
for f in [u/'PORT-STATUS.md',r/'ROADMAP.md']:f.write_text('# Current:0.3.2 WindowServer-only candidate\n\n'+status+'---\n\n'+f.read_text())
shutil.copy2(r/'ROADMAP.md',u/'ROADMAP.md');(v/'VALIDATION.md').write_text(status);shutil.copy2(v/'VALIDATION.md',u/'desktop-0.3.2-validation.md')
for name in ['nvmtl_vk.c','nvmtl_vk.h','NVMTLEventSync.m','nvmtl_desktop_policy.h']:
 src=r/'NullMoth/plugin'/name;shutil.copy2(src,v/name)
 old=r/'backups/desktop-0.3.2-before'/name;patch=''.join(difflib.unified_diff(old.read_text().splitlines(True),src.read_text().splitlines(True),fromfile='a/plugin/'+name,tofile='b/plugin/'+name));(v/(name+'.patch')).write_text(patch)
for src in [r/'desktop-build/plugin-0.3.2.log',p/'install-windowserver.sh',p/'BUILD-MANIFEST.json',p/'WINDOWSERVER-BASELINE-SHA256SUMS.txt',r/'desktop-sources/collect-desktop-failure.sh']:shutil.copy2(src,v/src.name)
files=sorted(x for x in p.rglob('*') if x.is_file() and not x.is_symlink() and 'reports' not in x.relative_to(p).parts and x.name!='SHA256SUMS.txt' and not x.name.startswith('._'))
(p/'SHA256SUMS.txt').write_text(''.join(hashlib.sha256(x.read_bytes()).hexdigest()+'  '+str(x.relative_to(p))+'\n' for x in files))
for src in p.rglob('*'):
 rel=src.relative_to(p)
 if 'reports' in rel.parts or src.name.startswith('._') or src.is_symlink():continue
 dst=u/'Desktop'/rel
 if src.is_dir():dst.mkdir(parents=True,exist_ok=True)
 elif not dst.exists() or src.read_bytes()!=dst.read_bytes():shutil.copy2(src,dst)
shutil.copy2(r/'desktop-sources/collect-desktop-failure.sh',u/'collect-desktop-failure.sh')
(u/'install-windowserver.sh').write_text('''#!/bin/bash
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
LOG="$HERE/windowserver-install-$(date +%Y%m%d-%H%M%S).txt"
/bin/bash "$HERE/Desktop/install-windowserver.sh" "$@" 2>&1 | tee "$LOG"
result=${PIPESTATUS[0]}
echo "WINDOWSERVER INSTALL exit=$result" | tee -a "$LOG"
exit "$result"
''')
for line in (u/'Desktop/SHA256SUMS.txt').read_text().splitlines():
 h,rel=line.split('  ',1);assert hashlib.sha256((u/'Desktop'/rel).read_bytes()).hexdigest()==h,rel
for target in [u/'Desktop/Library/GPUBundles/NVMTLDriver.bundle',u/'Desktop/Library/Extensions/NMXGPU.kext',u/'Desktop/Library/Extensions/NMXAccel.kext']:subprocess.run(['codesign','--verify','--strict',str(target)],check=True)
for name in ['install-windowserver.sh','collect-desktop-failure.sh']:subprocess.run(['/bin/bash','-n',str(u/name)],check=True)
f=u/'SHA256SUMS.json';m=json.loads(f.read_text())
for name in ['PORT-STATUS.md','ROADMAP.md','install-windowserver.sh','collect-desktop-failure.sh','windowserver-0.3.2-research.md','desktop-0.3.2-validation.md']:m[name]=hashlib.sha256((u/name).read_bytes()).hexdigest()
f.write_text(json.dumps(m,indent=2)+'\n');print('Published WindowServer candidate0.3.2:',len(files),'USB hashes verified; plugin/kernel/accel signatures verified. Baseline preserved; no hardware tests or boot changes made.')
