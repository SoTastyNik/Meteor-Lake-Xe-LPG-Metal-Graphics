from pathlib import Path
import shutil,subprocess,plistlib,json,hashlib,difflib
r=Path(__file__).resolve().parent.parent;p=r/'latitude-desktop';u=Path('/Volumes/SEQOUIA/iGPU-Port');v=r/'port-artifacts/desktop-0.2.7';v.mkdir(parents=True,exist_ok=True)
backup=u/'backups/desktop-0.2.7-before';backup.mkdir(parents=True,exist_ok=True)
for rel in ['Desktop/Library/GPUBundles/NVMTLDriver.bundle','Desktop/Library/GPUBundles/nvmtl/libdrm.2.dylib','Desktop/install-runtime.sh','Desktop/test-readback.sh','Desktop/tools/latitude-readback-test','Desktop/tools/latitude-readback-test.m','Desktop/BUILD-MANIFEST.json','Desktop/README.md','Desktop/SHA256SUMS.txt','ROADMAP.md','PORT-STATUS.md']:
 src=u/rel;dst=backup/rel
 if not src.exists() or dst.exists():continue
 dst.parent.mkdir(parents=True,exist_ok=True)
 if src.is_dir():shutil.copytree(src,dst)
 else:shutil.copy2(src,dst)
b=p/'Library/GPUBundles/NVMTLDriver.bundle';f=b/'Contents/Info.plist';d=plistlib.loads(f.read_bytes());d.update(CFBundleVersion='0.2.7',CFBundleShortVersionString='0.2.7');f.write_bytes(plistlib.dumps(d));shutil.copy2(r/'desktop-build/NVMTLDriver-0.2.7',b/'Contents/MacOS'/d['CFBundleExecutable'])
lib=p/'Library/GPUBundles/nvmtl/libdrm.2.dylib';shutil.copy2(r/'build-tree/drm-build/libdrm.2.dylib',lib);subprocess.run(['install_name_tool','-id','/Library/GPUBundles/nvmtl/libdrm.2.dylib',str(lib)],check=True)
for target in [b,lib,p/'tools/latitude-readback-test',p/'tools/latitude-drm-route-test']:
 subprocess.run(['codesign','--force','--sign','-',str(target)],check=True);subprocess.run(['codesign','--verify','--strict',str(target)],check=True)
f=p/'BUILD-MANIFEST.json';m=json.loads(f.read_text());m['runtime_revision']='desktop-0.2.7-iokit';m['built']['metal_plugin']='NVMTLDriver 0.2.7: 0.2.6 readback fixes plus prior-access synchronization for IOSurface reupload and release-visible readback identity traces';m['built']['libdrm']='Forced IOKit discovery stays off devfs; token render-node classification; automatic IOKit discovery fallback when directory opens but nodes are unavailable';m['candidate_0_2_6']['on_target']='Report 20261018-201754: all 10 direct cases passed (1200 frames); IOKit failed before any ioctl due to forced-mode enumeration using raw devfs opens. No kernel hang/reset messages in saved history. Physical desktop was not retested.'
m['candidate_0_2_7']={'fixes':['Use IOKit metadata enumeration before devfs scanning in forced IOKit mode','Classify tracked IOKit token descriptors as DRM render nodes','Automatic enumeration can fall back through IOKit if directory access succeeds but individual node queries yield no devices; explicit direct mode stays isolated','IOSurface reuploads synchronize prior accesses using the tracked old layout and an all-command producer scope, instead of treating every reupload as first use','Retain readback identity messages in release logs by using the actual first-submit: filter prefix'],
 'tests':['Low-level discovery/open/fd-identity/nested-pointer ioctl probe before Metal creation','IOKit tested first; actual ioctl counters required','RGBA/BGRA IOSurface CPU backing checked immediately after command completion, before getBytes can affect state','22-case IOKit/direct matrix, 1000 iterations before automatic one-shot desktop arming','Native ASan/UBSan enumeration, routing, upload/readback barrier and readback failure tests; native Metal harness tests; mocked desktop-arm failure/success tests'],
 'desktop':'test-and-arm-desktop.sh runs 1000 iterations across all 22 cases and sets GPU/panel one-shots only after success; no automatic reboot',
 'pending':['IOKit hardware results and actual WindowServer desktop boot','IOSurface publication checks on Intel','Broader shared-image recording concurrency and physical desktop stability']};f.write_text(json.dumps(m,indent=2)+'\n')
