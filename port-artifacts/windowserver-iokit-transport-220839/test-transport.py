from pathlib import Path
import subprocess
r=Path(__file__).resolve().parent.parent
s=(r/'libdrm/xf86drm.c').read_text()
a=s.index('static unsigned long long nmx_direct_calls');b=s.index('\n/* the node the IOKit',a)
code=s[a:b]
a=s.index('drm_public int drmNmxOpen(');b=s.index('\nstatic int drm_darwin_uc_device',a)
open_code=s[a:b]
pre='''#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
#include <fcntl.h>
#include <assert.h>
#define drm_public
#define NMX_UC_NODE "/dev/dri/renderD128"
typedef int io_connect_t;
static int conn, creates, calls, direct_result, open_calls, tokens;
static io_connect_t nmx_uc_get(int fd,int create){(void)fd;creates+=create;return conn;}
static int nmx_uc_call(int c,unsigned long r,void *a){(void)c;(void)r;(void)a;calls++;return 0;}
static int fake_ioctl(int fd,unsigned long r,void *a){(void)fd;(void)r;(void)a;errno=EPERM;return direct_result;}
static int fake_open(const char *p,int flags){(void)p;(void)flags;open_calls++;errno=EPERM;return -1;}
static int nmx_token_open(int flags){(void)flags;tokens++;return 123;}
#define ioctl fake_ioctl
#define open fake_open
'''
post='''int main(void){
 setenv("NMX_DRM_TEST_TRANSPORT","direct",1);conn=0;direct_result=-1;
 assert(drmNmxIoctl(1,0,NULL)==-1 && creates==0 && calls==0 && nmx_direct_calls==1);
 conn=5;assert(drmNmxIoctl(1,0,NULL)==-1 && errno==EXDEV && calls==0);
 assert(drmNmxOpen(NMX_UC_NODE,O_RDWR)==-1 && tokens==0 && open_calls==1);
 setenv("NMX_DRM_TEST_TRANSPORT","iokit",1);conn=5;
 assert(drmNmxIoctl(1,0,NULL)==0 && calls==1 && nmx_iokit_calls==1 && nmx_direct_calls==1);
 conn=0;assert(drmNmxIoctl(1,0,NULL)==-1 && errno==EXDEV && creates==0);
 assert(drmNmxOpen(NMX_UC_NODE,O_RDWR)==123 && tokens==1 && open_calls==1);
 setenv("NMX_DRM_TEST_TRANSPORT","typo",1);
 assert(drmNmxIoctl(1,0,NULL)==-1 && errno==EINVAL);
 assert(drmNmxOpen(NMX_UC_NODE,O_RDWR)==-1 && errno==EINVAL);
 unsetenv("NMX_DRM_TEST_TRANSPORT");conn=0;direct_result=0;
 assert(drmNmxIoctl(1,0,NULL)==0 && calls==1);
 puts("PASS actual transport implementation: forced route isolation, no cross-file fallback, invalid-mode rejection, counters, normal direct success");
}
'''
f=r/'desktop-build/test-transport.c';f.write_text(pre+code+open_code+post)
subprocess.run(['xcrun','clang','-fsanitize=address,undefined','-g',str(f),'-o',str(r/'desktop-build/test-transport')],check=True)
subprocess.run([str(r/'desktop-build/test-transport')],check=True)
