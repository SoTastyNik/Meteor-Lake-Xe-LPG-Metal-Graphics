from pathlib import Path
import subprocess
r=Path(__file__).resolve().parent.parent;s=(r/'NullMoth/plugin/nvmtl_vk.c').read_text();fixture=(r/'desktop-build/test-pool-lifetime.c').read_text();pre=fixture[:fixture.index('static void *worker')]
pre=pre.replace('assert(p);atomic_fetch_add','assert(p);assert(!must_wait || waited);atomic_fetch_add').replace('static int fail_create,fail_allocate,fail_begin;','static int fail_create,fail_allocate,fail_begin,must_wait,waited;')
pre+='''
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
'''
a=s.index('typedef struct { nvk_cmdbuf cb; unsigned begun');b=s.index('\n',a);pre+=s[a:b]+'\nstatic void nvmtl_pre_drop(nvmtl_prologue *p){}\n';a=s.index('struct nvmtl_inflight {');b=s.index('\n',a);pre+=s[a:b]+'\n'
a=s.index('int nvmtl_vk_submit_finish(');b=s.index('\nstatic void nvmtl_vk_buffer_destroy_body',a)
post='''
int main(int argc,char **argv){
 assert(argc==2);int mode=atoi(argv[1]);nvk_cmdbuf c;nvmtl_inflight f={0};main_cmd=&c;
 assert(!nvmtl_pool_begin_raw(&c));assert(!nvmtl_pool_begin_raw(&f.pre.cb));assert(!nvmtl_pool_begin_raw(&reset));f.c=&c;f.fence=(VkFence)99;f.pre.begun=1;c.wseq=10;
 nvmtl_pool_state(&c,NVK_POOL_SUBMITTED);nvmtl_pool_state(&f.pre.cb,NVK_POOL_SUBMITTED);nvmtl_pool_state(&reset,NVK_POOL_SUBMITTED);
 must_wait=1;wait_result=mode==1?VK_TIMEOUT:mode==2?VK_ERROR_DEVICE_LOST:VK_SUCCESS;witness_fail=mode==3;
 int result=nvmtl_vk_submit_finish(&f);uint64_t st[8];nvmtl_vk_command_pool_stats(st);assert(waited);
 if(!mode){assert(!result&&st[0]==3&&st[1]==3&&!st[2]&&!st[4]&&!st[5]&&st[6]==3&&fence_destroy==1);assert(nvmtl_vk_submit_finish(&f)==-1&&fence_destroy==1);}
 else {assert(result==-2&&st[0]==3&&!st[1]&&st[2]==3&&st[4]==3&&!st[5]&&!fence_destroy&&g_state==-1);}
 printf("PASS actual submit_finish mode=%d: main, prologue and counter-reset pools obey fence/witness lifetime\\n",mode);
}
'''
f=r/'desktop-build/test-pool-completion.c';f.write_text(pre+s[a:b]+post);exe=r/'desktop-build/test-pool-completion';subprocess.run(['xcrun','clang','-fsanitize=address,undefined','-g','-Wno-unused-function','-I',str(r/'Vulkan-Headers/include'),'-I',str(r/'NullMoth/plugin'),str(f),'-o',str(exe)],check=True)
for mode in range(4):subprocess.run([str(exe),str(mode)],check=True)
