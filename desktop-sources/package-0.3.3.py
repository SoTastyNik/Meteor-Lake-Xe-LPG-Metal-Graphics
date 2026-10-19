from pathlib import Path
import hashlib,json,plistlib,shutil,subprocess,difflib
r=Path(__file__).resolve().parent.parent;p=r/'latitude-desktop';u=Path('/Volumes/SEQOUIA/iGPU-Port');v=r/'port-artifacts/desktop-0.3.3';v.mkdir(parents=True,exist_ok=True)
def sha(f):return hashlib.sha256(f.read_bytes()).hexdigest()
assert u.is_dir()
backup=u/'backups/desktop-0.3.3-before'
for rel in ['Desktop/Library/GPUBundles/NVMTLDriver.bundle','Desktop/Library/NullMoth/load-panel-framebuffer.sh','Desktop/Library/NullMoth/latitude-desktop-journal','Desktop/BUILD-MANIFEST.json','Desktop/README.md','Desktop/install-windowserver.sh','Desktop/SHA256SUMS.txt','collect-desktop-failure.sh','PORT-STATUS.md','ROADMAP.md','SHA256SUMS.json']:
 src=u/rel;dst=backup/rel
 if not src.exists() or dst.exists():continue
 dst.parent.mkdir(parents=True,exist_ok=True)
 if src.is_dir():shutil.copytree(src,dst)
 else:shutil.copy2(src,dst)
# Compare the complete preserved runtime, except the three deliberately changed components.
changed=['Library/GPUBundles/NVMTLDriver.bundle/','Library/NullMoth/load-panel-framebuffer.sh','Library/NullMoth/latitude-desktop-journal']
for f in (p/'Library').rglob('*'):
 rel=str(f.relative_to(p))
 if not f.is_file() or f.is_symlink() or f.name.startswith('._') or any(rel.startswith(x) for x in changed):continue
 assert f.read_bytes()==(u/'Desktop'/rel).read_bytes(),rel
for line in (p/'WINDOWSERVER-BASELINE-SHA256SUMS.txt').read_text().splitlines():
 h,rel=line.split('  ',1);assert sha(u/rel)==h,rel
