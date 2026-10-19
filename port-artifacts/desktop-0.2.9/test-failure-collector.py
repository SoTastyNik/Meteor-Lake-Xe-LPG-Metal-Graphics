from pathlib import Path
import subprocess,tempfile,os,time
r=Path(__file__).resolve().parent.parent
with tempfile.TemporaryDirectory(prefix='latitude-capture-test-') as tmp:
 p=Path(tmp);(p/'bin').mkdir();report=p/'reports/readback-20261018-203542';report.mkdir(parents=True)
 (report/'results.txt').write_text('iokit-padded exit=1\n');(report/'boot.txt').write_text('boot fixture\n');epoch=1792352276;os.utime(report/'results.txt',(epoch,epoch))
 (p/'collect-readback-failure.sh').write_bytes((r/'latitude-desktop/collect-readback-failure.sh').read_bytes())
 scripts={'id':'echo 0','log':'printf "%s\\n" "$*" >> "$COLLECT_COMMANDS"; echo "fixture recovered kernel error"','dmesg':'echo kernel-fixture','sysctl':'echo boot-fixture','ioreg':'echo registry-fixture','nvram':'[ "$#" = 1 ] || exit 99; echo "query:$1" >> "$COLLECT_COMMANDS"; exit 1','sleep':'exec /bin/sleep 3'}
 for name,source in scripts.items():
  f=p/'bin'/name;f.write_text('#!/bin/bash\n'+source+'\n');f.chmod(0o755)
 env=os.environ.copy();env.update(PATH=str(p/'bin')+':/usr/bin:/bin',COLLECT_COMMANDS=str(p/'commands.txt'))
 start=time.monotonic();c=subprocess.run(['/bin/bash',str(p/'collect-readback-failure.sh')],env=env,capture_output=True,text=True,timeout=2);elapsed=time.monotonic()-start
 assert c.returncode==0 and elapsed<2,c.stdout+c.stderr
 saved=list((p/'reports').glob('readback-failure-*'));assert len(saved)==1
 assert (saved[0]/'failure-window.txt').read_text().strip()=='fixture recovered kernel error'
 assert 'history exit=0' in (saved[0]/'status.txt').read_text()
 commands=(p/'commands.txt').read_text();assert '--last' not in commands and '--start' in commands and '--end' in commands
 assert 'query:nullmoth-panel-once' in commands and 'query:nullmoth-gpu-once' in commands
 print('PASS actual read-only collector with mocked system commands: report-derived time window, saved evidence, NVRAM queries only, watchdog does not hold terminal pipe open')
