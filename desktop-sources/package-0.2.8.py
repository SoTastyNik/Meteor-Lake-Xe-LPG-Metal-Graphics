from pathlib import Path
import hashlib,json,plistlib,shutil,subprocess,difflib
r=Path(__file__).resolve().parent.parent;p=r/'latitude-desktop';u=Path('/Volumes/SEQOUIA/iGPU-Port');v=r/'port-artifacts/desktop-0.2.8';v.mkdir(parents=True,exist_ok=True)
backup=u/'backups/desktop-0.2.8-before';backup.mkdir(parents=True,exist_ok=True)
for rel in ['Desktop/Library/GPUBundles/NVMTLDriver.bundle','Desktop/BUILD-MANIFEST.json','Desktop/README.md','Desktop/install-runtime.sh','Desktop/test-readback.sh','Desktop/test-and-arm-desktop.sh','Desktop/SHA256SUMS.txt','PORT-STATUS.md','ROADMAP.md']:
 src=u/rel;dst=backup/rel
 if not src.exists() or dst.exists():continue
 dst.parent.mkdir(parents=True,exist_ok=True)
 if src.is_dir():shutil.copytree(src,dst)
 else:shutil.copy2(src,dst)
b=p/'Library/GPUBundles/NVMTLDriver.bundle';f=b/'Contents/Info.plist';d=plistlib.loads(f.read_bytes());d.update(CFBundleVersion='0.2.8',CFBundleShortVersionString='0.2.8');f.write_bytes(plistlib.dumps(d));shutil.copy2(r/'desktop-build/NVMTLDriver-0.2.8',b/'Contents/MacOS'/d['CFBundleExecutable']);subprocess.run(['codesign','--force','--sign','-',str(b)],check=True);subprocess.run(['codesign','--verify','--strict',str(b)],check=True)
f=p/'BUILD-MANIFEST.json';m=json.loads(f.read_text());m['runtime_revision']='desktop-0.2.8-diagnostics';m['stage']='Controlled GPU-hang comparison; physical desktop activation disabled';m['built']['metal_plugin']='NVMTLDriver 0.2.8: opt-in direct diagnostics, phase-specific submission/readback errors and command-pool-only fresh-allocation control';m['candidate_0_2_7']['on_target']='IOKit discovery plus three 1000-frame cases pass; padded case fails at frame 745. Recovered log confirms GPU HANG 12:1:00b79797, readback VK_ERROR_DEVICE_LOST after 13072 ms and context reset. No desktop opt-in was armed.'
m['candidate_0_2_8']={
 'purpose':'Isolate command-pool lifetime versus staging lifetime without calling this a verified GPU-hang fix',
 'diagnostics':['NVMTL_DIAGNOSTIC_STDERR=1 retains filtered failure and submit/readback traces directly in each test log, independently of syslog throttling','Every Intel submission begin/queue/fence outcome is traced during explicit diagnostics; failures identify record/staging/end/fence/submit/completion phase','Kernel/IOKit events captured live; historical queries use only the current run interval','Watchdog stdout/stderr detached so sleeping grandchildren cannot keep the terminal logging pipe open'],
 'comparison':['Same three retained-resource 1000-frame warmups in all profiles, followed by the same 1920x1080/pitch7744 1000-frame case','fresh-pools: NVMTL_COMMAND_POOL_FRESH=1 bypasses command-pool cache only; completion-witness recording/checks and address-page caching stay enabled','fresh-staging: dedicated readback staging allocations; normal command-pool/witness/address-page policy retained','retained: normal policy with the same explicit diagnostics for a control run','Only one comparison per boot UUID; pending GPU opt-in rejected until reboot; no profile produces a desktop gate'],
 'guards':['--desktop installer mode and test-and-arm-desktop.sh are disabled in this diagnostic candidate','prepare-readback-boot.sh removes panel opt-in before arming a GPU-only boot; never reboots automatically'],
 'local_validation':['ASan/UBSan actual command-pool cache, logger, readback recording/failure and copy-plan tests','Mocked actual runner validates all three profile environments, same-boot retry refusal, current-run capture and no desktop gate','Mocked boot-helper and desktop-entry tests verify GPU-only opt-in and refusal when panel marker remains','Read-only collector test proves bounded report-time capture and no terminal-pipe retention','Native fault-injection regression: 80 failed command buffers complete with errors'],
 'pending':'Target comparison results and underlying GPU-hang fix; no WindowServer success claim'};f.write_text(json.dumps(m,indent=2)+'\n')
