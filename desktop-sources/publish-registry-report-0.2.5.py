from pathlib import Path
import subprocess,shutil,hashlib,json,difflib
r=Path(__file__).resolve().parent.parent;p=r/'latitude-desktop';u=Path('/Volumes/SEQOUIA/iGPU-Port');v=r/'port-artifacts/registry-report';v.mkdir(exist_ok=True)
def sha(f):return hashlib.sha256(f.read_bytes()).hexdigest()
def copy(a,b):
 b.parent.mkdir(parents=True,exist_ok=True);t=b.with_name(b.name+'.publish-tmp');shutil.copy2(a,t);t.replace(b)
def verify(root,manifest):
 for line in manifest.read_text().splitlines():
  h,n=line.split('  ',1);assert sha(root/n)==h,n
verify(u,p/'WINDOWSERVER-BASELINE-SHA256SUMS.txt')
fixed=['WindowServerKernel/NMXGPU.kext/Contents/MacOS/NMXGPU','PreviousWindowServerKernel/NMXGPU.kext/Contents/MacOS/NMXGPU','Library/Extensions/NMXGPU.kext/Contents/MacOS/NMXGPU','Library/GPUBundles/NVMTLDriver.bundle/Contents/MacOS/NVMTLDriver','WindowServerPlugin/NVMTLDriver.bundle/Contents/MacOS/NVMTLDriver','WindowServerTransport/libdrm.2.dylib','Library/GPUBundles/nvmtl/libdrm.2.dylib','Library/Extensions/NMXAccel.kext/Contents/MacOS/NMXAccel']
retained={n:sha(u/'Desktop'/n) for n in fixed}
for n,h in retained.items():assert sha(p/n)==h,n
old=p/'PreviousWindowServerFramebuffer/LatitudeMTLFB.kext/Contents/MacOS/LatitudeMTLFB';new=p/'WindowServerFramebuffer/LatitudeMTLFB.kext/Contents/MacOS/LatitudeMTLFB'
assert sha(old)==sha(u/'Desktop/WindowServerFramebuffer/LatitudeMTLFB.kext/Contents/MacOS/LatitudeMTLFB')
efi=u.parent/'EFI';efi_hashes={str(f.relative_to(efi)):sha(f) for f in efi.rglob('*') if f.is_file() and not f.name.startswith('._')}
archive=u/'backups/usable-desktop-1.0.15-20261019-224818.tar.gz';archive_sha=sha(archive);assert archive_sha=='2aff830cf573dca9aa0bf5525fe0416370b2410104676ea6910e1a996bc9fe02'
backup=u/'backups/registry-report-before-0.2.5'
for n in ['Desktop/WindowServerFramebuffer','Desktop/Library/NullMoth','Desktop/install-windowserver.sh','Desktop/BUILD-MANIFEST.json','Desktop/SHA256SUMS.txt','Desktop/README.md','collect-desktop-failure.sh','PORT-STATUS.md','SHA256SUMS.json']:
 a=u/n;b=backup/n
 if b.exists():continue
 if a.is_dir():shutil.copytree(a,b)
 else:copy(a,b)
