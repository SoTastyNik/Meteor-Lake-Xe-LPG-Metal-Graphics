from pathlib import Path
import hashlib,json,plistlib,shutil,subprocess,difflib
r=Path(__file__).resolve().parent.parent;p=r/'latitude-desktop';u=Path('/Volumes/SEQOUIA/iGPU-Port');v=r/'port-artifacts/memory-report-0.3.6'
def sha(f):return hashlib.sha256(f.read_bytes()).hexdigest()
def copy(a,b):
 b.parent.mkdir(parents=True,exist_ok=True);t=b.with_name(b.name+'.publish-tmp');shutil.copy2(a,t);t.replace(b)
def verify(root,m):
 for line in m.read_text().splitlines():
  h,n=line.split('  ',1);assert sha(root/n)==h,n
config=u.parent/'EFI/OC/config.plist';config_sha=sha(config)
assert config.read_bytes()==(v/'config-before.plist').read_bytes(),'EFI changed since candidate preparation'
assert not plistlib.loads(config.read_bytes()).get('DeviceProperties',{}).get('Add',{}).get('PciRoot(0x0)/Pci(0x2,0x0)',{}),'Unexpected injected GPU properties'
verify(u,p/'WINDOWSERVER-BASELINE-SHA256SUMS.txt')
fixed=['WindowServerKernel/NMXGPU.kext/Contents/MacOS/NMXGPU','PreviousWindowServerKernel/NMXGPU.kext/Contents/MacOS/NMXGPU','WindowServerFramebuffer/LatitudeMTLFB.kext/Contents/MacOS/LatitudeMTLFB','Library/GPUBundles/NVMTLDriver.bundle/Contents/MacOS/NVMTLDriver','WindowServerTransport/libdrm.2.dylib','Library/GPUBundles/nvmtl/libdrm.2.dylib','Library/Extensions/NMXAccel.kext/Contents/MacOS/NMXAccel']
retained={n:sha(u/'Desktop'/n) for n in fixed}
for n,h in retained.items():assert sha(p/n)==h,n
backup=u/'backups/memory-report-before-0.3.6'
for n in ['Desktop/install-windowserver.sh','Desktop/BUILD-MANIFEST.json','Desktop/SHA256SUMS.txt','Desktop/README.md','collect-desktop-failure.sh','PORT-STATUS.md','SHA256SUMS.json']:
 b=backup/n
 if not b.exists():copy(u/n,b)
