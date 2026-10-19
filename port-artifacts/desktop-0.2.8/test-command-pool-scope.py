from pathlib import Path
import subprocess
r=Path(__file__).resolve().parent.parent;s=(r/'NullMoth/plugin/nvmtl_vk.c').read_text();a=s.index('static int nvmtl_command_pool_fresh(');b=s.index('\nstatic nvmtl_address_page *nvmtl_keep_page_pop',a)
pre='''#include <assert.h>
#include <stdlib.h>
#include <string.h>
#include <pthread.h>
#include <stdio.h>
#include <vulkan/vulkan.h>
#define NVMTL_KEEP 256
static pthread_mutex_t g_keep_lock=PTHREAD_MUTEX_INITIALIZER;
static VkCommandPool g_keep_pool[NVMTL_KEEP];static unsigned g_keep_npool;
static int nvmtl_keep_on(void){return 1;}
'''
post='''int main(void){
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
'''
f=r/'desktop-build/test-command-pool-scope.c';f.write_text(pre+s[a:b]+post);subprocess.run(['xcrun','clang','-g','-fsanitize=address,undefined','-I',str(r/'Vulkan-Headers/include'),str(f),'-o',str(r/'desktop-build/test-command-pool-scope')],check=True);subprocess.run([str(r/'desktop-build/test-command-pool-scope')],check=True)
