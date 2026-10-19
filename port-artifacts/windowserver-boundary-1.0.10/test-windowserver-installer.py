from pathlib import Path
import tempfile,subprocess,os,shutil,sys
r=Path(__file__).resolve().parent.parent
with tempfile.TemporaryDirectory(prefix='ws-installer-') as tmp:
 base=Path(tmp)
 for mode in ['previous','current','cache-repair-previous','success','baseline','kernel','partial','verify','journal','kc-preflight','kc-commit','cache-repair','bad-path','bad-uuid','final-build-fail']:
  p=base/mode;p.mkdir();pkg=p/'Desktop';pkg.mkdir();(p/'bin').mkdir();lib=p/'installed/Library'
  for root in [pkg/'Library',lib]:
   for name in ['NMXGPU','NMXAccel']:
    f=root/f'Extensions/{name}.kext/Contents/MacOS/{name}';f.parent.mkdir(parents=True);f.write_text('verified-'+name)
   f=root/'GPUBundles/nvmtl/libdrm.2.dylib';f.parent.mkdir(parents=True);f.write_text('verified-drm')
   f=root/'GPUBundles/NVMTLDriver.bundle/Contents/MacOS/NVMTLDriver';f.parent.mkdir(parents=True);f.write_text('old-plugin' if root==lib else 'new-plugin')
  for root in [pkg/'Library',lib]:
   f=root/'NullMoth/load-panel-framebuffer.sh';f.parent.mkdir(parents=True,exist_ok=True);f.write_text('#!/bin/bash\n# '+('old' if root==lib else 'new')+' loader\n')
   f=root/'NullMoth/latitude-desktop-journal';f.write_text('#!/bin/bash\n[ "$MODE" != journal ]\n' if root!=lib else '#!/bin/bash\n# old helper\n');f.chmod(0o755)
  for name in ['NMXGPU','NMXAccel']:(pkg/(name+'-UUID.txt')).write_text('verified-'+name+'-uuid\n')
  (pkg/'SHA256SUMS.txt').write_text('fixture');(pkg/'WINDOWSERVER-BASELINE-SHA256SUMS.txt').write_text('fixture')
  f=pkg/'WindowServerKernel/NMXGPU.kext/Contents/MacOS/NMXGPU';f.parent.mkdir(parents=True);f.write_text('diagnostic-kernel')
  if mode=='cache-repair':(lib/'Extensions/NMXGPU.kext/Contents/MacOS/NMXGPU').write_text('diagnostic-kernel')
  (pkg/'WindowServerKernel/NMXGPU-UUID.txt').write_text('E770B985-14A4-3ADE-A1EE-63204C3A9996')
  previous=pkg/'PreviousWindowServerKernel';shutil.copytree(pkg/'WindowServerKernel',previous)
  (previous/'NMXGPU.kext/Contents/MacOS/NMXGPU').write_text('previous-kernel')
  (previous/'NMXGPU-UUID.txt').write_text('previous-uuid')
  if mode in ['previous','cache-repair-previous']:(lib/'Extensions/NMXGPU.kext/Contents/MacOS/NMXGPU').write_text('previous-kernel')
  if mode=='current':(lib/'Extensions/NMXGPU.kext/Contents/MacOS/NMXGPU').write_text('diagnostic-kernel')
  system=p/'System'
  for cache in ['BootKernelExtensions.kc','SystemKernelExtensions.kc']:
   f=system/'KernelCollections'/cache;f.parent.mkdir(parents=True,exist_ok=True);f.write_text('system-cache')
  f=lib/'KernelCollections/AuxiliaryKernelExtensions.kc';f.parent.mkdir(parents=True);f.write_text('old-cache')
  helper=(r/'latitude-desktop/update-windowserver-kernel.sh').read_text().replace('/System/Library',str(system)).replace('/Library',str(lib))
  (pkg/'update-windowserver-kernel.sh').write_text(helper)
  s=(r/'latitude-desktop/install-windowserver.sh').read_text().replace('/Library',str(lib));s=s.replace('$HERE'+str(lib),'$HERE/Library');(pkg/'install-windowserver.sh').write_text(s)
  scripts={'id':'echo 0','uname':'echo x86_64','sw_vers':'echo 24H32','ioreg':'case "$*" in *GFX0*) echo \'"device-id" = <457d0000>\';; esac','kcditto':'if [ "$MODE" = kc-commit ] && [ ! -f "$MOCK_ONCE" ]; then touch "$MOCK_ONCE"; exit 7; fi','kmutil':'if [ "$1" = create ]; then [ "$MODE" != kc-preflight ] || exit 6; while [ "$#" -gt 0 ]; do if [ "$1" = -A ]; then shift; echo new-cache > "$1"; break; fi; shift; done; exit 0; fi; if [ "$MODE" = kernel ]; then echo \'com.nullmoth.NMXGPU (1.0.7) wrong-uuid\'; else echo \'com.nullmoth.NMXGPU (1.0.8) verified-NMXGPU-uuid\'; fi; echo \'com.nullmoth.NMXAccel (0.2.4) verified-NMXAccel-uuid\'; echo com.dhinakg.AMFIPass','codesign':'if [ "$MODE" = verify ] && [ "${@: -1}" = "$MOCK_DEST" ]; then exit 1; fi; exit 0','shasum':'[ "$MODE" != baseline ] || exit 1; echo fixture-sha','chown':'exit 0','ditto':'exec /bin/cp -R "$1" "$2"','nvram':'echo "$*" >> "$MOCK_NVRAM"; if [ "$MODE" = partial ] && [ "$*" = nullmoth-panel-once=1 ]; then exit 1; fi; echo "$*"'}
  (pkg/'WindowServerKernel/NMXGPU-VERSION.txt').write_text('1.0.10')
  shutil.copy2(r/'latitude-desktop/validate-kernel-prelink',pkg/'validate-kernel-prelink')
  emitter=pkg/'emit-prelink';emitter.write_text('#!'+sys.executable+'\n'+"""import os,plistlib
entry={'CFBundleIdentifier':'com.nullmoth.NMXGPU','CFBundleVersion':'1.0.10','OSBundleUUID':bytes.fromhex('e770b98514a43adea1ee63204c3a9996'),'_PrelinkBundlePath':os.environ['MOCK_KERNEL_DEST'],'_PrelinkExecutableRelativePath':'Contents/MacOS/NMXGPU','_PrelinkExecutableSize':3071690}
if os.environ['MODE']=='bad-path':entry['_PrelinkBundlePath']='/temporary/NMXGPU.kext'
if os.environ['MODE']=='bad-uuid':entry['OSBundleUUID']=bytes(16)
import sys
sys.stdout.buffer.write(plistlib.dumps({'_PrelinkInfoDictionary':[entry]}))
""");emitter.chmod(0o755)
  scripts['kmutil']='\nif [ "$1" = create ]; then\n  output=\'\'; paths=\'\'\n  while [ "$#" -gt 0 ]; do\n    case "$1" in -A) shift; output=$1;; -p) shift; paths="$paths $1";; esac\n    shift\n  done\n  case "$output" in *next-aux.kc) [ "$MODE" != preflight-fail ] && [ "$MODE" != kc-preflight ] || exit 6;; *installed-aux.kc) [ "$MODE" != final-build-fail ] || exit 7;; esac\n  printf \'new-cache\\n%s\\n%s\\n\' "$MOCK_UUID" "$paths" > "$output"\n  exit 0\nfi\nif [ "$1" = inspect ]; then exec "$MOCK_PRELINK_EMITTER"; fi\nif [ "$MODE" = kernel ]; then echo \'com.nullmoth.NMXGPU (1.0.7) wrong-uuid\'\nelif [ "$MODE" = previous ]; then echo \'com.nullmoth.NMXGPU (1.0.9) previous-uuid\'\nelif [ "$MODE" = current ]; then echo \'com.nullmoth.NMXGPU (1.0.10) E770B985-14A4-3ADE-A1EE-63204C3A9996\'\nelif [ "$MODE" != cache-repair ] && [ "$MODE" != cache-repair-previous ]; then echo \'com.nullmoth.NMXGPU (1.0.8) verified-NMXGPU-uuid\'; fi\necho \'com.nullmoth.NMXAccel (0.2.4) verified-NMXAccel-uuid\'\necho com.dhinakg.AMFIPass\n'
  for name,body in scripts.items():
   f=p/'bin'/name;f.write_text('#!/bin/bash\n'+body+'\n');f.chmod(0o755)
  dest=lib/'GPUBundles/NVMTLDriver.bundle';env=os.environ.copy();env.update(PATH=str(p/'bin')+':/usr/bin:/bin',MODE=mode,MOCK_PRELINK_EMITTER=str(emitter),MOCK_DEST=str(dest),MOCK_NVRAM=str(p/'nvram.txt'),MOCK_ONCE=str(p/'once'),MOCK_UUID='E770B985-14A4-3ADE-A1EE-63204C3A9996',MOCK_KERNEL_DEST=str(lib/'Extensions/NMXGPU.kext'))
  c=subprocess.run(['/bin/bash',str(pkg/'install-windowserver.sh')],env=env,capture_output=True,text=True,timeout=5)
  plugin=(dest/'Contents/MacOS/NVMTLDriver').read_text();calls=(p/'nvram.txt').read_text().splitlines() if (p/'nvram.txt').exists() else []
  if mode in ['success','cache-repair','previous','current','cache-repair-previous']:assert c.returncode==0 and plugin=='new-plugin' and (['nullmoth-gpu-once=1','nullmoth-panel-once=1']==calls[2:4] if mode in ['cache-repair','cache-repair-previous'] else calls[:2]==['nullmoth-gpu-once=1','nullmoth-panel-once=1']),c.stdout+c.stderr
  else:
   assert c.returncode!=0 and plugin=='old-plugin',mode+c.stdout+c.stderr
   if mode in ['partial','verify','journal','kc-commit','bad-path','bad-uuid','final-build-fail']:assert calls[-2:]==['-d nullmoth-panel-once','-d nullmoth-gpu-once'],calls
   else:assert not calls,calls
  assert (lib/'Extensions/NMXGPU.kext/Contents/MacOS/NMXGPU').read_text()==('diagnostic-kernel' if mode in ['success','cache-repair','previous','current','cache-repair-previous'] else 'verified-NMXGPU'),mode+c.stdout+c.stderr
  cache=(lib/'KernelCollections/AuxiliaryKernelExtensions.kc').read_text()
  if mode in ['success','cache-repair','previous','current','cache-repair-previous']:assert str(lib/'Extensions/NMXGPU.kext') in cache and '.latitude-windowserver.' not in cache and (pkg/'reports').is_dir(),cache
  else:assert cache=='old-cache',mode+c.stdout+c.stderr
  expected='new'  if mode in ['success','cache-repair','previous','current','cache-repair-previous'] else 'old'
  assert expected+' loader' in (lib/'NullMoth/load-panel-framebuffer.sh').read_text()
  if mode not in ['success','cache-repair','previous','current','cache-repair-previous']:assert 'old helper' in (lib/'NullMoth/latitude-desktop-journal').read_text()
  assert 'test-readback.sh'  not in s and 'test-and-arm-desktop.sh' not in s
 print('PASS actual desktop-only installer: baseline/kernel guards before mutation, plugin/capture/kernel/cache replacement/backup, one-shot arming, rollback and opt-in cleanup on verification/journal/kernel-preflight/kernel-mirroring/partial-arm failures; permanent final path/UUID verified, absent-loaded-kernel repair; no GPU suite')
