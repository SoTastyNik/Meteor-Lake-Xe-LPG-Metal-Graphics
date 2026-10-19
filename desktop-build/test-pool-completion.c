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
static int fail_create,fail_allocate,fail_begin,must_wait,waited;
static void nvlog(const char *fmt,...){(void)fmt;}
static VkResult pvkCreateCommandPool(VkDevice d,const VkCommandPoolCreateInfo *i,const VkAllocationCallbacks *a,VkCommandPool *p){(void)d;(void)a;assert(i->flags==VK_COMMAND_POOL_CREATE_TRANSIENT_BIT);if(fail_create)return VK_ERROR_OUT_OF_HOST_MEMORY;*p=(VkCommandPool)(uintptr_t)(atomic_fetch_add(&handles,1)+100);return VK_SUCCESS;}
static VkResult nvmtl_opaque_AllocateCommandBuffers(VkDevice d,const VkCommandBufferAllocateInfo *i,void **p){(void)d;if(fail_allocate)return VK_ERROR_OUT_OF_HOST_MEMORY;*p=(void *)((uintptr_t)i->commandPool+100000);return VK_SUCCESS;}
static VkResult pvkBeginCommandBuffer(VkCommandBuffer c,const VkCommandBufferBeginInfo *i){(void)c;assert(i->flags==VK_COMMAND_BUFFER_USAGE_ONE_TIME_SUBMIT_BIT);return fail_begin?VK_ERROR_OUT_OF_HOST_MEMORY:VK_SUCCESS;}
static void pvkDestroyCommandPool(VkDevice d,VkCommandPool p,const VkAllocationCallbacks *a){(void)d;(void)a;assert(p);assert(!must_wait || waited);atomic_fetch_add(&destroy_calls,1);}
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

