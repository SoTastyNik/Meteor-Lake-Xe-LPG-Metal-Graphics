from pathlib import Path
import subprocess,os,shutil,sys
r=Path(__file__).resolve().parent.parent;d=r/'desktop-build/policy-fixture';d.mkdir(exist_ok=True)
source='''#include <assert.h>
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
 printf("PASS actual release constructor: effective=%u expected=%u\\n",actual,expected);return 0;}
'''
(d/'fixture.c').write_text(source);subprocess.run(['xcrun','clang','-g','-fsanitize=address,undefined',str(d/'fixture.c'),'-o',str(d/'latitude-readback-test')],check=True);shutil.copy2(d/'latitude-readback-test',d/'other-process')
plugin=Path(sys.argv[1]) if len(sys.argv)>1 else r/'desktop-build/NVMTLDriver-release-policy-test-0.3.0'
base=os.environ.copy()
for k in list(base):
 if k.startswith(('NVMTL_','NVK_','NAK_','NVRM_')):base.pop(k)
base.update(NVMTL_DIAGNOSTIC_STDERR='1',NVMTL_READBACK_TRACE='1',NVMTL_POOL_REUSE='1',NVMTL_ENABLE='1',NVMTL_UNRELATED='must-strip',NVK_UNRELATED='must-strip',NVRM_UNRELATED='must-strip')
for executable,changes,expected in [('latitude-readback-test',{'NVMTL_COMMAND_POOL_FRESH':'0'},47),('latitude-readback-test',{},47),('latitude-readback-test',{'NVMTL_COMMAND_POOL_FRESH':'1'},47),('latitude-readback-test',{'NVMTL_READBACK_STAGE_FRESH':'1'},63),('other-process',{'NVMTL_COMMAND_POOL_FRESH':'1'},38),('latitude-readback-test',{'NVMTL_DIAGNOSTIC_STDERR':'0','NVMTL_COMMAND_POOL_FRESH':'1'},38)]:
 env=base.copy();env.update(changes);c=subprocess.run([str(d/executable),str(plugin),str(expected)],env=env,capture_output=True,text=True);assert c.returncode==0,c.stderr;print(c.stdout.strip())
print('PASS real native release plugin startup: test controls survive only for explicit probe; unrelated controls and other processes remain scrubbed')
