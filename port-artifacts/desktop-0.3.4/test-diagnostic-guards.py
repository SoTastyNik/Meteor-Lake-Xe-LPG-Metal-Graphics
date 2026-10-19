from pathlib import Path
import tempfile,subprocess,os
r=Path(__file__).resolve().parent.parent
for script,args in [('test-and-arm-desktop.sh',[]),('install-runtime.sh',['--desktop'])]:
 c=subprocess.run(['/bin/bash',str(r/'latitude-desktop'/script),*args],capture_output=True,text=True);assert c.returncode==2 and ('disabled' in c.stderr or 'disabled' in c.stdout)
with tempfile.TemporaryDirectory(prefix='latitude-boot-guard-test-') as tmp:
 p=Path(tmp);(p/'bin').mkdir()
 for name,source in {'id':'echo 0','uname':'echo x86_64','nvram':'echo "$*" >> "$MOCK_LOG"\nif [ "$*" = nullmoth-panel-once ]; then [ "${PANEL_STUCK:-0}" = 1 ]; else exit 0; fi'}.items():
  f=p/'bin'/name;f.write_text('#!/bin/bash\n'+source+'\n');f.chmod(0o755)
 env=os.environ.copy();env.update(PATH=str(p/'bin')+':/usr/bin:/bin',MOCK_LOG=str(p/'calls.txt'))
 c=subprocess.run(['/bin/bash',str(r/'latitude-desktop/prepare-readback-boot.sh')],env=env,capture_output=True);assert c.returncode==0
 assert (p/'calls.txt').read_text().splitlines()==['-d nullmoth-panel-once','nullmoth-panel-once','nullmoth-gpu-once=1']
 (p/'calls.txt').unlink();env['PANEL_STUCK']='1';c=subprocess.run(['/bin/bash',str(r/'latitude-desktop/prepare-readback-boot.sh')],env=env,capture_output=True);assert c.returncode!=0 and 'nullmoth-gpu-once=1' not in (p/'calls.txt').read_text()
print('PASS diagnostic guards: desktop installer/arming entry points blocked; GPU-only boot helper clears panel marker and refuses to arm if panel marker remains (mocked NVRAM)')
