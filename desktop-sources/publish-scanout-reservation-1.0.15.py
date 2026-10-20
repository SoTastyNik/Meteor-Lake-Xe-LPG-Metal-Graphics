from pathlib import Path
import shutil,hashlib,json,subprocess,difflib
r=Path(__file__).resolve().parent.parent;p=r/'latitude-desktop';u=Path('/Volumes/SEQOUIA/iGPU-Port')
v=r/'port-artifacts/windowserver-scanout-reservation-1.0.15';v.mkdir(exist_ok=True)
def sha(f):return hashlib.sha256(f.read_bytes()).hexdigest()
def copy(a,b):
 b.parent.mkdir(parents=True,exist_ok=True);t=b.with_name(b.name+'.publish-tmp');shutil.copy2(a,t);t.replace(b)
def verify(root,manifest):
 for line in manifest.read_text().splitlines():
  h,n=line.split('  ',1);assert sha(root/n)==h,n
verify(u,p/'WINDOWSERVER-BASELINE-SHA256SUMS.txt')
assert sha(u/'Desktop/WindowServerKernel/NMXGPU.kext/Contents/MacOS/NMXGPU')==sha(p/'PreviousWindowServerKernel/NMXGPU.kext/Contents/MacOS/NMXGPU')
fixed=['Library/Extensions/NMXGPU.kext/Contents/MacOS/NMXGPU','Library/Extensions/NMXAccel.kext/Contents/MacOS/NMXAccel','WindowServerFramebuffer/LatitudeMTLFB.kext/Contents/MacOS/LatitudeMTLFB','Library/GPUBundles/NVMTLDriver.bundle/Contents/MacOS/NVMTLDriver','Library/GPUBundles/nvmtl/libdrm.2.dylib','WindowServerTransport/libdrm.2.dylib']
before={n:sha(u/'Desktop'/n) for n in fixed}
for n,h in before.items():assert sha(p/n)==h,n
efi=u.parent/'EFI/OC';config_hash=sha(efi/'config.plist');hid_hash=sha(efi/'Kexts/VoodooI2CHID.kext/Contents/MacOS/VoodooI2CHID')
backup=u/'backups/windowserver-before-scanout-reservation-1.0.15'
for n in ['Desktop/WindowServerKernel','Desktop/PreviousWindowServerKernel','Desktop/install-windowserver.sh','Desktop/BUILD-MANIFEST.json','Desktop/SHA256SUMS.txt','Desktop/README.md','collect-desktop-failure.sh','PORT-STATUS.md','SHA256SUMS.json']:
 a=u/n;b=backup/n
 if b.exists():continue
 if a.is_dir():shutil.copytree(a,b)
 else:copy(a,b)
kernel=p/'WindowServerKernel/NMXGPU.kext';binary=kernel/'Contents/MacOS/NMXGPU'
subprocess.run(['codesign','--verify','--strict',str(kernel)],check=True)
uuid=subprocess.check_output(['xcrun','dwarfdump','--uuid',str(binary)],text=True).split()[1]
assert uuid==(p/'WindowServerKernel/NMXGPU-UUID.txt').read_text().strip()
def imports(f):return set(subprocess.check_output(['nm','-uj',str(f)],text=True).splitlines())
added=imports(binary)-imports(p/'Library/Extensions/NMXGPU.kext/Contents/MacOS/NMXGPU')
assert added=={'__ZN9IOService11getPlatformEv'},added
validation={'kernel_version':'1.0.15','uuid':uuid,'sha256':sha(binary),'hardware_verified':False,'full_windowserver_acceleration_verified':False,'full_gpu_suite_rerun':False,'earliest_observed_failure':'GuC crash/exception and non-recoverable wedged on init at22:19:41, before WindowServer enumeration','change':'Replace whole-region stolen exclusion with validated, aligned firmware GOP prefix exclusion; restore remaining stolen allocator; initialization phase errors and collector summary','local_tests':['old enabled allocator overlap reproduced','actual initializer/bound helper:524288 offset/size cases ASan/UBSan plus overflow/refusal/other-device cases','actual console bridge ASan/UBSan valid/error/bounds cases','four changed kernel sources compile;438-object x86_64 link; added import limited to IOService::getPlatform already used by framebuffer','completion-context90000 sanitizer lifetimes pass','integrated installer/kernel helper upgrade/rollback/KC/prelink/arming regression fixtures pass','collector preserves crash/panic data on failed history search'],'retained_payloads':before,'usb_hid_sha256':hid_hash,'limits':'GuC crash causality and hardware recovery not proven; old failed-ring physical overlap not proven; full desktop unresolved'}
(v/'VALIDATION.json').write_text(json.dumps(validation,indent=2)+'\n')
sources=['drm-kmod/drivers/gpu/drm/i915/intel_memory_region.c','drm-kmod/drivers/gpu/drm/i915/gem/i915_gem_stolen.c','drm-kmod/drivers/gpu/drm/i915/gt/intel_gt.c','NullMoth/gpu-port/xkpi/xnu/nmx_vm.cpp','NullMoth/gpu-port/xkpi/bsdcompat/include/nmx_xnu.h']
patch=''
for n in sources:
 a=r/'backups/scanout-reservation-before-1.0.15'/Path(n).name;b=r/n
 copy(b,v/'source'/n)
 patch+=''.join(difflib.unified_diff(a.read_text().splitlines(True),b.read_text().splitlines(True),fromfile='a/'+n,tofile='b/'+n))
