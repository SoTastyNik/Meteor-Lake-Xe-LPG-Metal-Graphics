from pathlib import Path
import shutil,hashlib,json,subprocess,difflib
r=Path(__file__).resolve().parent.parent;p=r/'latitude-desktop';u=Path('/Volumes/SEQOUIA/iGPU-Port');v=r/'port-artifacts/windowserver-firmware-stolen-1.0.13';v.mkdir(parents=True,exist_ok=True)
def sha(f):return hashlib.sha256(f.read_bytes()).hexdigest()
assert u.is_dir()
# Check every frozen evidence file before publication, without running GPU work.
for line in (p/'WINDOWSERVER-BASELINE-SHA256SUMS.txt').read_text().splitlines():
 h,rel=line.split('  ',1);assert sha(u/rel)==h,rel
for rel in ['Library/Extensions/NMXGPU.kext/Contents/MacOS/NMXGPU','Library/Extensions/NMXAccel.kext/Contents/MacOS/NMXAccel','Library/Extensions/LatitudeMTLFB.kext/Contents/MacOS/LatitudeMTLFB','Library/GPUBundles/NVMTLDriver.bundle/Contents/MacOS/NVMTLDriver','WindowServerFramebuffer/LatitudeMTLFB.kext/Contents/MacOS/LatitudeMTLFB']:
 assert sha(p/rel)==sha(u/'Desktop'/rel),rel
backup=u/'backups/windowserver-before-firmware-stolen-1.0.13'
for rel in ['Desktop/WindowServerKernel','Desktop/PreviousWindowServerKernel','Desktop/install-windowserver.sh','Desktop/README.md','Desktop/BUILD-MANIFEST.json','Desktop/SHA256SUMS.txt','PORT-STATUS.md','SHA256SUMS.json']:
 src=u/rel;dst=backup/rel
 if dst.exists():continue
 dst.parent.mkdir(parents=True,exist_ok=True)
 if src.is_dir():shutil.copytree(src,dst)
 else:shutil.copy2(src,dst)
for rel in ['intel_memory_region.c','gt/intel_ring.c']:
 src=r/'drm-kmod/drivers/gpu/drm/i915'/rel;old=r/'backups/firmware-stolen-before'/src.name
 dst=v/'source'/rel;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,dst)
 dst.with_suffix(dst.suffix+'.patch').write_text(''.join(difflib.unified_diff(old.read_text().splitlines(True),src.read_text().splitlines(True),fromfile='a/'+rel,tofile='b/'+rel)))
for name in ['test-firmware-stolen.py','link-kernel-1.0.13.py','test-windowserver-installer.py','test-windowserver-kernel.py']:
 shutil.copy2(r/'desktop-sources'/name,v/name)
shutil.copy2(r/'research/windowserver-firmware-stolen-1.0.13.md',v/'RESEARCH.md')
validation={'kernel':'1.0.13','uuid':(p/'WindowServerKernel/NMXGPU-UUID.txt').read_text().strip(),'sha256':sha(p/'WindowServerKernel/NMXGPU.kext/Contents/MacOS/NMXGPU'),'hardware_verified':False,'target_suite_run':False,'passes':['438-object x86_64 link; undefined imports identical to frozen1.0.8','Actual region-probe/ring-allocation sanitizer tests: old path stolen; protected path internal; other-device/non-port and error cleanup','Actual integrated desktop installer: predecessor1.0.12/current1.0.13 guards, cache repair, final KC paths, rollback and one-shot cleanup','Actual kernel helper transactional GPU/framebuffer/KC rollback fixtures','Actual request-ring capture sanitizer fixtures','Saved22-case/26000-frame evidence file hashes verified; no GPU tests rerun'],'limits':'Failed-ring DSM overlap unproven; next target must verify exclusion log and stolen=0 rings, then actual compositor behavior'}
(v/'VALIDATION.json').write_text(json.dumps(validation,indent=2)+'\n')
files=sorted(f for f in p.rglob('*') if f.is_file() and not f.is_symlink() and 'reports' not in f.relative_to(p).parts and f.name!='SHA256SUMS.txt' and not f.name.startswith('._'))
(p/'SHA256SUMS.txt').write_text(''.join(sha(f)+'  '+str(f.relative_to(p))+'\n' for f in files))
for src in files+[p/'SHA256SUMS.txt']:
 dst=u/'Desktop'/src.relative_to(p);dst.parent.mkdir(parents=True,exist_ok=True)
 if not dst.exists() or sha(src)!=sha(dst):
  tmp=dst.with_name(dst.name+'.publish-tmp');shutil.copy2(src,tmp);tmp.replace(dst)
shutil.copy2(r/'research/windowserver-firmware-stolen-1.0.13.md',u/'windowserver-firmware-stolen-1.0.13.md')
shutil.copy2(v/'VALIDATION.json',u/'windowserver-firmware-stolen-1.0.13-validation.json')
status=u/'PORT-STATUS.md';intro='# Current: NMXGPU1.0.13 firmware-owned DSM exclusion\n\nSource inspection found missing initial-plane ownership protection: i915 could allocate stolen objects while LatitudeMTLFB retains the panel there.1.0.13 withholds stolen regions on7d45, allowing standard system-memory fallback. Previous1.0.12 still corrupted its ring. The specific failed-ring overlap is unproven; hardware desktop success remains unverified.\n\nLocally built/signed, sanitizer regression and installer/KC rollback checks pass. Original1.0.8/22-case baseline retained. No full GPU suite rerun. Dell: install-windowserver.sh on fallback; after exit0 restart USB once without ResetNVRAM; collect-desktop-failure.sh on trial if usable, otherwise poweroff/USBfallback then collect before reinstall. No automatic reboot. See windowserver-firmware-stolen-1.0.13.md.\n\n---\n\n'
if not status.read_text().startswith('# Current: NMXGPU1.0.13'):status.write_text(intro+status.read_text())
f=u/'SHA256SUMS.json';m=json.loads(f.read_text())
for name in ['PORT-STATUS.md','windowserver-firmware-stolen-1.0.13.md','windowserver-firmware-stolen-1.0.13-validation.json']:m[name]=sha(u/name)
f.write_text(json.dumps(m,indent=2)+'\n')
for line in (u/'Desktop/SHA256SUMS.txt').read_text().splitlines():
 h,rel=line.split('  ',1);assert sha(u/'Desktop'/rel)==h,rel
for name,h in m.items():
 if isinstance(h,str):assert (u/name).is_file() and sha(u/name)==h,name
for rel in ['WindowServerKernel/NMXGPU.kext','PreviousWindowServerKernel/NMXGPU.kext','WindowServerFramebuffer/LatitudeMTLFB.kext','Library/GPUBundles/NVMTLDriver.bundle','validate-kernel-prelink']:
 subprocess.run(['codesign','--verify','--strict',str(u/'Desktop'/rel)],check=True)
for rel in ['install-windowserver.sh','update-windowserver-kernel.sh']:
 subprocess.run(['/bin/bash','-n',str(u/'Desktop'/rel)],check=True)
print('Published firmware-stolen1.0.13:',len(files),'package files;',len(m),'root hashes; signatures, shell syntax and frozen evidence verified. No target install, NVRAM edits, GPU suite or reboot.')
print(json.dumps(validation,indent=2))
