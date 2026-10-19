from pathlib import Path
import shutil,hashlib,json,subprocess,difflib
r=Path(__file__).resolve().parent.parent;p=r/'latitude-desktop';u=Path('/Volumes/SEQOUIA/iGPU-Port');v=r/'port-artifacts/windowserver-completion-context-1.0.14';v.mkdir(parents=True,exist_ok=True)
def sha(f):return hashlib.sha256(f.read_bytes()).hexdigest()
assert u.is_dir()
# Check every frozen evidence file before publication, without running GPU work.
for line in (p/'WINDOWSERVER-BASELINE-SHA256SUMS.txt').read_text().splitlines():
 h,rel=line.split('  ',1);assert sha(u/rel)==h,rel
for rel in ['Library/Extensions/NMXGPU.kext/Contents/MacOS/NMXGPU','Library/Extensions/NMXAccel.kext/Contents/MacOS/NMXAccel','Library/Extensions/LatitudeMTLFB.kext/Contents/MacOS/LatitudeMTLFB','Library/GPUBundles/NVMTLDriver.bundle/Contents/MacOS/NVMTLDriver','WindowServerFramebuffer/LatitudeMTLFB.kext/Contents/MacOS/LatitudeMTLFB']:
 assert sha(p/rel)==sha(u/'Desktop'/rel),rel
backup=u/'backups/windowserver-before-completion-context-1.0.14'
for rel in ['Desktop/WindowServerKernel','Desktop/PreviousWindowServerKernel','Desktop/install-windowserver.sh','Desktop/README.md','Desktop/BUILD-MANIFEST.json','Desktop/SHA256SUMS.txt','PORT-STATUS.md','SHA256SUMS.json']:
 src=u/rel;dst=backup/rel
 if dst.exists():continue
 dst.parent.mkdir(parents=True,exist_ok=True)
 if src.is_dir():shutil.copytree(src,dst)
 else:shutil.copy2(src,dst)
for rel in ['gt/intel_breadcrumbs.c']:
 src=r/'drm-kmod/drivers/gpu/drm/i915'/rel;old=r/'backups/completion-context-before-1.0.14'/src.name
 dst=v/'source'/rel;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,dst)
 dst.with_suffix(dst.suffix+'.patch').write_text(''.join(difflib.unified_diff(old.read_text().splitlines(True),src.read_text().splitlines(True),fromfile='a/'+rel,tofile='b/'+rel)))
for name in ['test-completion-context.py','link-kernel-1.0.14.py','test-windowserver-installer.py','test-windowserver-kernel.py']:
 shutil.copy2(r/'desktop-sources'/name,v/name)
shutil.copy2(r/'research/windowserver-completion-context-1.0.14.md',v/'RESEARCH.md')
for name in ['completion-context-old-asan.txt','completion-before-request-iterator.txt','compile-breadcrumbs-1.0.14.log','kernel-link-1.0.14.log']:shutil.copy2(r/'desktop-build'/name,v/name)
validation={'kernel':'1.0.14','uuid':(p/'WindowServerKernel/NMXGPU-UUID.txt').read_text().strip(),'sha256':sha(p/'WindowServerKernel/NMXGPU.kext/Contents/MacOS/NMXGPU'),'hardware_verified':False,'target_suite_run':False,'passes':['438-object x86_64 link; undefined imports identical to frozen1.0.8','Actual old enqueue/worker/GuC callback reproduces context UAF; final implementation ASan/UBSan90000 lifetimes including publication race, parent/child, cancel, bulk remove, competing signal and duplicate signaling, zero live objects','Request iterator negative-control UAF reproduced and fixed','Actual integrated installer supports exact predecessor1.0.13/current1.0.14 identities, cache repair, final KC validation, rollback and marker cleanup','Actual kernel helper transactional rollback fixtures','Frozen22-case/26000-frame evidence file hashes verified; no GPU suite rerun'],'limits':'Dell panic ordering not conclusively proven; candidate retains prior unverified DSM exclusion; full accelerated desktop unresolved'}
(v/'VALIDATION.json').write_text(json.dumps(validation,indent=2)+'\n')
files=sorted(f for f in p.rglob('*') if f.is_file() and not f.is_symlink() and 'reports' not in f.relative_to(p).parts and f.name!='SHA256SUMS.txt' and not f.name.startswith('._'))
(p/'SHA256SUMS.txt').write_text(''.join(sha(f)+'  '+str(f.relative_to(p))+'\n' for f in files))
for src in files+[p/'SHA256SUMS.txt']:
 dst=u/'Desktop'/src.relative_to(p);dst.parent.mkdir(parents=True,exist_ok=True)
 if not dst.exists() or sha(src)!=sha(dst):
  tmp=dst.with_name(dst.name+'.publish-tmp');shutil.copy2(src,tmp);tmp.replace(dst)
shutil.copy2(r/'research/windowserver-completion-context-1.0.14.md',u/'windowserver-completion-context-1.0.14.md')
shutil.copy2(v/'VALIDATION.json',u/'windowserver-completion-context-1.0.14-validation.json')
status=u/'PORT-STATUS.md';intro='# Current: NMXGPU1.0.14 completion context lifetime\n\n1.0.13 panicked in GuC retirement at8seconds.1.0.14 adds explicit context/parent ownership to queued breadcrumb requests and safe successor iteration. Old UAF reproduced with actual functions in sanitizer fixture;90000 corrected lifetimes pass. Kernel build/signature and installer/KC rollback checks pass. Target panic cure and accelerated desktop remain UNVERIFIED.\n\nDell fallback: install-windowserver.sh; after exit0 restart USB once without ResetNVRAM. On failure poweroff/USBfallback then collect-desktop-failure.sh before reinstall. Collector includes kernel panics. No full GPU suite rerun or automatic reboot. See windowserver-completion-context-1.0.14.md.\n\n---\n\n' 
if not status.read_text().startswith('# Current: NMXGPU1.0.14'):status.write_text(intro+status.read_text())
f=u/'SHA256SUMS.json';m=json.loads(f.read_text())
for name in ['PORT-STATUS.md','windowserver-completion-context-1.0.14.md','windowserver-completion-context-1.0.14-validation.json']:m[name]=sha(u/name)
f.write_text(json.dumps(m,indent=2)+'\n')
for line in (u/'Desktop/SHA256SUMS.txt').read_text().splitlines():
 h,rel=line.split('  ',1);assert sha(u/'Desktop'/rel)==h,rel
for name,h in m.items():
 if isinstance(h,str):assert (u/name).is_file() and sha(u/name)==h,name
for rel in ['WindowServerKernel/NMXGPU.kext','PreviousWindowServerKernel/NMXGPU.kext','WindowServerFramebuffer/LatitudeMTLFB.kext','Library/GPUBundles/NVMTLDriver.bundle','validate-kernel-prelink']:
 subprocess.run(['codesign','--verify','--strict',str(u/'Desktop'/rel)],check=True)
for rel in ['install-windowserver.sh','update-windowserver-kernel.sh']:
 subprocess.run(['/bin/bash','-n',str(u/'Desktop'/rel)],check=True)
print('Published completion-context1.0.14:',len(files),'package files;',len(m),'root hashes; signatures, shell syntax and frozen evidence verified. No target install, NVRAM edits, GPU suite or reboot.')
print(json.dumps(validation,indent=2))
