from pathlib import Path
import hashlib,json,plistlib,shutil,subprocess,difflib
r=Path(__file__).resolve().parent.parent;p=r/'latitude-desktop';u=Path('/Volumes/SEQOUIA/iGPU-Port');v=r/'port-artifacts/desktop-0.3.5';v.mkdir(parents=True,exist_ok=True)
def sha(f):return hashlib.sha256(f.read_bytes()).hexdigest()
assert u.is_dir()
backup=u/'backups/desktop-0.3.5-before'
for rel in ['Desktop/Library/GPUBundles/NVMTLDriver.bundle','Desktop/Library/NullMoth/load-panel-framebuffer.sh','Desktop/Library/NullMoth/latitude-desktop-journal','Desktop/BUILD-MANIFEST.json','Desktop/README.md','Desktop/install-windowserver.sh','Desktop/update-windowserver-kernel.sh','collect-desktop-failure.sh','Desktop/SHA256SUMS.txt','PORT-STATUS.md','ROADMAP.md','SHA256SUMS.json']:
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
b=p/'Library/GPUBundles/NVMTLDriver.bundle';f=b/'Contents/Info.plist';m=plistlib.loads(f.read_bytes());m.update(CFBundleVersion='0.3.5',CFBundleShortVersionString='0.3.5');f.write_bytes(plistlib.dumps(m));shutil.copy2(r/'desktop-build/NVMTLDriver-0.3.5',b/'Contents/MacOS/NVMTLDriver')
subprocess.run(['codesign','--force','--sign','-',str(b)],check=True)
for f in [b,p/'Library/NullMoth/latitude-desktop-journal',p/'Library/Extensions/NMXGPU.kext',p/'Library/Extensions/NMXAccel.kext',p/'WindowServerKernel/NMXGPU.kext']:subprocess.run(['codesign','--verify','--strict',str(f)],check=True)
for f in [b/'Contents/MacOS/NVMTLDriver',p/'Library/NullMoth/latitude-desktop-journal']:assert subprocess.check_output(['lipo','-archs',str(f)],text=True).strip()=='x86_64'
for f in [p/'install-windowserver.sh',p/'update-windowserver-kernel.sh',p/'Library/NullMoth/load-panel-framebuffer.sh',r/'desktop-sources/collect-desktop-failure.sh',p/'update-windowserver-kernel.sh']:subprocess.run(['/bin/bash','-n',str(f)],check=True)
research=r/'research/windowserver-0.3.5-research.md';shutil.copy2(research,v/'RESEARCH.md');shutil.copy2(research,u/research.name)
intro='# Candidate0.3.5 — compression isolation plus request/GuC capture\n\nFresh readback staging did not prevent the0.3.4 GPU hang. This candidate disables image compression only in8086:7d45 WindowServer and installs diagnostic NMXGPU1.0.9. Its capture now includes owned request state and parsed GuC registers; legacy zero register placeholders alone were insufficient. This is an unverified workaround candidate, not a proven hang cure.\n\nThe installer verifies the saved22case/26,000frame application evidence. It does not rerun the suite. The original1.0.8 kernel remains frozen in the package;1.0.9 adds error diagnostics, without a scheduling, firmware, reset-policy or timeout change. Accelerator, framebuffer, firmware and transport remain unchanged. Compression off may affect bandwidth/performance.\n\nOn the Dell fallback desktop:\n\n```sh\nsudo /bin/bash /Volumes/SEQOUIA/iGPU-Port/install-windowserver.sh\n```\n\nThis version also builds the next auxiliary kernel collection and backs up the previous GPU kernel/cache before committing. Wait for exit=0 and ONE desktop boot armed, then restart directly through USB once without ResetNVRAM. Kernel1.0.9 takes effect on restart. No automatic reboot or GPU tests.\n\nIf black/frozen/artifacting: power off, boot USB again for fallback, collect before reinstalling:\n\n```sh\nsudo /bin/bash /Volumes/SEQOUIA/iGPU-Port/collect-desktop-failure.sh\n```\n\nIf visible, collect on that boot. A visible fallback desktop is not an acceleration pass. Bring back the USB after this single attempt.\n\n[Research, source audit, validation and remaining limits](../windowserver-0.3.5-research.md).\n\n---\n\nHistorical instructions below are superseded by this workflow.\n\n'
f=p/'README.md';f.write_text(intro+f.read_text())
f=p/'BUILD-MANIFEST.json';m=json.loads(f.read_text());m['runtime_revision']='desktop-0.3.5-windowserver-noccs-guc-capture';m['stage']='Compiled/local checks passed; scoped noccs workaround plus request/GuC kernel capture; hardware desktop pending';m['built']['metal_plugin']='NVMTLDriver0.3.5: scoped noccs before ICD load; prior fresh staging/pools and bounded diagnostics preserved'
m['candidate_0_3_3']['on_target']='Active desktop failure captured130037: first8submissions/3readbacks complete; fourth readback5000ms timeout; rcs0 request8:24 not started; GPUHANG; later CoreAnimation and CoreDisplay crashes. Sandbox denied direct plugin journal; sample produced no file.'
m['candidate_0_3_4']['on_target']='Failed131639: submission8/third readback used distinct dedicated staging; lock and QueueSubmit succeeded;5sec fence timeout then GPUHANG. Fresh staging not sufficient. Sample captured restartedPID405, not original failure.'
m['candidate_0_3_5']={'changes':['INTEL_DEBUG includes noccs before Intel ICD dlopen only for8086:7d45 WindowServer','NMXGPU1.0.9 error-path request state and parsedGuC capture instead of relying solely on legacy zero placeholders','Transactional kernel/AuxKC update with preflight, backup/rollback, kcditto; current/fallback kernel identity collected'],'preserved':'Firmware, accelerator, framebuffer/claim, transport, original frozen1.0.8 and22case evidence; scheduling/reset/timeouts, fresh pools and quarantine unchanged','research':'windowserver-0.3.5-research.md','hardware_status':'Unverified compression workaround and diagnostic kernel; root cause remains unknown','kernel_uuid':(p/'WindowServerKernel/NMXGPU-UUID.txt').read_text().strip(),'kernel_sha256':sha(p/'WindowServerKernel/NMXGPU.kext/Contents/MacOS/NMXGPU'),'plugin_sha256':sha(b/'Contents/MacOS/NVMTLDriver')};f.write_text(json.dumps(m,indent=2)+'\n')
status='# Current:0.3.5 compression-isolation and kernel-capture candidate\n\nThe0.3.4 active desktop still hung on submission8/third readback with dedicated staging. The next candidate sets noccs only for this WindowServer/device and installs diagnostic NMXGPU1.0.9. Kernel capture now reports referenced request state and parsed GuC registers; zero legacy ring fields were not a complete hardware snapshot. No exact root cause or complete desktop fix is claimed.\n\nLocal builds, signatures, sanitizer fixtures, kernel link/import comparison, compression scope, installer/KC rollback and regressions pass. Saved22case/26,000frame evidence and original1.0.8 bundle are retained; no suite rerun requested. Firmware, accelerator, framebuffer and transport remain unchanged. The1.0.9 kernel changes diagnostics, not scheduling/reset/timeouts.\n\nNext: Dell fallback install-windowserver.sh; this also prebuilds/backs up/updates AuxKC and kernel. Afterexit0 restart USB once without ResetNVRAM. Then collect-desktop-failure.sh on visible desktop, or poweroff/USBfallback then collect if it fails. No automatic reboot. See windowserver-0.3.5-research.md.\n\n---\n\n'
for f in [u/'PORT-STATUS.md',r/'ROADMAP.md']:f.write_text(status+f.read_text())
shutil.copy2(r/'ROADMAP.md',u/'ROADMAP.md')
validation={'hardware_desktop_verified':False,'target_tests_run':False,'frozen_baseline':'22cases/26000frames/80020pools retained with originalkernel1.0.8; new diagnostic kernel not covered by that pass','local_passes':['Release x86_64 plugin/kernel/helper compile and ad-hoc signatures','438object kernel link; undefined imports identical to1.0.8','Actual parsedGuC logger ASan/UBSan:absent node, null/empty/large lists,192register bound; no new MMIO/waits/allocations','Actual noccs helper ASan/UBSan:exact scope, preserved existing flags, unset/empty/oversized handling; before-ICD-load ordering','Actual integrated installer+kernel helper with OS mocks:guards, success, KC preflight/mirroring, signature, journal and partial-arm rollback restores plugin/tools/kernel/cache','Separate actual kernel helper:already-current no-op and late rollback','Collector retains crashes/logs with current-kernel identity query, history failures still preserve artifacts','Actual native release policy masks47/63/38 and80failed command buffers','Actual readback implementation:20000balanced mocked allocations; timeout/backend-loss retention and app scope','Actual logger budget/throttle and loader/sample/fallback tests'],'unresolved':'Physical desktop and compression hypothesis; primary GPU hang cause not established'}
(v/'VALIDATION.json').write_text(json.dumps(validation,indent=2)+'\n');shutil.copy2(v/'VALIDATION.json',u/'desktop-0.3.5-validation.json')
for name in ['nvmtl_vk.c','NVMTLObjects.m','nvmtl_desktop_policy.h']:
 src=r/'NullMoth/plugin'/name;shutil.copy2(src,v/name);old=r/'backups/desktop-0.3.5-before'/name
 (v/(name+'.patch')).write_text(''.join(difflib.unified_diff(old.read_text().splitlines(True),src.read_text().splitlines(True),fromfile='a/plugin/'+name,tofile='b/plugin/'+name)))
