from pathlib import Path
import tempfile,subprocess,os,plistlib
r=Path(__file__).resolve().parent.parent
with tempfile.TemporaryDirectory(prefix='latitude-profile-test-') as tmp:
 base=Path(tmp)
 for profile in ['retained','fresh-pools','fresh-staging']:
  p=base/profile;p.mkdir();(p/'bin').mkdir();(p/'tools').mkdir();(p/'live').mkdir()
  source=(r/'latitude-desktop/test-readback.sh').read_text().replace(' /Library/GPUBundles',' '+str(p/'live')).replace(chr(34)+'/Library/GPUBundles',chr(34)+str(p/'live'))
  (p/'test-readback.sh').write_text(source)
  for folder in [p/'live',p/'Library/GPUBundles']:
   (folder/'NVMTLDriver.bundle/Contents/MacOS').mkdir(parents=True);(folder/'nvmtl').mkdir()
   (folder/'NVMTLDriver.bundle/Contents/MacOS/NVMTLDriver').write_bytes(b'fixture-plugin')
   (folder/'nvmtl/libdrm.2.dylib').write_bytes(b'fixture-libdrm')
   (folder/'NVMTLDriver.bundle/Contents/Info.plist').write_bytes(plistlib.dumps({'CFBundleVersion':'0.2.9'}))
  scripts={'uname':'echo x86_64','id':'echo 0','kmutil':'echo fixture-kexts','sysctl':'if [ "$*" = "-n kern.bootsessionuuid" ]; then echo fixture-boot-uuid; else echo fixture-boottime; fi','nvram':'exit 1','ioreg':'case "$*" in *NMXAccel*) echo \'"MetalPluginName" = "NVMTLDriver"\' ;; esac','log':'if [ "$1" = stream ]; then exec /bin/sleep 3; else echo "$*" >> "$MOCK_HISTORY"; echo fixture-current-history; fi','sleep':'exec /bin/sleep 3'}
  for name,body in scripts.items():
   f=p/'bin'/name;f.write_text('#!/bin/bash\n'+body+'\n');f.chmod(0o755)
  (p/'tools/latitude-drm-route-test').write_text('#!/bin/bash\necho "PASS fixture discovery"\n');(p/'tools/latitude-drm-route-test').chmod(0o755)
  tool=p/'tools/latitude-readback-test';tool.write_text('''#!/bin/bash
printf 'pool=%s cmdfresh=%s stagefresh=%s diag=%s args=%s\\n' "$NVMTL_POOL_REUSE" "${NVMTL_COMMAND_POOL_FRESH:-off}" "${NVMTL_READBACK_STAGE_FRESH:-off}" "$NVMTL_DIAGNOSTIC_STDERR" "$*" >> "$MOCK_CASES"
echo 'PASS effective backend policy: fixture'
echo 'PASS exact readback: fixture, no GPU execution'
echo 'NMX transport counters: requested=iokit direct=0 iokit=1'
''');tool.chmod(0o755)
  env=os.environ.copy();env.update(PATH=str(p/'bin')+':/usr/bin:/bin',SUDO_USER='',MOCK_CASES=str(p/'cases.txt'),MOCK_HISTORY=str(p/'history.txt'))
  for key in ['NVMTL_COMMAND_POOL_FRESH','NVMTL_READBACK_STAGE_FRESH','NVMTL_NO_POOL_REUSE']:env[key]='inherited-must-be-cleared'
  c=subprocess.run(['/bin/bash',str(p/'test-readback.sh'),'1000',profile],env=env,capture_output=True,text=True,timeout=4)
  assert c.returncode==0,c.stdout+c.stderr
  lines=(p/'cases.txt').read_text().splitlines();assert len(lines)==4
  assert all(line.startswith('pool=1 cmdfresh=off stagefresh=off diag=1') for line in lines[:3])
  expected='pool=1 cmdfresh='+('1' if profile=='fresh-pools' else 'off')+' stagefresh='+('1' if profile=='fresh-staging' else 'off')+' diag=1'
  assert lines[3].startswith(expected),lines
  assert '--padding 64' in lines[3] and '--size 1920x1080' in lines[3]
  assert not list((p/'reports').rglob('desktop-gate.txt'))
  history=(p/'history.txt').read_text();assert '--start' in history and '--end' in history and '--last' not in history
  c=subprocess.run(['/bin/bash',str(p/'test-readback.sh'),'1000',profile],env=env,capture_output=True,text=True,timeout=4);assert c.returncode==2 and len((p/'cases.txt').read_text().splitlines())==4
 print('PASS actual comparison runner with mocked hardware: identical three-case warmup, one-variable command-pool/staging options, inherited flags cleared, direct diagnostics, current-run history, same-boot retry refused, no desktop gate')
