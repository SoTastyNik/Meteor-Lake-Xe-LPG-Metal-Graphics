# fork_linux_rcu.py <override/src/linux_rcu.c>: macOS forms of LinuxKPI's RCU read sections and grace-period wait.
#
# FreeBSD's sched_pin() keeps a reader on its CPU until rcu_read_unlock(), so both ends find the same per-CPU epoch
# record. The port's sched_pin() only turns interrupts off: a reader that blocks (a contended lock under
# rcu_read_lock, or any SRCU reader, which may sleep by design) resumes on whatever CPU xnu picks, and the unlock then
# ended the section on another CPU's record. The first record stayed active forever and every synchronize_rcu() spun
# on it (login hang, 2026-10-16: WindowServer, SecurityAgent and the RCU cleaner all in ck_epoch_synchronize_wait).
# Here the outermost lock remembers its record on the thread, the unlock ends the section there, and each record has
# a spin lock because a migrated unlock touches another CPU's record. sched_bind() is a no-op too, so the grace-period
# wait yields instead of trying to move to the blocking CPU, and reports what it waits on when that takes seconds.
import pathlib, sys
p = pathlib.Path(sys.argv[1]); s = p.read_text()
def replace_func(sig_line, new_body):
    global s
    anchored = "\n" + sig_line
    assert s.count(anchored) == 1, (sig_line, s.count(anchored))
    i = s.index(anchored) + 1
    start = s.rfind("\n\n", 0, i) + 2
    end = s.index("\n}\n", i) + 3
    s = s[:start] + new_body.strip("\n") + "\n" + s[end:]
def replace_once(old, new):
    global s
    assert s.count(old) == 1, (old[:60], s.count(old))
    s = s.replace(old, new)

replace_once("""	TAILQ_HEAD(, task_struct) ts_head;
	int cpuid;
	int type;
} __aligned(CACHE_LINE_SIZE);
""", """	TAILQ_HEAD(, task_struct) ts_head;
	int cpuid;
	int type;
	volatile u_int nmx_busy;	/* macOS port: the record's lock (a migrated unlock reaches other CPUs' records) */
} __aligned(CACHE_LINE_SIZE);

/* macOS port: taken inside a critical section (interrupts off), so a holder is never preempted */
static inline void
nmx_record_lock(struct linux_epoch_record *record)
{
	while (!atomic_cmpset_acq_int(&record->nmx_busy, 0, 1))
		cpu_spinwait();
}

static inline void
nmx_record_unlock(struct linux_epoch_record *record)
{
	atomic_store_rel_int(&record->nmx_busy, 0);
}

/* macOS port: reports of a reader that unlocked on another CPU than it locked on, and of grace-period stalls */
static volatile int nmx_rcu_migrations[RCU_TYPE_MAX];	/* per type: SRCU's boot-time ones would hide RCU's */
static volatile int nmx_rcu_reports;
#define	NMX_RCU_REPORTS_MAX	8
""")

replace_once("""	record = &DPCPU_GET(linux_epoch_record[type]);

	/*
	 * Use a critical section to prevent recursion inside
	 * ck_epoch_begin(). Else this function supports recursion.
	 */
	critical_enter();
	ck_epoch_begin(&record->epoch_record,
	    (ck_epoch_section_t *)&ts->rcu_section[type]);
	TAILQ_INSERT_TAIL(&record->ts_head, ts, rcu_entry[type]);
	critical_exit();
}
""", """	record = &DPCPU_GET(linux_epoch_record[type]);

	/*
	 * Use a critical section to prevent recursion inside
	 * ck_epoch_begin(). Else this function supports recursion.
	 */
	critical_enter();
	/* macOS port: the unlock ends the section on this record, wherever the thread runs by then */
	ts->task_thread->td_rcu_cpu[type] = record->cpuid + 1;
	ts->task_thread->td_rcu_ra[type] = __builtin_return_address(0);
	nmx_record_lock(record);
	ck_epoch_begin(&record->epoch_record,
	    (ck_epoch_section_t *)&ts->rcu_section[type]);
	TAILQ_INSERT_TAIL(&record->ts_head, ts, rcu_entry[type]);
	nmx_record_unlock(record);
	critical_exit();
}
""")

replace_once("""	record = &DPCPU_GET(linux_epoch_record[type]);

	/*
	 * Use a critical section to prevent recursion inside
	 * ck_epoch_end(). Else this function supports recursion.
	 */
	critical_enter();
	ck_epoch_end(&record->epoch_record,
	    (ck_epoch_section_t *)&ts->rcu_section[type]);
	TAILQ_REMOVE(&record->ts_head, ts, rcu_entry[type]);
	critical_exit();
""", """	/*
	 * macOS port: the record the lock used. A reader that blocked
	 * inside the section may be on another CPU now.
	 */
	{
		int cpu1 = ts->task_thread->td_rcu_cpu[type];

		if (cpu1 == 0) {
			printf("NullMoth xkpi: rcu_read_unlock(%u) with no record "
			    "(tid %d)\\n", type, ts->task_thread->td_tid);
			sched_unpin();
			return;
		}
		record = &DPCPU_ID_GET(cpu1 - 1, linux_epoch_record[type]);
		if (cpu1 - 1 != curcpu) {
			int n = atomic_fetchadd_int(&nmx_rcu_migrations[type], 1);

			if (n < NMX_RCU_REPORTS_MAX)
				printf("NullMoth xkpi: RCU(%u) reader tid %d "
				    "locked on cpu %d at %p, unlocks on cpu %d "
				    "(migration %d)\\n", type,
				    ts->task_thread->td_tid, cpu1 - 1,
				    ts->task_thread->td_rcu_ra[type], curcpu,
				    n + 1);
		}
		ts->task_thread->td_rcu_cpu[type] = 0;
	}

	/*
	 * Use a critical section to prevent recursion inside
	 * ck_epoch_end(). Else this function supports recursion.
	 */
	critical_enter();
	nmx_record_lock(record);
	ck_epoch_end(&record->epoch_record,
	    (ck_epoch_section_t *)&ts->rcu_section[type]);
	TAILQ_REMOVE(&record->ts_head, ts, rcu_entry[type]);
	nmx_record_unlock(record);
	critical_exit();
""")