for f in [p/'WindowServerFramebuffer/LatitudeMTLFB.kext',p/'Library/NullMoth/latitude-gpu-identity']:subprocess.run(['codesign','--verify','--strict',str(f)],check=True)
for f in [p/'install-windowserver.sh',p/'Library/NullMoth/load-panel-framebuffer.sh',r/'desktop-sources/collect-desktop-failure.sh']:subprocess.run(['/bin/bash','-n',str(f)],check=True)
def imp(f):return set(subprocess.check_output(['nm','-uj',str(f)],text=True).splitlines())
imports=sorted(imp(new)-imp(old));expected=['__ZN12IOUserClient18clientHasPrivilegeEPvPKc','__ZN12OSDictionary9metaClassE','__ZN8OSNumber10withNumberEyj','__ZN8OSNumber9metaClassE','__ZN8OSString9metaClassE','_current_task'];assert imports==expected,imports
uuid=subprocess.check_output(['xcrun','dwarfdump','--uuid',str(new)],text=True).split()[1]
assert uuid==(p/'WindowServerFramebuffer/LatitudeMTLFB-UUID.txt').read_text().strip()
validation={'framebuffer_version':'0.2.5','uuid':uuid,'sha256':sha(new),'reporter_sha256':sha(p/'Library/NullMoth/latitude-gpu-identity'),'hardware_display_label_verified':False,'method':'Root helper waits for PCI claim, directly queries ANV name and device-local shared heap, passes typed report to LatitudeMTLFB, which publishes model Data and VRAM,totalMB Number on matched PCI device plus mirrors to FB and accelerator. Helper verifies PCI readback.','memory_meaning':'Actual ANV shared device-local heap capacity, not current free RAM or dedicated VRAM; whole MiB for standard UI property, exact bytes preserved in NMXSharedMemoryBytes.','no_fixed_gpu_name_or_memory_size':True,'physical_mapping_unchanged':True,'efi_hashes':efi_hashes,'working_checkpoint_sha256':archive_sha,'retained_payloads':retained,'added_kernel_imports':imports,'local_checks':['framebuffer x86_64 compile/link/signature pass','reporter x86_64 build/signature pass','actual kernel method ASan/UBSan: PCI/FB/accelerator fields, >4GiB capacities, privilege/device/claim/type/name/bounds/OOM rejection, no physical mapping changes','actual reporter ASan/UBSan simulated ICD/IOKit: variable names/capacities and >4GiB readback, failure guards, unclaimed GPU refused before query','installer fixtures: prior framebuffer accepted, root helper installed/backed up, helper verification failure rolls back, existing KC/transport/plugin rollback passes','loader fixtures: identity helper only on successful active framebuffer, reporting failure preserves framebuffer result, fallback skips','collector fixtures pass; identity logs retained; profiler query bounded'],'full_gpu_suite_rerun':False,'limits':['Host SPDisplaysReporter disassembly confirms model/VRAM,totalMB path and Intel shared-memory classification; target Sequoia formatting still requires actual boot.','If reporting fails or times out, script records failure and leaves actual framebuffer mappings alone; no fabricated label is substituted.','This reporting change does not establish a performance or CoreAnimation timeout fix.']}
(v/'VALIDATION.json').write_text(json.dumps(validation,indent=2)+'\n')
doc=r/'research/windowserver-registry-report-0.2.5.md'
doc.write_text('''# Driver-queried GPU identity and shared memory in System Information

## Diagnosis

The successful 1.0.15 desktop checkpoint is retained. The former Metal-only 0.3.6 correction did not publish the PCI registry properties used by System Information; that gap is addressed by this candidate.

Apple IOGraphics sets IOFBMemorySize from the actual framebuffer range length. On this panel that is the rowBytes*height scanout image, not the GPU's shared system-memory heap. It must remain physically accurate. Our old panel start also wrote an arbitrary 1GiB IOFBMemorySize property; that write is now excluded on the Latitude path. No physical aperture, timing, scanout allocation, GPU kernel, accelerator or transport logic is altered.

Inspection of both slices of this host's SPDisplaysReporter binary shows a separate PCI device property path: numeric VRAM,totalMB is read ahead of VRAM,totalsize (the latter uses a 32-bit byte value and truncates heaps above 4GiB). model supplies the GPU label. Intel vendor-id selects shared-memory presentation. These host binary findings are local evidence, not a claim to have executed Sequoia's reporter on the Dell.

## Implementation

LatitudeMTLFB 0.2.5 accepts only a narrowly scoped LatitudeGPUIdentity report through setProperties. It checks administrator privilege using the calling task, exact Intel 8086:7d45 device/claim and validated panel state, typed fields, version, bounded printable name, nonzero shared heap no larger than queried physical RAM, and safe MiB range. It then publishes the queried model as NUL-terminated Data and VRAM,totalMB as a Number on the actual PCI provider, mirroring onto our framebuffer/accelerator. Exact bytes and provenance remain in NMXSharedMemoryBytes/NMXGPUIdentity. Other setProperties requests follow the inherited implementation. It never enlarges getVRAMRange, getApertureRange or IOFBMemorySize to the shared heap size.

The new root boot helper latitude-gpu-identity waits up to 14 seconds for the matching framebuffer and nmxgpu-claimed before opening our installed ANV driver directly. It queries physical-device properties and memory properties, requires a unique integrated 8086:7d45 GPU, validates counts/indices/heap bounds and uses the largest actual DEVICE_LOCAL heap. For this integrated GPU that heap is shared system RAM. Name and capacity are queried each active desktop boot; neither a marketing name nor 1536/2048MB is hardcoded. Device-ID and ANV memory-limit overrides are cleared for this reporting query. No logical Vulkan device, queue, shader, allocation or rendering test is created.

The heap capacity is the driver's usable allocation limit, not instantaneous free RAM, a recommendation, or reserved dedicated VRAM. Mesa ANV's default integrated heap policy restricts the kernel-reported system-memory region: half up to 4GiB, three quarters above that. Thus a 16GiB region could expose a 12GiB heap; the actual query controls the label. This is not an assertion of the Dell's next returned value. The standard property uses whole MiB; exact bytes remain visible for auditing.

After publication the helper reads back the PCI model and VRAM,totalMB and reports VERIFIED only if both match. load-panel-framebuffer.sh runs it under a 20-second watchdog after successful framebuffer load; reporting failure does not change the framebuffer load result. It preserves current/previous LatitudeGPUIdentity.log. The collector copies those logs and records a bounded system_profiler SPDisplaysDataType JSON snapshot. On fallback without a panel claim, the helper does not run. The installer backs up/replaces/restores this helper together with the loader/plugin, preserves the previous 0.2.4 framebuffer, validates the new framebuffer UUID/version in the final AuxKC and retains the unchanged GPU1.0.15 kernel.

## Validation and next boot

x86_64 framebuffer and helper compile/link and signatures pass. Actual kernel reporting method and reporter code run under ASan/UBSan with mocked IOKit/driver endpoints: varying driver names and >4GiB capacities are preserved; invalid privilege/device/claim/field/name/count/index/size cases fail; failed publication/readback is rejected. Installer/KC/rollback and loader failure-isolation fixtures pass. These are local checks; target System Information output remains unverified until the next Dell trial. No 22-case GPU suite rerun.

On the Dell USB fallback desktop:

```sh
sudo /bin/bash /Volumes/SEQOUIA/iGPU-Port/install-windowserver.sh
```

After exit=0, restart through this USB once without ResetNVRAM. On a usable trial desktop run:

```sh
sudo /bin/bash /Volumes/SEQOUIA/iGPU-Port/collect-desktop-failure.sh
```

If the trial fails, power off and boot USB fallback, then collect before reinstalling. Reporting success means matched PCI property readback plus a System Information snapshot showing the queried name/shared capacity. Existing actual scanout size in IOFBMemorySize is expected and must not be mistaken for a failed shared-heap publication. No automatic reboot, target install or NVRAM changes were performed on the build host. The saved working 1.0.15 EFI/archive remains unchanged.

## Primary references

- [Apple IOGraphics framebuffer source](https://github.com/apple-oss-distributions/IOGraphics/blob/main/IOGraphicsFamily/IOFramebuffer.cpp): IOFBMemorySize follows physical mapping length.
- [Apple XNU IOKit user-client source](https://github.com/apple-oss-distributions/xnu/blob/main/iokit/Kernel/IOUserClient.cpp): calling-task privilege validation.
- [Vulkan physical-device properties](https://docs.vulkan.org/refpages/latest/refpages/source/VkPhysicalDeviceProperties.html): deviceName and PCI identity fields.
- [Vulkan physical-device memory properties](https://docs.vulkan.org/refpages/latest/refpages/source/VkPhysicalDeviceMemoryProperties.html): heaps and device-local memory flags.
- [Mesa ANV physical-device source](https://gitlab.freedesktop.org/mesa/mesa/-/blob/main/src/intel/vulkan/anv_physical_device.c): integrated system heap restrictions. The local compiled-source tree was inspected read-only.

Source snapshots, exact validation hashes and host reporter disassembly are in port-artifacts/registry-report. Reporting correction does not by itself cure remaining composition timeouts or establish a performance improvement.
''')
copy(doc,v/'RESEARCH.md')
sources=[r/'desktop-sources'/n for n in ['latitude_gpu_identity.h','latitude_gpu_identity_kernel.inc','latitude-gpu-identity.m','test-gpu-identity-kernel.py','test-gpu-identity-reporter.py','build-gpu-identity.py','build-framebuffer-0.2.5.py','test-windowserver-installer.py','test-desktop-loader.py']]
for f in sources:copy(f,v/'source'/f.name)
copy(r/'NullMoth/kexts/NMXVGAFB/nmxvgafb.cpp',v/'source/nmxvgafb.cpp')
patch=''
for f in [r/'NullMoth/kexts/NMXVGAFB/nmxvgafb.cpp',p/'install-windowserver.sh',p/'Library/NullMoth/load-panel-framebuffer.sh',r/'desktop-sources/collect-desktop-failure.sh']:
 original=r/'backups/registry-report-before-0.2.5'/f.name
 patch+=''.join(difflib.unified_diff(original.read_text().splitlines(True),f.read_text().splitlines(True),fromfile='a/'+str(f.relative_to(r)),tofile='b/'+str(f.relative_to(r))))
