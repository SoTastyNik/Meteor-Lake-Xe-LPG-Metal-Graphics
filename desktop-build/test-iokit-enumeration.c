#define _DARWIN_C_SOURCE 1
#include <assert.h>
#include <dirent.h>
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/types.h>
#define drm_public
#define MAX_DRM_NODES 256
#define DRM_DIR_NAME "/dev/dri"
#define DRM_NODE_RENDER 2
#define MIN2(a,b) ((a)<(b)?(a):(b))
typedef void *drmDevicePtr;
static int route, dirs, fallback, sandbox_result=1, token=-1, stats;
static int nmx_test_route(void){return route;}
static int drm_device_validate_flags(unsigned f){return f?-EINVAL:0;}
static int drm_darwin_sandbox_devices(unsigned flags,drmDevicePtr *d,int n){(void)flags;fallback++;if(d&&n>0)*d=(void *)123;return sandbox_result;}
static DIR *fake_opendir(const char *s){(void)s;dirs++;return (DIR *)1;}
static struct dirent *fake_readdir(DIR *d){(void)d;return NULL;}
static int fake_closedir(DIR *d){(void)d;return 0;}
static int process_device(drmDevicePtr *d,const char *n,int fd,int fetch,unsigned flags){(void)d;(void)n;(void)fd;(void)fetch;(void)flags;assert(0);return -1;}
static void drmFoldDuplicatedDevices(drmDevicePtr *d,int n){(void)d;(void)n;}
static void drmFreeDevice(drmDevicePtr *d){(void)d;}
static int drm_darwin_token_type(int fd){(void)fd;return token;}
static int fake_fstat(int fd,struct stat *st){(void)fd;stats++;memset(st,0,sizeof *st);st->st_mode=S_IFIFO;return 0;}
static int drmNodeIsDRM(int a,int b){(void)a;(void)b;return 0;}
static int drmGetMinorType(int a,int b){(void)a;(void)b;return -1;}
#define opendir fake_opendir
#define readdir fake_readdir
#define closedir fake_closedir
#define fstat fake_fstat
drm_public int drmGetDevices2(uint32_t flags, drmDevicePtr devices[],
                              int max_devices)
{
    drmDevicePtr local_devices[MAX_DRM_NODES];
    drmDevicePtr device;
    DIR *sysdir;
    struct dirent *dent;
    int ret, i, node_count, device_count;

    if (drm_device_validate_flags(flags))
        return -EINVAL;

#ifdef __APPLE__
    /* Select the same transport for discovery and rendering. A forced IOKit
     * process must not enumerate through temporary devfs descriptors. */
    const int route = nmx_test_route();
    if (route < 0) return -EINVAL;
    if (route == 2)
        return drm_darwin_sandbox_devices(flags, devices, max_devices);
#endif
    sysdir = opendir(DRM_DIR_NAME);
#ifdef __APPLE__
    if (!sysdir && route != 1 && (errno == EPERM || errno == EACCES))
        return drm_darwin_sandbox_devices(flags, devices, max_devices);
#endif
    if (!sysdir)
        return -errno;

    i = 0;
    while ((dent = readdir(sysdir))) {
        ret = process_device(&device, dent->d_name, -1, devices != NULL, flags);
        if (ret)
            continue;

        if (i >= MAX_DRM_NODES) {
            fprintf(stderr, "More than %d drm nodes detected. "
                    "Please report a bug - that should not happen.\n"
                    "Skipping extra nodes\n", MAX_DRM_NODES);
            break;
        }
        local_devices[i] = device;
        i++;
    }
    node_count = i;

    drmFoldDuplicatedDevices(local_devices, node_count);

    device_count = 0;
    for (i = 0; i < node_count; i++) {
        if (!local_devices[i])
            continue;

        if ((devices != NULL) && (device_count < max_devices))
            devices[device_count] = local_devices[i];
        else
            drmFreeDevice(&local_devices[i]);

        device_count++;
    }

    closedir(sysdir);
#ifdef __APPLE__
    /* Directory access can succeed while individual node queries are denied. */
    if (device_count == 0 && route == 0) {
        ret = drm_darwin_sandbox_devices(flags, devices, max_devices);
        if (ret > 0) return ret;
    }
#endif
    if (devices != NULL)
        return MIN2(device_count, max_devices);

    return device_count;
}
drm_public int drmGetNodeTypeFromFd(int fd)
{
#ifdef __APPLE__
    if (drm_darwin_token_type(fd) == DRM_NODE_RENDER)
        return DRM_NODE_RENDER;
#endif
    struct stat sbuf;
    int maj, min, type;

    if (fstat(fd, &sbuf))
        return -1;

    maj = major(sbuf.st_rdev);
    min = minor(sbuf.st_rdev);

    if (!drmNodeIsDRM(maj, min) || !S_ISCHR(sbuf.st_mode)) {
        errno = EINVAL;
        return -1;
    }

    type = drmGetMinorType(maj, min);
    if (type == -1)
        errno = ENODEV;
    return type;
}
int main(void){
 drmDevicePtr d=NULL;route=2;assert(drmGetDevices2(0,&d,1)==1 && d==(void *)123 && dirs==0 && fallback==1);
 assert(drmGetDevices2(0,NULL,0)==1 && dirs==0 && fallback==2);
 sandbox_result=-EACCES;assert(drmGetDevices2(0,&d,1)==-EACCES && dirs==0);sandbox_result=1;
 route=1;int prev=fallback;assert(drmGetDevices2(0,&d,1)==0 && dirs==1 && fallback==prev);
 route=0;assert(drmGetDevices2(0,&d,1)==1 && dirs==2 && fallback==prev+1);
 sandbox_result=-EACCES;assert(drmGetDevices2(0,&d,1)==0);
 route=-1;prev=dirs;assert(drmGetDevices2(0,&d,1)==-EINVAL && dirs==prev);
 route=2;prev=fallback;assert(drmGetDevices2(1,&d,1)==-EINVAL && fallback==prev);
 token=DRM_NODE_RENDER;assert(drmGetNodeTypeFromFd(1)==DRM_NODE_RENDER && stats==0);
 token=-1;assert(drmGetNodeTypeFromFd(1)==-1 && stats==1 && errno==EINVAL);
 puts("PASS actual enumeration/node-type code: forced IOKit never opens devfs, direct never falls back, auto discovers after denied node queries, invalid flags/modes rejected, tracked token classified as render node");
}
