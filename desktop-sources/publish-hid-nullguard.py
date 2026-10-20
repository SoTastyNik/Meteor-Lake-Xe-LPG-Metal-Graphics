from pathlib import Path
import hashlib, json, shutil, subprocess, difflib, plistlib

r=Path(__file__).resolve().parent.parent
u=Path('/Volumes/SEQOUIA/iGPU-Port'); p=r/'latitude-desktop'
v=r/'port-artifacts/hid-nullguard-1.0.1'; build=r/'desktop-build/hid-nullguard'
efi=u.parent/'EFI/OC'; target=efi/'Kexts/VoodooI2CHID.kext'
def sha(f): return hashlib.sha256(f.read_bytes()).hexdigest()
def copy(src,dst):
    dst.parent.mkdir(parents=True,exist_ok=True)
    shutil.copy2(src,dst)
def verify_manifest(root, manifest):
    for line in manifest.read_text().splitlines():
        h,rel=line.split('  ',1); assert sha(root/rel)==h,rel

assert u.is_dir() and target.is_dir()
verify_manifest(u,p/'WINDOWSERVER-BASELINE-SHA256SUMS.txt')
config_hash=sha(efi/'config.plist')
old=v/'Original-VoodooI2CHID.kext'
new=build/'VoodooI2CHID.kext'
binary='Contents/MacOS/VoodooI2CHID'
assert sha(target/binary) in {sha(old/binary),sha(new/binary)}
assert plistlib.loads((new/'Contents/Info.plist').read_bytes())['CFBundleVersion']=='1.0.1'
subprocess.run(['codesign','--verify','--strict',str(new)],check=True)
old_symbols=set(subprocess.check_output(['nm','-gjU',str(old/binary)],text=True).splitlines())
new_symbols=set(subprocess.check_output(['nm','-gjU',str(new/binary)],text=True).splitlines())
assert old_symbols<=new_symbols
gpu_hashes={rel:sha(u/'Desktop'/rel) for rel in [
    'WindowServerKernel/NMXGPU.kext/Contents/MacOS/NMXGPU',
    'WindowServerFramebuffer/LatitudeMTLFB.kext/Contents/MacOS/LatitudeMTLFB',
    'Library/GPUBundles/NVMTLDriver.bundle/Contents/MacOS/NVMTLDriver']}
backup=u/'backups/hid-nullguard-before'
if not (backup/'VoodooI2CHID.kext').exists():
    shutil.copytree(old,backup/'VoodooI2CHID.kext')
for name in ['config.plist']:
    if not (backup/name).exists(): copy(efi/name,backup/name)
for rel in ['Desktop/Library/NullMoth/load-panel-framebuffer.sh','collect-desktop-failure.sh','Desktop/BUILD-MANIFEST.json','Desktop/SHA256SUMS.txt','PORT-STATUS.md','SHA256SUMS.json']:
    if not (backup/rel).exists(): copy(u/rel,backup/rel)

src=r/'research/voodooi2c-core/VoodooI2C Satellites/VoodooI2CHID/VoodooI2CHID/VoodooI2CTouchscreenHIDEventDriver.cpp'
original=r/'research/voodooi2chid-source/VoodooI2CHID/VoodooI2CTouchscreenHIDEventDriver.cpp'
patch=''.join(difflib.unified_diff(original.read_text().splitlines(True),src.read_text().splitlines(True),fromfile='a/VoodooI2CHID/VoodooI2CTouchscreenHIDEventDriver.cpp',tofile='b/VoodooI2CHID/VoodooI2CTouchscreenHIDEventDriver.cpp'))
(v/'IOFBTransform-nullguard.patch').write_text(patch)
copy(src,v/src.name)
for name in ['build-hid-nullguard.py','test-hid-transform-nullguard.py','test-desktop-loader.py','test-desktop-crash-collector.py']:
    copy(r/'desktop-sources'/name,v/name)
for name in ['disassembly.txt','old-null-transform-sanitizer.txt']:
    copy(build/name,v/name)
validation={
    'version':'1.0.1','uuid':'D7FE79DC-8031-304F-8FBC-E413C10B56F7',
    'sha256':sha(new/binary),'original_sha256':sha(old/binary),
    'core_commit':'e3ac3ed207170c39db88d6a67a76cc9fd3a1895a',
    'hid_commit':'a478fd605043989269584a73e23a15cc78994f5b',
    'gpio_header_commit':'733dc8063f5ef07288a7bc648fff5348df6d8f65',
    'tests':['original null dereference reproduced with ASan/UBSan','actual patched function: 200000 modeled cases pass','original public symbols preserved; disassembly null branch verified','loader/collector mocked OS regressions pass'],
    'new_imports':['IOHIDEventService::newUserClient','IOHIDEventService::dispatchBiometricEvent'],
    'hardware_verified':False,'full_gpu_suite_rerun':False,
    'full_windowserver_acceleration_verified':False,'unchanged_gpu_payloads':gpu_hashes,
    'opencore_config_sha256':config_hash}
(v/'VALIDATION.json').write_text(json.dumps(validation,indent=2)+'\n')