(v/'scanout-reservation.patch').write_text(patch)
for n in ['test-scanout-reservation.py','link-kernel-1.0.15.py','test-windowserver-installer.py','test-windowserver-kernel.py']:copy(r/'desktop-sources'/n,v/n)
for n in ['compile-region-1.0.15.log','compile-stolen-1.0.15.log','compile-gt-1.0.15.log','compile-vm-1.0.15.log','kernel-link-1.0.15.log']:copy(r/'desktop-build'/n,v/n)
doc=r/'research/windowserver-scanout-reservation-1.0.15.md';copy(doc,v/'RESEARCH.md')
mf=p/'BUILD-MANIFEST.json';m=json.loads(mf.read_text());m['stage']='NMXGPU1.0.15: firmware scanout reserved within restored stolen allocator; local checks pass, hardware GPU startup and accelerated desktop unverified';m['scanout_reservation']=validation;mf.write_text(json.dumps(m,indent=2)+'\n')
f=p/'README.md';intro='# Current: GPU startup / scanout reservation1.0.15\n\nFull boot log shows GuC crashed and i915 wedged during initialization before WindowServer reported zero devices.1.0.15 replaces blanket stolen-memory exclusion with a validated firmware framebuffer prefix reservation, restoring the remaining allocator. Local sanitizer/build/installer rollback checks pass; hardware recovery and accelerated composition remain unverified. Run install-windowserver.sh on Dell USB fallback; exit0 then restart USB once without ResetNVRAM. On failure collect-desktop-failure.sh before reinstall. No22-case rerun. See ../windowserver-scanout-reservation-1.0.15.md.\n\n---\n\n'
if not f.read_text().startswith('# Current: GPU startup'):f.write_text(intro+f.read_text())
files=sorted(f for f in p.rglob('*') if f.is_file() and not f.is_symlink() and 'reports' not in f.relative_to(p).parts and f.name!='SHA256SUMS.txt' and not f.name.startswith('._'))
(p/'SHA256SUMS.txt').write_text(''.join(sha(f)+'  '+str(f.relative_to(p))+'\n' for f in files))
for f in files+[p/'SHA256SUMS.txt']:
 dst=u/'Desktop'/f.relative_to(p)
 if not dst.exists() or sha(dst)!=sha(f):copy(f,dst)
copy(r/'desktop-sources/collect-desktop-failure.sh',u/'collect-desktop-failure.sh')
copy(doc,u/doc.name);copy(v/'VALIDATION.json',u/'windowserver-scanout-reservation-1.0.15-validation.json');copy(v/'scanout-reservation.patch',u/'windowserver-scanout-reservation-1.0.15.patch')
f=r/'research/windowserver-result-222154.md';s=f.read_text();correction='**Follow-up correction:** the full failed-boot log contains GuC crash/exception at22:19:41.790/.791 and non-recoverable wedged-on-init at22:19:41.795, preceding all Vulkan queries. The topology failure is downstream of an already failed GPU initialization. See windowserver-scanout-reservation-1.0.15.md.\n\n'
if not s.startswith('**Follow-up correction:**'):f.write_text(correction+s)
copy(f,u/f.name)
status=u/'PORT-STATUS.md';intro='# Current: NMXGPU1.0.15 GPU startup / firmware scanout reservation\n\nCorrected diagnosis: GuC crashed and i915 wedged during GPU initialization at22:19:41, BEFORE WindowServer zero-device queries.1.0.15 replaces whole stolen-region exclusion with bounds-checked/aligned actual GOP prefix exclusion and restores remaining stolen allocator. Adds init-phase errors and collector initialization summary. Local ASan/UBSan,438-object build, signature and installer/KC rollback checks pass. Hardware recovery and full accelerated desktop remain UNVERIFIED.\n\nDell fallback: install-windowserver.sh; after exit0 restart USB once without ResetNVRAM. On failure poweroff/USBfallback and collect-desktop-failure.sh before reinstalling. No22-case rerun. See windowserver-scanout-reservation-1.0.15.md.\n\n---\n\n'
if not status.read_text().startswith('# Current: NMXGPU1.0.15'):status.write_text(intro+status.read_text())
mf=u/'SHA256SUMS.json';m=json.loads(mf.read_text())
for n in ['PORT-STATUS.md','collect-desktop-failure.sh',doc.name,'windowserver-scanout-reservation-1.0.15-validation.json','windowserver-scanout-reservation-1.0.15.patch','windowserver-result-222154.md']:m[n]=sha(u/n)
mf.write_text(json.dumps(m,indent=2)+'\n')
verify(u/'Desktop',p/'SHA256SUMS.txt');verify(u,p/'WINDOWSERVER-BASELINE-SHA256SUMS.txt')
for n,h in m.items():assert sha(u/n)==h,n
for n,h in before.items():assert sha(u/'Desktop'/n)==h,n
assert sha(config:=efi/'config.plist')==config_hash and sha(efi/'Kexts/VoodooI2CHID.kext/Contents/MacOS/VoodooI2CHID')==hid_hash
for n in ['WindowServerKernel/NMXGPU.kext','PreviousWindowServerKernel/NMXGPU.kext']:subprocess.run(['codesign','--verify','--strict',str(u/'Desktop'/n)],check=True)
for f in [u/'Desktop/install-windowserver.sh',u/'collect-desktop-failure.sh']:subprocess.run(['/bin/bash','-n',str(f)],check=True)
print(json.dumps(validation,indent=2));print('Published1.0.15:',len(files),'package files. All manifests/signatures/syntax/frozen evidence verified; no host install, NVRAM edit, GPU suite or reboot.')
