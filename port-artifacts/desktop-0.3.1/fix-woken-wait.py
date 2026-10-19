from pathlib import Path
import shutil
r=Path(__file__).resolve().parent.parent;x=r/'NullMoth/gpu-port/xkpi';src=Path('/Users/ved/igpu-build/kpi/freebsd-src/sys/compat/linuxkpi/common/src/linux_schedule.c');out=x/'override/src/linux_schedule.c';backup=r/'backups/desktop-0.3.1-before';backup.mkdir(parents=True,exist_ok=True)
for f in [x/'lkobj/linux_schedule.o',r/'latitude-desktop/Library/Extensions/NMXGPU.kext/Contents/MacOS/NMXGPU']:
 d=backup/f.name
 if not d.exists():shutil.copy2(f,d)
s=src.read_text();old='''\tsleepq_lock(wchan);
\twq->flags |= WQ_FLAG_WOKEN;
\tsleepq_signal(wchan, SLEEPQ_SLEEP, 0, 0);''';new='''\tsleepq_lock(wchan);
\twq->flags |= WQ_FLAG_WOKEN;
\t/* schedule_timeout checks task state under this same channel lock. */
\tif ((atomic_read(&((struct task_struct *)wq->private)->state) & state) != 0)
\t\tset_task_state(((struct task_struct *)wq->private), TASK_WAKING);
\tsleepq_signal(wchan, SLEEPQ_SLEEP, 0, 0);''';assert s.count(old)==1;out.write_text(s.replace(old,new));print('Created LinuxKPI scheduler override with persistent wake state under the sleep-channel lock.')