intro='''# Candidate 0.2.7 — IOKit discovery and desktop preparation

The Dell's 0.2.6 report passed all ten direct tests (1,200 frames). Forced IOKit failed before any ioctl: enumeration used temporary raw devfs opens, then the forced IOKit policy rejected them. This candidate routes forced discovery through IOKit metadata and recognizes tracked IOKit tokens as render nodes. It also falls back through IOKit when automatic discovery can read the directory but cannot query its nodes.

The IOSurface reupload path now waits for prior image accesses using the tracked old layout rather than treating every reupload as an initial discard. This is a synchronization correction for the WindowServer path, not proof its hang is cured. Readback identity traces now match the release-log filter. Kernel, panel registration, firmware and security settings are unchanged.

On the Dell:

```sh
sudo /bin/bash /Volumes/SEQOUIA/iGPU-Port/install-readback.sh
```

After install exit=0, reboot through USB once. Then:

```sh
sudo /bin/bash /Volumes/SEQOUIA/iGPU-Port/test-and-arm-desktop.sh
```

This checks IOKit first and runs 1,000 iterations in each of 22 cases. It validates actual transport counters, exact pixels, padded rows, concurrency/reuse variants and both RGBA/BGRA IOSurface backing bytes. Backing bytes are checked immediately after GPU completion, before getBytes. The low-level discovery probe has a 60-second watchdog; workload cases have a 600-second watchdog. Progress prints every 50 frames. Reports remain under Desktop/reports/readback-TIMESTAMP. The script enables the experimental GPU/panel desktop for ONE boot only after the entire suite passes; it does not reboot automatically. On failure it stops and does not enable a desktop boot.

After the all-cases-passed/desktop-enabled message, reboot through USB. If usable, exercise window movement/resizing and collect with `sudo /bin/bash /Volumes/SEQOUIA/iGPU-Port/collect-desktop.sh`. If black/artifacting, power off and boot USB again WITHOUT reinstalling, then collect from fallback. A passing isolated suite is not a desktop success claim.

For a short diagnostic run without arming: `sudo /bin/bash /Volumes/SEQOUIA/iGPU-Port/test-readback.sh`. Local tests pass; Intel IOKit access, IOSurface publication and physical WindowServer remain pending.

Primary references: [Khronos synchronization](https://docs.vulkan.org/guide/latest/synchronization_examples.html), [Apple IOUserClient interface](https://github.com/apple-oss-distributions/IOKitUser/blob/main/IOKitLib.h). Detailed source changes and local validation are preserved in port-artifacts/desktop-0.2.7 on the build Mac.

---

## Historical candidate notes

'''
f=p/'README.md';f.write_text(intro+f.read_text())
for name in ['install-runtime.sh','test-readback.sh','test-and-arm-desktop.sh','collect-runtime.sh']:subprocess.run(['/bin/bash','-n',str(p/name)],check=True)
files=sorted(x for x in p.rglob('*') if x.is_file() and not x.is_symlink() and 'reports' not in x.relative_to(p).parts and x.name!='SHA256SUMS.txt' and not x.name.startswith('._'))
(p/'SHA256SUMS.txt').write_text(''.join(hashlib.sha256(x.read_bytes()).hexdigest()+'  '+str(x.relative_to(p))+'\n' for x in files))
for src in p.rglob('*'):
 rel=src.relative_to(p)
 if 'reports' in rel.parts or src.name.startswith('._'):continue
 dst=u/'Desktop'/rel
 if src.is_symlink():continue
 if src.is_dir():dst.mkdir(parents=True,exist_ok=True)
 elif not dst.exists() or src.read_bytes()!=dst.read_bytes():shutil.copy2(src,dst)
(u/'test-and-arm-desktop.sh').write_text('''#!/bin/bash
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
LOG="$HERE/test-and-arm-desktop-$(date +%Y%m%d-%H%M%S).txt"
/bin/bash "$HERE/Desktop/test-and-arm-desktop.sh" 2>&1 | tee "$LOG"
result=${PIPESTATUS[0]}
echo "DESKTOP PREPARATION exit=$result" | tee -a "$LOG"
exit "$result"
''')
for tool,name in [('test-iokit-enumeration','enumeration.txt'),('test-readback','barriers.txt'),('test-readback-recording','recording.txt'),('test-transport','transport.txt')]:
 with (v/name).open('w') as out:subprocess.run([str(r/'desktop-build'/tool)],stdout=out,stderr=subprocess.STDOUT,check=True)
