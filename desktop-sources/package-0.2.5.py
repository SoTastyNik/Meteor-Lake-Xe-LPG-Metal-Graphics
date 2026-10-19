from pathlib import Path
import hashlib,json,subprocess,plistlib,shutil
root=Path(__file__).resolve().parent.parent;p=root/'latitude-desktop'
for bundle,binary,version in [('Library/Extensions/NMXGPU.kext','NMXGPU-1.0.7','1.0.7'),('Library/GPUBundles/NVMTLDriver.bundle','NVMTLDriver-0.2.5','0.2.5')]:
 b=p/bundle;info=b/'Contents/Info.plist';d=plistlib.loads(info.read_bytes());shutil.copy2(root/'desktop-build'/binary,b/'Contents/MacOS'/d['CFBundleExecutable']);d.update(CFBundleVersion=version,CFBundleShortVersionString=version);info.write_bytes(plistlib.dumps(d))
 subprocess.run(['codesign','--force','--sign','-',str(b)],check=True);subprocess.run(['codesign','--verify','--strict',str(b)],check=True)
f=p/'BUILD-MANIFEST.json';m=json.loads(f.read_text());m['runtime_revision']='desktop-0.2.5';m['built']['metal_plugin']='NVMTLDriver 0.2.5: terminal-error command buffers, scoped cache/barrier mitigation and first-submit tracing';m['built']['kernel']['revision']='1.0.7: bounded summary of already-captured first-error registers; no new MMIO accesses';m['desktop_candidate']['gpu_runtime_base']='1.0.6 app-tested base plus 1.0.7 captured-error summary; GPU execution changes not claimed'
m['candidate_0_2_4_validation']['on_target']='19:12 boot in report 20261018-191454 verified pipe identity, phase 2 and active pipe; rendering timed out and WindowServer crashed; desktop test failed'
m['candidate_0_2_5']={
'fix':'Failed command recording returns a command buffer with an encoding error and safe terminal encoders, completing as MTLCommandBufferStatusError instead of returning nil and provoking the observed rendering recursion',
'mitigation':'Set INTEL_DEBUG=stall before Mesa initialization only for WindowServer on 8086:7d45, preserving explicit INTEL_DEBUG values; experimental GPU synchronization/cache mitigation',
'diagnostics':'First 24 Intel submission begin/queue/fence events retained in release log; first actual 7d45 GPU error prints bounded captured GT/engine/GuC register summary',
'local_validation':['Real plugin fault-injection build: 80 failed command buffers completed with errors and completion callbacks, no scheduling claims or capacity exhaustion','Failed-encoder forwarding: 40000 repeated scissor/viewport pairs, no GPU method calls, ASan/UBSan passed','Scoped policy, registration identity and release-log fixtures passed ASan/UBSan','x86_64 release plugin and 438-object kernel link; no new kernel undefined symbols; signatures verified'],
'pending':'Target kmutil preflight, desktop boot, correct pixels, completion counters and no GPU hang remain unverified',
'limits':'Fault summary is not a full GPU coredump. Terminal encoders do not restore a stopped GPU. Stall mode can reduce performance and may not fix this hang.'}
f.write_text(json.dumps(m,indent=2)+'\n')
s=p/'install-runtime.sh';text=s.read_text();text=text.replace('Latitude desktop candidate 0.2.4 — verified pipe registration and failure capture','Latitude desktop candidate 0.2.5 — failure handling and conservative GPU barriers');s.write_text(text)
r=p/'README.md';text=r.read_text()
if not text.startswith('# Desktop candidate 0.2.5'):
 r.write_text('''# Desktop candidate 0.2.5 — failure handling and GPU barrier experiment

Candidate 0.2.4 confirmed registration and phase-2 power-on, then a five-second fence timeout disabled the backend. WindowServer subsequently exhausted its stack retrying nil command buffers. The new plugin returns terminal-error command buffers with encoders that accept calls without issuing GPU commands. Commit reports an error; it does not report successful rendering. A native fault-injection build of the real plugin exercised 80 such buffers, error callbacks, waits and capacity release. A separate forwarding test exercised 40,000 scissor/viewport pairs under ASan/UBSan.

For WindowServer on 8086:7D45 only, this candidate selects Mesa INTEL_DEBUG=stall before initialization, unless explicitly configured already. This documented experimental mode adds cache flushes/barriers between drawing operations. It may reduce performance; it is not a confirmed cure for this GPU hang. Other applications keep the existing policy. Reference: https://docs.mesa3d.org/drivers/anv.html#debugging-tips . The five-second WindowServer fence timeout stays unchanged.

GPU 1.0.7 adds a bounded first-error register summary from state already captured by i915: no extra MMIO reads, no mode-setting changes and no full-coredump serialization. Release logs also retain the first 24 Intel submission begin/queue/fence events. These supplement the saved startup log and recovery collector. NMXAccel remains 0.2.4, panel/claim 0.2.3. No firmware, security or persistent boot-opt-in changes.

Install on the Dell with `sudo /bin/bash /Volumes/SEQOUIA/iGPU-Port/install-desktop.sh`. After exit=0, reboot through USB once. If usable, allow two minutes and collect with `sudo /bin/bash /Volumes/SEQOUIA/iGPU-Port/collect-desktop.sh`. If artifacting/black, power off and boot through USB again without reinstalling, then collect from the fallback desktop. Correct accelerated composition and GPU stability remain unverified.

''' +text)
for script in ['install-runtime.sh','collect-runtime.sh','rollback-runtime.sh','Library/NullMoth/load-panel-framebuffer.sh']:subprocess.run(['/bin/bash','-n',str(p/script)],check=True)
files=sorted(x for x in p.rglob('*') if x.is_file() and not x.is_symlink() and 'reports' not in x.relative_to(p).parts and x.name!='SHA256SUMS.txt' and not x.name.startswith('._'))
(p/'SHA256SUMS.txt').write_text(''.join(hashlib.sha256(x.read_bytes()).hexdigest()+'  '+str(x.relative_to(p))+'\n' for x in files))
with (root/'desktop-build/package-0.2.5-check.txt').open('w') as out:subprocess.run(['shasum','-a','256','-c','SHA256SUMS.txt'],cwd=p,stdout=out,check=True)
print('Packaged',len(files),'checksummed files')