if not (backup/'EFI-config.plist').exists():copy(config,backup/'EFI-config.plist')
bundle=p/'WindowServerPlugin/NVMTLDriver.bundle';binary=bundle/'Contents/MacOS/NVMTLDriver'
copy(r/'desktop-build/NVMTLDriver-0.3.6',binary)
subprocess.run(['codesign','--force','--sign','-','--timestamp=none',str(bundle)],check=True)
subprocess.run(['codesign','--verify','--strict',str(bundle)],check=True)
def symbols(f,flag):return set(subprocess.check_output(['nm',flag,str(f)],text=True).splitlines())
baseline=p/'Library/GPUBundles/NVMTLDriver.bundle/Contents/MacOS/NVMTLDriver'
assert not (symbols(baseline,'-gjU')-symbols(binary,'-gjU')),'Baseline exports removed'
added_imports=sorted(symbols(binary,'-uj')-symbols(baseline,'-uj'))
assert not added_imports,added_imports
uuid=subprocess.check_output(['xcrun','dwarfdump','--uuid',str(binary)],text=True).split()[1]
validation={'plugin_version':'0.3.6','uuid':uuid,'sha256':sha(binary),'hardware_verified':False,'efi_unchanged_sha256':config_sha,'gpu_name_source':'VkPhysicalDeviceProperties.deviceName, returned directly for scoped integrated GPU','shared_capacity_source':'VkPhysicalDeviceMemoryProperties actual DEVICE_LOCAL heap; never forced to 1536/2048MB','recommended_working_set':'VK_EXT_memory_budget if available; otherwise existing conservative 70-percent queried-heap estimate, explicitly labelled; bounded by queried heap and no fixed 1/2GiB fallback','dedicated_memory_for_UMA':0,'system_information_Display_7MB_fixed':False,'retained_payloads':retained,'checks':['three plugin build variants pass','ASan/UBSan heap/type validation, shared-budget bounds and target scope pass','release logger pass','installer rollback/KC/one-shot fixtures pass','collector crash preservation and bounded display query pass','baseline exports preserved; no added external imports','code signature verified'],'full_gpu_suite_rerun':False,'limits':['No target validation yet. System Information obtains framebuffer identity through a separate registry path; this candidate does not bridge Vulkan identity into that path.','The physical scanout mapping remains its real size. No OpenCore VRAM or model injection.','Unsupported MTL userptr imports bypassed using the existing copy path; no zero-copy implementation or promise of curing CA timeouts.']}
(v/'VALIDATION.json').write_text(json.dumps(validation,indent=2)+'\n')
doc=r/'research/windowserver-memory-report-0.3.6.md'
doc.write_text('''# Query-based Metal memory reporting 0.3.6

The working 1.0.15 desktop checkpoint remains saved in checkpoints/usable-desktop-1.0.15-20261019-224818 and its dated USB archive. This candidate changes the Metal plugin and collector, preserving kernel, framebuffer, accelerator, transport and EFI configuration.

Per the user's correction, no fixed GPU model or 1536/2048MB property is injected. The unpublished config-2048MB.plist was removed. On the scoped integrated Intel GPU the Metal name comes directly from VkPhysicalDeviceProperties.deviceName (the existing backend previously reported Intel(R) Graphics (MTL)). Heap sizes come from VkPhysicalDeviceMemoryProperties. Unified-memory identity requires the actual integrated device type and matching PCI identity; dedicatedMemorySize is zero for that UMA device. This is shared system RAM, not dedicated VRAM.

The recommended working set uses the queried memory budget when available and never exceeds the queried device-local heap. If the backend lacks a usable budget extension, the existing conservative 70-percent heap estimate is explicitly identified as an estimate. A recommendation is not instantaneous free RAM or a physical reservation. The former fixed 1GiB floor and sparse full-heap shortcut are bypassed for this integrated device. Failed initialization reports unknown/zero, not invented 2GiB.

The existing plugin attempted host-pointer imports that the current compiled i915 userptr implementation cannot provide (compiled stub returns ENODEV). This candidate bypasses those failed attempts for 8086:7d45, using the already working private-image/copy fallback. It does not implement zero-copy or establish that CoreAnimation timeout/CPU issues are cured.

## The separate Display 7MB entry

Apple IOGraphics derives IOFBMemorySize from getVRAMRange length. This framebuffer intentionally exposes its actual rowBytes*height physical scanout range, approximately 7.9MiB. Enlarging that mapping to a pretend 2GiB would misrepresent the physical mapping. System Information also reads registry identity/memory properties separately from Metal. Therefore this plugin correction does not yet implement automatic registry publication for that display entry and cannot promise that label will change on the next boot. No cosmetic property injection substitutes for that remaining integration.

The collector now records a bounded SPDisplaysDataType JSON snapshot (20-second watchdog) to compare actual macOS labels and Metal support after the next boot. No 22-case suite rerun. Use install-windowserver.sh on the Dell fallback, wait for exit=0, then restart via USB once without resetting NVRAM. Collect on the usable trial boot, or on fallback after a failed trial, before reinstalling.

## Primary sources

- [Apple unified-memory API](https://developer.apple.com/documentation/metal/mtldevice/hasunifiedmemory)
- [Apple recommended working set](https://developer.apple.com/documentation/metal/mtldevice/recommendedmaxworkingsetsize)
- [Vulkan memory heaps and budgets](https://docs.vulkan.org/spec/latest/chapters/memory.html)
- [Apple IOGraphics framebuffer source](https://github.com/apple-oss-distributions/IOGraphics/blob/main/IOGraphicsFamily/IOFramebuffer.cpp)

Local checks and exact payload hashes are in the adjacent validation JSON. Hardware behavior of 0.3.6 remains unverified. Successful WindowServer GPU work from the earlier 1.0.15 report remains established.
''')
copy(doc,v/'RESEARCH.md')
patch=''
for name in ['NVMTLDevice.m','nvmtl_vk.c','nvmtl_vk.h','NVMTLObjects.m','nvmtl_log_failure.h']:
 a=r/'backups/memory-report-before-0.3.6'/name;b=r/'NullMoth/plugin'/name
 patch+=''.join(difflib.unified_diff(a.read_text().splitlines(True),b.read_text().splitlines(True),fromfile='a/'+name,tofile='b/'+name))
 copy(b,v/'source'/name)
