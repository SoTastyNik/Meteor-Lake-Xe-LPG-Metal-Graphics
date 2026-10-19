from pathlib import Path
import subprocess,tempfile,os
r=Path(__file__).resolve().parent.parent
with tempfile.TemporaryDirectory(prefix='desktop-journal-') as d:
 p=Path(d);log=p/'attempt.trace';exe=p/'journal'
 subprocess.run(['xcrun','clang','-g','-fsanitize=address,undefined','-DLATITUDE_JOURNAL_TEST',f'-DNVMTL_DESKTOP_JOURNAL_PATH="{log}"','-I',str(r/'NullMoth/plugin'),str(r/'desktop-sources/latitude-desktop-journal.c'),'-o',str(exe)],check=True)
 def run(*args,ok=True):
  c=subprocess.run([str(exe),*args],capture_output=True,text=True);assert (c.returncode==0)==ok,c.stderr;return c
 run('prepare');run('stage','test-stage','detail\nsecond-line','9');s=log.read_text();assert 'phase=test-stage result=9 detail=detail second-line' in s and 'boot=' in s and 'tid=' in s
 assert log.stat().st_mode&0o777==0o600
 run('prepare');assert Path(str(log)+'.previous').read_text()==s
 run('flush',str(log));log.chmod(0o666);run('stage','denied',ok=False);log.chmod(0o600)
 log.write_bytes(b'x'*(256*1024));run('stage','full',ok=False)
 log.unlink();target=p/'target';target.write_text('unchanged');log.symlink_to(target);run('stage','symlink',ok=False);run('prepare',ok=False);assert target.read_text()=='unchanged'
 print('PASS actual journal helper ASan/UBSan: prepare/rotation, mode0600, boot/thread/stage data, newline normalization, flush, unsafe modes/symlinks and cap rejected')