with (v/'arming.txt').open('w') as out:subprocess.run(['/usr/bin/python3',str(r/'desktop-sources/test-desktop-arm.py')],stdout=out,stderr=subprocess.STDOUT,check=True)
for bgra in [False,True]:
 with (v/('native-bgra.txt' if bgra else 'native-rgba.txt')).open('w') as out:subprocess.run([str(r/'desktop-build/latitude-readback-test-native'),'--allow-native','--iterations','100','--size','1920x1080','--padding','64','--iosurface',*(['--bgra'] if bgra else [])],stdout=out,stderr=subprocess.STDOUT,check=True)
for src in [r/'libdrm/xf86drm.c',r/'NullMoth/plugin/nvmtl_readback.h',r/'latitude-desktop/tools/latitude-readback-test.m',r/'latitude-desktop/tools/latitude-drm-route-test.c',r/'desktop-sources/test-iokit-enumeration.py',r/'desktop-sources/test-desktop-arm.py',r/'desktop-build/failure-regression-0.2.7.txt',p/'BUILD-MANIFEST.json']:shutil.copy2(src,v/src.name)
patch=[]
for old,new,rel in [(r/'backups/desktop-0.2.7-before/xf86drm.c',r/'libdrm/xf86drm.c','libdrm/xf86drm.c'),(r/'backups/desktop-0.2.7-before/nvmtl_vk.c',r/'NullMoth/plugin/nvmtl_vk.c','NullMoth/plugin/nvmtl_vk.c')]:patch.extend(difflib.unified_diff(old.read_text().splitlines(True),new.read_text().splitlines(True),fromfile='a/'+rel,tofile='b/'+rel))
(v/'changes.patch').write_text(''.join(patch))
status='''## Candidate 0.2.7 prepared — target validation pending

0.2.6 passed all 10 direct cases on the Dell (1,200 frames, report 20261018-201754). Forced IOKit failed during enumeration before any ioctl. The new candidate fixes inconsistent forced-route enumeration and token node classification, adds automatic IOKit discovery fallback, and corrects prior-access synchronization during IOSurface reuploads. It also fixes the release filter prefix so image/staging traces are retained.

The revised suite tests IOKit first, probes metadata and nested-pointer ioctls, and checks actual RGBA/BGRA IOSurface backing pixels immediately after GPU completion. `test-and-arm-desktop.sh` runs 1,000 iterations across 22 cases and enables ONE desktop boot only if all cases pass. It does not reboot automatically. Use install-readback.sh, reboot USB once, then test-and-arm-desktop.sh. Details: Desktop/README.md.

Local ASan/UBSan routing/discovery/barrier/failure tests and native Apple M4 harness checks pass. They do not establish Intel IOKit correctness or WindowServer success. Both still need the target test. Shared-image recording concurrency and broader display features remain unverified.

'''
for f in [r/'ROADMAP.md',u/'PORT-STATUS.md']:
 text=f.read_text();idx=text.find('\n## ');idx=idx if idx>=0 else text.find('\n')
 f.write_text(text[:idx]+'\n\n'+status+text[idx:])
shutil.copy2(r/'ROADMAP.md',u/'ROADMAP.md');shutil.copy2(r/'ROADMAP.md',r/'research/desktop-roadmap-20261018.md')
(v/'VALIDATION.md').write_text(status+'\nSee enumeration.txt, barriers.txt, recording.txt, transport.txt and arming.txt for local fixtures. Native RGBA/BGRA backing-pixel tests each checked 100 full-HD frames on Apple M4. The current plugin fault-injection regression passed 80 failed command buffers. Hardware results are pending.\n')
shutil.copy2(v/'VALIDATION.md',u/'desktop-0.2.7-validation.md')
for line in (u/'Desktop/SHA256SUMS.txt').read_text().splitlines():
 digest,rel=line.split('  ',1);assert hashlib.sha256((u/'Desktop'/rel).read_bytes()).hexdigest()==digest,rel
for target in [u/'Desktop/Library/GPUBundles/NVMTLDriver.bundle',u/'Desktop/Library/GPUBundles/nvmtl/libdrm.2.dylib',u/'Desktop/tools/latitude-readback-test',u/'Desktop/tools/latitude-drm-route-test']:subprocess.run(['codesign','--verify','--strict',str(target)],check=True)
subprocess.run(['/bin/bash','-n',str(u/'test-and-arm-desktop.sh')],check=True)
f=u/'SHA256SUMS.json';m=json.loads(f.read_text())
for name in ['PORT-STATUS.md','ROADMAP.md','test-and-arm-desktop.sh','desktop-0.2.7-validation.md']:m[name]=hashlib.sha256((u/name).read_bytes()).hexdigest()
f.write_text(json.dumps(m,indent=2)+'\n')
print('Candidate 0.2.7 published:',len(files),'package hashes and four signatures verified; target reports preserved')