#include <time.h>
#include <unistd.h>
void nvmtl_desktop_trace(const char *p,const char *d,int r){}
static int g_state=1,g_vendor=0x8086,witness_fail;static VkResult wait_result;static int fence_destroy;
static _Atomic uint64_t g_submit_wait_ns,g_submit_waits;
static long g_slow_submit_ms;static unsigned g_peak_sets,g_peak_fbs,g_ndescPools,g_timestamp_bits=64;
static uint64_t g_pt_seq,g_pre_subs,g_pre_copies,g_pre_fills,g_pre_bytes,g_pre_fail;
static struct {double timestampPeriod;}g_lim;
#define NVMTL_WSEQ_BLIND 0xFFFFFFFFu
static long nvmtl_gpu_wait_budget_ms(void){return 0;}
static int nvmtl_submit_trace(uint64_t i){return 0;}
uint64_t nvmtl_perf_now(void){return 0;}
static int nvmtl_keep_verdict(unsigned i){return witness_fail?-1:1;}
static VkResult pvkWaitForFences(VkDevice d,unsigned n,const VkFence *f,VkBool32 all,uint64_t t){assert(!fence_destroy);waited=1;return wait_result;}
static void pvkDestroyFence(VkDevice d,VkFence f,const VkAllocationCallbacks *a){assert(waited&&wait_result==VK_SUCCESS&&!witness_fail);fence_destroy++;}
static VkResult pvkGetQueryPoolResults(VkDevice d,VkQueryPool q,unsigned a,unsigned b,size_t n,void *v,VkDeviceSize stride,VkQueryResultFlags flags){abort();}
static void pvkDestroyQueryPool(VkDevice d,VkQueryPool q,const VkAllocationCallbacks *a){abort();}
int nvmtl_vk_interval_seconds(const nvmtl_gpu_interval *t,double *a,double *b){abort();}
static void nvmtl_perf_submit(unsigned n,uint64_t *pt){}
static nvk_cmdbuf reset;static nvk_cmdbuf *main_cmd;
static void nvmtl_counter_pool_state(nvk_cmdbuf *c,uint32_t st){if(c==main_cmd)nvmtl_pool_state(&reset,st);}
static void nvmtl_cmd_retire(nvk_cmdbuf *c){assert(c->pool_state==NVK_POOL_COMPLETE);assert(nvmtl_pool_destroy(c));if(c==main_cmd){assert(reset.pool_state==NVK_POOL_COMPLETE);assert(nvmtl_pool_destroy(&reset));}}
typedef struct { nvk_cmdbuf cb; unsigned begun, n, fills, copies, nhold; unsigned long long bytes; void *hold[4]; } nvmtl_prologue;
static void nvmtl_pre_drop(nvmtl_prologue *p){}
struct nvmtl_inflight { nvk_cmdbuf *c; VkFence fence; nvmtl_prologue pre; uint64_t pt[8]; uint64_t diagnostic_id; };
int nvmtl_vk_submit_finish(nvmtl_inflight *f)
{
    if(!f || !f->c || !f->fence)return -1;
    nvk_cmdbuf *const c = f->c; const VkFence fence = f->fence; uint64_t *const pt = f->pt;
    nvmtl_prologue *const pre = &f->pre;
    const long budget_ms = nvmtl_gpu_wait_budget_ms();
    const uint64_t w0 = clock_gettime_nsec_np(CLOCK_MONOTONIC_RAW);
    VkResult wr; long waited_ms = 0;
    nvmtl_desktop_trace("fence-wait-begin","",0);
    for (;;) {
        wr = pvkWaitForFences(g_dev, 1, &fence, VK_TRUE, 250ull * 1000 * 1000);
        waited_ms = (long)((clock_gettime_nsec_np(CLOCK_MONOTONIC_RAW) - w0) / 1000000ull);
        if (wr != VK_TIMEOUT) break;
        if (waited_ms >= budget_ms) break;
    }
    nvmtl_desktop_trace("fence-wait-end","",wr);
    if (nvmtl_submit_trace(f->diagnostic_id) || (wr != VK_SUCCESS && g_vendor == 0x8086))
        nvlog("first-submit: #%llu fence result %d after %ld ms", (unsigned long long)f->diagnostic_id, wr, waited_ms);
    pt[5] = nvmtl_perf_now();
    atomic_fetch_add(&g_submit_wait_ns, clock_gettime_nsec_np(CLOCK_MONOTONIC_RAW) - w0);
    atomic_fetch_add(&g_submit_waits, 1);
    if (waited_ms > g_slow_submit_ms) {
        g_slow_submit_ms = waited_ms;
        if (waited_ms >= 1000)
            nvlog("vk: slowest submit so far %ld ms (budget %ld ms) - this is the wait the old 5 s watchdog called a dead device", waited_ms, budget_ms);
    }
    if (wr != VK_SUCCESS || g_state != 1) {
        g_state = -1;
        nvmtl_pool_state(c,NVK_POOL_QUARANTINED);
        if(pre->begun)nvmtl_pool_state(&pre->cb,NVK_POOL_QUARANTINED);
        nvmtl_counter_pool_state(c,NVK_POOL_QUARANTINED);
        nvlog("vk: fence wait -> %d after %ld ms (budget %ld ms); disabling backend without retiring in-flight resources", wr, waited_ms, budget_ms);
        return -2;
    }
    if (c->wseq && c->wseq != NVMTL_WSEQ_BLIND) {
        if (nvmtl_keep_verdict(c->wseq) < 0) {
            g_state = -1;
            nvmtl_pool_state(c,NVK_POOL_QUARANTINED);
            if(pre->begun)nvmtl_pool_state(&pre->cb,NVK_POOL_QUARANTINED);
            nvmtl_counter_pool_state(c,NVK_POOL_QUARANTINED);
            nvlog("vk: completion witness missing; disabling backend and retaining all in-flight resources");
            return -2;
        }
        c->wseq = 0;
    }
    nvmtl_pool_state(c,NVK_POOL_COMPLETE);
    if(pre->begun)nvmtl_pool_state(&pre->cb,NVK_POOL_COMPLETE);
    nvmtl_counter_pool_state(c,NVK_POOL_COMPLETE);
    c->timing.host_after_ns = clock_gettime_nsec_np(CLOCK_UPTIME_RAW);
    if (c->timing_pool && c->timing.clock.valid) {
        uint64_t pair[4] = {0};
        VkResult qr = pvkGetQueryPoolResults(g_dev, (VkQueryPool)c->timing_pool, 0, 2,
            sizeof pair, pair, 16, VK_QUERY_RESULT_64_BIT | VK_QUERY_RESULT_WITH_AVAILABILITY_BIT);
        if (qr == VK_SUCCESS && pair[1] && pair[3]) {
            c->timing.start_tick = pair[0]; c->timing.end_tick = pair[2]; c->timing.valid = 1;
            double a, b;
            if (nvmtl_vk_interval_seconds(&c->timing, &a, &b)) c->timing.valid = 0;
        }
    }
    if (c->pt_pool && c->pt_n) {
        uint64_t r[256] = {0}; const unsigned n = c->pt_n;
        if (pvkGetQueryPoolResults(g_dev, (VkQueryPool)c->pt_pool, 0, 2 * n, sizeof(uint64_t) * 2 * n, r, 8, VK_QUERY_RESULT_64_BIT) == VK_SUCCESS) {
            static FILE *pf; if (!pf) { char fp[512]; const char *td = getenv("TMPDIR"); snprintf(fp, sizeof fp, "%s/nvmtl-passtime-%d.log", td && *td ? td : "/tmp", (int)getpid()); pf = fopen(fp, "a"); }
            const double us = g_lim.timestampPeriod / 1000.0; const uint64_t mask = g_timestamp_bits >= 64 ? ~0ull : ((1ull << g_timestamp_bits) - 1);
            const uint64_t seq = ++g_pt_seq;
            for (unsigned i = 0; pf && i < n; i++) {
                const double gpu = (double)((r[2 * i + 1] - r[2 * i]) & mask) * us;
                const double gap = i ? (double)((r[2 * i] - r[2 * i - 1]) & mask) * us : 0.0;
                fprintf(pf, "cb %llu pass %u %ux%u fmt %u gpu_us %.1f gap_us %.1f fs %08x %08x %08x %08x\n", (unsigned long long)seq, i, c->pt_w[i], c->pt_h[i], c->pt_f[i], gpu, gap,
                        c->pt_fs[i][0], c->pt_fs[i][1], c->pt_fs[i][2], c->pt_fs[i][3]);
            }
            if (pf) fflush(pf);
        }
        pvkDestroyQueryPool(g_dev, (VkQueryPool)c->pt_pool, NULL); c->pt_pool = NULL; c->pt_n = 0;
    }
    pvkDestroyFence(g_dev, fence, NULL);
    if (c->nsets > g_peak_sets) { g_peak_sets = c->nsets; nvlog("vk: commit high-water: %u descriptor sets = %u draws in one command buffer (%u pools open)", c->nsets, c->nsets / 2, g_ndescPools); }
    if (c->nfb > g_peak_fbs) g_peak_fbs = c->nfb;
    if (c->skipped) nvlog("vk: commit with %u draws/dispatches SKIPPED (no descriptor set could be allocated)", c->skipped);
    const unsigned perf_sets = c->nsets;
    pt[6] = nvmtl_perf_now();
    if (pre->begun) {
        pre->cb.wseq = c->wseq; nvmtl_cmd_retire(&pre->cb); nvmtl_pre_drop(pre);
        const unsigned long long k = g_pre_subs++; g_pre_copies += pre->copies; g_pre_fills += pre->fills; g_pre_bytes += pre->bytes;
        if (!k || ((k + 1) & 0xFFF) == 0)
            nvlog("vk: pre-submit prologue census: %llu submits carried %llu managed uploads + %llu zero fills (%llu KB) - each WAS its own submit; %llu prologues failed",
                  k + 1, (unsigned long long)g_pre_copies, (unsigned long long)g_pre_fills, (unsigned long long)(g_pre_bytes >> 10), (unsigned long long)g_pre_fail);
    }
    nvmtl_cmd_retire(c);
    pt[7] = nvmtl_perf_now();
    nvmtl_perf_submit(perf_sets, pt);
    f->fence=VK_NULL_HANDLE;f->c=NULL;
    return 0;
}

