from pathlib import Path
import tempfile,subprocess,os,plistlib
r=Path(__file__).resolve().parent.parent
with tempfile.TemporaryDirectory(prefix='latitude-full-test-') as tmp:
 p=Path(tmp);(p/'bin').mkdir();(p/'tools').mkdir()
 source=(r/'latitude-desktop/test-readback.sh').read_text().replace('/Library/GPUBundles',str(p/'live')).replace('/Library/Extensions',str(p/'live-extensions'))
 # Restore the package-relative path after replacing absolute installation references.
 source=source.replace('$HERE'+str(p/'live-extensions'),'$HERE/Library/Extensions').replace('$HERE'+str(p/'live'),'$HERE/Library/GPUBundles').replace('$HERE'+str(p/'live-extensions'),'$HERE/Library/Extensions')
 (p/'test-readback.sh').write_text(source)
 for folder in [p/'live',p/'Library/GPUBundles']:
  (folder/'NVMTLDriver.bundle/Contents/MacOS').mkdir(parents=True);(folder/'nvmtl').mkdir()
  (folder/'NVMTLDriver.bundle/Contents/MacOS/NVMTLDriver').write_bytes(b'fixture-plugin');(folder/'nvmtl/libdrm.2.dylib').write_bytes(b'fixture-libdrm')
  (folder/'NVMTLDriver.bundle/Contents/Info.plist').write_bytes(plistlib.dumps({'CFBundleVersion':'0.3.0'}))
 (p/'NMXGPU-UUID.txt').write_text('fixture-gpu-uuid\n')
 for folder in [p/'live-extensions',p/'Library/Extensions']:
  f=folder/'NMXGPU.kext/Contents/MacOS/NMXGPU';f.parent.mkdir(parents=True);f.write_bytes(b'fixture-kernel')
 scripts={'uname':'echo x86_64','id':'echo 0','kmutil':'if [ "${FAIL_MODE:-}" = kernel ]; then echo \'com.nullmoth.NMXGPU (1.0.7) old-uuid\'; else echo \'com.nullmoth.NMXGPU (1.0.8) fixture-gpu-uuid\'; fi','sysctl':'echo fixture-boot-uuid','nvram':'exit 1','ioreg':'case "$*" in *NMXAccel*) echo \'"MetalPluginName" = "NVMTLDriver"\' ;; esac','log':'echo \'Filtering the log data using GPU HANG\'; echo \'2026-10-18 23:54:00 Df log[1:1] args GPU HANG\'; if [ "$1" = stream ]; then if [ "${FAIL_MODE:-}" = tlb ]; then echo \'2026-10-18 23:54:00 Df kernel[0:1] TLB invalidation response timed out for seqno 1\'; fi; exec /bin/sleep 3; elif [ "${FAIL_MODE:-}" = history ]; then exit 1; elif [ "${FAIL_MODE:-}" = hang ]; then echo "2026-10-18 23:55:12.278 Df kernel[0:1] GPU HANG fixture"; else echo fixture-current-history; fi','sleep':'exec /bin/sleep 3'}
 for name,body in scripts.items():
  f=p/'bin'/name;f.write_text('#!/bin/bash\n'+body+'\n');f.chmod(0o755)
 (p/'tools/latitude-drm-route-test').write_text('#!/bin/bash\necho PASS-discovery\n');(p/'tools/latitude-drm-route-test').chmod(0o755)
 f=p/'tools/latitude-readback-test';f.write_text('''#!/bin/bash
printf '%s route=%s stage=%s\\n' "$*" "$NMX_DRM_TEST_TRANSPORT" "${NVMTL_READBACK_STAGE_FRESH:-off}" >> "$MOCK_CASES"
[ "${FAIL_MODE:-}" = policy ] || echo 'PASS effective backend policy: fixture'
[ "${FAIL_MODE:-}" = cleanup ] || echo 'PASS command-pool cleanup: fixture'
echo 'PASS exact readback: fixture'
echo 'PASS IOSurface backing: fixture'
if [ "$NMX_DRM_TEST_TRANSPORT" = iokit ]; then echo 'NMX transport counters: requested=iokit direct=0 iokit=1'; else echo 'NMX transport counters: requested=direct direct=1 iokit=0'; fi
''');f.chmod(0o755)
 env=os.environ.copy();env.update(PATH=str(p/'bin')+':/usr/bin:/bin',SUDO_USER='',MOCK_CASES=str(p/'cases.txt'),READBACK_GATE_FILE=str(p/'gate'))
 for mode in ['success','policy','cleanup','hang','history','tlb','kernel']:
  (p/'reports/readback-last-boot.txt').unlink(missing_ok=True);(p/'cases.txt').unlink(missing_ok=True);(p/'gate').unlink(missing_ok=True);env['FAIL_MODE']=mode
  c=subprocess.run(['/bin/bash',str(p/'test-readback.sh'),'1000','full'],env=env,capture_output=True,text=True,timeout=10)
  if mode=='success':
   assert not c.returncode,c.stdout+c.stderr;assert (p/'gate').read_text().startswith('candidate=0.3.1 cases=22 iterations=1000 boot=fixture-boot-uuid')
   lines=(p/'cases.txt').read_text().splitlines();assert len(lines)==22;assert sum('route=iokit' in l for l in lines)==11;assert sum('route=direct' in l for l in lines)==11
   assert sum('--expect-policy enforced-fresh-staging' in l for l in lines)==2;assert sum('--iosurface' in l for l in lines)==4
  else:assert c.returncode and not (p/'gate').exists(),mode+c.stdout+c.stderr
 print('PASS actual 22-case runner: both routes, mandatory fresh policy/cleanup/IOSurface checks; missing policy, pool imbalance marker, real kernel hang/TLB timeout and incomplete history block gate; filter headers/log command metadata ignored')
 # Test the arm script against the exact gate, with no hardware/NVRAM changes.
 arm=(r/'latitude-desktop/test-and-arm-desktop.sh').read_text().replace('/Library/GPUBundles',str(p/'live')).replace('/Library/Extensions',str(p/'live-extensions')).replace('$HERE'+str(p/'live-extensions'),'$HERE/Library/Extensions').replace('$HERE'+str(p/'live'),'$HERE/Library/GPUBundles');(p/'test-and-arm-desktop.sh').write_text(arm)
 (p/'test-readback.sh').write_text('''#!/bin/bash
[ "${FAIL_MODE:-}" != suite ] || exit 1
[ "${FAIL_MODE:-}" != missing ] || exit 0
{ printf 'candidate=0.3.1 cases=22 iterations=1000 boot=fixture-boot-uuid\\n'; shasum -a 256 "'''+str(p/'live/NVMTLDriver.bundle/Contents/MacOS/NVMTLDriver')+'''" "'''+str(p/'live/nvmtl/libdrm.2.dylib')+'''" "'''+str(p/'live-extensions/NMXGPU.kext/Contents/MacOS/NMXGPU')+'''"; } > "$READBACK_GATE_FILE"
[ "${FAIL_MODE:-}" != stale ] || echo stale >> "$READBACK_GATE_FILE"
''')
 f=p/'bin/nvram';f.write_text('''#!/bin/bash
echo "$*" >> "$MOCK_NVRAM_LOG"
if [ "${FAIL_MODE:-}" = partial ] && [ "$*" = nullmoth-panel-once=1 ]; then exit 1; fi
''');env['MOCK_NVRAM_LOG']=str(p/'nvram.txt')
 for mode in ['suite','missing','stale','success','partial']:
  env['FAIL_MODE']=mode;(p/'nvram.txt').unlink(missing_ok=True);c=subprocess.run(['/bin/bash',str(p/'test-and-arm-desktop.sh')],env=env,capture_output=True,text=True,timeout=5)
  calls=(p/'nvram.txt').read_text().splitlines() if (p/'nvram.txt').exists() else []
  if mode=='success':assert not c.returncode and calls==['nullmoth-gpu-once=1','nullmoth-panel-once=1'],c.stdout+c.stderr
  elif mode=='partial':assert c.returncode and calls[-2:]==['-d nullmoth-panel-once','-d nullmoth-gpu-once']
  else:assert c.returncode and not calls,mode+c.stdout+c.stderr
 print('PASS actual desktop arm: suite failure, absent/stale gate never arm; passing gate arms once; partial NVRAM failure clears both markers')
