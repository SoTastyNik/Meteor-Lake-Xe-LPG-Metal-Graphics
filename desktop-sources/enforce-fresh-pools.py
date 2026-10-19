from pathlib import Path
r=Path('/Users/ved/Documents/iGPU Port');f=r/'NullMoth/plugin/nvmtl_vk.h';s=f.read_text().replace('unsigned in_rp, occlusion_reset; uint32_t wseq;', 'unsigned in_rp, occlusion_reset; uint32_t wseq; uint32_t pool_state;',1);s+='''
enum { NVK_POOL_RECORDING, NVK_POOL_SUBMITTED, NVK_POOL_COMPLETE, NVK_POOL_QUARANTINED };
void nvmtl_vk_command_pool_stats(uint64_t out[8]);
''';f.write_text(s)
f=r/'NullMoth/plugin/nvmtl_vk.c';s=f.read_text();s=s.replace('static VkCommandPool g_keep_pool[NVMTL_KEEP]; static unsigned g_keep_npool;\n','',1)
s=s.replace('vk: pool reuse ON (witness-guarded default) - empty command pools and address pages kept (<= %d), reused only on THE WITNESS','vk: address-page reuse ON (witness-guarded, <= %d); command pools are always fresh',1)
a=s.index('static int nvmtl_command_pool_fresh(void)');b=s.index('static nvmtl_address_page *nvmtl_keep_page_pop',a)
s=s[:a]+'''/* Permanent policy: no command-pool cache or environment opt-out exists. */
static int nvmtl_command_pool_fresh(void) { return 1; }
uint32_t nvmtl_vk_diagnostic_policy(void)
{
    const char *d=getenv("NVMTL_DIAGNOSTIC_STDERR"), *t=getenv("NVMTL_READBACK_TRACE"), *stage=getenv("NVMTL_READBACK_STAGE_FRESH");
    return (d && !strcmp(d,"1") ? 1u:0u) | 2u | 32u |
        (nvmtl_keep_on()?4u:0u) | (t && !strcmp(t,"1")?8u:0u) | (stage && !strcmp(stage,"1")?16u:0u);
}
static pthread_mutex_t nvmtl_submit_mutex = PTHREAD_RECURSIVE_MUTEX_INITIALIZER;
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
''' +s[b:]
# Queue records have no shared command pool; all work uses the per-recording owner.
a=s.index('int nvmtl_vk_queue_create(nvk_queue *out)');b=s.index('\nstatic long double nvmtl_tick_delta',a)
s=s[:a]+'''int nvmtl_vk_queue_create(nvk_queue *out)
{
    if(nvmtl_vk_init())return -1;
    memset(out,0,sizeof *out);
    return 0;
}
''' +s[b:]
a=s.index('    memset(out, 0, sizeof *out);\n    VkCommandPool pool = nvmtl_keep_pool_pop();',s.index('int nvmtl_vk_cmd_begin('));b=s.index('    if (pvkGetCalibratedTimestampsEXT',a)
s=s[:a]+'''    if(nvmtl_pool_begin_raw(out))return -1;
''' +s[b:]
# Dedicated dummy path uses the same fresh allocator but no managed-flush hooks,
# because descriptor initialization can already hold the descriptor lock.
a=s.index('    VkCommandPool pool = VK_NULL_HANDLE;',s.index('static void nvmtl_vk_zero_dummies(void)\n{'));b=s.index('    VkImageSubresourceRange range',a)
s=s[:a]+'''    nvk_cmdbuf owner;
    if(nvmtl_pool_begin_raw(&owner)){nvlog("vk: dummy zero-fill FAILED to begin");return;}
    VkCommandBuffer cb=(VkCommandBuffer)owner.cb;VkFence fence=VK_NULL_HANDLE;
''' +s[b:]
a=s.index('    if (pvkEndCommandBuffer(cb) != VK_SUCCESS)',s.index('static void nvmtl_vk_zero_dummies(void)\n{'));b=s.index('    nvlog("vk: dummy images ZEROED',a)
s=s[:a]+'''    if(pvkEndCommandBuffer(cb)!=VK_SUCCESS){nvlog("vk: dummy zero-fill FAILED to end");nvmtl_pool_destroy(&owner);return;}
    VkFenceCreateInfo fci={VK_STRUCTURE_TYPE_FENCE_CREATE_INFO,NULL,0};
    if(pvkCreateFence(g_dev,&fci,NULL,&fence)!=VK_SUCCESS){nvlog("vk: dummy zero-fill FAILED to create fence");nvmtl_pool_destroy(&owner);return;}
    VkSubmitInfo si={VK_STRUCTURE_TYPE_SUBMIT_INFO,NULL,0,NULL,NULL,1,&cb,0,NULL};
    nvmtl_pool_state(&owner,NVK_POOL_SUBMITTED);
    pthread_mutex_lock(&nvmtl_submit_mutex);
    VkResult sr=pvkQueueSubmit(g_queue,1,&si,fence);
    pthread_mutex_unlock(&nvmtl_submit_mutex);
    VkResult wr=sr==VK_SUCCESS?pvkWaitForFences(g_dev,1,&fence,VK_TRUE,2000000000ull):sr;
    if(wr!=VK_SUCCESS){
        nvmtl_pool_state(&owner,NVK_POOL_QUARANTINED);g_state=-1;
        nvlog("vk: dummy zero-fill FAILED -> %d; retaining uncertain pool and fence",wr);return;
    }
    nvmtl_pool_state(&owner,NVK_POOL_COMPLETE);
    pvkDestroyFence(g_dev,fence,NULL);nvmtl_pool_destroy(&owner);
''' +s[b:]
# Guard all referenced resources, not only the pool, against pending retirement.
s=s.replace('''static void nvmtl_cmd_retire(nvk_cmdbuf *c)
{
    nvmtl_counter_retire(c);''','''static void nvmtl_cmd_retire(nvk_cmdbuf *c)
{
    if(!c)return;
    if(c->pool && c->pool_state!=NVK_POOL_RECORDING && c->pool_state!=NVK_POOL_COMPLETE){
        nvmtl_pool_state(c,NVK_POOL_QUARANTINED);
        nvlog("command pool retirement REFUSED while pending; resources retained");return;
    }
    nvmtl_counter_retire(c);''',1)
