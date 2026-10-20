from pathlib import Path
import shutil, hashlib, json, subprocess, difflib
r=Path(__file__).resolve().parent.parent
p=r/'latitude-desktop';u=Path('/Volumes/SEQOUIA/iGPU-Port')
v=r/'port-artifacts/windowserver-iokit-transport-220839';v.mkdir(exist_ok=True)
def sha(f):return hashlib.sha256(f.read_bytes()).hexdigest()
def copy(a,b):
 b.parent.mkdir(parents=True,exist_ok=True)
 t=b.with_name(b.name+'.publish-tmp');shutil.copy2(a,t);t.replace(b)
def verify(root,m):
 for line in m.read_text().splitlines():
  h,rel=line.split('  ',1);assert sha(root/rel)==h,rel
assert u.is_dir()
verify(u,p/'WINDOWSERVER-BASELINE-SHA256SUMS.txt')
unchanged=['WindowServerKernel/NMXGPU.kext/Contents/MacOS/NMXGPU','WindowServerFramebuffer/LatitudeMTLFB.kext/Contents/MacOS/LatitudeMTLFB','Library/GPUBundles/NVMTLDriver.bundle/Contents/MacOS/NVMTLDriver','Library/GPUBundles/nvmtl/libdrm.2.dylib']
before={rel:sha(u/'Desktop'/rel) for rel in unchanged}
for rel,h in before.items():assert sha(p/rel)==h,rel
config=u.parent/'EFI/OC/config.plist';config_sha=sha(config)
hid=u.parent/'EFI/OC/Kexts/VoodooI2CHID.kext/Contents/MacOS/VoodooI2CHID';hid_sha=sha(hid)
backup=u/'backups/windowserver-transport-before-220839'
for rel in ['Desktop/install-windowserver.sh','Desktop/BUILD-MANIFEST.json','Desktop/SHA256SUMS.txt','Desktop/README.md','collect-desktop-failure.sh','PORT-STATUS.md','SHA256SUMS.json']:
 if not (backup/rel).exists():copy(u/rel,backup/rel)
lib=p/'WindowServerTransport/libdrm.2.dylib'
subprocess.run(['codesign','--verify','--strict',str(lib)],check=True)
for flag in ['-gjU','-ju']:
 assert set(subprocess.check_output(['nm',flag,str(lib)],text=True).splitlines())==set(subprocess.check_output(['nm',flag,str(p/'Library/GPUBundles/nvmtl/libdrm.2.dylib')],text=True).splitlines())
validation={'candidate':'WindowServer IOKit transport correction','sha256':sha(lib),'baseline_sha256':sha(p/'Library/GPUBundles/nvmtl/libdrm.2.dylib'),'architecture':'x86_64','hardware_verified':False,'full_gpu_suite_rerun':False,'full_windowserver_acceleration_verified':False,'tests':['old actual functions reproduce mixed devfs/IOKit identity gap','corrected actual functions pass ASan/UBSan access-pattern and route/errno/identity fixtures','existing transport and enumeration fixtures pass','integrated installer replacement/known-current/signature-failure and later failure rollback fixtures pass','collector crash-preservation fixtures pass','x86_64 link; public exports and imports match baseline; codesign strict verification'],'unchanged_gpu_payloads':before,'unchanged_usb_hid_sha256':hid_sha,'limits':'Target zero-device rejection not yet proven resolved; framebuffer warnings may be separate; earlier GPU failures remain unvalidated'}
(v/'VALIDATION.json').write_text(json.dumps(validation,indent=2)+'\n')
old=r/'backups/windowserver-transport-before-220839/xf86drm.c';new=r/'libdrm/xf86drm.c'
(v/'libdrm-iokit-identity.patch').write_text(''.join(difflib.unified_diff(old.read_text().splitlines(True),new.read_text().splitlines(True),fromfile='a/xf86drm.c',tofile='b/xf86drm.c')))
copy(new,v/'xf86drm.c');copy(lib,v/'libdrm.2.dylib')
for name in ['test-windowserver-transport.py','test-transport.py','test-iokit-enumeration.py','test-windowserver-installer.py']:
 copy(r/'desktop-sources'/name,v/name)
