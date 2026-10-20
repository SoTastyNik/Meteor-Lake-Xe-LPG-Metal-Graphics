from pathlib import Path
import tempfile,subprocess
r=Path(__file__).resolve().parent.parent
s=r'''
#define VK_NO_PROTOTYPES
#include <vulkan/vulkan.h>
#include <assert.h>
#include <stdio.h>
#include <stdint.h>
#include "nvmtl_pipeline_cache.h"
static unsigned creates;static VkResult outcome=VK_SUCCESS;
static VkResult create(VkDevice d,const VkPipelineCacheCreateInfo*i,const VkAllocationCallbacks*a,VkPipelineCache*out){
 assert(d==(VkDevice)(uintptr_t)1 && i->sType==VK_STRUCTURE_TYPE_PIPELINE_CACHE_CREATE_INFO && !i->pNext && !i->flags && !i->initialDataSize && !i->pInitialData && !a);
 creates++;*out=(VkPipelineCache)(uintptr_t)7;return outcome;
}
int main(){
 VkDevice owner=(VkDevice)(uintptr_t)1,other=(VkDevice)(uintptr_t)2;VkPipelineCache cache=(VkPipelineCache)(uintptr_t)55;
 assert(nvmtl_pipeline_cache_start(owner,0,create,&cache)==VK_SUCCESS&&!cache&&!creates);
 assert(nvmtl_pipeline_cache_start(owner,1,NULL,&cache)==VK_SUCCESS&&!cache&&!creates);
 assert(nvmtl_pipeline_cache_start(owner,1,create,&cache)==VK_SUCCESS&&cache==(VkPipelineCache)(uintptr_t)7&&creates==1);
 assert(nvmtl_pipeline_cache_pick(owner,owner,0,cache)==cache);
 assert(!nvmtl_pipeline_cache_pick(other,owner,0,cache));
 assert(nvmtl_pipeline_cache_pick(owner,owner,(VkPipelineCache)(uintptr_t)9,cache)==(VkPipelineCache)(uintptr_t)9);
 outcome=VK_ERROR_OUT_OF_HOST_MEMORY;assert(nvmtl_pipeline_cache_start(owner,1,create,&cache)==outcome&&!cache);
 assert(!nvmtl_pipeline_cache_pick(owner,owner,0,cache));
 puts("PASS actual pipeline cache helpers ASan/UBSan: default internally synchronized flags, scoped device ownership, requested-cache preservation, disabled/absent/create-failed fallback; no command-pool change");
}
'''
with tempfile.TemporaryDirectory() as d:
 p=Path(d);(p/'test.c').write_text(s);subprocess.run(['xcrun','clang','-fsanitize=address,undefined','-g','-I',str(r/'Vulkan-Headers/include'),'-I',str(r/'NullMoth/plugin'),str(p/'test.c'),'-o',str(p/'test')],check=True);subprocess.run([str(p/'test')],check=True)
