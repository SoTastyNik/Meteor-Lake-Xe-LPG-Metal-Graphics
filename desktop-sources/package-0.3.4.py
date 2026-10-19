from pathlib import Path
import hashlib,json,plistlib,shutil,subprocess,difflib
r=Path(__file__).resolve().parent.parent;p=r/'latitude-desktop';u=Path('/Volumes/SEQOUIA/iGPU-Port');v=r/'port-artifacts/desktop-0.3.4';v.mkdir(parents=True,exist_ok=True)
def sha(f):return hashlib.sha256(f.read_bytes()).hexdigest()
assert u.is_dir()
backup=u/'backups/desktop-0.3.4-before'
for rel in ['Desktop/Library/GPUBundles/NVMTLDriver.bundle','Desktop/Library/NullMoth/load-panel-framebuffer.sh','Desktop/Library/NullMoth/latitude-desktop-journal','Desktop/BUILD-MANIFEST.json','Desktop/README.md','Desktop/install-windowserver.sh','Desktop/SHA256SUMS.txt','PORT-STATUS.md','ROADMAP.md','SHA256SUMS.json']:
 src=u/rel;dst=backup/rel
 if not src.exists() or dst.exists():continue
 dst.parent.mkdir(parents=True,exist_ok=True)
 if src.is_dir():shutil.copytree(src,dst)
 else:shutil.copy2(src,dst)
# Exact immutable runtime comparison before publishing.
changed=['Library/GPUBundles/NVMTLDriver.bundle/','Library/NullMoth/load-panel-framebuffer.sh','Library/NullMoth/latitude-desktop-journal']
for f in (p/'Library').rglob('*'):
 rel=str(f.relative_to(p))
 if not f.is_file() or f.is_symlink() or f.name.startswith('._') or any(rel.startswith(x) for x in changed):continue
 assert f.read_bytes()==(u/'Desktop'/rel).read_bytes(),rel
for line in (p/'WINDOWSERVER-BASELINE-SHA256SUMS.txt').read_text().splitlines():
 h,rel=line.split('  ',1);assert sha(u/rel)==h,rel