b=p/'Library/GPUBundles/NVMTLDriver.bundle';info=b/'Contents/Info.plist';m=plistlib.loads(info.read_bytes());m.update(CFBundleVersion='0.3.3',CFBundleShortVersionString='0.3.3');info.write_bytes(plistlib.dumps(m));shutil.copy2(r/'desktop-build/NVMTLDriver-0.3.3',b/'Contents/MacOS/NVMTLDriver')
subprocess.run(['codesign','--force','--sign','-',str(b)],check=True)
for f in [b,p/'Library/NullMoth/latitude-desktop-journal',p/'Library/Extensions/NMXGPU.kext',p/'Library/Extensions/NMXAccel.kext']:subprocess.run(['codesign','--verify','--strict',str(f)],check=True)
for f in [b/'Contents/MacOS/NVMTLDriver',p/'Library/NullMoth/latitude-desktop-journal']:assert 'x86_64' in subprocess.check_output(['lipo','-archs',str(f)],text=True)
for f in [p/'install-windowserver.sh',p/'Library/NullMoth/load-panel-framebuffer.sh',r/'desktop-sources/collect-desktop-failure.sh']:subprocess.run(['/bin/bash','-n',str(f)],check=True)
research=r/'research/windowserver-0.3.3-research.md';shutil.copy2(research,v/'RESEARCH.md');shutil.copy2(research,u/research.name)
intro='''# Candidate0.3.3 — WindowServer startup diagnostic and bounded submission lock

The latest black-screen boot did not preserve enough evidence to locate the failure. This candidate bounds the desktop submission-lock wait, quarantines resources on failure, and adds a pre-created, synced startup journal plus early loader stages and an attempted WindowServer stack sample. This is a targeted diagnostic/lock fix; working accelerated desktop output is not yet established.

The verified22-case/26,000-frame application baseline is retained. GPU kernel, accelerator, framebuffer/claim, firmware and transport remain unchanged. No hardware suite needs repeating.

On the Dell fallback desktop:

```sh
sudo /bin/bash /Volumes/SEQOUIA/iGPU-Port/install-windowserver.sh
```

After exit=0 and ONE desktop boot armed, reboot through this USB once. The installer backs up/replaces the plugin and two capture tools, prepares the journal and arms one GPU+panel attempt. It runs no GPU tests and does not reboot automatically.

If black/frozen/artifacting, power off and boot USB again for fallback. Then collect before reinstalling:

```sh
sudo /bin/bash /Volumes/SEQOUIA/iGPU-Port/collect-desktop-failure.sh
```

The same read-only collector can capture a working desktop after a few minutes. It includes the new startup journal/sample plus recent full WindowServer crash reports. Bring the USB back for inspection.

Synced logging is best effort; disk waits and sandbox/sample permissions can still prevent capture. [Evidence, research and limits](../windowserver-0.3.3-research.md).

---

Historical instructions below are superseded by this workflow.

'''
f=p/'README.md';f.write_text(intro+f.read_text())
f=p/'BUILD-MANIFEST.json';m=json.loads(f.read_text());m['runtime_revision']='desktop-0.3.3-windowserver-startup-trace';m['stage']='Targeted startup diagnostic/host-lock fix compiled and locally checked; Dell desktop validation pending';m['built']['metal_plugin']='NVMTLDriver0.3.3: bounded WindowServer submission-lock acquisition, resource quarantine on failure, retained startup stage trace'
m['candidate_0_3_3']={'evidence':'0.3.2 failed boot12:32:04 has only live header, empty registry, no new crash or retained plugin activity; older.previous logs are not evidence for it','changes':['Monotonic recursive desktop lock deadline; failure disables backend and quarantines without submitting/freeing or foreign unlock','Pre-created0600_windowserver-owned journal; boot/thread/stage records; F_FULLFSYNC with fallback;256 plugin records/256KiB file threshold','Loader stages before claim/handoff, bounded queries and attempted stack sample, periodic log flush','Collector retains journal/previous and sample/errors; installer backs up/rolls back plugin+loader+helper'],'preserved':'22case/26000frame baseline; original kernels/UUIDs, accelerator, framebuffer/claim, transport, firmware; fresh pools and fence/witness retirement; app concurrency','limitations':['No root cause established for latest black screen','Journal sync may block/perturb timing; persistence is best effort','WindowServer sandbox or sample permission may deny access; errors retained where possible','Dell desktop validation pending'],'plugin_sha256':sha(b/'Contents/MacOS/NVMTLDriver'),'helper_sha256':sha(p/'Library/NullMoth/latitude-desktop-journal')};f.write_text(json.dumps(m,indent=2)+'\n')
status='''# Current: candidate0.3.3 ready for one targeted WindowServer boot

The0.3.2 black-screen boot lacks retained plugin/fence evidence; no exact cause is established. Candidate0.3.3 bounds the previously unbounded desktop submission-lock acquisition and adds a pre-created startup stage journal, early loader capture and an attempted WindowServer sample. Failed lock acquisition disables the backend and quarantines resources safely. Local build, signature, sanitizer, policy, error-path, installer rollback, loader and collector checks pass. Hardware desktop validation remains pending.

The verified22case/26,000frame baseline remains intact. No GPU suite rerun is requested. Kernel, accelerator, framebuffer/claim, transport and firmware remain byte-identical. On Dell fallback: install-windowserver.sh, then after exit0 reboot through USB once. After failure: poweroff/USBfallback, collect-desktop-failure.sh before reinstalling. See windowserver-0.3.3-research.md for evidence and limits.

---

'''
for f in [u/'PORT-STATUS.md',r/'ROADMAP.md']:f.write_text(status+f.read_text())
shutil.copy2(r/'ROADMAP.md',u/'ROADMAP.md')
validation={'target_tests_run':False,'desktop_verified':False,'preserved_hardware_baseline':'22cases/26000frames;80020pools reclaimed','local_passes':['x86_64 release compile and ad-hoc signature','ASan/UBSan actual submit wrapper:3000 serialized calls, recursion/error unlock, app concurrency, forced contention deadline and quarantine','ASan/UBSan journal helper prepare/rotation/0600/flush/record fields/newline normalization/symlink-mode-cap rejection','Actual loader with mocked OS: pre-claim/pre-handoff capture, stack sample, fallback preservation, load-error status','Actual installer mocks: baseline/kernel guards; success; verification, journal and partial-arm rollback restores all3files','Actual collector: new journal/sample artifacts, full recent system/user crashes, history failure retention','Actual event publication and readback method regressions','Pool lifetime30000objects/3threads and4fence/witness completion modes','Actual native release constructor effective diagnostic masks47/63/38','80failed native command-buffer regression'],'build_warnings':'335 compiler warnings; see plugin-0.3.3.log; build succeeds'}
(v/'VALIDATION.json').write_text(json.dumps(validation,indent=2)+'\n');shutil.copy2(v/'VALIDATION.json',u/'desktop-0.3.3-validation.json')
for name in ['nvmtl_vk.c','nvmtl_vk.h','NVMTLDevice.m','NVMTLObjects.m','nvmtl_desktop_wait.h','nvmtl_desktop_journal.h']:
 src=r/'NullMoth/plugin'/name;shutil.copy2(src,v/name);old=r/'backups/desktop-0.3.3-before'/name
 (v/(name+'.patch')).write_text(''.join(difflib.unified_diff(old.read_text().splitlines(True) if old.exists() else [],src.read_text().splitlines(True),fromfile='a/plugin/'+name,tofile='b/plugin/'+name)))
