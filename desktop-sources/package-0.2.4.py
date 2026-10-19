from pathlib import Path
import json,hashlib,subprocess
root=Path(__file__).resolve().parent.parent;p=root/'latitude-desktop';mfile=p/'BUILD-MANIFEST.json';m=json.loads(mfile.read_text())
m['runtime_revision']='desktop-0.2.4'
m['built']['accelerator']='NMXAccel 0.2.4, Sequoia, verified framebuffer/pipe identity before arming'
m['built']['metal_plugin']='NVMTLDriver 0.2.4 x86_64, failure diagnostics incl. positive timeout disabling backend'
m['desktop_candidate']['framebuffer']='LatitudeMTLFB 0.2.3 in Auxiliary KC, LatitudePanelClaim 0.2.3; unchanged in candidate 0.2.4'
m['fixes_from_20261018_185355']=[
'Adopt an existing unique display pipe by framebuffer identity, rather than requiring a count increment',
'Set registered/piped bits only after validating pipe identity; leave refused heads pending for retry',
'Bound pipe walks to the existing 16-slot ABI; reject null entries and duplicate framebuffer identities',
'Keep backend-disabling positive Vulkan fence-timeout failures in release syslog',
'Log VkResult on host allocation import and command-buffer allocate/begin failure',
'Capture a 120-second live desktop log and registry snapshots only on an opted-in attempt; preserve across fallback boot',
'Collector copies saved logs, recent WindowServer crash reports and a bounded 15-minute retained desktop log']
m['candidate_0_2_4_validation']={
'local':'x86_64 accelerator and plugin built and signatures verified; identity and release-filter fixtures passed ASan/UBSan; shell scripts pass bash -n',
'on_target':'Pending target kmutil preflight, installation and one experimental boot',
'known_unresolved':'GPU hang root cause not yet established; extra firmware framebuffer unchanged; no full first-GPU-coredump export yet'}
mfile.write_text(json.dumps(m,indent=2)+'\n')
readme=p/'README.md';s=readme.read_text()
if not s.startswith('# Desktop candidate 0.2.4'):
 readme.write_text('''# Desktop candidate 0.2.4 — pipe registration correction

The 18:38 failed boot created a pipe before manual registration; the old code rejected its unchanged count and skipped phase-2 power notifications. NMXAccel now finds a unique pipe by framebuffer identity before adding one, and only marks the head registered after validation. Refusals remain retryable. Null, duplicate and out-of-range pipe tables are rejected. Existing Sequoia private-family offsets remain a compatibility limitation.

The Metal plugin now preserves positive fence-timeout/backend-disable messages in release syslog and logs VkResult for imported allocation and command-buffer creation failures. This fixes missing diagnostic evidence; it is not a proven fix for the separate GPU hang.

On an opted-in boot the existing background loader captures 120 seconds of live WindowServer/driver logs and registry snapshots at roughly 2, 10 and 30 seconds. The following fallback boot preserves them. collect-desktop.sh copies those logs, recent WindowServer crash reports and a bounded 15-minute retained log. These are text/registry diagnostics, not a complete GPU coredump.

Local: accelerator and plugin compile for x86_64; signatures verify; identity lookup and timeout-log regression cases pass ASan/UBSan; scripts pass Bash syntax checks. Target kmutil validation and actual desktop operation remain pending. Framebuffer/claim stay at 0.2.3, GPU stays at 1.0.6, firmware and EFI recovery policy are unchanged. Extra firmware display suppression is deferred to a separate experiment.

On the Dell: run `sudo /bin/bash /Volumes/SEQOUIA/iGPU-Port/install-desktop.sh`. Only after desktop install exit=0, reboot through the USB once. If usable, run `sudo /bin/bash /Volumes/SEQOUIA/iGPU-Port/collect-desktop.sh`. If black/artifacting, power off and boot through USB again without reinstalling, then run that collector from the fallback desktop.

''' + s)
for file in ['install-runtime.sh','collect-runtime.sh','rollback-runtime.sh','Library/NullMoth/load-panel-framebuffer.sh']:
 subprocess.run(['/bin/bash','-n',str(p/file)],check=True)
files=sorted(x for x in p.rglob('*') if x.is_file() and not x.is_symlink() and 'reports' not in x.relative_to(p).parts and x.name!='SHA256SUMS.txt' and not x.name.startswith('._'))
(p/'SHA256SUMS.txt').write_text(''.join(hashlib.sha256(x.read_bytes()).hexdigest()+'  '+str(x.relative_to(p))+'\n' for x in files))
subprocess.run(['shasum','-a','256','-c','SHA256SUMS.txt'],cwd=p,stdout=(root/'desktop-build/package-0.2.4-verification.txt').open('w'),check=True)
print('Manifest and',len(files),'package checksums verified')