doc=r/'research/windowserver-iokit-transport-220839.md';copy(doc,v/'RESEARCH.md')
mf=p/'BUILD-MANIFEST.json';m=json.loads(mf.read_text());m['stage']='WindowServer IOKit transport correction: local regression/build/rollback checks pass; physical accelerated desktop unresolved';m['windowserver_transport']=validation;mf.write_text(json.dumps(m,indent=2)+'\n')
readme=p/'README.md';intro='# Current WindowServer IOKit transport candidate\n\nLatest boot reaches CoreDisplay but Vulkan reports zero devices. This candidate corrects mixed devfs/IOKit identity handling after a denied writable render-node open and records bounded startup ioctl results. GPU1.0.14, framebuffer0.2.4 and HID1.0.1 are retained. Hardware success remains unverified. Use install-windowserver.sh on the Dell fallback, restart through USB once after exit0, and collect-desktop-failure.sh on failure before reinstalling. No22-case rerun. See ../windowserver-iokit-transport-220839.md.\n\n---\n\n'
if not readme.read_text().startswith('# Current WindowServer IOKit transport'):readme.write_text(intro+readme.read_text())
files=sorted(f for f in p.rglob('*') if f.is_file() and not f.is_symlink() and 'reports' not in f.relative_to(p).parts and f.name!='SHA256SUMS.txt' and not f.name.startswith('._'))
(p/'SHA256SUMS.txt').write_text(''.join(sha(f)+'  '+str(f.relative_to(p))+'\n' for f in files))
for f in files+[p/'SHA256SUMS.txt']:
 dst=u/'Desktop'/f.relative_to(p)
 if not dst.exists() or sha(dst)!=sha(f):copy(f,dst)
copy(r/'desktop-sources/collect-desktop-failure.sh',u/'collect-desktop-failure.sh')
copy(doc,u/doc.name);copy(v/'VALIDATION.json',u/'windowserver-iokit-transport-validation.json');copy(v/'libdrm-iokit-identity.patch',u/'windowserver-libdrm-iokit-identity.patch')
status=u/'PORT-STATUS.md';intro='# Current: WindowServer IOKit transport correction\n\n22:07 trial: three CoreDisplay assertion crashes; Vulkan zero devices; sandbox denies writable render-node opens and ioctls. Reproduced mixed transport identity gap corrected: denied writable renderD128 opens use IOKit token directly; existing IOKit real-fd identity uses its DRM file. Added bounded startup ioctl results. Local sanitizer/build/installer rollback checks pass; Dell fix and full acceleration remain UNVERIFIED. GPU1.0.14, framebuffer0.2.4, plugin0.3.5 and HID1.0.1 retained.\n\nRun install-windowserver.sh on Dell fallback; exit0 then restart USB once without ResetNVRAM. On failure fallback and collect-desktop-failure.sh before reinstalling. No22-case rerun. See windowserver-iokit-transport-220839.md.\n\n---\n\n'
if not status.read_text().startswith('# Current: WindowServer IOKit transport'):status.write_text(intro+status.read_text())
mf=u/'SHA256SUMS.json';m=json.loads(mf.read_text())
for name in ['PORT-STATUS.md','collect-desktop-failure.sh',doc.name,'windowserver-iokit-transport-validation.json','windowserver-libdrm-iokit-identity.patch']:m[name]=sha(u/name)
mf.write_text(json.dumps(m,indent=2)+'\n')
verify(u/'Desktop',p/'SHA256SUMS.txt');verify(u,p/'WINDOWSERVER-BASELINE-SHA256SUMS.txt')
for name,h in m.items():assert sha(u/name)==h,name
for rel,h in before.items():assert sha(u/'Desktop'/rel)==h,rel
assert sha(config)==config_sha and sha(hid)==hid_sha
subprocess.run(['codesign','--verify','--strict',str(u/'Desktop/WindowServerTransport/libdrm.2.dylib')],check=True)
for f in [u/'Desktop/install-windowserver.sh',u/'collect-desktop-failure.sh']:subprocess.run(['/bin/bash','-n',str(f)],check=True)
print(json.dumps(validation,indent=2))
print('Published transport candidate:',len(files),'package files. Verified all manifests, signatures, syntax, frozen evidence and unchanged GPU/EFI payloads. No target install, GPU suite, NVRAM edits or reboot.')
