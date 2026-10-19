from pathlib import Path
import shutil,json,hashlib,subprocess
r=Path('/Users/ved/Documents/iGPU Port');u=Path('/Volumes/SEQOUIA/iGPU-Port');v=r/'port-artifacts/desktop-0.2.8-diagnostics';v.mkdir(parents=True,exist_ok=True)
# Only publish the read-only collector now. Keep the installed/tested USB
# driver candidate at 0.2.7 until the original error has been recovered.
shutil.copy2(r/'latitude-desktop/collect-readback-failure.sh',u/'Desktop/collect-readback-failure.sh')
(u/'collect-readback-failure.sh').write_text('''#!/bin/bash
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
LOG="$HERE/readback-failure-collection-$(date +%Y%m%d-%H%M%S).txt"
/bin/bash "$HERE/Desktop/collect-readback-failure.sh" 2>&1 | tee "$LOG"
result=${PIPESTATUS[0]}
echo "FAILURE COLLECTION exit=$result" | tee -a "$LOG"
exit "$result"
''')
# Add the collector without rewriting the existing candidate's binary hashes.
f=u/'Desktop/SHA256SUMS.txt';lines=[line for line in f.read_text().splitlines() if not line.endswith('  collect-readback-failure.sh')];digest=hashlib.sha256((u/'Desktop/collect-readback-failure.sh').read_bytes()).hexdigest();lines.append(digest+'  collect-readback-failure.sh');f.write_text('\n'.join(sorted(lines,key=lambda line:line.split('  ',1)[1]))+'\n')
result='''# Candidate 0.2.7 target result: IOKit works, long-run readback fails

Report: Desktop/reports/readback-20261018-203542. Install succeeded. IOKit enumeration/open/token identity/nested-pointer ioctl probe passed. Small raw, small render and full-HD render each passed 1,000 frames through verified IOKit transport. Padded full-HD readback failed at zero-based frame 745: channel 0 of pixel (0,0) remained 165 (0xA5, the initial destination fill), expected 33. It made 2,007,898 IOKit ioctl calls, zero direct calls. The ioctl count alone does not establish a fault cause. The test stopped before pool/staging A/B or IOSurface tests. No desktop gate or panel opt-in was set by the failed suite.

The untouched destination is consistent with an early readback error, but the existing public getBytes API is void. It is not proof of a stride arithmetic defect, GPU data corruption or a specific fence failure. The historical log search timed out while still reading earlier 20:18 events, before the current 20:35 boot. Its absence of a current GPU error is not useful evidence.

A read-only collector now queries a narrow failure-time interval derived from the report timestamp, captures kernel/NVMTL/IOKit messages, and saves current boot/registry/dmesg without issuing GPU tests or changing boot variables. Run `sudo /bin/bash /Volumes/SEQOUIA/iGPU-Port/collect-readback-failure.sh` on the Dell before another install or reboot. Save the USB afterward for inspection.

Local diagnostic build 0.2.8 is prepared but is NOT the USB runtime: explicit test-only stderr logging survives syslog throttling; readback and submit errors identify their phase; a revised runner captures kernel events live, bounds historical search to the current run and provides one-variable retained/fresh-pool/fresh-staging profiles. No GPU execution fix is claimed from this evidence. USB runtime remains 0.2.7 pending recovery of its original error.
'''
(u/'desktop-0.2.7-result.md').write_text(result);(v/'TARGET-RESULT.md').write_text(result)
f=u/'PORT-STATUS.md';old=f.read_text();backup=u/'backups/desktop-0.2.8-diagnostics';backup.mkdir(parents=True,exist_ok=True);shutil.copy2(f,backup/'PORT-STATUS.md');f.write_text('# Current: 0.2.7 IOKit discovery passes; long-run readback blocked\n\n'+result+'\n---\n\n'+old)
for tool,name in [('test-diagnostic-stderr','logger-fixture-output.txt'),('test-readback-recording','readback-fixture.txt')]:
 if tool=='test-diagnostic-stderr':continue
 with (v/name).open('w') as out:subprocess.run([str(r/'desktop-build'/tool)],stdout=out,stderr=subprocess.STDOUT,check=True)
with (v/'logger-fixture.txt').open('w') as out:subprocess.run(['/usr/bin/python3',str(r/'desktop-sources/test-diagnostic-stderr.py')],stdout=out,stderr=subprocess.STDOUT,check=True)
for src in [r/'desktop-sources/test-diagnostic-stderr.py',r/'latitude-desktop/collect-readback-failure.sh',r/'latitude-desktop/test-readback.sh',r/'desktop-build/plugin-0.2.8.log']:shutil.copy2(src,v/src.name)
for line in (u/'Desktop/SHA256SUMS.txt').read_text().splitlines():
 digest,rel=line.split('  ',1);assert hashlib.sha256((u/'Desktop'/rel).read_bytes()).hexdigest()==digest,rel
for rel in ['collect-readback-failure.sh','Desktop/collect-readback-failure.sh']:subprocess.run(['/bin/bash','-n',str(u/rel)],check=True)
f=u/'SHA256SUMS.json';m=json.loads(f.read_text())
for name in ['collect-readback-failure.sh','desktop-0.2.7-result.md','PORT-STATUS.md']:m[name]=hashlib.sha256((u/name).read_bytes()).hexdigest()
f.write_text(json.dumps(m,indent=2)+'\n')
print('Published read-only failure collector; USB 0.2.7 runtime and package hashes preserved/verified; local 0.2.8 diagnostic build archived')
