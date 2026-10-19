#include <mach/mach.h>
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
/* created, destroyed, live, peak, quarantined, pending, completed, abandoned */
static uint64_t g_command_pool_stats[8];
static pthread_mutex_t g_command_pool_stats_lock = PTHREAD_MUTEX_INITIALIZER;
void nvmtl_vk_command_pool_stats(uint64_t out[8])
{
    pthread_mutex_lock(&g_command_pool_stats_lock);
    memcpy(out,g_command_pool_stats,sizeof g_command_pool_stats);
    pthread_mutex_unlock(&g_command_pool_stats_lock);
}
static void nvmtl_pool_created(nvk_cmdbuf *c, VkCommandPool pool)
{
    c->pool=(void *)pool; c->pool_state=NVK_POOL_RECORDING;
    pthread_mutex_lock(&g_command_pool_stats_lock);
    g_command_pool_stats[0]++;g_command_pool_stats[2]++;
    if(g_command_pool_stats[2]>g_command_pool_stats[3])g_command_pool_stats[3]=g_command_pool_stats[2];
    pthread_mutex_unlock(&g_command_pool_stats_lock);
}
static void nvmtl_pool_state(nvk_cmdbuf *c,uint32_t state)
{
    if(!c || !c->pool || c->pool_state==state)return;
    pthread_mutex_lock(&g_command_pool_stats_lock);
    if(c->pool_state==NVK_POOL_SUBMITTED)g_command_pool_stats[5]--;
    if(state==NVK_POOL_SUBMITTED)g_command_pool_stats[5]++;
    if(state==NVK_POOL_QUARANTINED && c->pool_state!=NVK_POOL_QUARANTINED)g_command_pool_stats[4]++;
    c->pool_state=state;
    pthread_mutex_unlock(&g_command_pool_stats_lock);
}
static int nvmtl_pool_destroy(nvk_cmdbuf *c)
{
    if(!c || !c->pool)return 1;
    if(c->pool_state!=NVK_POOL_RECORDING && c->pool_state!=NVK_POOL_COMPLETE){
        nvmtl_pool_state(c,NVK_POOL_QUARANTINED);
        nvlog("command pool retirement REFUSED: completion uncertain; retaining pool %p",c->pool);return 0;
    }
    const uint32_t state=c->pool_state;
    /* Destruction also frees every command buffer allocated from this pool. */
    pvkDestroyCommandPool(g_dev,(VkCommandPool)c->pool,NULL);
    c->pool=NULL;c->cb=NULL;
    pthread_mutex_lock(&g_command_pool_stats_lock);
    g_command_pool_stats[1]++;g_command_pool_stats[2]--;
    g_command_pool_stats[state==NVK_POOL_COMPLETE?6:7]++;
    pthread_mutex_unlock(&g_command_pool_stats_lock);
    return 1;
}
static int nvmtl_pool_begin_raw(nvk_cmdbuf *c)
{
    memset(c,0,sizeof *c);
    VkCommandPool pool=VK_NULL_HANDLE;
    VkCommandPoolCreateInfo pi={VK_STRUCTURE_TYPE_COMMAND_POOL_CREATE_INFO,NULL,VK_COMMAND_POOL_CREATE_TRANSIENT_BIT,g_qfam};
    VkResult result=pvkCreateCommandPool(g_dev,&pi,NULL,&pool);
    if(result!=VK_SUCCESS){nvlog("vk: fresh command pool creation FAILED -> %d",result);return -1;}
    nvmtl_pool_created(c,pool);
    VkCommandBufferAllocateInfo ai={VK_STRUCTURE_TYPE_COMMAND_BUFFER_ALLOCATE_INFO,NULL,pool,VK_COMMAND_BUFFER_LEVEL_PRIMARY,1};
    result=nvmtl_opaque_AllocateCommandBuffers(g_dev,&ai,&c->cb);
    if(result!=VK_SUCCESS){nvlog("vk: vkAllocateCommandBuffers FAILED -> %d",result);nvmtl_pool_destroy(c);return -1;}
    VkCommandBufferBeginInfo bi={VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO,NULL,VK_COMMAND_BUFFER_USAGE_ONE_TIME_SUBMIT_BIT,NULL};
    result=pvkBeginCommandBuffer(c->cb,&bi);
    if(result!=VK_SUCCESS){nvlog("vk: vkBeginCommandBuffer FAILED -> %d",result);nvmtl_pool_destroy(c);return -1;}
    return 0;
}
static void *worker(void *arg){(void)arg;for(int n=0;n<10000;n++){nvk_cmdbuf c;assert(!nvmtl_pool_begin_raw(&c));assert(c.pool_state==NVK_POOL_RECORDING);nvmtl_pool_state(&c,NVK_POOL_SUBMITTED);nvmtl_pool_state(&c,NVK_POOL_COMPLETE);assert(nvmtl_pool_destroy(&c));assert(!c.pool&&!c.cb);assert(nvmtl_pool_destroy(&c));}return NULL;}
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
