from pathlib import Path
import subprocess
r=Path(__file__).resolve().parent.parent;s=(r/'NullMoth/plugin/NVMTLDevice.m').read_text();a=s.index('#define NVLOG_SITES');b=s.index('const char *nvmtl_log_path',a);throttle=s[a:b];a=s.index('void nvlog(const char *fmt, ...)');b=s.index('\n#define NVMTL_OOM_STREAK',a);logger=s[a:b]
pre='''#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <stdarg.h>
#include <string.h>
#include <unistd.h>
#include <pthread.h>
#include <time.h>
#include <assert.h>
#include "nvmtl_log_failure.h"
#define NVMTL_RELEASE 1
#define LOG_ERR 3
static int logged;
#define syslog(...) ((void)++logged)
'''
post='''int main(void){
 for(int i=0;i<40;i++)nvlog("readback FAILED phase=test value=%d",i);
 assert(logged==8);
 setenv("NVMTL_DIAGNOSTIC_STDERR","1",1);
 for(int i=0;i<20;i++)nvlog("readback FAILED phase=test value=%d",40+i);
 assert(logged==8);
 nvlog("ordinary cached memory type %u",0u);
 setenv("NVMTL_DIAGNOSTIC_STDERR","0",1);nvlog("readback FAILED phase=test value=%d",60);
 puts("PASS actual release logger: explicit stderr diagnostics survive per-site throttle; unset/zero stay off; routine messages excluded; syslog throttle unchanged");
}
'''
f=r/'desktop-build/test-diagnostic-stderr.c';f.write_text(pre+throttle+logger+post)
subprocess.run(['xcrun','clang','-g','-fsanitize=address,undefined','-I',str(r/'NullMoth/plugin'),str(f),'-o',str(r/'desktop-build/test-diagnostic-stderr')],check=True)
c=subprocess.run([str(r/'desktop-build/test-diagnostic-stderr')],capture_output=True,text=True,check=True);lines=c.stderr.splitlines();assert len(lines)==20 and all('NVMTL-DIAG' in line and 'readback FAILED phase=test' in line for line in lines);print(c.stdout.strip())
