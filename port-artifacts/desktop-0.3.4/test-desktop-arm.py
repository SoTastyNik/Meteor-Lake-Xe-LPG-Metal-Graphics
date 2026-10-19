from pathlib import Path
import tempfile,subprocess,os
r=Path(__file__).resolve().parent.parent
with tempfile.TemporaryDirectory(prefix='latitude-arm-test-') as tmp:
 p=Path(tmp);(p/'bin').mkdir();(p/'test-and-arm-desktop.sh').write_bytes((r/'latitude-desktop/test-and-arm-desktop.sh').read_bytes());(p/'test-readback.sh').write_text('#!/bin/bash\nexit "${GATE_RESULT:-0}"\n')
 for name,source in {'id':'echo 0','uname':'echo x86_64','nvram':'echo "$*" >> "$MOCK_NVRAM_LOG"\nif [ "${FAIL_PANEL:-0}" = 1 ] && [ "$*" = nullmoth-panel-once=1 ]; then exit 1; fi'}.items():
  f=p/'bin'/name;f.write_text('#!/bin/bash\n'+source+'\n');f.chmod(0o755)
 env=os.environ.copy();env.update(PATH=str(p/'bin')+':/usr/bin:/bin',MOCK_NVRAM_LOG=str(p/'nvram.txt'))
 env['GATE_RESULT']='1';c=subprocess.run(['/bin/bash',str(p/'test-and-arm-desktop.sh')],env=env,capture_output=True);assert c.returncode!=0 and not (p/'nvram.txt').exists()
 env['GATE_RESULT']='0';c=subprocess.run(['/bin/bash',str(p/'test-and-arm-desktop.sh')],env=env,capture_output=True);assert c.returncode==0;assert (p/'nvram.txt').read_text().splitlines()==['nullmoth-gpu-once=1','nullmoth-panel-once=1']
 (p/'nvram.txt').unlink();env['FAIL_PANEL']='1';c=subprocess.run(['/bin/bash',str(p/'test-and-arm-desktop.sh')],env=env,capture_output=True);assert c.returncode!=0;assert (p/'nvram.txt').read_text().splitlines()[-2:]==['-d nullmoth-panel-once','-d nullmoth-gpu-once']
print('PASS actual desktop-arm script with mocked commands: failed suite never arms, passing suite arms once, partial arming failure clears both opt-ins')