replace_func("linux_synchronize_rcu_cb(ck_epoch_t *epoch __unused, ck_epoch_record_t *epoch_record, void *arg __unused)\n", r"""
/*
 * macOS port: what a grace period waits on, printed once when the wait
 * passes 2 seconds: every reader still inside a section of this type.
 */
static void
nmx_rcu_report_stall(unsigned type, int waited)
{
	struct linux_epoch_record *record;
	struct task_struct *ts;
	int i;

	printf("NullMoth xkpi: synchronize_rcu(%u) has waited %d ms; "
	    "readers still inside:\n", type, waited * 1000 / hz);
	CPU_FOREACH(i) {
		record = &DPCPU_ID_GET(i, linux_epoch_record[type]);
		critical_enter();
		nmx_record_lock(record);
		if (record->epoch_record.active != 0)
			printf("NullMoth xkpi:   cpu %d record active %u\n", i,
			    record->epoch_record.active);
		TAILQ_FOREACH(ts, &record->ts_head, rcu_entry[type])
			printf("NullMoth xkpi:     tid %d depth %d locked at "
			    "%p\n", ts->task_thread->td_tid,
			    ts->rcu_recurse[type],
			    ts->task_thread->td_rcu_ra[type]);
		nmx_record_unlock(record);
		critical_exit();
	}
}

struct nmx_rcu_wait {
	unsigned type;
	int start;
	int reported;
};

/*
 * macOS port: sched_bind() cannot move this thread to the CPU that
 * blocks the grace period, so wait by yielding: a short timed wait at
 * first, then one tick at a time once the reader is clearly slow.
 */
static void
linux_synchronize_rcu_cb(ck_epoch_t *epoch __unused, ck_epoch_record_t *epoch_record __unused, void *arg)
{
	struct nmx_rcu_wait *w = arg;
	int waited = ticks - w->start;

	if (waited < 2)
		mi_switch(SW_VOL | SWT_RELINQUISH);
	else
		pause("W", 1);
	if (waited > 2 * hz && !w->reported) {
		w->reported = 1;
		if (atomic_fetchadd_int(&nmx_rcu_reports, 1) < NMX_RCU_REPORTS_MAX)
			nmx_rcu_report_stall(w->type, waited);
	}
}
""")

replace_once("""	ck_epoch_synchronize_wait(&linux_epoch[type],
	    &linux_synchronize_rcu_cb, NULL);
""", """	{
		struct nmx_rcu_wait w = { .type = type, .start = ticks };

		ck_epoch_synchronize_wait(&linux_epoch[type],
		    &linux_synchronize_rcu_cb, &w);
	}
""")

# a thread whose record is dropped while it is still inside a section: end the section, so the record does not stay
# active (and its ts_head does not keep a freed task_struct)
s = s.rstrip("\n") + r"""

/*
 * macOS port: called when the port drops a thread's record (end of a
 * system call, exit of a port-started kernel thread) before LinuxKPI frees
 * its task_struct. A section still open here would hold every later grace
 * period: report it and end it.
 */
static void
linux_rcu_thread_exit(struct thread *td)
{
	struct linux_epoch_record *record;
	struct task_struct *ts = td->td_lkpi_task;
	unsigned type;

	if (ts == NULL)
		return;
	for (type = 0; type != RCU_TYPE_MAX; type++) {
		if (ts->rcu_recurse[type] == 0 || td->td_rcu_cpu[type] == 0)
			continue;
		printf("NullMoth xkpi: tid %d leaves with RCU(%u) read section "
		    "open (depth %d, locked at %p); ending it\n", td->td_tid,
		    type, ts->rcu_recurse[type], td->td_rcu_ra[type]);
		record = &DPCPU_ID_GET(td->td_rcu_cpu[type] - 1,
		    linux_epoch_record[type]);
		critical_enter();
		nmx_record_lock(record);
		ck_epoch_end(&record->epoch_record,
		    (ck_epoch_section_t *)&ts->rcu_section[type]);
		TAILQ_REMOVE(&record->ts_head, ts, rcu_entry[type]);
		nmx_record_unlock(record);
		critical_exit();
		ts->rcu_recurse[type] = 0;
		td->td_rcu_cpu[type] = 0;
		sched_unpin();
	}
}

static void
linux_rcu_thread_exit_init(void *arg __unused)
{
	nmx_rcu_thread_exit_hook = linux_rcu_thread_exit;
}
SYSINIT(linux_rcu_thread_exit, SI_SUB_CPU, SI_ORDER_ANY, linux_rcu_thread_exit_init, NULL);
"""
p.write_text(s)