a=s.index('    if (c->cb && c->pool) {',s.index('static void nvmtl_cmd_retire('));b=s.index('\n}\n',a)
s=s[:a]+'''    nvmtl_pool_destroy(c);''' +s[b:]
# Keep the mutex at allocator scope so the dummy initialization also uses it.
needle='static pthread_mutex_t nvmtl_submit_mutex = PTHREAD_RECURSIVE_MUTEX_INITIALIZER;';a=s.index(needle);b=s.index(needle,a+len(needle));s=s[:b]+s[b+len(needle):]
s=s.replace('static int nvmtl_counter_flush(nvk_cmdbuf *c);','static void nvmtl_counter_pool_state(nvk_cmdbuf *c,uint32_t state);\nstatic int nvmtl_counter_flush(nvk_cmdbuf *c);',1)
needle='''    result = g_state == 1 ? pvkQueueSubmit(g_queue, 1, &si, fence) : VK_ERROR_DEVICE_LOST;''';s=s.replace(needle,'''    nvmtl_pool_state(c,NVK_POOL_SUBMITTED);
    if(pre->begun)nvmtl_pool_state(&pre->cb,NVK_POOL_SUBMITTED);
    nvmtl_counter_pool_state(c,NVK_POOL_SUBMITTED);
'''+needle,1)
s=s.replace('''        g_state = -1;
        nvlog("vk: queue submit ->''','''        g_state = -1;
        nvmtl_pool_state(c,NVK_POOL_QUARANTINED);
        if(pre->begun)nvmtl_pool_state(&pre->cb,NVK_POOL_QUARANTINED);
        nvmtl_counter_pool_state(c,NVK_POOL_QUARANTINED);
        nvlog("vk: queue submit ->''',1)
s=s.replace('''int nvmtl_vk_submit_finish(nvmtl_inflight *f)
{
    nvk_cmdbuf''','''int nvmtl_vk_submit_finish(nvmtl_inflight *f)
{
    if(!f || !f->c || !f->fence)return -1;
    nvk_cmdbuf''',1)
s=s.replace('''        g_state = -1;
        nvlog("vk: fence wait ->''','''        g_state = -1;
        nvmtl_pool_state(c,NVK_POOL_QUARANTINED);
        if(pre->begun)nvmtl_pool_state(&pre->cb,NVK_POOL_QUARANTINED);
        nvmtl_counter_pool_state(c,NVK_POOL_QUARANTINED);
        nvlog("vk: fence wait ->''',1)
s=s.replace('''            g_state = -1;
            nvlog("vk: completion witness missing''','''            g_state = -1;
            nvmtl_pool_state(c,NVK_POOL_QUARANTINED);
            if(pre->begun)nvmtl_pool_state(&pre->cb,NVK_POOL_QUARANTINED);
            nvmtl_counter_pool_state(c,NVK_POOL_QUARANTINED);
            nvlog("vk: completion witness missing''',1)
s=s.replace('''    c->timing.host_after_ns = clock_gettime_nsec_np''','''    nvmtl_pool_state(c,NVK_POOL_COMPLETE);
    if(pre->begun)nvmtl_pool_state(&pre->cb,NVK_POOL_COMPLETE);
    nvmtl_counter_pool_state(c,NVK_POOL_COMPLETE);
    c->timing.host_after_ns = clock_gettime_nsec_np''',1)
s=s.replace('''    nvmtl_perf_submit(perf_sets, pt);
    return 0;''','''    nvmtl_perf_submit(perf_sets, pt);
    f->fence=VK_NULL_HANDLE;f->c=NULL;
    return 0;''',1)
needle='''static int nvmtl_counter_fail(nvk_cmdbuf *c)''';a=s.index(needle);s=s[:a]+'''static void nvmtl_counter_pool_state(nvk_cmdbuf *c,uint32_t state)
{
    nvmtl_counter_recording *r=c ? c->counter_recording:NULL;
    if(r)nvmtl_pool_state(&r->reset,state);
}
''' +s[a:]
f.write_text(s)
p=r/'NullMoth/plugin/NVMTLDevice.m';s=p.read_text().replace('- (NSUInteger)nvmtlDiagnosticPolicy { return nvmtl_vk_diagnostic_policy(); }','''- (NSUInteger)nvmtlDiagnosticPolicy { return nvmtl_vk_diagnostic_policy(); }
- (NSArray *)nvmtlCommandPoolStats {
    uint64_t s[8];nvmtl_vk_command_pool_stats(s);
    return @[@(s[0]),@(s[1]),@(s[2]),@(s[3]),@(s[4]),@(s[5]),@(s[6]),@(s[7])];
}''',1);p.write_text(s)
