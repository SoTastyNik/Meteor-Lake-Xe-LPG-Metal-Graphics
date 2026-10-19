from pathlib import Path
import hashlib,json,plistlib,shutil,subprocess,difflib
r=Path(__file__).resolve().parent.parent;p=r/'latitude-desktop';u=Path('/Volumes/SEQOUIA/iGPU-Port');v=r/'port-artifacts/desktop-0.3.0';v.mkdir(parents=True,exist_ok=True)
assert u.is_dir()
backup=u/'backups/desktop-0.3.0-before'
for rel in ['Desktop/Library/GPUBundles/NVMTLDriver.bundle','Desktop/tools/latitude-readback-test','Desktop/BUILD-MANIFEST.json','Desktop/README.md','Desktop/install-runtime.sh','Desktop/test-readback.sh','Desktop/test-and-arm-desktop.sh','Desktop/diagnose-readback.sh','Desktop/SHA256SUMS.txt','PORT-STATUS.md','ROADMAP.md']:
 src=u/rel;dst=backup/rel
 if not src.exists() or dst.exists():continue
 dst.parent.mkdir(parents=True,exist_ok=True)
 if src.is_dir():shutil.copytree(src,dst)
 else:shutil.copy2(src,dst)
b=p/'Library/GPUBundles/NVMTLDriver.bundle';f=b/'Contents/Info.plist';d=plistlib.loads(f.read_bytes());d.update(CFBundleVersion='0.3.0',CFBundleShortVersionString='0.3.0');f.write_bytes(plistlib.dumps(d));shutil.copy2(r/'desktop-build/NVMTLDriver-0.3.0',b/'Contents/MacOS'/d['CFBundleExecutable'])
for target in [b,p/'tools/latitude-readback-test']:
 subprocess.run(['codesign','--force','--sign','-',str(target)],check=True);subprocess.run(['codesign','--verify','--strict',str(target)],check=True)
checks=[('test-pool-lifetime.py','pool-lifetime.txt'),('test-pool-completion.py','pool-completion.txt'),('test-release-probe-controls.py','release-policy.txt'),('test-fresh-runner.py','hardware-gate-fixtures.txt'),('test-readback-recording.py','readback-regression.txt'),('test-diagnostic-stderr.py','logger-regression.txt')]
for script,name in checks:
 with (v/name).open('w') as out:subprocess.run(['/usr/bin/python3',str(r/'desktop-sources'/script)],stdout=out,stderr=subprocess.STDOUT,check=True)
 shutil.copy2(r/'desktop-sources'/script,v/script)
for f in p.glob('*.sh'):subprocess.run(['/bin/bash','-n',str(f)],check=True)
f=p/'BUILD-MANIFEST.json';m=json.loads(f.read_text());m['stage']='Fresh-pool enforced candidate compiled; full 22-case target validation and accelerated physical desktop remain pending';m['runtime_revision']='desktop-0.3.0-fresh-pool-enforced';m['built']['metal_plugin']='NVMTLDriver 0.3.0: permanently fresh command pools, fence/witness-gated immediate destruction, lifetime counters and full 22-case hardware gate'
m['candidate_0_3_0']={
 'policy':'Every command-pool object is newly created; command-pool handle cache/recycling removed. No environment opt-out. Normal, counter-reset, prologue and dummy initialization allocations use the common allocator. Queue creation no longer allocates an unused pool.',
 'cleanup':'Completed pools are destroyed within completion processing, before the wait returns; destruction frees their command buffers. Recording/allocate/begin/end/fence-create failures clean up unsubmitted pools immediately. Pending or uncertain submissions are quarantined and disable/fail the backend/gate; no unsafe timeout reclamation.',
 'unchanged':'Completion witnesses and address-page caching remain enabled as in the passing fresh-pool target comparison. Readback staging, kernel, firmware, framebuffer and security policy unchanged.',
 'telemetry':'created, destroyed, live, peak, quarantined, pending, completed, abandoned. Every successful target case must have created=destroyed=completed+abandoned and zero live/pending/quarantined; progress records process resident bytes. This does not assert that every other allocator/cache in the driver is leak-free.',
 'evidence':'Verified reports readback-20261018-232358 (fresh pools, 4000 frames pass) and 232908 (retained pools, submission #305 render fence lost at padded frame101). Adopted workaround; underlying mechanism and long-term stability unproven.',
 'gate':'22 cases, 11 per route (IOKit then direct), 1000 iterations per worker. Policy 0x2f, or 0x3f for fresh staging. Exact pixels/padding, IOSurface backing, route counters, zero-live pool cleanup, current-run hang check and bounded history required. Only one suite per boot. test-and-arm runs the full suite and verifies same-invocation proof, boot UUID and installed binary hashes before one-shot GPU/panel arming; partial arming failure clears both. No automatic reboot.',
 'local_validation':['x86_64 Sequoia release driver/tool compile; ad-hoc signatures verified','Actual allocator/retirement under ASan+UBSan: 30000 lifetimes across three threads, allocation/begin failure cleanup and pending-pool quarantine','Actual submit_finish under ASan+UBSan: main/prologue/reset success cleanup, timeout/device-loss/witness-failure no unsafe free, no double completion','Real native release constructor: fresh policy unconditional in test and other processes; zero opt-out ignored','Mocked actual 22-case runner and arm script: pass plus missing-policy, missing-cleanup, GPU-hang, historical-capture, missing/stale gate and partial-arm failure cases','Actual readback and release-logger regressions; native 80 failed command buffers regression','Native Apple Metal harness smoke test, explicitly not Intel hardware validation'],
 'pending':'Install on Dell, fresh USB GPU-only boot, full 22-case target test; only after passing, a separate one-shot accelerated WindowServer/panel test and longer hardware soak.'};f.write_text(json.dumps(m,indent=2)+'\n')