copy(r/'NullMoth/plugin/nvmtl_memory_identity.h',v/'source/nvmtl_memory_identity.h')
(v/'memory-report.patch').write_text(patch)
for name in ['test-memory-identity.py','build-windowserver-0.3.6.py','test-windowserver-log.py','test-desktop-crash-collector.py']:copy(r/'desktop-sources'/name,v/name)
mf=p/'BUILD-MANIFEST.json';m=json.loads(mf.read_text());m['stage']='Query-based Metal reporting0.3.6 atop hardware-confirmed usable GPU1.0.15 desktop; no injected model or VRAM';m['memory_reporting']=validation;mf.write_text(json.dumps(m,indent=2)+'\n')
intro='# Current: automatic Metal identity and shared-memory reporting0.3.6\n\nGPU name and heap capacity come from Vulkan queries. No fixed model or 2048MB injection; EFI unchanged. Unified-memory reporting corrected and unsupported host imports use existing copy fallback. System Information Display7MB registry reporting remains unresolved. GPU1.0.15/framebuffer0.2.4/transport retained and working checkpoint saved. Local builds/checks pass; this candidate requires target confirmation. No full GPU suite rerun. See ../windowserver-memory-report-0.3.6.md.\n\n---\n\n'
f=p/'README.md'
if not f.read_text().startswith('# Current: automatic Metal'):f.write_text(intro+f.read_text())
files=sorted(f for f in p.rglob('*') if f.is_file() and not f.is_symlink() and 'reports' not in f.relative_to(p).parts and f.name!='SHA256SUMS.txt' and not f.name.startswith('._'))
(p/'SHA256SUMS.txt').write_text(''.join(sha(f)+'  '+str(f.relative_to(p))+'\n' for f in files))
for f in files+[p/'SHA256SUMS.txt']:
 dst=u/'Desktop'/f.relative_to(p)
 if not dst.exists() or sha(dst)!=sha(f):copy(f,dst)
copy(r/'desktop-sources/collect-desktop-failure.sh',u/'collect-desktop-failure.sh')
copy(doc,u/doc.name);copy(v/'VALIDATION.json',u/'windowserver-memory-report-0.3.6-validation.json')
f=u/'PORT-STATUS.md'
if not f.read_text().startswith('# Current: automatic Metal'):f.write_text(intro.replace('../','')+f.read_text())
mf=u/'SHA256SUMS.json';m=json.loads(mf.read_text())
for n in ['collect-desktop-failure.sh',doc.name,'windowserver-memory-report-0.3.6-validation.json','PORT-STATUS.md']:m[n]=sha(u/n)
for n in m:
 if n.startswith('Desktop/'):m[n]=sha(u/n)
mf.write_text(json.dumps(m,indent=2)+'\n')
verify(u/'Desktop',p/'SHA256SUMS.txt');verify(u,p/'WINDOWSERVER-BASELINE-SHA256SUMS.txt')
for n,h in m.items():assert sha(u/n)==h,n
for n,h in retained.items():assert sha(u/'Desktop'/n)==h,n
assert sha(config)==config_sha
assert sha(u/'backups/usable-desktop-1.0.15-20261019-224818.tar.gz')=='2aff830cf573dca9aa0bf5525fe0416370b2410104676ea6910e1a996bc9fe02'
subprocess.run(['codesign','--verify','--strict',str(u/'Desktop/WindowServerPlugin/NVMTLDriver.bundle')],check=True)
for f in [u/'Desktop/install-windowserver.sh',u/'collect-desktop-failure.sh']:subprocess.run(['/bin/bash','-n',str(f)],check=True)
print(json.dumps(validation,indent=2));print('Published',len(files),'package files; all hashes, signatures and syntax verified. EFI and working checkpoint unchanged. No target install or reboot.')
