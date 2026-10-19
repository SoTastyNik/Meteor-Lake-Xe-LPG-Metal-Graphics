from pathlib import Path
import hashlib,json,subprocess,plistlib,shutil
r=Path(__file__).resolve().parent.parent;p=r/'latitude-desktop';backup=r/'backups/desktop-0.2.6-before/package';backup.mkdir(parents=True,exist_ok=True)
changed=['Library/GPUBundles/NVMTLDriver.bundle','Library/GPUBundles/nvmtl/libdrm.2.dylib','BUILD-MANIFEST.json','README.md','install-runtime.sh','SHA256SUMS.txt']
for rel in changed:
 src=p/rel;dst=backup/rel
 if dst.exists():continue
 dst.parent.mkdir(parents=True,exist_ok=True)
 if src.is_dir():shutil.copytree(src,dst)
 else:shutil.copy2(src,dst)
b=p/'Library/GPUBundles/NVMTLDriver.bundle';info=b/'Contents/Info.plist';d=plistlib.loads(info.read_bytes());shutil.copy2(r/'desktop-build/NVMTLDriver-0.2.6',b/'Contents/MacOS'/d['CFBundleExecutable']);d.update(CFBundleVersion='0.2.6',CFBundleShortVersionString='0.2.6');info.write_bytes(plistlib.dumps(d));subprocess.run(['codesign','--force','--sign','-',str(b)],check=True)
lib=p/'Library/GPUBundles/nvmtl/libdrm.2.dylib';shutil.copy2(r/'build-tree/drm-build/libdrm.2.dylib',lib);subprocess.run(['install_name_tool','-id','/Library/GPUBundles/nvmtl/libdrm.2.dylib',str(lib)],check=True);subprocess.run(['codesign','--force','--sign','-',str(lib)],check=True)
subprocess.run(['codesign','--force','--sign','-',str(p/'tools/latitude-readback-test')],check=True)
f=p/'BUILD-MANIFEST.json';m=json.loads(f.read_text());m['runtime_revision']='desktop-0.2.6-readback';m['stage']='Isolated readback correctness candidate; Intel hardware validation pending';m['built']['metal_plugin']='NVMTLDriver 0.2.6: shared validated readback, host dependency, subresource layout restoration, coherent-memory checks and resource-correlated tracing';m['built']['libdrm']='x86_64 IOKit transport plus fail-closed process-scoped direct/IOKit test routing and actual ioctl counters'
m['candidate_0_2_5']['on_target']='Failed: report 20261018-194932, readback fence timeout and GPU HANG; INTEL_DEBUG=stall did not fix the hang; WindowServer aborted after backend shutdown'
m['candidate_0_2_6']={
 'readback':['Transfer-write to host-read buffer barrier before CPU access','All-command producer dependency for both full and region reads','Restore copied mip/layer layout within the same command buffer; no readback mutation of shared layout state','Validate mip/layer/3D-slice/sample/usage/block/row bounds with checked arithmetic','Require known host-visible coherent staging type; no noncoherent staging silently accepted','Optional dedicated per-call staging, released only after successful completion; uncertain submissions retain allocations','Correlate readback sequence, image/stage identities, thread, memory type, copy parameters and fence outcome'],
 'experiments':['Deterministic changing-seed Metal upload/render/readback with exact pixel and padding comparisons','64x64 and 1920x1080, fresh/reused command pools and staging, fresh textures, independent two-thread work, serialized shared-texture handoff, IOSurface output','Forced direct/IOKit transport selected before opening DRM files, fail closed instead of switching handle namespaces, nonzero matching-route counters required'],
 'installation':'Default --readback-only: consume GPU opt-in once while removing panel opt-in; --desktop remains explicit and is not the recommended next test',
 'negative_experiment':'Automatic WindowServer INTEL_DEBUG=stall removed; opt-in NVMTL_DESKTOP_STALL retained for explicit diagnostic comparisons',
 'local_validation':['ASan/UBSan copy-plan and actual readback recording/failure tests','ASan/UBSan actual transport branch tests','Native Apple M4 harness exact-pixel checks, explicitly not Intel driver validation','x86_64 plugin, libdrm and test executable built'],
 'unresolved':['Intel target execution and 1000-frame gate','Resource concurrency outside readback: shared layout tracking in other render/compute/blit paths is not solved by this patch','No compatible synchronization validation layer has been proven loaded','Full GPU error export/GEM-request correlation remains conditional on isolated failure evidence','Desktop composition, modesetting, cursor, brightness, sleep/wake, video and external display support remain unverified']}