intro='''# Candidate 0.3.0 — fresh-pool enforced

Command-pool recycling is removed for every queue and helper path. Every submission gets a newly created pool; successful completion destroys it and all its command buffers before returning. Unsubmitted pools are destroyed on abandonment/failure. Timeout, device-loss or missing-witness resources remain quarantined, stop the backend and fail the gate, because completion is uncertain. Address-page caching and completion witnesses remain enabled.

The verified fresh-pool comparison passed 4,000 frames; the retained control lost the render fence at submission #305, padded frame101. This supports the permanent workaround. It does not prove the cause, long-term stability, or accelerated WindowServer output. Candidate 0.3.0 has compiled and passed local lifetime/failure/gate tests; its target checklist is still pending.

On the Dell, install:

```sh
sudo /bin/bash /Volumes/SEQOUIA/iGPU-Port/install-readback.sh
```

After install exit=0, reboot through this USB once. Then run:

```sh
sudo /bin/bash /Volumes/SEQOUIA/iGPU-Port/test-and-arm-desktop.sh
```

This runs all 22 cases at 1,000 iterations per worker: raw/render small, full-HD, padded, repeated forced-fresh pools, fresh staging, fresh textures, independent queues, serial shared-texture handoff, RGBA IOSurface and BGRA IOSurface, through both IOKit and direct access. Every case checks actual loaded policy, exact pixels/padding and transport; surface cases also check published backing bytes. Pool counters must balance with zero live/pending/quarantined pools. Resident-memory progress is retained in the logs for soak analysis; other allocator caches are outside this pool-balance guarantee.

Only a passing same-invocation suite with the same boot UUID and binary hashes arms GPU+panel for one desktop boot. The script does not reboot. After its explicit success message, reboot through this USB when ready. A suite failure leaves desktop unarmed. Bring back the saved report. For another suite, prepare-readback-boot.sh and reboot USB first. If a desktop boot artifacts/hangs, power off and boot this USB again for firmware-display fallback; do not repeatedly reinstall.

The historical `fresh-pools` diagnostic is now a focused test of the permanent policy; the retained-pool profile is removed. Policy bits are 0x2f for normal tests and 0x3f with fresh staging; all other release processes also enforce fresh pools. Numeric Vulkan handle values may be reused by the Vulkan allocator after object destruction; no old pool object or command buffer is recycled by this driver.

Pool destruction follows the Vulkan requirement that command buffers are no longer pending: [vkDestroyCommandPool](https://docs.vulkan.org/refpages/latest/refpages/source/vkDestroyCommandPool.html), [vkWaitForFences](https://docs.vulkan.org/refpages/latest/refpages/source/vkWaitForFences.html).

---

Historical candidate notes below describe older packages and are superseded by the steps above.

'''
f=p/'README.md';f.write_text(intro+f.read_text())
status='''## Candidate 0.3.0 fresh-pool enforced prepared

The master plugin now creates fresh command pools everywhere and destroys completed pools immediately after fence/witness completion. Pool cache/pop/push paths are removed; queue initialization no longer leaks an unused pool, and dummy initialization uses the common tracked allocator. Unsubmitted allocations clean up promptly. Uncertain GPU completion is quarantined and blocks the hardware gate.

Local compilation, sanitizer lifetime/completion checks, release constructor policy checks and mocked full 22-case/arming guards pass. USB signatures and hashes are verified. These are local checks; 0.3.0 has not yet passed the Dell hardware checklist or accelerated WindowServer/panel test.

Next on Dell: install-readback.sh; after exit=0 reboot USB once; then test-and-arm-desktop.sh. The script runs all 22 cases (1000 iterations each worker) and arms one desktop boot only after the current-run gate passes. No automatic reboot. Keep using the one-shot fallback after a failed panel boot.

'''
for f in [u/'PORT-STATUS.md',r/'ROADMAP.md']:
 old=f.read_text();f.write_text('# Current: 0.3.0 fresh-pool enforced candidate\n\n'+status+'---\n\n'+old)
