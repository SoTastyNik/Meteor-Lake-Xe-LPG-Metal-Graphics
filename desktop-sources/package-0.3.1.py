from pathlib import Path
import hashlib,json,plistlib,shutil,subprocess,difflib
r=Path(__file__).resolve().parent.parent;p=r/'latitude-desktop';u=Path('/Volumes/SEQOUIA/iGPU-Port');v=r/'port-artifacts/desktop-0.3.1';v.mkdir(parents=True,exist_ok=True)
backup=u/'backups/desktop-0.3.1-before'
for rel in ['Desktop/Library/Extensions/NMXGPU.kext','Desktop/BUILD-MANIFEST.json','Desktop/README.md','Desktop/install-runtime.sh','Desktop/test-readback.sh','Desktop/test-and-arm-desktop.sh','Desktop/SHA256SUMS.txt','PORT-STATUS.md','ROADMAP.md']:
 src=u/rel;dst=backup/rel
 if not src.exists() or dst.exists():continue
 dst.parent.mkdir(parents=True,exist_ok=True)
 if src.is_dir():shutil.copytree(src,dst)
 else:shutil.copy2(src,dst)
b=p/'Library/Extensions/NMXGPU.kext';f=b/'Contents/Info.plist';m=plistlib.loads(f.read_bytes());m.update(CFBundleVersion='1.0.8',CFBundleShortVersionString='1.0.8');f.write_bytes(plistlib.dumps(m));shutil.copy2(r/'desktop-build/NMXGPU-1.0.8',b/'Contents/MacOS/NMXGPU')
subprocess.run(['codesign','--force','--sign','-',str(b)],check=True);subprocess.run(['codesign','--verify','--strict',str(b)],check=True)
uuid=subprocess.check_output(['xcrun','dwarfdump','--uuid',str(b/'Contents/MacOS/NMXGPU')],text=True).split()[1];(p/'NMXGPU-UUID.txt').write_text(uuid+'\n')
for name in ['test-woken-wait.py','test-guc-gate.py','test-failure-collector.py']:
 with (v/(name[:-3]+'.txt')).open('w') as out:subprocess.run(['/usr/bin/python3',str(r/'desktop-sources'/name)],stdout=out,stderr=subprocess.STDOUT,check=True)
 shutil.copy2(r/'desktop-sources'/name,v/name)