b=p/'Library/GPUBundles/NVMTLDriver.bundle';f=b/'Contents/Info.plist';m=plistlib.loads(f.read_bytes());m.update(CFBundleVersion='0.3.4',CFBundleShortVersionString='0.3.4');f.write_bytes(plistlib.dumps(m));shutil.copy2(r/'desktop-build/NVMTLDriver-0.3.4',b/'Contents/MacOS/NVMTLDriver')
subprocess.run(['codesign','--force','--sign','-',str(b)],check=True)
for f in [b,p/'Library/NullMoth/latitude-desktop-journal',p/'Library/Extensions/NMXGPU.kext',p/'Library/Extensions/NMXAccel.kext']:subprocess.run(['codesign','--verify','--strict',str(f)],check=True)
for f in [b/'Contents/MacOS/NVMTLDriver',p/'Library/NullMoth/latitude-desktop-journal']:assert subprocess.check_output(['lipo','-archs',str(f)],text=True).strip()=='x86_64'
for f in [p/'install-windowserver.sh',p/'Library/NullMoth/load-panel-framebuffer.sh',r/'desktop-sources/collect-desktop-failure.sh']:subprocess.run(['/bin/bash','-n',str(f)],check=True)
research=r/'research/windowserver-0.3.4-research.md';shutil.copy2(research,v/'RESEARCH.md');shutil.copy2(research,u/research.name)
intro='''# Candidate0.3.4 — dedicated WindowServer readback staging

The0.3.3 active desktop boot still hung: fourth readback timeout, kernel GPU hang, then WindowServer crashes. This candidate gives each8086:7d45 WindowServer readback its own dedicated staging allocation, freed after completion and CPU copy, with quarantine on uncertain completion. It also frees known unsubmitted staging failures and fixes denied diagnostic writes, truncated startup logging and false-success stack samples. This is a controlled mitigation candidate, not a confirmed GPU-hang cure.

Kernel, firmware, accelerator, framebuffer, transport and the verified22case/26,000frame application baseline remain unchanged. No full-suite rerun is required.

On the Dell fallback desktop:

```sh
sudo /bin/bash /Volumes/SEQOUIA/iGPU-Port/install-windowserver.sh
```

After exit=0 and ONE desktop boot armed, restart directly through USB once. Do not reset NVRAM; that clears the one-shot markers. This installer has backups/rollback and does not reboot or run GPU tests.

If black/frozen/artifacting: power off, boot USB again for fallback, and collect before reinstalling:

```sh
sudo /bin/bash /Volumes/SEQOUIA/iGPU-Port/collect-desktop-failure.sh
```

If the desktop is visible, run the same collector on that boot. A visible fallback desktop is not acceleration evidence. Bring the USB back after this single targeted attempt.

[Detailed source research, evidence, changes, validation and unresolved risks](../windowserver-0.3.4-research.md).

---

Historical instructions below are superseded by this workflow.

'''
f=p/'README.md';f.write_text(intro+f.read_text())
f=p/'BUILD-MANIFEST.json';m=json.loads(f.read_text());m['runtime_revision']='desktop-0.3.4-windowserver-dedicated-readback';m['stage']='Compiled/local checks passed; dedicated-staging desktop candidate; hardware validation pending';m['built']['metal_plugin']='NVMTLDriver0.3.4: scoped dedicated fresh WindowServer readback allocations, safe known-error cleanup, bounded startup syslog'
m['candidate_0_3_3']['on_target']='Active desktop failure captured130037: first8submissions/3readbacks complete; fourth readback5000ms timeout; rcs0 request8:24 not started; GPUHANG; later CoreAnimation and CoreDisplay crashes. Sandbox denied direct plugin journal; sample produced no file.'
m['candidate_0_3_4']={'changes':['Dedicated mode3 readback allocation per MeteorLake WindowServer call; no TLS/suballocation/park reuse','Free owned staging after successful CPU copy or known pre-submit failure; uncertain submission/backend loss retains allocation','Startup trace uses existing syslog; root loader persists it; first24submit/32readback caller budgets no longer hidden by eight-format throttle','Stack sample positive PID and output/error validation; false success rejected'],'preserved':'NMXGPU1.0.8/Accel0.2.4/framebuffer/claim/firmware/libdrm and26k application baseline; app staging policy/concurrency; serial desktop wrapper and fence/witness quarantine','research':'windowserver-0.3.4-research.md','hardware_status':'Pending one targeted physical desktop boot; staging reuse is a hypothesis, not proven root cause','plugin_sha256':sha(b/'Contents/MacOS/NVMTLDriver'),'helper_sha256':sha(p/'Library/NullMoth/latitude-desktop-journal')};f.write_text(json.dumps(m,indent=2)+'\n')
status='''# Current:0.3.4 dedicated readback candidate ready; desktop success unverified

Latest active0.3.3 attempt completed eight initial submissions/three readbacks, then readback4 timed out and the kernel reported a GPU hang. New WindowServer crashes followed backend loss. Root logs survived; plugin file logging was sandbox-denied and sample falsely exited0 without a usable stack.

Candidate0.3.4 scopes dedicated fresh staging to8086:7d45 WindowServer, cleans known pre-submit allocation failures, and fixes those logging/sampler defects. Local compile, signatures, sanitizer fixtures,20,000balanced mocked allocation lifetimes, release policy,80failed-buffer, installer rollback and loader checks pass. No claim of a complete/future-proof desktop fix. See windowserver-0.3.4-research.md for primary references, hypotheses and unresolved risks.

No kernel/firmware/accelerator/framebuffer/transport change; saved22case/26,000frame baseline remains. Next: Dell fallback install-windowserver.sh; afterexit0 reboot USB once without ResetNVRAM. Then collect-desktop-failure.sh on visible desktop, or after poweroff/USBfallback if it fails. No full-suite rerun or auto-reboot.

---

'''
for f in [u/'PORT-STATUS.md',r/'ROADMAP.md']:f.write_text(status+f.read_text())
shutil.copy2(r/'ROADMAP.md',u/'ROADMAP.md')
validation={'hardware_desktop_verified':False,'hardware_tests_run':False,'baseline':'22cases/26000frames/80020pools retained; byte-identical kernel/accel/framebuffer/firmware/transport','local_passes':['x86_64 release compile and strict ad-hoc signature verification','Actual readback under ASan/UBSan:20000balanced mocked dedicated allocation lifetimes; padded pixels and transfer/host barriers; known pre-submit cleanup; uncertainty/backend loss retention; process/device scope and app TLS preserved','Actual release logger under ASan/UBSan:all24startup submissions survive per-format throttle;256stage cap; app/error throttling preserved; no file-write path','Actual loader with mocked OS:active/fallback/load error, empty sample output despiteexit0, task failure/process0 and refusedPID0','Actual installer mocks:baseline/loaded-kernel guards, success and3component rollback for verify/journal/partial-arm failures','Actual bounded submit wrapper under ASan/UBSan:3000desktop calls, app concurrency, recursive flush, contention deadline/quarantine/no foreign unlock','Actual native release-constructor diagnostic masks47/63/38 unchanged','80failed native command-buffer regressions'],'unresolved':'GPU hang root cause and physical desktop success; dedicated staging requires Dell validation'}
(v/'VALIDATION.json').write_text(json.dumps(validation,indent=2)+'\n');shutil.copy2(v/'VALIDATION.json',u/'desktop-0.3.4-validation.json')
for name in ['nvmtl_vk.c','NVMTLDevice.m','NVMTLObjects.m','nvmtl_desktop_policy.h']:
 src=r/'NullMoth/plugin'/name;shutil.copy2(src,v/name);old=r/'backups/desktop-0.3.4-before'/name
 (v/(name+'.patch')).write_text(''.join(difflib.unified_diff(old.read_text().splitlines(True),src.read_text().splitlines(True),fromfile='a/plugin/'+name,tofile='b/plugin/'+name)))
