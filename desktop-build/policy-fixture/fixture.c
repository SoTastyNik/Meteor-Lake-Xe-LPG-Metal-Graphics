#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>
#include <dlfcn.h>
int main(int argc,char **argv){assert(argc==3);void *h=dlopen(argv[1],RTLD_NOW|RTLD_LOCAL);if(!h){fputs(dlerror(),stderr);return 2;}
 uint32_t(*policy)(void)=dlsym(h,"nvmtl_vk_diagnostic_policy");assert(policy);
 uint32_t actual=policy(),expected=(uint32_t)strtoul(argv[2],NULL,0);assert(actual==expected);
 assert(!getenv("NVMTL_UNRELATED")&&!getenv("NVK_UNRELATED")&&!getenv("NVRM_UNRELATED"));
 if(expected!=38)assert(getenv("NVMTL_DIAGNOSTIC_STDERR")&&!strcmp(getenv("NVMTL_DIAGNOSTIC_STDERR"),"1"));
 else assert(!getenv("NVMTL_DIAGNOSTIC_STDERR")&&!getenv("NVMTL_COMMAND_POOL_FRESH")&&!getenv("NVMTL_READBACK_STAGE_FRESH"));
 printf("PASS actual release constructor: effective=%u expected=%u\n",actual,expected);return 0;}