for src in [p/'install-windowserver.sh',p/'Library/NullMoth/load-panel-framebuffer.sh',r/'desktop-sources/latitude-desktop-journal.c',r/'desktop-sources/collect-desktop-failure.sh',r/'desktop-build/plugin-0.3.3.log',p/'BUILD-MANIFEST.json']+list((r/'desktop-sources').glob('test-*.py')):shutil.copy2(src,v/src.name)
files=sorted(x for x in p.rglob('*') if x.is_file() and not x.is_symlink() and 'reports' not in x.relative_to(p).parts and x.name!='SHA256SUMS.txt' and not x.name.startswith('._'))
(p/'SHA256SUMS.txt').write_text(''.join(sha(x)+'  '+str(x.relative_to(p))+'\n' for x in files))
for src in p.rglob('*'):
 rel=src.relative_to(p)
 if 'reports' in rel.parts or src.name.startswith('._') or src.is_symlink():continue
 dst=u/'Desktop'/rel
 if src.is_dir():dst.mkdir(parents=True,exist_ok=True)
 elif not dst.exists() or src.read_bytes()!=dst.read_bytes():shutil.copy2(src,dst)
shutil.copy2(r/'desktop-sources/collect-desktop-failure.sh',u/'collect-desktop-failure.sh')
for line in (u/'Desktop/SHA256SUMS.txt').read_text().splitlines():h,rel=line.split('  ',1);assert sha(u/'Desktop'/rel)==h,rel
for line in (p/'WINDOWSERVER-BASELINE-SHA256SUMS.txt').read_text().splitlines():h,rel=line.split('  ',1);assert sha(u/rel)==h,rel
for target in [u/'Desktop/Library/GPUBundles/NVMTLDriver.bundle',u/'Desktop/Library/NullMoth/latitude-desktop-journal']:subprocess.run(['codesign','--verify','--strict',str(target)],check=True)
f=u/'SHA256SUMS.json';m=json.loads(f.read_text())
for name in ['PORT-STATUS.md','ROADMAP.md','collect-desktop-failure.sh','windowserver-0.3.3-research.md','desktop-0.3.3-validation.json']:m[name]=sha(u/name)
f.write_text(json.dumps(m,indent=2)+'\n')
print('Published0.3.3:',len(files),'package hashes and saved22case evidence verified; kernel/accel/framebuffer/firmware/transport preserved. No target tests, installation, NVRAM changes or reboot performed.')
print('PluginSHA256',sha(b/'Contents/MacOS/NVMTLDriver'))
