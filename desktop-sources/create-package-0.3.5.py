from pathlib import Path
r=Path(__file__).resolve().parent.parent
s=(r/'desktop-sources/package-0.3.4.py').read_text().replace('0.3.4','0.3.5').replace('candidate_0_3_4','candidate_0_3_5')
s=s.replace("'Desktop/install-windowserver.sh'","'Desktop/install-windowserver.sh','Desktop/update-windowserver-kernel.sh','collect-desktop-failure.sh'")
s=s.replace("p/'Library/Extensions/NMXAccel.kext']","p/'Library/Extensions/NMXAccel.kext',p/'WindowServerKernel/NMXGPU.kext']")
s=s.replace("r/'desktop-sources/collect-desktop-failure.sh']","r/'desktop-sources/collect-desktop-failure.sh',p/'update-windowserver-kernel.sh']")
a=s.index("intro='''");b=s.index("\nf=p/'README.md'",a)
s=s[:a]+'''intro='''+repr('''# Candidate0.3.5 — compression isolation plus request/GuC capture

Fresh readback staging did not prevent the0.3.4 GPU hang. This candidate disables image compression only in8086:7d45 WindowServer and installs diagnostic NMXGPU1.0.9. Its capture now includes owned request state and parsed GuC registers; legacy zero register placeholders alone were insufficient. This is an unverified workaround candidate, not a proven hang cure.

The installer verifies the saved22case/26,000frame application evidence. It does not rerun the suite. The original1.0.8 kernel remains frozen in the package;1.0.9 adds error diagnostics, without a scheduling, firmware, reset-policy or timeout change. Accelerator, framebuffer, firmware and transport remain unchanged. Compression off may affect bandwidth/performance.

On the Dell fallback desktop:

```sh
sudo /bin/bash /Volumes/SEQOUIA/iGPU-Port/install-windowserver.sh
```

This version also builds the next auxiliary kernel collection and backs up the previous GPU kernel/cache before committing. Wait for exit=0 and ONE desktop boot armed, then restart directly through USB once without ResetNVRAM. Kernel1.0.9 takes effect on restart. No automatic reboot or GPU tests.

If black/frozen/artifacting: power off, boot USB again for fallback, collect before reinstalling:

```sh
sudo /bin/bash /Volumes/SEQOUIA/iGPU-Port/collect-desktop-failure.sh
```

If visible, collect on that boot. A visible fallback desktop is not an acceleration pass. Bring back the USB after this single attempt.

[Research, source audit, validation and remaining limits](../windowserver-0.3.5-research.md).

---

Historical instructions below are superseded by this workflow.

''')+s[b:]
a=s.index("m['candidate_0_3_4']") if "m['candidate_0_3_4']" in s else -1
# New record is explicit: retain previous hardware outcomes as history.
needle="m['candidate_0_3_5']=";a=s.index(needle);b=s.index(";f.write_text(json.dumps(m,indent=2)",a)
s=s[:a]+'''m['candidate_0_3_4']['on_target']='Failed131639: submission8/third readback used distinct dedicated staging; lock and QueueSubmit succeeded;5sec fence timeout then GPUHANG. Fresh staging not sufficient. Sample captured restartedPID405, not original failure.'
m['candidate_0_3_5']={'changes':['INTEL_DEBUG includes noccs before Intel ICD dlopen only for8086:7d45 WindowServer','NMXGPU1.0.9 error-path request state and parsedGuC capture instead of relying solely on legacy zero placeholders','Transactional kernel/AuxKC update with preflight, backup/rollback, kcditto; current/fallback kernel identity collected'],'preserved':'Firmware, accelerator, framebuffer/claim, transport, original frozen1.0.8 and22case evidence; scheduling/reset/timeouts, fresh pools and quarantine unchanged','research':'windowserver-0.3.5-research.md','hardware_status':'Unverified compression workaround and diagnostic kernel; root cause remains unknown','kernel_uuid':(p/'WindowServerKernel/NMXGPU-UUID.txt').read_text().strip(),'kernel_sha256':sha(p/'WindowServerKernel/NMXGPU.kext/Contents/MacOS/NMXGPU'),'plugin_sha256':sha(b/'Contents/MacOS/NVMTLDriver')}'''+s[b:]
s=s.replace("'desktop-0.3.5-windowserver-dedicated-readback'","'desktop-0.3.5-windowserver-noccs-guc-capture'")
s=s.replace("'Compiled/local checks passed; dedicated-staging desktop candidate; hardware validation pending'","'Compiled/local checks passed; scoped noccs workaround plus request/GuC kernel capture; hardware desktop pending'")
s=s.replace("'NVMTLDriver0.3.5: scoped dedicated fresh WindowServer readback allocations, safe known-error cleanup, bounded startup syslog'","'NVMTLDriver0.3.5: scoped noccs before ICD load; prior fresh staging/pools and bounded diagnostics preserved'")
a=s.index("status='''");b=s.index("\nfor f in [u/'PORT-STATUS.md'",a)
s=s[:a]+'''status='''+repr('''# Current:0.3.5 compression-isolation and kernel-capture candidate

The0.3.4 active desktop still hung on submission8/third readback with dedicated staging. The next candidate sets noccs only for this WindowServer/device and installs diagnostic NMXGPU1.0.9. Kernel capture now reports referenced request state and parsed GuC registers; zero legacy ring fields were not a complete hardware snapshot. No exact root cause or complete desktop fix is claimed.

Local builds, signatures, sanitizer fixtures, kernel link/import comparison, compression scope, installer/KC rollback and regressions pass. Saved22case/26,000frame evidence and original1.0.8 bundle are retained; no suite rerun requested. Firmware, accelerator, framebuffer and transport remain unchanged. The1.0.9 kernel changes diagnostics, not scheduling/reset/timeouts.

Next: Dell fallback install-windowserver.sh; this also prebuilds/backs up/updates AuxKC and kernel. Afterexit0 restart USB once without ResetNVRAM. Then collect-desktop-failure.sh on visible desktop, or poweroff/USBfallback then collect if it fails. No automatic reboot. See windowserver-0.3.5-research.md.

---

''')+s[b:]
a=s.index("validation={");b=s.index("\n(v/'VALIDATION.json')",a)
s=s[:a]+'''validation={'hardware_desktop_verified':False,'target_tests_run':False,'frozen_baseline':'22cases/26000frames/80020pools retained with originalkernel1.0.8; new diagnostic kernel not covered by that pass','local_passes':['Release x86_64 plugin/kernel/helper compile and ad-hoc signatures','438object kernel link; undefined imports identical to1.0.8','Actual parsedGuC logger ASan/UBSan:absent node, null/empty/large lists,192register bound; no new MMIO/waits/allocations','Actual noccs helper ASan/UBSan:exact scope, preserved existing flags, unset/empty/oversized handling; before-ICD-load ordering','Actual integrated installer+kernel helper with OS mocks:guards, success, KC preflight/mirroring, signature, journal and partial-arm rollback restores plugin/tools/kernel/cache','Separate actual kernel helper:already-current no-op and late rollback','Collector retains crashes/logs with current-kernel identity query, history failures still preserve artifacts','Actual native release policy masks47/63/38 and80failed command buffers','Actual readback implementation:20000balanced mocked allocations; timeout/backend-loss retention and app scope','Actual logger budget/throttle and loader/sample/fallback tests'],'unresolved':'Physical desktop and compression hypothesis; primary GPU hang cause not established'}'''+s[b:]
s=s.replace("['nvmtl_vk.c','NVMTLDevice.m','NVMTLObjects.m','nvmtl_desktop_policy.h']","['nvmtl_vk.c','NVMTLObjects.m','nvmtl_desktop_policy.h']")
s=s.replace("p/'install-windowserver.sh',p/'Library/NullMoth/load-panel-framebuffer.sh'","p/'install-windowserver.sh',p/'update-windowserver-kernel.sh',p/'Library/NullMoth/load-panel-framebuffer.sh'")
s=s.replace("r/'desktop-build/build-NVMTLDriver-0.3.5.log']","r/'desktop-build/build-NVMTLDriver-0.3.5.log',r/'desktop-build/kernel-link-1.0.9.log',r/'desktop-build/kernel-error-1.0.9.log',r/'desktop-build/kernel-guc-capture-1.0.9.log',r/'desktop-sources/collect-desktop-failure.sh']")
needle="for line in (u/'Desktop/SHA256SUMS.txt')";i=s.index(needle);s=s[:i]+'''shutil.copy2(r/'desktop-sources/collect-desktop-failure.sh',u/'collect-desktop-failure.sh')
for rel in ['i915_gpu_error.c','gt/uc/intel_guc_capture.c','gt/uc/intel_guc_capture.h']:
 src=r/'drm-kmod/drivers/gpu/drm/i915'/rel;old=r/'backups/kernel-1.0.9-before'/rel
 dst=v/'kernel-source'/rel;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,dst)
 (dst.parent/(dst.name+'.patch')).write_text(''.join(difflib.unified_diff(old.read_text().splitlines(True),src.read_text().splitlines(True),fromfile='a/'+rel,tofile='b/'+rel)))
'''+s[i:]
s=s.replace("u/'Desktop/Library/NullMoth/latitude-desktop-journal']","u/'Desktop/Library/NullMoth/latitude-desktop-journal',u/'Desktop/WindowServerKernel/NMXGPU.kext']")
s=s.replace("['PORT-STATUS.md','ROADMAP.md','windowserver-0.3.5-research.md'","['PORT-STATUS.md','ROADMAP.md','collect-desktop-failure.sh','windowserver-0.3.5-research.md'")
s=s.replace('immutable runtime preserved.','baseline retained; new diagnostic kernel separately staged.')
(r/'desktop-sources/package-0.3.5.py').write_text(s)