(v/'registry-report.patch').write_text(patch)
copy(r/'desktop-build/framebuffer-0.2.5.log',v/'framebuffer-build.log')
mf=p/'BUILD-MANIFEST.json';m=json.loads(mf.read_text());m['stage']='LatitudeMTLFB0.2.5 query-based registry name/shared-memory reporting atop hardware-confirmed usable GPU1.0.15 desktop; target label verification pending';m['registry_reporting']=validation;mf.write_text(json.dumps(m,indent=2)+'\n')
intro='# Current: queried GPU name and shared capacity in System Information\n\nLatitudeMTLFB0.2.5 and the new boot helper publish the actual ANV deviceName/shared heap to the matched PCI model/VRAM,totalMB registry fields. No fixed GPU name/2048MB injection; physical scanout mapping and GPU1.0.15 unchanged. Local build, sanitizer, installer/rollback and loader checks pass. Target label confirmation pending. Saved working checkpoint and EFI unchanged. See ../windowserver-registry-report-0.2.5.md.\n\nDell fallback: install-windowserver.sh; after exit0 restart through USB once without ResetNVRAM. Collect on usable trial, or fallback after failure, before reinstalling. No full GPU suite rerun. Historical notes below are superseded by this candidate.\n\n---\n\n'
f=p/'README.md'
if not f.read_text().startswith('# Current: queried GPU name'):f.write_text(intro+f.read_text())
files=sorted(f for f in p.rglob('*') if f.is_file() and not f.is_symlink() and 'reports' not in f.relative_to(p).parts and f.name!='SHA256SUMS.txt' and not f.name.startswith('._'))
(p/'SHA256SUMS.txt').write_text(''.join(sha(f)+'  '+str(f.relative_to(p))+'\n' for f in files))
for f in files+[p/'SHA256SUMS.txt']:
 dst=u/'Desktop'/f.relative_to(p)
 if not dst.exists() or sha(dst)!=sha(f):copy(f,dst)
