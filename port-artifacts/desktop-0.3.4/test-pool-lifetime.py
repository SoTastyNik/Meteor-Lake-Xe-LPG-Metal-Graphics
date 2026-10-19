from pathlib import Path
import subprocess
r=Path(__file__).resolve().parent.parent;s=(r/'NullMoth/plugin/nvmtl_vk.c').read_text();a=s.index('/* created, destroyed, live, peak, quarantined, pending, completed, abandoned */');b=s.index('static nvmtl_address_page *nvmtl_keep_page_pop',a)
pre='''#include <mach/mach.h>
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>
#include <stdatomic.h>
#include <stdarg.h>
#include <pthread.h>
#include <assert.h>
#include <vulkan/vulkan.h>
#include "nvmtl_vk.h"
static VkDevice g_dev=(VkDevice)1;static unsigned g_qfam;
static _Atomic unsigned long long handles,destroy_calls;
static int fail_create,fail_allocate,fail_begin;
static void nvlog(const char *fmt,...){(void)fmt;}
static VkResult pvkCreateCommandPool(VkDevice d,const VkCommandPoolCreateInfo *i,const VkAllocationCallbacks *a,VkCommandPool *p){(void)d;(void)a;assert(i->flags==VK_COMMAND_POOL_CREATE_TRANSIENT_BIT);if(fail_create)return VK_ERROR_OUT_OF_HOST_MEMORY;*p=(VkCommandPool)(uintptr_t)(atomic_fetch_add(&handles,1)+100);return VK_SUCCESS;}
static VkResult nvmtl_opaque_AllocateCommandBuffers(VkDevice d,const VkCommandBufferAllocateInfo *i,void **p){(void)d;if(fail_allocate)return VK_ERROR_OUT_OF_HOST_MEMORY;*p=(void *)((uintptr_t)i->commandPool+100000);return VK_SUCCESS;}
static VkResult pvkBeginCommandBuffer(VkCommandBuffer c,const VkCommandBufferBeginInfo *i){(void)c;assert(i->flags==VK_COMMAND_BUFFER_USAGE_ONE_TIME_SUBMIT_BIT);return fail_begin?VK_ERROR_OUT_OF_HOST_MEMORY:VK_SUCCESS;}
static void pvkDestroyCommandPool(VkDevice d,VkCommandPool p,const VkAllocationCallbacks *a){(void)d;(void)a;assert(p);atomic_fetch_add(&destroy_calls,1);}
'''
post='''static void *worker(void *arg){(void)arg;for(int n=0;n<10000;n++){nvk_cmdbuf c;assert(!nvmtl_pool_begin_raw(&c));assert(c.pool_state==NVK_POOL_RECORDING);nvmtl_pool_state(&c,NVK_POOL_SUBMITTED);nvmtl_pool_state(&c,NVK_POOL_COMPLETE);assert(nvmtl_pool_destroy(&c));assert(!c.pool&&!c.cb);assert(nvmtl_pool_destroy(&c));}return NULL;}
int main(void){
 nvk_cmdbuf c;uint64_t st[8];
 fail_create=1;assert(nvmtl_pool_begin_raw(&c));fail_create=0;nvmtl_vk_command_pool_stats(st);assert(st[0]==0&&st[2]==0);
 fail_allocate=1;assert(nvmtl_pool_begin_raw(&c));fail_allocate=0;
 fail_begin=1;assert(nvmtl_pool_begin_raw(&c));fail_begin=0;
 nvmtl_vk_command_pool_stats(st);assert(st[0]==2&&st[1]==2&&st[2]==0&&st[7]==2);
 pthread_t threads[3];for(int n=0;n<3;n++)assert(!pthread_create(&threads[n],NULL,worker,NULL));for(int n=0;n<3;n++)pthread_join(threads[n],NULL);
 nvmtl_vk_command_pool_stats(st);assert(st[0]==30002&&st[1]==30002&&st[2]==0&&st[4]==0&&st[5]==0&&st[6]==30000);
 assert(!nvmtl_pool_begin_raw(&c));nvmtl_pool_state(&c,NVK_POOL_SUBMITTED);unsigned long long before=atomic_load(&destroy_calls);assert(!nvmtl_pool_destroy(&c));assert(atomic_load(&destroy_calls)==before&&c.pool&&c.pool_state==NVK_POOL_QUARANTINED);assert(!nvmtl_pool_destroy(&c));
 nvmtl_vk_command_pool_stats(st);assert(st[0]==30003&&st[1]==30002&&st[2]==1&&st[4]==1&&st[5]==0);
 puts("PASS actual pool allocator/retirement: 30000 completed lifetimes across 3 threads, allocation/begin-failure cleanup, balanced counters, no double destroy, pending-pool quarantine without destruction");
}
'''
f=r/'desktop-build/test-pool-lifetime.c';f.write_text(pre+s[a:b]+post);subprocess.run(['xcrun','clang','-fsanitize=address,undefined','-g','-I',str(r/'Vulkan-Headers/include'),'-I',str(r/'NullMoth/plugin'),str(f),'-o',str(r/'desktop-build/test-pool-lifetime')],check=True);subprocess.run([str(r/'desktop-build/test-pool-lifetime')],check=True)
