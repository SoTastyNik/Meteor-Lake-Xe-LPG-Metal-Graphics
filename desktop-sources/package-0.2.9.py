from pathlib import Path
import hashlib,json,plistlib,shutil,subprocess,difflib
r=Path(__file__).resolve().parent.parent;p=r/'latitude-desktop';u=Path('/Volumes/SEQOUIA/iGPU-Port');v=r/'port-artifacts/desktop-0.2.9';v.mkdir(parents=True,exist_ok=True)
backup=u/'backups/desktop-0.2.9-before';backup.mkdir(parents=True,exist_ok=True)
for rel in ['Desktop/Library/GPUBundles/NVMTLDriver.bundle','Desktop/BUILD-MANIFEST.json','Desktop/README.md','Desktop/install-runtime.sh','Desktop/test-readback.sh','Desktop/test-and-arm-desktop.sh','Desktop/SHA256SUMS.txt','PORT-STATUS.md','ROADMAP.md']:
 src=u/rel;dst=backup/rel
 if not src.exists() or dst.exists():continue
 dst.parent.mkdir(parents=True,exist_ok=True)
 if src.is_dir():shutil.copytree(src,dst)
 else:shutil.copy2(src,dst)
b=p/'Library/GPUBundles/NVMTLDriver.bundle';f=b/'Contents/Info.plist';d=plistlib.loads(f.read_bytes());d.update(CFBundleVersion='0.2.9',CFBundleShortVersionString='0.2.9');f.write_bytes(plistlib.dumps(d));shutil.copy2(r/'desktop-build/NVMTLDriver-0.2.9',b/'Contents/MacOS'/d['CFBundleExecutable']);subprocess.run(['codesign','--force','--sign','-',str(b)],check=True);subprocess.run(['codesign','--verify','--strict',str(b)],check=True)
f=p/'BUILD-MANIFEST.json';m=json.loads(f.read_text());m['runtime_revision']='desktop-0.2.9-diagnostics';m['stage']='Controlled GPU-hang comparison; physical desktop activation disabled';m['built']['metal_plugin']='NVMTLDriver 0.2.9: opt-in direct diagnostics, phase-specific submission/readback errors and command-pool-only fresh-allocation control';m['candidate_0_2_7']['on_target']='IOKit discovery plus three 1000-frame cases pass; padded case fails at frame 745. Recovered log confirms GPU HANG 12:1:00b79797, readback VK_ERROR_DEVICE_LOST after 13072 ms and context reset. No desktop opt-in was armed.'
m['candidate_0_2_8']={
 'purpose':'Isolate command-pool lifetime versus staging lifetime without calling this a verified GPU-hang fix',
 'diagnostics':['NVMTL_DIAGNOSTIC_STDERR=1 retains filtered failure and submit/readback traces directly in each test log, independently of syslog throttling','Every Intel submission begin/queue/fence outcome is traced during explicit diagnostics; failures identify record/staging/end/fence/submit/completion phase','Kernel/IOKit events captured live; historical queries use only the current run interval','Watchdog stdout/stderr detached so sleeping grandchildren cannot keep the terminal logging pipe open'],
 'comparison':['Same three retained-resource 1000-frame warmups in all profiles, followed by the same 1920x1080/pitch7744 1000-frame case','fresh-pools: NVMTL_COMMAND_POOL_FRESH=1 bypasses command-pool cache only; completion-witness recording/checks and address-page caching stay enabled','fresh-staging: dedicated readback staging allocations; normal command-pool/witness/address-page policy retained','retained: normal policy with the same explicit diagnostics for a control run','Only one comparison per boot UUID; pending GPU opt-in rejected until reboot; no profile produces a desktop gate'],
 'guards':['--desktop installer mode and test-and-arm-desktop.sh are disabled in this diagnostic candidate','prepare-readback-boot.sh removes panel opt-in before arming a GPU-only boot; never reboots automatically'],
 'local_validation':['ASan/UBSan actual command-pool cache, logger, readback recording/failure and copy-plan tests','Mocked actual runner validates all three profile environments, same-boot retry refusal, current-run capture and no desktop gate','Mocked boot-helper and desktop-entry tests verify GPU-only opt-in and refusal when panel marker remains','Read-only collector test proves bounded report-time capture and no terminal-pipe retention','Native fault-injection regression: 80 failed command buffers complete with errors'],
 'pending':'Target comparison results and underlying GPU-hang fix; no WindowServer success claim'};f.write_text(json.dumps(m,indent=2)+'\n')
