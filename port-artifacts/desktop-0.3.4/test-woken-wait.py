from pathlib import Path
import subprocess
r=Path(__file__).resolve().parent.parent
old=Path('/Users/ved/igpu-build/kpi/freebsd-src/sys/compat/linuxkpi/common/src/linux_schedule.c').read_text();new=(r/'NullMoth/gpu-port/xkpi/override/src/linux_schedule.c').read_text();i915=(r/'drm-kmod/drivers/gpu/drm/i915/gt/uc/intel_guc_submission.c').read_text()
def function(s,needle):
 a=s.index(needle);a=s.rfind('\n',0,a)+1;b=s.index('{',a);depth=1;j=b+1
 while depth:
  depth+= (s[j]=='{')-(s[j]=='}');j+=1
 return s[a:j]+'\n'
wake_old='int\n'+function(old,'woken_wake_function(wait_queue_t').replace('woken_wake_function(','old_woken_wake_function(',1)
wake_new='int\n'+function(new,'woken_wake_function(wait_queue_t')
sched='long\n'+function(new,'linux_schedule_timeout(long timeout)')
wait=function(i915,'must_wait_woken(struct wait_queue_entry')
pre='''#include <assert.h>
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
'''
stubs='''
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
'''
post='''
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
'''
f=r/'desktop-build/test-woken-wait.c';f.write_text(pre+wake_old+wake_new+stubs+sched+wait+post);exe=r/'desktop-build/test-woken-wait';subprocess.run(['xcrun','clang','-fsanitize=address,undefined','-g',str(f),'-o',str(exe)],check=True);subprocess.run([str(exe)],check=True)