copy(r/'desktop-sources/collect-desktop-failure.sh',u/'collect-desktop-failure.sh');copy(doc,u/doc.name);copy(v/'VALIDATION.json',u/'windowserver-registry-report-0.2.5-validation.json')
f=u/'PORT-STATUS.md'
if not f.read_text().startswith('# Current: queried GPU name'):f.write_text(intro.replace('../','')+f.read_text())
mf=u/'SHA256SUMS.json';m=json.loads(mf.read_text())
for n in ['collect-desktop-failure.sh',doc.name,'windowserver-registry-report-0.2.5-validation.json','PORT-STATUS.md']:m[n]=sha(u/n)
for n in m:
 if n.startswith('Desktop/'):m[n]=sha(u/n)
mf.write_text(json.dumps(m,indent=2)+'\n')
verify(u/'Desktop',p/'SHA256SUMS.txt');verify(u,p/'WINDOWSERVER-BASELINE-SHA256SUMS.txt')
for n,h in m.items():assert sha(u/n)==h,n
for n,h in retained.items():assert sha(u/'Desktop'/n)==h,n
for n,h in efi_hashes.items():assert sha(efi/n)==h,n
assert sha(archive)==archive_sha
for f in [u/'Desktop/WindowServerFramebuffer/LatitudeMTLFB.kext',u/'Desktop/Library/NullMoth/latitude-gpu-identity']:subprocess.run(['codesign','--verify','--strict',str(f)],check=True)
print('Published registry-report0.2.5:',len(files),'package files; manifests/signatures/syntax, previous framebuffer, frozen GPU evidence, EFI and saved checkpoint verified. No target install, NVRAM changes, suite rerun or reboot.')
print(json.dumps({k:validation[k] for k in ['framebuffer_version','uuid','sha256','reporter_sha256','hardware_display_label_verified']},indent=2))