intro='''# Candidate 0.2.9 — repair and verify effective test controls

The 0.2.8 run confirms another GPU hang at frame 169, but its command-pool comparison was invalid. Release startup deliberately removes NVMTL_* environment settings, which removed both the fresh-pool switch and diagnostic logging. Requested settings in a policy file did not prove the driver used them. No pool-reuse conclusion should be drawn from that run.

This candidate preserves six exact =1 test controls only in the explicitly enabled latitude-readback-test process. Other processes and unrelated settings keep the original release scrub. The actual native release plugin constructor was tested, not just a mock of the runner: retained/fresh-pool/fresh-staging policy bits survived, while unrelated controls and controls in another process were removed.

The test now queries effective settings inside the loaded Metal driver AFTER release initialization. It prints POLICY effective=... expected=... and requires an exact match before submitting the workload. Fresh-pool runs require 0xf; retained warmups require 0xd; fresh-staging requires 0x1d. Missing/wrong policy stops the test. The runner also requires the effective-policy PASS marker. Desktop activation remains disabled.

On the Dell:

```sh
sudo /bin/bash /Volumes/SEQOUIA/iGPU-Port/install-readback.sh
```

After install exit=0, reboot through USB once, then:

```sh
sudo /bin/bash /Volumes/SEQOUIA/iGPU-Port/diagnose-readback.sh fresh-pools
```

The same three warmups precede the padded full-HD case. This run will prove fresh command pools are actually selected while completion witnesses and address-page caching stay enabled. Direct stderr diagnostics and live kernel capture remain active. Bring the USB back after the result. No desktop boot is armed, and no GPU-hang fix is claimed yet.

A second comparison needs a clean GPU boot: prepare-readback-boot.sh, reboot USB, then diagnose-readback.sh fresh-staging or retained. Do not mix variants in the same boot. No kernel, firmware, panel or security changes in this candidate. The policy bug and the persistent GPU hang are separate findings.

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
status='''## Candidate 0.2.9 effective-policy repair prepared

The latest 0.2.8 test (readback-20261018-231611) hit GPU HANG 12:1:00b79797 at frame 169. It does not test fresh pools: release initialization stripped NVMTL_* settings, including the experimental flags and direct diagnostics. The policy file only recorded intent. No conclusion about pool reuse is justified.

The fix narrowly preserves explicit controls for the named test process and adds an in-driver effective-policy query. Each workload refuses to run unless the actual post-initialization policy matches the requested profile. Tests against the real native release plugin constructor passed for all three profiles, unrelated controls and another process. Desktop activation remains disabled; target validation remains pending.

Next: install-readback.sh, reboot USB, then diagnose-readback.sh fresh-pools. No GPU-hang cure is claimed.

'''
f=u/'PORT-STATUS.md';text=f.read_text();f.write_text('# Current: 0.2.9 controlled GPU-hang comparison ready\n\n'+status+'---\n\n'+text)
f=r/'ROADMAP.md';text=f.read_text();idx=text.find('\n## ');f.write_text(text[:idx]+'\n\n'+status+text[idx:]);shutil.copy2(f,u/'ROADMAP.md');shutil.copy2(f,r/'research/desktop-roadmap-20261018.md')
(v/'VALIDATION.md').write_text(status+'\nLocal fixture outputs are stored here. Mocked test runs do not exercise Intel hardware. The 0.2.9 release plugin is x86_64 and ad-hoc signed. USB hashes/signature and shell syntax are checked separately.\n')
for script,outname in [('test-release-probe-controls.py','real-release-startup.txt'),('test-command-pool-scope.py','pool-scope.txt'),('test-diagnostic-stderr.py','direct-logger.txt'),('test-readback-recording.py','readback-recording.txt'),('test-comparison-runner.py','runner.txt'),('test-diagnostic-guards.py','guards.txt'),('test-failure-collector.py','collector.txt')]:
 with (v/outname).open('w') as out:subprocess.run(['/usr/bin/python3',str(r/'desktop-sources'/script)],stdout=out,stderr=subprocess.STDOUT,check=True)
 shutil.copy2(r/'desktop-sources'/script,v/script)
for src in [r/'NullMoth/plugin/nvmtl_vk.c',r/'NullMoth/plugin/NVMTLDevice.m',r/'NullMoth/plugin/NVMTLObjects.m',r/'NullMoth/plugin/nvmtl_probe_controls.h',r/'latitude-desktop/tools/latitude-readback-test.m',r/'desktop-build/plugin-0.2.9.log',r/'desktop-build/failure-regression-0.2.8.txt',p/'BUILD-MANIFEST.json',p/'test-readback.sh',p/'diagnose-readback.sh',p/'prepare-readback-boot.sh']:shutil.copy2(src,v/src.name)
patch=[]
for name in ['nvmtl_vk.c','NVMTLObjects.m']:
 old=r/'backups/desktop-0.2.9-before'/name;new=r/'NullMoth/plugin'/name;patch.extend(difflib.unified_diff(old.read_text().splitlines(True),new.read_text().splitlines(True),fromfile='a/NullMoth/plugin/'+name,tofile='b/NullMoth/plugin/'+name))
(v/'changes.patch').write_text(''.join(patch));shutil.copy2(v/'VALIDATION.md',u/'desktop-0.2.9-validation.md')
for line in (u/'Desktop/SHA256SUMS.txt').read_text().splitlines():
 digest,rel=line.split('  ',1);assert hashlib.sha256((u/'Desktop'/rel).read_bytes()).hexdigest()==digest,rel
subprocess.run(['codesign','--verify','--strict',str(u/'Desktop/Library/GPUBundles/NVMTLDriver.bundle')],check=True)
for name in ['diagnose-readback.sh','prepare-readback-boot.sh']:subprocess.run(['/bin/bash','-n',str(u/name)],check=True)
f=u/'SHA256SUMS.json';m=json.loads(f.read_text())
for name in ['PORT-STATUS.md','ROADMAP.md','diagnose-readback.sh','prepare-readback-boot.sh','desktop-0.2.9-validation.md']:m[name]=hashlib.sha256((u/name).read_bytes()).hexdigest()
f.write_text(json.dumps(m,indent=2)+'\n')
print('Published 0.2.9:',len(files),'USB package hashes and plugin signature verified; original reports preserved')