for f in p.glob('*.sh'):subprocess.run(['/bin/bash','-n',str(f)],check=True)
research='''# 0.3.1 — GuC wait compatibility fix after verified 0.3.0 hang

## Target evidence

Report readback-20261018-235331 loaded NVMTLDriver0.3.0 and verified actual policy0x2f, including permanent fresh pools. GPU registration worked after the explicit GPU-only boot. First four cases passed 1000 frames each: small raw, small render, full-HD render, padded full-HD. Each ended created=destroyed, zero live/pending/quarantined, peak1. Thus fresh allocation and prompt successful-completion cleanup were exercised on target.

At23:54:50.264, after the padded process finished and before the next process connected, kernel logged GuC TLB invalidation response timeout for seqno1. The fifth case subsequently hung on upload submission#1285 at zero-based frame428. Its preceding readback#428 completed, and that frame's render had not begun. QueueSubmit returned0; fence returned-4 after10798ms. Kernel reported rcs0 request12:2574 not yet started and GPU HANG12:1:00b79797. Pool counters1286created/1285destroyed/1quarantined show the uncertain pool was retained as designed. No desktop gate/activation occurred.

Fresh pools are insufficient as a complete hardware-stability fix. The earlier passing comparison was too short to establish long-term stability or isolate a root cause. The TLB error before the failing process makes kernel teardown/invalidation synchronization an investigation priority; it does not prove causation.

## Research and reproduced defect

The i915 invalidation path waits on WQ_FLAG_WOKEN using must_wait_woken, then schedule_timeout. Linux's woken callback both marks the flag and invokes the task wake machinery. The FreeBSD LinuxKPI callback in this port marked WOKEN and signaled the sleep channel, but did not persist TASK_WAKING. Its schedule_timeout checks TASK_WAKING under that channel lock before registering sleep. A reply between the outer flag check and registration could therefore signal an empty channel, then the waiter sleeps to expiry despite the flag being set.

The new override/src/linux_schedule.c retains the existing lock, WOKEN flag and signal; for matching task states it also sets TASK_WAKING under the same lock, following the port's existing wake_up_task protocol. This closes the reproduced pre-enrollment wake gap while leaving the timeout duration, actual GPU acknowledgement requirement and quarantine behavior intact. The common scheduler fix is used by all matching woken-callback users; the LinuxKPI impact is broader than one i915 call site. True missing hardware replies can still time out.

The actual old/patched woken callbacks, actual schedule_timeout, and actual i915 must_wait_woken are extracted into a deterministic scheduler fixture. The old version reproduces false expiry in the pre-enrollment race. Patched version preserves positive remaining time. 100000 total scenarios cover old/new paths, wake before flag check, pre-enrollment wake, registered wake, spurious wake then real response, and genuine timeout; ASan/UBSan pass. This verifies a software race fix, not a Dell hang cure. Kernel1.0.8 compiles, links438existing objects and introduces no new undefined symbols versus1.0.7.

Primary source references:
- [Linux i915 invalidation waiter](https://github.com/torvalds/linux/blob/master/drivers/gpu/drm/i915/gt/uc/intel_guc_submission.c)
- [Linux wait/woken callback](https://github.com/torvalds/linux/blob/master/kernel/sched/wait.c)
- [FreeBSD LinuxKPI scheduler and woken callback](https://github.com/freebsd/freebsd-src/blob/main/sys/compat/linuxkpi/common/src/linux_schedule.c)

## Candidate and gate

Candidate0.3.1 carries NMXGPU1.0.8, unchanged NVMTLDriver0.3.0 fresh-pool implementation and unchanged firmware/framebuffer/security settings. Runtime expects kernel1.0.8 and the exact built Mach-O UUID, compares installed kernel/plugin/libdrm with the USB, and includes all three hashes in the same-invocation gate. The suite now rejects kernel TLB invalidation timeouts as well as hangs/resets. Its parser requires timestamped kernel records, excluding filter headers and log-command metadata that mention GPU HANG. Such metadata caused a false-positive match in the old parser, though the latest report contains a real hang as well. The full22case hardware gate remains required; no auto-reboot.

Next target steps: install-readback.sh, reboot USB once, test-and-arm-desktop.sh. Candidate0.3.1 hardware and accelerated WindowServer/panel results remain pending. Do not infer stable physical display from local build or sanitizer results.
'''
(v/'RESEARCH.md').write_text(research);(r/'research/verified-0.3.1-guc-wake-fix.md').write_text(research);(u/'fresh-pool-guc-research.md').write_text(research)
f=p/'BUILD-MANIFEST.json';m=json.loads(f.read_text());m['runtime_revision']='desktop-0.3.1-guc-wake-fix';m['stage']='NMXGPU1.0.8 wake-race fix compiled; target22case/desktop validation pending';m['built']['kernel']['revision']='1.0.8: LinuxKPI woken callback persists matching TASK_WAKING under sleep-channel lock; 1.0.7 capture retained';m['built']['kernel']['uuid']=uuid
m['candidate_0_3_0']['on_target']='readback-235331:4x1000frames pass with exact pool balance; then GuC TLB invalidation timeout before fifth process; fifth case upload#1285 fence lost at frame428. Fresh pools alone insufficient. No desktop armed.'
m['candidate_0_3_1']={'fix':'LinuxKPI wake callback now persists matching task wake state under its existing sleep-channel lock; resolves reproduced lost-wakeup race before schedule_timeout registers its sleeper','scope':'Kernel shared woken-callback path; all command pools remain fresh. Plugin binary unchanged0.3.0; no new firmware, framebuffer or security settings','evidence':'ASan/UBSan actual wake/schedule_timeout/i915 waiter fixture reproduces old false timeout;100000old/new scenarios pass; no claim that observed hardware hang cause is proven','gate':'Loaded kernel1.0.8 with exact UUID required; installed kernel hash also bound into proof. Per-case live and final historical timestamped-kernel events reject TLB timeouts/hangs/resets; log-filter and log-command metadata ignored. Full22cases required.','pending':'Target install/preflight, fresh USB boot, full22case suite, then separate physical WindowServer/panel test'}
f.write_text(json.dumps(m,indent=2)+'\n')
intro='''# Candidate 0.3.1 — GuC wake-race fix

The latest0.3.0 target test passed4,000frames with balanced fresh command-pool destruction, then recorded a GuC TLB-invalidation timeout before the fifth process. That process subsequently lost an upload fence at frame428. Fresh pools remain enforced, but are insufficient to establish GPU stability.

Kernel1.0.8 fixes a reproduced LinuxKPI missed-wakeup race: a GuC reply arriving before the sleeper registers now leaves a task wake state that schedule_timeout observes under the same lock. Local sanitizer tests reproduce the old false timeout and pass100,000scenarios with the fix, including real timeout behavior. Hardware causation and stability remain unproven. NVMTLDriver remains0.3.0 because its binary is unchanged.

On the Dell:

```sh
sudo /bin/bash /Volumes/SEQOUIA/iGPU-Port/install-readback.sh
```

After install exit=0, reboot through this USB once, then:

```sh
sudo /bin/bash /Volumes/SEQOUIA/iGPU-Port/test-and-arm-desktop.sh
```

The full22case suite checks loaded NMXGPU1.0.8 and its exact build UUID before workloads. Any recorded kernel TLB timeout/hang/reset blocks the gate. Same-invocation proof binds the kernel, Metal plugin and libdrm hashes before one-shot GPU+panel arming. It never reboots automatically. Surface/WindowServer stability remains a separate test after the gate passes.

If the suite fails, collect-readback-failure.sh before reinstalling; logs save automatically as well. After failed desktop output, power off and boot USB again for fallback, then collect-desktop-failure.sh. [Detailed evidence and primary references](../fresh-pool-guc-research.md).

---

Historical candidate notes below are superseded by the steps above.

'''
f=p/'README.md';f.write_text(intro+f.read_text())
status='''## Candidate0.3.1 prepared: NMXGPU1.0.8 GuC wait compatibility fix

The verified0.3.0 test passed4,000frames with zero live command pools. A GuC TLB-invalidation timeout preceded the fifth process, which later hung on upload#1285 at frame428. Fresh pools remain enabled but do not establish complete stability.

A deterministic test of actual scheduler/i915 wait code reproduced a pre-enrollment lost wake in the LinuxKPI woken callback. Kernel1.0.8 persists the task wake state under the sleep-channel lock.100,000sanitizer scenarios and438-object kernel link pass; no new undefined symbols. This fixes a verified software race; target hang causation and hardware validation remain pending.

Next: install-readback.sh; after exit=0 reboot USB once; test-and-arm-desktop.sh. Full22case gate now requires the loaded1.0.8UUID and rejects timestamped kernel TLB errors/hangs/resets. Log-filter/command metadata are excluded. Driver/plugin/firmware/display policies otherwise unchanged; no automatic reboot. Research: fresh-pool-guc-research.md.

'''
for f in [u/'PORT-STATUS.md',r/'ROADMAP.md']:
 f.write_text('# Current:0.3.1 GuC wait compatibility candidate\n\n'+status+'---\n\n'+f.read_text())