for src in [p/'install-windowserver.sh',p/'Library/NullMoth/load-panel-framebuffer.sh',r/'desktop-sources/latitude-desktop-journal.c',p/'BUILD-MANIFEST.json',r/'desktop-build/build-NVMTLDriver-0.3.4.log']+list((r/'desktop-sources').glob('test-*.py')):shutil.copy2(src,v/src.name)
files=sorted(f for f in p.rglob('*') if f.is_file() and not f.is_symlink() and 'reports' not in f.relative_to(p).parts and f.name!='SHA256SUMS.txt' and not f.name.startswith('._'))
(p/'SHA256SUMS.txt').write_text(''.join(sha(f)+'  '+str(f.relative_to(p))+'\n' for f in files))
for src in p.rglob('*'):
 rel=src.relative_to(p)
 if 'reports' in rel.parts or src.name.startswith('._') or src.is_symlink():continue
 dst=u/'Desktop'/rel
 if src.is_dir():dst.mkdir(parents=True,exist_ok=True)
 elif not dst.exists() or src.read_bytes()!=dst.read_bytes():shutil.copy2(src,dst)
for line in (u/'Desktop/SHA256SUMS.txt').read_text().splitlines():h,rel=line.split('  ',1);assert sha(u/'Desktop'/rel)==h,rel
for line in (p/'WINDOWSERVER-BASELINE-SHA256SUMS.txt').read_text().splitlines():h,rel=line.split('  ',1);assert sha(u/rel)==h,rel
for f in [u/'Desktop/Library/GPUBundles/NVMTLDriver.bundle',u/'Desktop/Library/NullMoth/latitude-desktop-journal']:subprocess.run(['codesign','--verify','--strict',str(f)],check=True)
f=u/'SHA256SUMS.json';m=json.loads(f.read_text())
for name in ['PORT-STATUS.md','ROADMAP.md','windowserver-0.3.4-research.md','desktop-0.3.4-validation.json']:m[name]=sha(u/name)
f.write_text(json.dumps(m,indent=2)+'\n')
for name,h in m.items():
 if isinstance(h,str) and (u/name).is_file():assert sha(u/name)==h,name
print('Published0.3.4:',len(files),'package hashes, root manifest and saved hardware evidence verified; immutable runtime preserved. No target installation, tests, NVRAM changes or reboot.')
print('PluginSHA256',sha(b/'Contents/MacOS/NVMTLDriver'))