f.write_text(json.dumps(m,indent=2)+'\n')
readme='''# Candidate 0.2.6 — isolated readback test

The last desktop test still hung the GPU. This candidate repairs two concrete readback synchronization gaps and adds a controlled reproducer. It is not a confirmed desktop fix.

The default installer now selects **readback-only**: GPU enabled for one boot, custom panel ownership disabled. Firmware scanout stays available for running the application test. Run on the Dell:

```sh
sudo /bin/bash /Volumes/SEQOUIA/iGPU-Port/install-readback.sh
```

After exit=0, reboot through the USB once, then run:

```sh
sudo /bin/bash /Volumes/SEQOUIA/iGPU-Port/test-readback.sh
```

The first run uses 100 iterations per worker/case. It checks exact pixels at 64x64 and 1920x1080, padded rows, pool/staging/texture reuse, two independent threads, serialized shared-texture handoff, and IOSurface output. Each case prints progress every 50 frames and has a 600-second watchdog. The suite stops on the first failure. Actual route counters must prove direct devfs versus IOKit; a process name alone is insufficient. Logs are saved under `Desktop/reports/readback-TIMESTAMP`. It does not automatically run another desktop boot.

After reviewing the smoke-test report, the longer gate is `sudo /bin/bash /Volumes/SEQOUIA/iGPU-Port/test-readback.sh 1000`. Passing either suite does not certify WindowServer. Do not run against a GPU already hung by a desktop attempt. If the GPU hangs, power off and boot USB again without reinstalling; the GPU opt-in is one-shot.

Readback now waits for relevant prior GPU writes, copies the requested mip/layer, makes transfer writes visible to the host, restores that subresource's prior layout, waits for completion and only then copies CPU bytes. Coherent staging is verified; invalid bounds/usage/samples and unknown/noncoherent staging are refused. `NVMTL_READBACK_STAGE_FRESH=1` selects dedicated allocations bypassing buffer pools/parking. Failure retains potentially pending memory. `NVMTL_READBACK_TRACE=1` records copy identity, resources, memory type, thread and completion. Broader shared-image recording concurrency remains unresolved pending measurements.

Reference: [Khronos CPU readback synchronization examples](https://docs.vulkan.org/guide/latest/synchronization_examples.html) and [copy validity requirements](https://docs.vulkan.org/refpages/latest/refpages/source/vkCmdCopyImageToBuffer.html). The prior automatic `INTEL_DEBUG=stall` experiment failed on target and is no longer selected automatically.

Local checks verify recording/error paths and the harness on Apple M4. Intel readback stability, synchronization-layer validation, full GPU error export and physical desktop acceptance remain pending. NMXGPU remains 1.0.7, NMXAccel 0.2.4, panel/claim 0.2.3; no new kernel, firmware or security changes in this candidate.

---

## Historical candidate notes (commands below describe earlier desktop experiments)

'''
f=p/'README.md';old=f.read_text();f.write_text(readme+old)
for script in ['install-runtime.sh','test-readback.sh','collect-runtime.sh','rollback-runtime.sh','Library/NullMoth/load-panel-framebuffer.sh']:subprocess.run(['/bin/bash','-n',str(p/script)],check=True)
for b in [p/'Library/GPUBundles/NVMTLDriver.bundle',lib,p/'tools/latitude-readback-test']:subprocess.run(['codesign','--verify','--strict',str(b)],check=True)
files=sorted(x for x in p.rglob('*') if x.is_file() and not x.is_symlink() and 'reports' not in x.relative_to(p).parts and x.name!='SHA256SUMS.txt' and not x.name.startswith('._'))
(p/'SHA256SUMS.txt').write_text(''.join(hashlib.sha256(x.read_bytes()).hexdigest()+'  '+str(x.relative_to(p))+'\n' for x in files))
print('Packaged',len(files),'checksummed files')