intro='''# Candidate 0.2.8 — controlled GPU-hang comparison

The recovered 0.2.7 log confirms a GPU hang during the padded readback wait: `12:1:00b79797`, then Vulkan device loss (-4) after 13.1 seconds and a context reset. The untouched 0xA5 destination follows the failed readback; it is not evidence of a proven row-stride arithmetic defect. IOKit discovery and three 1,000-frame cases passed before this failure.

This diagnostic candidate adds direct error logs and isolated lifetime controls. It is not a confirmed fix for the GPU hang. WindowServer activation is disabled during this comparison; the installer accepts readback-only mode.

On the Dell:

```sh
sudo /bin/bash /Volumes/SEQOUIA/iGPU-Port/install-readback.sh
```

After install exit=0, reboot through USB once, even if macOS shows no extension-update prompt. Then run:

```sh
sudo /bin/bash /Volumes/SEQOUIA/iGPU-Port/diagnose-readback.sh fresh-pools
```

The run keeps the original three 1,000-frame warmups, then repeats the failing padded full-HD case with fresh command pools. Completion-witness commands/checks and address-page caching stay enabled. The older NVMTL_POOL_REUSE=0 switch disabled those mechanisms too; this new comparison uses a narrower NVMTL_COMMAND_POOL_FRESH switch instead.

Each case prints progress every 50 frames, stops on the first failure and saves detailed stderr directly alongside live kernel events in Desktop/reports/readback-TIMESTAMP. Historical lookup is limited to the current run. Test clients retain exact late submit/fence/readback IDs and error phases without relying on syslog throttling. Sleeping watchdog children no longer hold the terminal logging pipe open.

Bring the USB report back after this first comparison. It does not arm the desktop or automatically prepare another test boot. To compare a different profile later, first prepare a clean GPU-only boot:

```sh
sudo /bin/bash /Volumes/SEQOUIA/iGPU-Port/prepare-readback-boot.sh
```

Reboot through USB, then use `diagnose-readback.sh fresh-staging` (only readback staging is fresh) or `diagnose-readback.sh retained` (normal resources with the same diagnostics). Do not run variants back-to-back on the same GPU boot; the runner refuses that. A passing fresh-pool result by itself is not proof that pool reuse caused the original hang, especially if added diagnostics affect timing. A control/repeat comparison is needed.

No new kernel, firmware, panel-registration or security changes. GPU remains 1.0.7, accelerator 0.2.4, panel/claim 0.2.3 and libdrm remains the 0.2.7 IOKit correction. Correct accelerated WindowServer composition and a GPU-hang fix remain pending.

---

## Historical candidate notes

'''
f=p/'README.md';f.write_text(intro+f.read_text())
for name in ['install-runtime.sh','test-readback.sh','test-and-arm-desktop.sh','diagnose-readback.sh','prepare-readback-boot.sh','collect-readback-failure.sh']:subprocess.run(['/bin/bash','-n',str(p/name)],check=True)
files=sorted(x for x in p.rglob('*') if x.is_file() and not x.is_symlink() and 'reports' not in x.relative_to(p).parts and x.name!='SHA256SUMS.txt' and not x.name.startswith('._'));(p/'SHA256SUMS.txt').write_text(''.join(hashlib.sha256(x.read_bytes()).hexdigest()+'  '+str(x.relative_to(p))+'\n' for x in files))
for src in p.rglob('*'):
 rel=src.relative_to(p)
 if 'reports' in rel.parts or src.name.startswith('._') or src.is_symlink():continue
 dst=u/'Desktop'/rel
 if src.is_dir():dst.mkdir(parents=True,exist_ok=True)
 elif not dst.exists() or src.read_bytes()!=dst.read_bytes():shutil.copy2(src,dst)
