#include <assert.h>
#include <stdio.h>
#include <stdint.h>
#include <string.h>
#include <limits.h>
#ifndef __unused
#define __unused
#endif
#define TASK_RUNNING 0
#define TASK_UNINTERRUPTIBLE 2
#define TASK_WAKING 4
#define WQ_FLAG_WOKEN 2
#define SLEEPQ_SLEEP 0
#define ERESTARTSYS 512
#define EWOULDBLOCK 35
#define MAX_SCHEDULE_TIMEOUT LONG_MAX
struct task_struct {int state;};struct wait_queue_entry{int flags;void *private;};typedef struct wait_queue_entry wait_queue_t;
static struct task_struct task;static struct task_struct *current=&task;
static long jiffies;static int mode,legacy,locked,enrolled,signals,lost,inject,blocks;
static wait_queue_t *active;
#define atomic_read(p) (*(p))
#define set_task_state(t,s) ((t)->state=(s))
#define set_current_state(s) set_task_state(current,s)
#define __set_current_state(s) set_current_state(s)
#define smp_store_mb(p,v) ((p)=(v))
static void sleepq_lock(void *p);static void sleepq_release(void *p);static void sleepq_signal(void *p,int a,int b,int c);static int linux_add_to_sleepqueue(void *a,struct task_struct *b,const char *c,long t,int state);
int
old_woken_wake_function(wait_queue_t *wq, unsigned int state,
    int flags __unused, void *key __unused)
{
	void *wchan;

	wchan = wq->private;

	sleepq_lock(wchan);
	wq->flags |= WQ_FLAG_WOKEN;
	sleepq_signal(wchan, SLEEPQ_SLEEP, 0, 0);
	sleepq_release(wchan);

	return (1);
}
int
woken_wake_function(wait_queue_t *wq, unsigned int state,
    int flags __unused, void *key __unused)
{
	void *wchan;

	wchan = wq->private;

	sleepq_lock(wchan);
	wq->flags |= WQ_FLAG_WOKEN;
	/* schedule_timeout checks task state under this same channel lock. */
	if ((atomic_read(&((struct task_struct *)wq->private)->state) & state) != 0)
		set_task_state(((struct task_struct *)wq->private), TASK_WAKING);
	sleepq_signal(wchan, SLEEPQ_SLEEP, 0, 0);
	sleepq_release(wchan);

	return (1);
}

static void deliver(void){if(legacy)old_woken_wake_function(active,TASK_UNINTERRUPTIBLE,0,NULL);else woken_wake_function(active,TASK_UNINTERRUPTIBLE,0,NULL);}
static void sleepq_lock(void *p){assert(p==current);if(inject){inject=0;deliver();}assert(!locked);locked=1;}
static void sleepq_release(void *p){assert(locked&&p==current);locked=0;}
static void sleepq_signal(void *p,int a,int b,int c){assert(locked&&p==current);signals++;if(!enrolled)lost++;}
static int linux_add_to_sleepqueue(void *a,struct task_struct *b,const char *c,long t,int state){assert(locked);blocks++;enrolled=1;sleepq_release(a);
 if(mode==2){deliver();jiffies++;enrolled=0;return 0;}
 if(mode==4&&blocks==1){jiffies++;enrolled=0;return 0;}
 if(mode==4&&blocks==2){deliver();jiffies++;enrolled=0;return 0;}
 jiffies+=t;enrolled=0;return -EWOULDBLOCK;
}
#define schedule_timeout(t) linux_schedule_timeout(t)
long
linux_schedule_timeout(long timeout)
{
	struct task_struct *task;
	long remainder;
	int ret, state;

	task = current;

	remainder = jiffies + timeout;

	sleepq_lock(task);
	state = atomic_read(&task->state);
	if (state != TASK_WAKING) {
		ret = linux_add_to_sleepqueue(task, task, "sched", timeout,
		    state);
	} else {
		sleepq_release(task);
		ret = 0;
	}
	set_task_state(task, TASK_RUNNING);

	if (timeout == MAX_SCHEDULE_TIMEOUT)
		return (MAX_SCHEDULE_TIMEOUT);

	/* range check return value */
	remainder -= jiffies;

	/* range check return value */
	if (ret == -ERESTARTSYS && remainder < 1)
		remainder = 1;
	else if (remainder < 0)
		remainder = 0;
	else if (remainder > timeout)
		remainder = timeout;
	return (remainder);
}
static long must_wait_woken(struct wait_queue_entry *wq_entry, long timeout)
{
	/*
	 * This is equivalent to wait_woken() with the exception that
	 * we do not wake up early if the kthread task has been completed.
	 * As we are called from page reclaim in any task context,
	 * we may be invoked from stopped kthreads, but we *must*
	 * complete the wait from the HW.
	 */
	do {
		set_current_state(TASK_UNINTERRUPTIBLE);
		if (wq_entry->flags & WQ_FLAG_WOKEN)
			break;

		timeout = schedule_timeout(timeout);
	} while (timeout);

	/* See wait_woken() and woken_wake_function() */
	__set_current_state(TASK_RUNNING);
	smp_store_mb(wq_entry->flags, wq_entry->flags & ~WQ_FLAG_WOKEN);

	return timeout;
}

static void check(int old,int scenario){
 task.state=TASK_RUNNING;jiffies=0;mode=scenario;legacy=old;locked=enrolled=signals=lost=blocks=inject=0;
 wait_queue_t w={.private=current};active=&w;
 if(scenario==0)deliver();
 if(scenario==1)inject=1;
 long left=must_wait_woken(&w,100);
 assert(!locked&&task.state==TASK_RUNNING&&!(w.flags&WQ_FLAG_WOKEN));
 if(scenario==3||(old&&scenario==1)){assert(!left&&blocks==1);}
 else {assert(left>0);if(scenario==0||scenario==1)assert(!blocks);}
 if(scenario==1)assert(signals==1&&lost==1);
 if(scenario==4)assert(blocks==2&&signals==1);
}
int main(void){
 for(int i=0;i<10000;i++)for(int old=0;old<2;old++)for(int s=0;s<5;s++)check(old,s);
 puts("PASS actual wake/schedule_timeout/i915 must_wait_woken: legacy pre-enrollment response reproduces false timeout; patched task state prevents it; before-check, enrolled, spurious wake and true-timeout cases retain semantics (100000 scenarios)");
}
