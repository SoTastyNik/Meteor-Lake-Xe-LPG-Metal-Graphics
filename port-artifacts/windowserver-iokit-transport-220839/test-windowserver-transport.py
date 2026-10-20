from pathlib import Path
import subprocess
r=Path(__file__).resolve().parent.parent
pre=r'''#include <assert.h>
#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <string.h>
#define drm_public
#define NMX_UC_NODE "/dev/dri/renderD128"
#define DRM_NODE_RENDER 2
typedef int io_connect_t;
typedef void *drmDevicePtr;
static int conn, route, direct_calls, token_calls, denied_errno=EPERM, readonly_allowed=1;
static int nmx_test_route(void){return route;}
static int fake_open(const char *p,int flags){(void)p;direct_calls++;if((flags&O_ACCMODE)==O_RDONLY && readonly_allowed)return 50;errno=denied_errno;return -1;}
static int nmx_token_open(int flags){(void)flags;token_calls++;return 123;}
static int drm_device_validate_flags(unsigned f){return f&~1;}
static int drm_darwin_token_type(int fd){return fd==123?DRM_NODE_RENDER:-1;}
static io_connect_t nmx_uc_get(int fd,int create){(void)fd;assert(!create);return conn;}
static int drm_darwin_uc_device(int c,drmDevicePtr *d){assert(c==7);*d=(void *)77;return 0;}
#define open fake_open
'''
post=r'''int main(void){
 drmDevicePtr d=0;
#ifdef OLD
 assert(drmNmxOpen(NMX_UC_NODE,O_RDWR)==50 && direct_calls==2 && token_calls==0);
 conn=7;assert(drm_darwin_token_device(50,0,&d)==-ENOENT);
 puts("PASS old negative control: denied writable node uses read-only fd; attached IOKit file ignored by device identity lookup");
#else
 for(int e=0;e<2;e++){
  denied_errno=e?EACCES:EPERM;direct_calls=token_calls=0;
  assert(drmNmxOpen(NMX_UC_NODE,O_RDWR|O_CLOEXEC)==123 && direct_calls==1 && token_calls==1);
 }
 conn=7;assert(drm_darwin_token_device(50,0,&d)==0 && d==(void *)77);
 assert(drm_darwin_token_device(123,1,&d)==0);
 assert(drm_darwin_token_device(123,2,&d)==-EINVAL);
 assert(drm_darwin_token_device(123,0,0)==-EINVAL);
 conn=0;assert(drm_darwin_token_device(50,0,&d)==-ENOENT);
 route=1;int prev=token_calls;assert(drmNmxOpen(NMX_UC_NODE,O_RDWR)==-1 && token_calls==prev);
 route=2;int before=direct_calls;assert(drmNmxOpen(NMX_UC_NODE,O_RDWR)==123 && direct_calls==before);
 route=0;assert(drmNmxOpen(NMX_UC_NODE,O_RDONLY)==50);
 prev=token_calls;assert(drmNmxOpen("/dev/other",O_RDWR)==50 && token_calls==prev);
 denied_errno=ENOENT;assert(drmNmxOpen(NMX_UC_NODE,O_RDWR)==-1 && token_calls==prev);
 puts("PASS corrected transport: denied RW render open stays IOKit; established real-fd identity stays on same DRM file; validation, non-permission errors, direct/IOKit route isolation and unrelated nodes preserved");
#endif
}
'''
for old in [True,False]:
 s=(r/('backups/windowserver-transport-before-220839/xf86drm.c' if old else 'libdrm/xf86drm.c')).read_text()
 a=s.index('drm_public int drmNmxOpen(');b=s.index('\nstatic int drm_darwin_uc_device',a);opening=s[a:b]
 a=s.index('static int drm_darwin_token_device(int fd, uint32_t flags, drmDevicePtr *device)\n{');b=s.index('\n/* the NullMoth DRM node ioctls',a)
 f=r/'desktop-build'/('test-ws-transport-old.c' if old else 'test-ws-transport.c');f.write_text(pre+'\n#include <stdint.h>\n'+opening+s[a:b]+post)
 subprocess.run(['xcrun','clang','-g','-fsanitize=address,undefined',*(['-DOLD'] if old else []),str(f),'-o',str(f.with_suffix(''))],check=True)
 subprocess.run([str(f.with_suffix(''))],check=True)