for name in ['diagnose-readback.sh','prepare-readback-boot.sh']:
 (u/name).write_text('''#!/bin/bash
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
LOG="$HERE/'''+name[:-3]+'''-$(date +%Y%m%d-%H%M%S).txt"
/bin/bash "$HERE/Desktop/'''+name+'''" "$@" 2>&1 | tee "$LOG"
result=${PIPESTATUS[0]}
echo "'''+name[:-3]+''' exit=$result" | tee -a "$LOG"
exit "$result"
''')
status='''## Candidate 0.2.8 diagnostic comparison prepared

Recovered 0.2.7 evidence confirms GPU HANG 12:1:00b79797 and readback VK_ERROR_DEVICE_LOST after 13,072 ms, followed by a context reset. IOKit access passed; correct WindowServer remains unverified.

The USB now contains plugin 0.2.8 with direct per-test diagnostics and a command-pool-only fresh-allocation switch. The same three warmups precede a single retained/fresh-pool/fresh-staging comparison. Witnesses and address-page caching stay on in the fresh-command-pool case. The runner checks boot UUIDs and refuses another comparison in the same boot. Kernel events are captured live and historical lookup starts at the current run. Desktop activation is disabled in this candidate; no GPU-hang cure is claimed.

Next target step: install-readback.sh, reboot USB once, then `sudo /bin/bash /Volumes/SEQOUIA/iGPU-Port/diagnose-readback.sh fresh-pools`. Return the first report before selecting the next clean-boot variant. Further variants require prepare-readback-boot.sh and a USB reboot. Full instructions: Desktop/README.md.

'''
f=u/'PORT-STATUS.md';text=f.read_text();f.write_text('# Current: 0.2.8 controlled GPU-hang comparison ready\n\n'+status+'---\n\n'+text)
f=r/'ROADMAP.md';text=f.read_text();idx=text.find('\n## ');f.write_text(text[:idx]+'\n\n'+status+text[idx:]);shutil.copy2(f,u/'ROADMAP.md');shutil.copy2(f,r/'research/desktop-roadmap-20261018.md')
(v/'VALIDATION.md').write_text(status+'\nLocal fixture outputs are stored here. Mocked test runs do not exercise Intel hardware. The 0.2.8 release plugin is x86_64 and ad-hoc signed. USB hashes/signature and shell syntax are checked separately.\n')
for script,outname in [('test-command-pool-scope.py','pool-scope.txt'),('test-diagnostic-stderr.py','direct-logger.txt'),('test-readback-recording.py','readback-recording.txt'),('test-comparison-runner.py','runner.txt'),('test-diagnostic-guards.py','guards.txt'),('test-failure-collector.py','collector.txt')]:
 with (v/outname).open('w') as out:subprocess.run(['/usr/bin/python3',str(r/'desktop-sources'/script)],stdout=out,stderr=subprocess.STDOUT,check=True)
 shutil.copy2(r/'desktop-sources'/script,v/script)
for src in [r/'NullMoth/plugin/nvmtl_vk.c',r/'NullMoth/plugin/NVMTLDevice.m',r/'desktop-build/plugin-0.2.8.log',r/'desktop-build/failure-regression-0.2.8.txt',p/'BUILD-MANIFEST.json',p/'test-readback.sh',p/'diagnose-readback.sh',p/'prepare-readback-boot.sh']:shutil.copy2(src,v/src.name)
patch=[]
for name in ['nvmtl_vk.c','NVMTLDevice.m']:
 old=r/'backups/desktop-0.2.8-before'/name;new=r/'NullMoth/plugin'/name;patch.extend(difflib.unified_diff(old.read_text().splitlines(True),new.read_text().splitlines(True),fromfile='a/NullMoth/plugin/'+name,tofile='b/NullMoth/plugin/'+name))
(v/'changes.patch').write_text(''.join(patch));shutil.copy2(v/'VALIDATION.md',u/'desktop-0.2.8-validation.md')
for line in (u/'Desktop/SHA256SUMS.txt').read_text().splitlines():
 digest,rel=line.split('  ',1);assert hashlib.sha256((u/'Desktop'/rel).read_bytes()).hexdigest()==digest,rel
subprocess.run(['codesign','--verify','--strict',str(u/'Desktop/Library/GPUBundles/NVMTLDriver.bundle')],check=True)
for name in ['diagnose-readback.sh','prepare-readback-boot.sh']:subprocess.run(['/bin/bash','-n',str(u/name)],check=True)
f=u/'SHA256SUMS.json';m=json.loads(f.read_text())
for name in ['PORT-STATUS.md','ROADMAP.md','diagnose-readback.sh','prepare-readback-boot.sh','desktop-0.2.8-validation.md']:m[name]=hashlib.sha256((u/name).read_bytes()).hexdigest()
f.write_text(json.dumps(m,indent=2)+'\n')
print('Published 0.2.8:',len(files),'USB package hashes and plugin signature verified; original reports preserved')