for src in [p/'install-windowserver.sh',p/'update-windowserver-kernel.sh',p/'Library/NullMoth/load-panel-framebuffer.sh',r/'desktop-sources/latitude-desktop-journal.c',p/'BUILD-MANIFEST.json',r/'desktop-build/build-NVMTLDriver-0.3.5.log',r/'desktop-build/kernel-link-1.0.9.log',r/'desktop-build/kernel-error-1.0.9.log',r/'desktop-build/kernel-guc-capture-1.0.9.log',r/'desktop-sources/collect-desktop-failure.sh']+list((r/'desktop-sources').glob('test-*.py')):shutil.copy2(src,v/src.name)
files=sorted(f for f in p.rglob('*') if f.is_file() and not f.is_symlink() and 'reports' not in f.relative_to(p).parts and f.name!='SHA256SUMS.txt' and not f.name.startswith('._'))
(p/'SHA256SUMS.txt').write_text(''.join(sha(f)+'  '+str(f.relative_to(p))+'\n' for f in files))
for src in p.rglob('*'):
 rel=src.relative_to(p)
 if 'reports' in rel.parts or src.name.startswith('._') or src.is_symlink():continue
 dst=u/'Desktop'/rel
 if src.is_dir():dst.mkdir(parents=True,exist_ok=True)
 elif not dst.exists() or src.read_bytes()!=dst.read_bytes():shutil.copy2(src,dst)
