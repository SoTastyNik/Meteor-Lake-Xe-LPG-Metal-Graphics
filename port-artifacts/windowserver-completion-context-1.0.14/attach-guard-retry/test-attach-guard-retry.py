from pathlib import Path
import tempfile,subprocess,os
r=Path(__file__).resolve().parent.parent
s=(r/'latitude-desktop/update-windowserver-kernel.sh').read_text();body=s[s.index('reset_windowserver_attach_guard()'):]
installer=(r/'latitude-desktop/install-windowserver.sh').read_text()
assert installer.index('commit_windowserver_kernel\n')<installer.index('reset_windowserver_attach_guard\n')<installer.index('nvram nullmoth-gpu-once=1')
with tempfile.TemporaryDirectory() as t:
 for mode in ['absent','present','delete-fails','sticky']:
  p=Path(t)/mode;p.mkdir();(p/'report').mkdir();(p/'bin').mkdir()
  if mode!='absent':(p/'marker').write_text('old attach panic')
  f=p/'bin/nvram';f.write_text('''#!/bin/bash
printf '%s\n' "$*" >> "$CALLS"
case "$*" in
nullmoth-gpu-attaching) [ -f "$MARKER" ] || exit 1; echo nullmoth-gpu-attaching=1;;
'-d nullmoth-gpu-attaching') [ "$MODE" != delete-fails ] || exit 7; [ "$MODE" = sticky ] || /bin/rm -f "$MARKER";;
*) exit 9;;
esac
''');f.chmod(0o755)
  f=p/'run';f.write_text('set -euo pipefail\n'+body+'\nreset_windowserver_attach_guard\necho armed > "$ARMED"\n')
  env=os.environ.copy();env.update(PATH=str(p/'bin')+':/bin:/usr/bin',REPORT=str(p/'report'),CALLS=str(p/'calls'),MARKER=str(p/'marker'),MODE=mode,ARMED=str(p/'armed'))
  x=subprocess.run(['/bin/bash',str(f)],env=env,capture_output=True,text=True)
  success=mode in ['absent','present'];assert (x.returncode==0)==success,x.stdout+x.stderr
  assert (p/'armed').exists()==success
  assert (p/'marker').exists()==(mode in ['delete-fails','sticky'])
  calls=(p/'calls').read_text().splitlines();assert all('nullmoth-gpu-attaching' in line for line in calls)
  assert len(calls)==(1 if mode=='absent' else 2 if mode=='delete-fails' else 3),calls
print('PASS actual retry helper: absent/present guard, deletion failure and sticky marker; never arms on failure; exact variable only; post-commit/pre-arm ordering')