# Publish the EFI bundle by verified copy then rename, retaining the original.
staged=target.with_name('VoodooI2CHID.kext.publish-tmp')
if staged.exists(): shutil.rmtree(staged)
shutil.copytree(new,staged)
assert sha(staged/binary)==validation['sha256']
subprocess.run(['codesign','--verify','--strict',str(staged)],check=True)
retired=target.with_name('VoodooI2CHID.kext.publish-old')
assert not retired.exists()
target.rename(retired)
try: staged.rename(target)
except BaseException:
    retired.rename(target); raise
shutil.rmtree(retired)
assert sha(efi/'config.plist')==config_hash

restore=u/'restore-usb-hid.sh'
restore.write_text('''#!/bin/bash
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
SOURCE="$HERE/backups/hid-nullguard-before/VoodooI2CHID.kext"
TARGET="$HERE/../EFI/OC/Kexts/VoodooI2CHID.kext"
[ -f "$SOURCE/Contents/MacOS/VoodooI2CHID" ] && [ -d "$TARGET" ] || exit 2
STAGE="$TARGET.restore-tmp"
[ ! -e "$STAGE" ] && [ ! -e "$TARGET.restore-old" ] || exit 2
cp -R "$SOURCE" "$STAGE"
cmp "$SOURCE/Contents/MacOS/VoodooI2CHID" "$STAGE/Contents/MacOS/VoodooI2CHID"
mv "$TARGET" "$TARGET.restore-old"
if ! mv "$STAGE" "$TARGET"; then mv "$TARGET.restore-old" "$TARGET"; exit 2; fi
rm -rf "$TARGET.restore-old"
echo 'Original USB VoodooI2CHID restored. OpenCore configuration unchanged. No reboot performed.'
'''); restore.chmod(0o755)

mfile=p/'BUILD-MANIFEST.json'; m=json.loads(mfile.read_text())
m['stage']='NMXGPU1.0.14 + HID1.0.1 null-transform guard; local checks pass; physical accelerated desktop unresolved'
m['hid_boot_guard']=validation
mfile.write_text(json.dumps(m,indent=2)+'\n')
copy(r/'desktop-sources/collect-desktop-failure.sh',u/'collect-desktop-failure.sh')
doc=r/'research/windowserver-hid-nullguard-1.0.1.md'
copy(doc,u/doc.name); copy(v/'VALIDATION.json',u/'hid-nullguard-1.0.1-validation.json')
copy(v/'IOFBTransform-nullguard.patch',u/'hid-nullguard-1.0.1.patch')
files=sorted(f for f in p.rglob('*') if f.is_file() and not f.is_symlink() and 'reports' not in f.relative_to(p).parts and f.name!='SHA256SUMS.txt' and not f.name.startswith('._'))
(p/'SHA256SUMS.txt').write_text(''.join(sha(f)+'  '+str(f.relative_to(p))+'\n' for f in files))
for f in files+[p/'SHA256SUMS.txt']:
    dst=u/'Desktop'/f.relative_to(p)
    if not dst.exists() or sha(dst)!=sha(f): copy(f,dst)
status=u/'PORT-STATUS.md'
intro='# Current: HID null-property panic guard + early capture\n\nLatest trial panicked in VoodooI2CHID forwardReport+0x4f at9.1seconds. Original USB binary matches panic UUID; missing IOFBTransform cast dereference reproduced. USB HID1.0.1 guards it and preserves input reports;200000 local cases pass. GPU1.0.14 unchanged. Full accelerated desktop remains UNVERIFIED. See windowserver-hid-nullguard-1.0.1.md.\n\nBoot Dell through USB fallback; run install-windowserver.sh; after exit0 restart through USB once without ResetNVRAM. On failure boot fallback and collect-desktop-failure.sh before reinstall. No22-case rerun. Original USB HID backed up; restore-usb-hid.sh restores it.\n\n---\n\n'
if not status.read_text().startswith('# Current: HID null-property'): status.write_text(intro+status.read_text())
mf=u/'SHA256SUMS.json'; root=json.loads(mf.read_text())
for name in ['PORT-STATUS.md','collect-desktop-failure.sh',doc.name,'hid-nullguard-1.0.1-validation.json','hid-nullguard-1.0.1.patch','restore-usb-hid.sh']:
    root[name]=sha(u/name)
mf.write_text(json.dumps(root,indent=2)+'\n')
verify_manifest(u/'Desktop',p/'SHA256SUMS.txt')
verify_manifest(u,p/'WINDOWSERVER-BASELINE-SHA256SUMS.txt')
for name,h in root.items(): assert sha(u/name)==h,name
for rel,h in gpu_hashes.items(): assert sha(u/'Desktop'/rel)==h,rel
for f in [restore,u/'collect-desktop-failure.sh',u/'Desktop/Library/NullMoth/load-panel-framebuffer.sh']:
    subprocess.run(['/bin/bash','-n',str(f)],check=True)
assert sha(efi/'config.plist')==config_hash
assert sha(target/binary)==validation['sha256']
print(json.dumps(validation,indent=2))
print('Published USB HID guard and capture update; manifests, signatures, syntax, unchanged GPU payloads and frozen evidence verified. No NVRAM change or reboot.')
