from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
import hashlib,json,shutil,tarfile
r=Path(__file__).resolve().parent.parent;u=Path('/Volumes/SEQOUIA');port=u/'iGPU-Port'
stamp=datetime.now(ZoneInfo('Europe/London')).strftime('%Y%m%d-%H%M%S')
name='usable-desktop-real-memory-0.2.5-'+stamp
out=r/'checkpoints'/name;out.mkdir(parents=True,exist_ok=False)
def sha(f):return hashlib.sha256(f.read_bytes()).hexdigest()
def copy(src,dst):dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,dst)
def tree(src,dst,skip_reports=False):
 for f in src.rglob('*'):
  relative=f.relative_to(src)
  if f.is_file() and not f.name.startswith('._') and not (skip_reports and 'reports' in relative.parts):copy(f,dst/relative)
old=port/'backups/usable-desktop-1.0.15-20261019-224818.tar.gz';old_sha=sha(old)
assert old_sha=='2aff830cf573dca9aa0bf5525fe0416370b2410104676ea6910e1a996bc9fe02'
# Verify the candidate payload against its package manifest before snapshotting.
for line in (port/'Desktop/SHA256SUMS.txt').read_text().splitlines():
 h,n=line.split('  ',1);assert sha(port/'Desktop'/n)==h,n
tree(u/'EFI',out/'EFI')
tree(port/'Desktop',out/'iGPU-Port/Desktop',skip_reports=True)
for n in ['install-windowserver.sh','collect-desktop-failure.sh','PORT-STATUS.md','SHA256SUMS.json','windowserver-result-231630.md','windowserver-result-231630.json','windowserver-registry-report-0.2.5.md','windowserver-registry-report-0.2.5-validation.json','windowserver-memory-report-0.3.6.md']:
 copy(port/n,out/'iGPU-Port'/n)
tree(port/'Desktop/reports/failure-detail-20261019-231630',out/'evidence/failure-detail-20261019-231630')
tree(port/'Desktop/reports/windowserver-install-20261019-231308',out/'evidence/windowserver-install-20261019-231308')
copy(port/'windowserver-install-20261019-231308.txt',out/'evidence/windowserver-install-20261019-231308.txt')
for n in ['latitude_gpu_identity.h','latitude_gpu_identity_kernel.inc','latitude-gpu-identity.m','build-gpu-identity.py','build-framebuffer-0.2.5.py','test-gpu-identity-kernel.py','test-gpu-identity-reporter.py']:
 copy(r/'desktop-sources'/n,out/'source'/n)
copy(r/'NullMoth/kexts/NMXVGAFB/nmxvgafb.cpp',out/'source/nmxvgafb.cpp')
(out/'README.txt').write_text('''Usable Dell desktop checkpoint: correct driver-queried GPU name and shared memory

Confirmed on Sequoia15.8.1/24H32, boot 19 October2026 23:14:31BST:
Intel(R) Graphics (MTL),12288MB shared heap (12884901888bytes),16GiB physical RAM.
GPU1.0.15; LatitudeMTLFB0.2.5; NMXAccel0.2.4; plugin0.3.6; guarded HID1.0.1.
GPU work confirmed; 24 capped initial fences and32 capped readbacks succeeded.
No new GPU hang/current-boot crash/panic captured. Smoothness remains unresolved:
42 CoreAnimation timeout lines, CPU128–206% in snapshots, early compilation and copy path.

EFI alone does not supply the corrected memory label. The matching Desktop driver
package, root installer/collector, reporting source, successful installer record
and target evidence are included with this EFI. The name/heap come from ANV
queries and kernel registry publication, not a hardcoded EFI name/VRAM property.

This is NOT a full disk/OS backup. Installed /Library runtime, the live target
AuxiliaryKernelExtensions.kc and live NVRAM are not captured. Boot markers are
one-shot and are not armed by saving/extracting this archive. The package contains
its existing guarded installation/rollback tools, which require the base Dell
runtime and supported OS; use the documented fallback installation procedure.
The root SHA256SUMS.json is preserved as historical package context; it can list
additional USB files outside this snapshot. The checkpoint SHA256SUMS.json is
the authoritative inventory for the files actually included here.

Restoration: inspect and verify this snapshot before replacing the USB EFI or
package. Use the saved matching package together with its EFI; restoring just
EFI does not reinstall the reporting framebuffer/helper/plugin on the OS.
Do not overwrite the system's current kernel collection with an unrelated host
cache. This checkpoint does not reboot, install, or reset NVRAM automatically.
The earlier dated1.0.15 checkpoint remains preserved separately.
''')
files=sorted(f for f in out.rglob('*') if f.is_file())
inventory={str(f.relative_to(out)):sha(f) for f in files}
(out/'SHA256SUMS.json').write_text(json.dumps(inventory,indent=2)+'\n')
for n,h in inventory.items():assert sha(out/n)==h,n
archive=r/'checkpoints'/(name+'.tar.gz')
with tarfile.open(archive,'w:gz',compresslevel=6) as tar:
 tar.add(out,arcname=name)
# Stream each archived regular file and match its saved inventory (including manifest).
archive_inventory=dict(inventory);archive_inventory['SHA256SUMS.json']=sha(out/'SHA256SUMS.json')
verified=0
with tarfile.open(archive,'r:gz') as tar:
 for entry in tar:
  if entry.isfile():
   rel=str(Path(entry.name).relative_to(name));stream=tar.extractfile(entry);h=hashlib.sha256()
   for chunk in iter(lambda:stream.read(1024*1024),b''):h.update(chunk)
   assert rel in archive_inventory and h.hexdigest()==archive_inventory[rel],rel;verified+=1
assert verified==len(archive_inventory)
usb_archive=port/'backups'/archive.name;copy(archive,usb_archive)
archive_sha=sha(archive);assert sha(usb_archive)==archive_sha
assert sha(old)==old_sha
location={'checkpoint':str(out),'local_archive':str(archive),'usb_archive':str(usb_archive),'sha256':archive_sha,'archive_entries_verified':verified,'archive_bytes':archive.stat().st_size,'confirmed_gpu_name':'Intel(R) Graphics (MTL)','shared_heap_mib':12288,'smoothness_resolved':False}
(out/'BACKUP-LOCATION.json').write_text(json.dumps(location,indent=2)+'\n')
copy(out/'BACKUP-LOCATION.json',port/'backups'/(name+'-location.json'))
print(json.dumps(location,indent=2))
