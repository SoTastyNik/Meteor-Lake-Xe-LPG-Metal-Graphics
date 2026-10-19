from pathlib import Path
import subprocess
r=Path(__file__).resolve().parent.parent;s=(r/'NullMoth/plugin/nvmtl_vk.c').read_text();a=s.index('int nvmtl_vk_submit_wait_at(');b=s.index('\nint nvmtl_vk_submit_begin_at',a)
pre='''#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <pthread.h>
#include <stdatomic.h>
#include <unistd.h>
#include "nvmtl_desktop_policy.h"
typedef struct{int x;}nvk_cmdbuf;typedef struct{int x;}nvmtl_inflight;
static pthread_mutex_t nvmtl_desktop_submit_mutex=PTHREAD_RECURSIVE_MUTEX_INITIALIZER;
static int serial,begin_fail,finish_fail;static _Atomic int in_flight,peak;static _Thread_local int nested;
static int recurse;
int nvmtl_vk_submit_wait_at(nvk_cmdbuf *,const char *);
static int nvmtl_vk_windowserver_serial(void){return serial;}
static int nvmtl_vk_submit_begin_at(nvk_cmdbuf *c,nvmtl_inflight *f,const char *w){if(begin_fail)return -1;if(recurse&&!nested){nested=1;assert(!nvmtl_vk_submit_wait_at(c,"managed nested upload"));nested=0;}int v=atomic_fetch_add(&in_flight,1)+1;int old=atomic_load(&peak);while(v>old&&!atomic_compare_exchange_weak(&peak,&old,v)){}usleep(50);return 0;}
static int nvmtl_vk_submit_finish(nvmtl_inflight *f){atomic_fetch_sub(&in_flight,1);return finish_fail?-2:0;}
'''
post='''
static void *worker(void *p){nvk_cmdbuf c;for(int i=0;i<1000;i++)assert(!nvmtl_vk_submit_wait_at(&c,"surface copy or render"));return NULL;}
int main(void){assert(nvmtl_windowserver_serial_policy(0x8086,0x7d45,"WindowServer"));assert(!nvmtl_windowserver_serial_policy(0x8086,0x7d45,"latitude-readback-test"));assert(!nvmtl_windowserver_serial_policy(0x8086,0x7d55,"WindowServer"));assert(!nvmtl_windowserver_serial_policy(0x10de,0x7d45,"WindowServer"));assert(!nvmtl_windowserver_serial_policy(0x8086,0x7d45,NULL));
 serial=1;pthread_t ts[3];for(int i=0;i<3;i++)pthread_create(&ts[i],NULL,worker,NULL);for(int i=0;i<3;i++)pthread_join(ts[i],NULL);assert(atomic_load(&peak)==1&&!atomic_load(&in_flight));
 nvk_cmdbuf c;begin_fail=1;assert(nvmtl_vk_submit_wait_at(&c,"begin failure")==-1);begin_fail=0;finish_fail=1;assert(nvmtl_vk_submit_wait_at(&c,"GPU timeout")==-2);finish_fail=0;recurse=1;assert(!nvmtl_vk_submit_wait_at(&c,"managed flush"));recurse=0;assert(!pthread_mutex_trylock(&nvmtl_desktop_submit_mutex));pthread_mutex_unlock(&nvmtl_desktop_submit_mutex);
 serial=0;peak=0;for(int i=0;i<3;i++)pthread_create(&ts[i],NULL,worker,NULL);for(int i=0;i<3;i++)pthread_join(ts[i],NULL);assert(atomic_load(&peak)>1&&!atomic_load(&in_flight));
 puts("PASS actual submit_wait wrapper: target/process scope, 3000 serialized desktop submissions across3threads, app concurrency preserved, begin/finish-error unlock, recursive managed flush without deadlock");}
'''
f=r/'desktop-build/test-windowserver-serial.c';f.write_text(pre+s[a:b]+post);exe=r/'desktop-build/test-windowserver-serial';subprocess.run(['xcrun','clang','-g','-fsanitize=address,undefined','-I',str(r/'NullMoth/plugin'),str(f),'-o',str(exe)],check=True);subprocess.run([str(exe)],check=True)
