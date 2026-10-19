from pathlib import Path
import tempfile,subprocess,os
r=Path(__file__).resolve().parent.parent
with tempfile.TemporaryDirectory(prefix='ws-installer-') as tmp:
 base=Path(tmp)
 for mode in ['success','baseline','kernel','partial','verify']:
  p=base/mode;p.mkdir();pkg=p/'Desktop';pkg.mkdir();(p/'bin').mkdir();lib=p/'installed/Library'
  for root in [pkg/'Library',lib]:
   for name in ['NMXGPU','NMXAccel']:
    f=root/f'Extensions/{name}.kext/Contents/MacOS/{name}';f.parent.mkdir(parents=True);f.write_text('verified-'+name)
   f=root/'GPUBundles/nvmtl/libdrm.2.dylib';f.parent.mkdir(parents=True);f.write_text('verified-drm')
   f=root/'GPUBundles/NVMTLDriver.bundle/Contents/MacOS/NVMTLDriver';f.parent.mkdir(parents=True);f.write_text('old-plugin' if root==lib else 'new-plugin')
  for name in ['NMXGPU','NMXAccel']:(pkg/(name+'-UUID.txt')).write_text('verified-'+name+'-uuid\n')
  (pkg/'SHA256SUMS.txt').write_text('fixture');(pkg/'WINDOWSERVER-BASELINE-SHA256SUMS.txt').write_text('fixture')
  s=(r/'latitude-desktop/install-windowserver.sh').read_text().replace('/Library',str(lib));s=s.replace('$HERE'+str(lib),'$HERE/Library');(pkg/'install-windowserver.sh').write_text(s)
  scripts={'id':'echo 0','uname':'echo x86_64','sw_vers':'echo 24H32','ioreg':'case "$*" in *GFX0*) echo \'"device-id" = <457d0000>\';; esac','kmutil':'if [ "$MODE" = kernel ]; then echo \'com.nullmoth.NMXGPU (1.0.7) wrong-uuid\'; else echo \'com.nullmoth.NMXGPU (1.0.8) verified-NMXGPU-uuid\'; fi; echo \'com.nullmoth.NMXAccel (0.2.4) verified-NMXAccel-uuid\'; echo com.dhinakg.AMFIPass','codesign':'if [ "$MODE" = verify ] && [ "${@: -1}" = "$MOCK_DEST" ]; then exit 1; fi; exit 0','shasum':'[ "$MODE" != baseline ] || exit 1; echo fixture-sha','chown':'exit 0','ditto':'exec /bin/cp -R "$1" "$2"','nvram':'echo "$*" >> "$MOCK_NVRAM"; if [ "$MODE" = partial ] && [ "$*" = nullmoth-panel-once=1 ]; then exit 1; fi; echo "$*"'}
  for name,body in scripts.items():
   f=p/'bin'/name;f.write_text('#!/bin/bash\n'+body+'\n');f.chmod(0o755)
  dest=lib/'GPUBundles/NVMTLDriver.bundle';env=os.environ.copy();env.update(PATH=str(p/'bin')+':/usr/bin:/bin',MODE=mode,MOCK_DEST=str(dest),MOCK_NVRAM=str(p/'nvram.txt'))
  c=subprocess.run(['/bin/bash',str(pkg/'install-windowserver.sh')],env=env,capture_output=True,text=True,timeout=5)
  plugin=(dest/'Contents/MacOS/NVMTLDriver').read_text();calls=(p/'nvram.txt').read_text().splitlines() if (p/'nvram.txt').exists() else []
  if mode=='success':assert c.returncode==0 and plugin=='new-plugin' and calls[:2]==['nullmoth-gpu-once=1','nullmoth-panel-once=1'],c.stdout+c.stderr
  else:
   assert c.returncode!=0 and plugin=='old-plugin',mode+c.stdout+c.stderr
   if mode in ['partial','verify']:assert calls[-2:]==['-d nullmoth-panel-once','-d nullmoth-gpu-once'],calls
   else:assert not calls,calls
  assert 'test-readback.sh' not in s and 'test-and-arm-desktop.sh' not in s
 print('PASS actual desktop-only installer: baseline/kernel guards before mutation, plugin-only replacement/backup, one-shot arming, rollback and opt-in cleanup on verification/partial-arm failures; no GPU suite')
