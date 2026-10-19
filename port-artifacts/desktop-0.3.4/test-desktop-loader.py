from pathlib import Path
import tempfile,subprocess,os
r=Path(__file__).resolve().parent.parent
with tempfile.TemporaryDirectory(prefix='desktop-loader-') as d:
 p=Path(d)
 for mode in ['active','fallback','load-fail','sample-empty','sample-zero','sample-pid-zero']:
  q=p/mode;q.mkdir();logs=q/'logs';logs.mkdir();bin=q/'bin';bin.mkdir();stages=q/'stages';calls=q/'calls'
  scripts={'journal':'echo "$*" >> "$STAGES"; exit 0','ioreg':'echo "$*" >> "$CALLS"; if [ "$MODE" != fallback ]; then echo "class LatitudePanelClaim"; fi','kmutil':'echo "FRAMEBUFFER" >> "$CALLS"; [ "$MODE" != load-fail ]','pgrep':'if [ "$MODE" = sample-pid-zero ]; then echo 0; else echo 163; fi','sample':'[ "$MODE" != sample-zero ] || { echo "pid_for_task failed; Sampling process 0"; exit 0; }; [ "$MODE" != sample-empty ] || exit 0; echo "SAMPLE" >> "$CALLS"; echo stack > "${@: -1}"','log':'echo live-record','ps':'echo WindowServer'}
  for name,body in scripts.items():f=bin/name;f.write_text('#!/bin/bash\n'+body+'\n');f.chmod(0o755)
  for name in ['LatitudeDesktopLive.log','LatitudeDesktopRegistry.log','LatitudeWindowServerSample.txt']:(logs/name).write_text('retained-old')
  s=(r/'latitude-desktop/Library/NullMoth/load-panel-framebuffer.sh').read_text().replace('/Library/Logs',str(logs)).replace('/Library/NullMoth/latitude-desktop-journal',str(bin/'journal'))
  for name,path in [('ioreg','/usr/sbin/'),('kmutil','/usr/bin/'),('sample','/usr/bin/'),('log','/usr/bin/'),('ps','/bin/'),('pgrep','/usr/bin/')]:s=s.replace(path+name,str(bin/name))
  s=s.replace('sleep "$delay"',':').replace('sleep 8',':').replace('  sleep 1','  :');f=q/'loader.sh';f.write_text(s)
  env=os.environ.copy();env.update(STAGES=str(stages),CALLS=str(calls),MODE=mode)
  c=subprocess.run(['/bin/bash',str(f)],env=env,capture_output=True,text=True,timeout=10)
  events=stages.read_text();operations=calls.read_text()
  assert events.index('loader-start')<events.index('claim-query-begin')
  if mode=='fallback':
   assert c.returncode==0 and 'fallback-skip' in events and 'FRAMEBUFFER' not in operations and (logs/'LatitudeDesktopLive.log').read_text()=='retained-old'
  else:
   assert 'FRAMEBUFFER' in operations
   if mode not in ['sample-empty','sample-zero','sample-pid-zero']:assert 'SAMPLE' in operations
   assert events.index('capture-begin')<events.index('framebuffer-load-begin')<events.index('framebuffer-load-end')
   assert 'sample-end' in events and 'registry-query-end' in events
   if mode.startswith('sample-'):assert 'sample-end WindowServer 2' in events,events
   assert (logs/'LatitudeDesktopLive.log.previous').read_text()=='retained-old'
   assert c.returncode==(1 if mode=='load-fail' else 0),c.stdout+c.stderr
 print('PASS actual loader with mocked OS commands: pre-claim/pre-handoff stages, active capture/sample, load-failure status, fallback preserves failed-attempt files; no GPU probes')
