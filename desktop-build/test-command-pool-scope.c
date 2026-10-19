#include <assert.h>
#include <stdlib.h>
#include <string.h>
#include <pthread.h>
#include <stdio.h>
#include <vulkan/vulkan.h>
#define NVMTL_KEEP 256
static pthread_mutex_t g_keep_lock=PTHREAD_MUTEX_INITIALIZER;
static VkCommandPool g_keep_pool[NVMTL_KEEP];static unsigned g_keep_npool;
static int nvmtl_keep_on(void){return 1;}
static int nvmtl_command_pool_fresh(void)
{
    const char *e=getenv("NVMTL_COMMAND_POOL_FRESH");
    return e && !strcmp(e,"1");
}
uint32_t nvmtl_vk_diagnostic_policy(void)
{
    const char *d=getenv("NVMTL_DIAGNOSTIC_STDERR"), *t=getenv("NVMTL_READBACK_TRACE"), *stage=getenv("NVMTL_READBACK_STAGE_FRESH");
    return (d && !strcmp(d,"1") ? 1u:0u) | (nvmtl_command_pool_fresh()?2u:0u) |
        (nvmtl_keep_on()?4u:0u) | (t && !strcmp(t,"1")?8u:0u) | (stage && !strcmp(stage,"1")?16u:0u);
}
static VkCommandPool nvmtl_keep_pool_pop(void)
{
    VkCommandPool p = VK_NULL_HANDLE;
    if (!nvmtl_keep_on() || nvmtl_command_pool_fresh()) return p;
    pthread_mutex_lock(&g_keep_lock); if (g_keep_npool) p = g_keep_pool[--g_keep_npool]; pthread_mutex_unlock(&g_keep_lock);
    return p;
}
static int nvmtl_keep_pool_push(VkCommandPool p)
{
    int kept = 0;
    if (!nvmtl_keep_on() || nvmtl_command_pool_fresh()) return 0;
    pthread_mutex_lock(&g_keep_lock); if (g_keep_npool < NVMTL_KEEP) { g_keep_pool[g_keep_npool++] = p; kept = 1; } pthread_mutex_unlock(&g_keep_lock);
    return kept;
}int main(void){
 VkCommandPool p=(VkCommandPool)1;
 assert(nvmtl_keep_pool_push(p)&&g_keep_npool==1);
 setenv("NVMTL_COMMAND_POOL_FRESH","1",1);
 assert(nvmtl_keep_pool_pop()==VK_NULL_HANDLE && g_keep_npool==1);
 assert(!nvmtl_keep_pool_push((VkCommandPool)2)&&g_keep_npool==1);
 assert(nvmtl_keep_on()==1);
 setenv("NVMTL_COMMAND_POOL_FRESH","0",1);
 assert(nvmtl_keep_pool_pop()==p&&g_keep_npool==0);
 puts("PASS actual command-pool cache: fresh-pool switch bypasses pop/push without disabling the shared keep/witness policy; zero restores normal reuse");
}
