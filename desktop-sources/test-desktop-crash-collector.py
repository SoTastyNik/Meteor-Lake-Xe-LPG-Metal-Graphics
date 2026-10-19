from pathlib import Path
import tempfile,subprocess,os,time
r=Path(__file__).resolve().parent.parent
with tempfile.TemporaryDirectory(prefix='desktop-crash-collector-') as tmp:
 base=Path(tmp)
 for mode in ['pass','no-crash','history-fails']:
  p=base/mode;p.mkdir();(p/'bin').mkdir();system=p/'system reports';user=p/'user home';(user/'Library/Logs/DiagnosticReports').mkdir(parents=True);system.mkdir()
  if mode!='no-crash':
   for folder in [system,user/'Library/Logs/DiagnosticReports']:
    (folder/'WindowServer-2026 sample.ips').write_text('full crash stack '+str(folder))
    f=folder/'WindowServer-old.crash';f.write_text('old');t=time.time()-3*86400;os.utime(f,(t,t))
    (folder/'OtherApp.ips').write_text('unrelated')
  panics=p/'panic reports';(panics/'Retired').mkdir(parents=True)
  if mode!='no-crash':
   (panics/'panic-full sample.ips').write_text('full panic evidence')
   (panics/'Retired/Kernel-2026.panic').write_text('retired panic evidence')
   old=panics/'old.panic';old.write_text('old panic');t=time.time()-3*86400;os.utime(old,(t,t))
   (panics/'OtherApp.ips').write_text('unrelated')
  retained=p/'retained-source';retained.mkdir();(retained/'LatitudeDesktopLive.log').write_text('failed boot live evidence');(retained/'LatitudeDesktopRegistry.log.previous').write_text('previous registry evidence')
  for name in ['LatitudeDesktopAttempt.trace','LatitudeDesktopAttempt.trace.previous','LatitudeWindowServerSample.txt','LatitudeWindowServerSample.stderr.txt']:(retained/name).write_text('captured '+name)
  script=(r/'desktop-sources/collect-desktop-failure.sh').read_text().replace('crash_root=/Library/Logs/DiagnosticReports','crash_root="'+str(system)+'"',1).replace('user_home=${HOME:-/var/root}','user_home="'+str(user)+'"').replace('/usr/bin/log show','log show').replace('/Library/Logs/$saved',str(retained)+'/$saved').replace('/Library/GPUBundles',str(p/'missing-runtime'))
  script=script.replace('for panic_root in /Library/Logs/DiagnosticReports /Library/Logs/PanicReporter; do','for panic_root in "'+str(panics)+'"; do').replace('/Library/Logs/panic.log',str(p/'missing-legacy-panic.log'))
  (p/'collect-desktop-failure.sh').write_text(script)
  for name,body in {'uname':'echo x86_64','sysctl':'echo boot-fixture','sw_vers':'echo version-fixture','log':'echo "fixture history"; exit "${MOCK_LOG_RESULT:-0}"','sleep':'exec /bin/sleep 3'}.items():
   f=p/'bin'/name;f.write_text('#!/bin/bash\n'+body+'\n');f.chmod(0o755)
  (p/'Desktop/reports').mkdir(parents=True)
  env=os.environ.copy();env.update(PATH=str(p/'bin')+':/usr/bin:/bin',SUDO_USER='',MOCK_LOG_RESULT='1' if mode=='history-fails' else '0')
  c=subprocess.run(['/bin/bash',str(p/'collect-desktop-failure.sh')],env=env,capture_output=True,text=True,timeout=3)
  assert c.returncode==(1 if mode=='history-fails' else 0),c.stdout+c.stderr
  out=next((p/'Desktop/reports').glob('failure-detail-*'));copied=list((out/'WindowServer-crashes').rglob('*.ips'))
  assert len(copied)==(0 if mode=='no-crash' else 2),list(out.rglob('*'))
  assert not list((out/'WindowServer-crashes').rglob('*.crash'))
  panic_files=list((out/'Kernel-panics').rglob('*.ips'))+list((out/'Kernel-panics').rglob('*.panic'))
  assert len(panic_files)==(0 if mode=='no-crash' else 2),panic_files
  assert all('panic evidence' in f.read_text() for f in panic_files)
  assert ('copied=0' if mode=='no-crash' else 'copied=2 failed=0') in (out/'panic-status.txt').read_text()

  assert (out/'retained-boot-files/LatitudeDesktopLive.log').read_text()=='failed boot live evidence'
  assert (out/'retained-boot-files/LatitudeDesktopRegistry.log.previous').read_text()=='previous registry evidence'
  for name in ['LatitudeDesktopAttempt.trace','LatitudeDesktopAttempt.trace.previous','LatitudeWindowServerSample.txt','LatitudeWindowServerSample.stderr.txt']:assert (out/'retained-boot-files'/name).read_text()=='captured '+name
  assert 'MISSING LatitudePanelLoad.log'  in (out/'retained-files-status.txt').read_text()
  if copied:
   assert all(f.read_text().startswith('full crash stack ') for f in copied)
   assert 'copied=2 failed=0' in (out/'crash-status.txt').read_text()
  else:assert 'No recent WindowServer crash report found' in (out/'crash-status.txt').read_text()
 print('PASS actual desktop collector: full system/user WindowServer crash files with spaces, old/unrelated reports excluded, distinct sources preserved, absent report reported, crashes retained when historical search fails; no GPU tests')