shutil.copy2(r/'ROADMAP.md',u/'ROADMAP.md')
validation=status+'\nValidation logs and frozen source files are stored in '+str(v)+'. Target hardware validation remains pending. No firmware, kernel, SIP or framebuffer changes in 0.3.0.\n'
(v/'VALIDATION.md').write_text(validation);shutil.copy2(v/'VALIDATION.md',u/'desktop-0.3.0-validation.md')
for name in ['plugin-0.3.0.log','readback-build-0.3.0.log','failure-regression-0.3.0.txt','native-harness-0.3.0.txt']:shutil.copy2(r/'desktop-build'/name,v/name)
for src in [r/'NullMoth/plugin/nvmtl_vk.c',r/'NullMoth/plugin/nvmtl_vk.h',r/'NullMoth/plugin/NVMTLDevice.m',p/'tools/latitude-readback-test.m',p/'BUILD-MANIFEST.json',p/'test-readback.sh',p/'test-and-arm-desktop.sh']:shutil.copy2(src,v/src.name)
patch=[]
for name in ['nvmtl_vk.c','nvmtl_vk.h']:
 old=r/'backups/desktop-0.2.10-before'/name;new=r/'NullMoth/plugin'/name;patch.extend(difflib.unified_diff(old.read_text().splitlines(True),new.read_text().splitlines(True),fromfile='a/NullMoth/plugin/'+name,tofile='b/NullMoth/plugin/'+name))
(v/'changes.patch').write_text(''.join(patch))
files=sorted(x for x in p.rglob('*') if x.is_file() and not x.is_symlink() and 'reports' not in x.relative_to(p).parts and x.name!='SHA256SUMS.txt' and not x.name.startswith('._'))
(p/'SHA256SUMS.txt').write_text(''.join(hashlib.sha256(x.read_bytes()).hexdigest()+'  '+str(x.relative_to(p))+'\n' for x in files))
for src in p.rglob('*'):
 rel=src.relative_to(p)
 if 'reports' in rel.parts or src.name.startswith('._') or src.is_symlink():continue
 dst=u/'Desktop'/rel
 if src.is_dir():dst.mkdir(parents=True,exist_ok=True)
 elif not dst.exists() or src.read_bytes()!=dst.read_bytes():shutil.copy2(src,dst)
for line in (u/'Desktop/SHA256SUMS.txt').read_text().splitlines():
 digest,rel=line.split('  ',1);assert hashlib.sha256((u/'Desktop'/rel).read_bytes()).hexdigest()==digest,rel
for target in [u/'Desktop/Library/GPUBundles/NVMTLDriver.bundle',u/'Desktop/tools/latitude-readback-test']:subprocess.run(['codesign','--verify','--strict',str(target)],check=True)
f=u/'SHA256SUMS.json';m=json.loads(f.read_text())
for name in ['PORT-STATUS.md','ROADMAP.md','desktop-0.3.0-validation.md']:m[name]=hashlib.sha256((u/name).read_bytes()).hexdigest()
f.write_text(json.dumps(m,indent=2)+'\n');print('Published 0.3.0 fresh-pool enforced:',len(files),'USB file hashes verified; driver/tool signatures verified; existing reports preserved')