int main(int argc,char **argv){
 assert(argc==2);int mode=atoi(argv[1]);nvk_cmdbuf c;nvmtl_inflight f={0};main_cmd=&c;
 assert(!nvmtl_pool_begin_raw(&c));assert(!nvmtl_pool_begin_raw(&f.pre.cb));assert(!nvmtl_pool_begin_raw(&reset));f.c=&c;f.fence=(VkFence)99;f.pre.begun=1;c.wseq=10;
 nvmtl_pool_state(&c,NVK_POOL_SUBMITTED);nvmtl_pool_state(&f.pre.cb,NVK_POOL_SUBMITTED);nvmtl_pool_state(&reset,NVK_POOL_SUBMITTED);
 must_wait=1;wait_result=mode==1?VK_TIMEOUT:mode==2?VK_ERROR_DEVICE_LOST:VK_SUCCESS;witness_fail=mode==3;
 int result=nvmtl_vk_submit_finish(&f);uint64_t st[8];nvmtl_vk_command_pool_stats(st);assert(waited);
 if(!mode){assert(!result&&st[0]==3&&st[1]==3&&!st[2]&&!st[4]&&!st[5]&&st[6]==3&&fence_destroy==1);assert(nvmtl_vk_submit_finish(&f)==-1&&fence_destroy==1);}
 else {assert(result==-2&&st[0]==3&&!st[1]&&st[2]==3&&st[4]==3&&!st[5]&&!fence_destroy&&g_state==-1);}
 printf("PASS actual submit_finish mode=%d: main, prologue and counter-reset pools obey fence/witness lifetime\n",mode);
}