shutil.copy2(r/'ROADMAP.md',u/'ROADMAP.md');(v/'VALIDATION.md').write_text(status);shutil.copy2(v/'VALIDATION.md',u/'desktop-0.3.1-validation.md')
src=Path('/Users/ved/igpu-build/kpi/freebsd-src/sys/compat/linuxkpi/common/src/linux_schedule.c');new=r/'NullMoth/gpu-port/xkpi/override/src/linux_schedule.c';(v/'scheduler.patch').write_text(''.join(difflib.unified_diff(src.read_text().splitlines(True),new.read_text().splitlines(True),fromfile='a/linux_schedule.c',tofile='b/override/src/linux_schedule.c')))
for f in [new,r/'desktop-build/linux-schedule-0.3.1.log',r/'desktop-build/kernel-link-1.0.8.log',r/'desktop-sources/fix-woken-wait.py',r/'desktop-sources/link-kernel-1.0.8.py',p/'test-readback.sh',p/'test-and-arm-desktop.sh',p/'BUILD-MANIFEST.json']:shutil.copy2(f,v/f.name)
files=sorted(x for x in p.rglob('*') if x.is_file() and not x.is_symlink() and 'reports' not in x.relative_to(p).parts and x.name!='SHA256SUMS.txt' and not x.name.startswith('._'))
(p/'SHA256SUMS.txt').write_text(''.join(hashlib.sha256(x.read_bytes()).hexdigest()+'  '+str(x.relative_to(p))+'\n' for x in files))
for src in p.rglob('*'):
 rel=src.relative_to(p)
 if 'reports' in rel.parts or src.name.startswith('._') or src.is_symlink():continue
 dst=u/'Desktop'/rel
 if src.is_dir():dst.mkdir(parents=True,exist_ok=True)
 elif not dst.exists() or src.read_bytes()!=dst.read_bytes():shutil.copy2(src,dst)
for line in (u/'Desktop/SHA256SUMS.txt').read_text().splitlines():
 h,rel=line.split('  ',1);assert hashlib.sha256((u/'Desktop'/rel).read_bytes()).hexdigest()==h,rel
for target in [u/'Desktop/Library/Extensions/NMXGPU.kext',u/'Desktop/Library/GPUBundles/NVMTLDriver.bundle']:subprocess.run(['codesign','--verify','--strict',str(target)],check=True)
f=u/'SHA256SUMS.json';m=json.loads(f.read_text())
for name in ['PORT-STATUS.md','ROADMAP.md','fresh-pool-guc-research.md','desktop-0.3.1-validation.md']:m[name]=hashlib.sha256((u/name).read_bytes()).hexdigest()
f.write_text(json.dumps(m,indent=2)+'\n');print('Published candidate0.3.1 / NMXGPU1.0.8:',len(files),'USB hashes and kernel/plugin signatures verified; reports preserved; target tests pending')
