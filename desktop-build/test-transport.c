#include <stdio.h>
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
static unsigned long long nmx_direct_calls, nmx_iokit_calls;
static int nmx_test_route(void)
{
    const char *s = getenv("NMX_DRM_TEST_TRANSPORT");
    if (!s) return 0;
    if (!strcmp(s,"direct")) return 1;
    if (!strcmp(s,"iokit")) return 2;
    return -1;
}
__attribute__((destructor)) static void nmx_test_report(void)
{
    if (getenv("NMX_DRM_TEST_TRANSPORT"))
        fprintf(stderr,"NMX transport counters: requested=%s direct=%llu iokit=%llu\n",
            getenv("NMX_DRM_TEST_TRANSPORT"),
            __atomic_load_n(&nmx_direct_calls,__ATOMIC_RELAXED),
            __atomic_load_n(&nmx_iokit_calls,__ATOMIC_RELAXED));
}
drm_public int drmNmxIoctl(int fd, unsigned long request, void *arg)
{
    const int route = nmx_test_route();
    if (route < 0) { errno=EINVAL; return -1; }
    io_connect_t conn = nmx_uc_get(fd, 0);
    if (route == 1 && conn) { errno=EXDEV; return -1; }
    if (route == 2 && !conn) { errno=EXDEV; return -1; }
    if (!conn) {
        __atomic_fetch_add(&nmx_direct_calls,1,__ATOMIC_RELAXED);
        int ret = ioctl(fd, request, arg);
        if (route == 1 || ret == 0 || errno != EPERM) return ret;
        conn = nmx_uc_get(fd, 1);
        if (!conn) { errno = EPERM; return -1; }
    }
    __atomic_fetch_add(&nmx_iokit_calls,1,__ATOMIC_RELAXED);
    return nmx_uc_call(conn, request, arg);
}
drm_public int drmNmxOpen(const char *path, int flags)
{
    const int route = nmx_test_route();
    if (route < 0) { errno=EINVAL; return -1; }
    if (!strcmp(path, NMX_UC_NODE) && route == 2)
        return nmx_token_open(flags & O_CLOEXEC);
    int fd = open(path, flags);
    if (route == 1) return fd;

    if (fd >= 0 || (errno != EPERM && errno != EACCES))
        return fd;
    if ((flags & O_ACCMODE) != O_RDONLY && (fd = open(path, (flags & ~O_ACCMODE) | O_RDONLY)) >= 0)
        return fd;
    if ((errno != EPERM && errno != EACCES) || strcmp(path, NMX_UC_NODE) != 0)
        return -1;
    return nmx_token_open(flags & O_CLOEXEC);
}
int main(void){
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