shutil.copy2(r/'desktop-sources/collect-desktop-failure.sh',u/'collect-desktop-failure.sh')
for rel in ['i915_gpu_error.c','gt/uc/intel_guc_capture.c','gt/uc/intel_guc_capture.h']:
 src=r/'drm-kmod/drivers/gpu/drm/i915'/rel;old=r/'backups/kernel-1.0.9-before'/rel
 dst=v/'kernel-source'/rel;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,dst)
 (dst.parent/(dst.name+'.patch')).write_text(''.join(difflib.unified_diff(old.read_text().splitlines(True),src.read_text().splitlines(True),fromfile='a/'+rel,tofile='b/'+rel)))
for line in (u/'Desktop/SHA256SUMS.txt').read_text().splitlines():h,rel=line.split('  ',1);assert sha(u/'Desktop'/rel)==h,rel
for line in (p/'WINDOWSERVER-BASELINE-SHA256SUMS.txt').read_text().splitlines():h,rel=line.split('  ',1);assert sha(u/rel)==h,rel
for f in [u/'Desktop/Library/GPUBundles/NVMTLDriver.bundle',u/'Desktop/Library/NullMoth/latitude-desktop-journal',u/'Desktop/WindowServerKernel/NMXGPU.kext']:subprocess.run(['codesign','--verify','--strict',str(f)],check=True)
f=u/'SHA256SUMS.json';m=json.loads(f.read_text())
for name in ['PORT-STATUS.md','ROADMAP.md','collect-desktop-failure.sh','windowserver-0.3.5-research.md','desktop-0.3.5-validation.json']:m[name]=sha(u/name)
f.write_text(json.dumps(m,indent=2)+'\n')
for name,h in m.items():
 if isinstance(h,str) and (u/name).is_file():assert sha(u/name)==h,name
print('Published0.3.5:',len(files),'package hashes, root manifest and saved hardware evidence verified; baseline retained; new diagnostic kernel separately staged. No target installation, tests, NVRAM changes or reboot.')
print('PluginSHA256',sha(b/'Contents/MacOS/NVMTLDriver'))
