#include <xf86drm.h>
#include <i915_drm.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <fcntl.h>
#include <errno.h>
#include <string.h>
#include <unistd.h>
int main(void) {
 setbuf(stdout,NULL);
 int fd=drmNmxOpen("/dev/dri/renderD128",O_RDWR|O_CLOEXEC);
 if(fd<0){fprintf(stderr,"DRM open failed: %s\n",strerror(errno));return 1;}
 const int params[]={I915_PARAM_CHIPSET_ID,I915_PARAM_REVISION,I915_PARAM_CS_TIMESTAMP_FREQUENCY,I915_PARAM_HAS_EXECBUF2};
 const char *names[]={"chipset","revision","timestamp_frequency","execbuf2"};
 for(unsigned i=0;i<sizeof(params)/sizeof(params[0]);i++) { int value=-1;struct drm_i915_getparam p={.param=params[i],.value=&value};errno=0;int rc=drmNmxIoctl(fd,DRM_IOCTL_I915_GETPARAM,&p);printf("GETPARAM %s rc=%d errno=%d value=%d (0x%x)\n",names[i],rc,errno,value,value); }
 const uint64_t ids[]={DRM_I915_QUERY_TOPOLOGY_INFO,DRM_I915_QUERY_GEOMETRY_SUBSLICES,DRM_I915_QUERY_ENGINE_INFO,DRM_I915_QUERY_MEMORY_REGIONS,DRM_I915_QUERY_HWCONFIG_BLOB};
 for(unsigned i=0;i<sizeof(ids)/sizeof(ids[0]);i++) {
  struct drm_i915_query_item item={.query_id=ids[i]};struct drm_i915_query q={.num_items=1,.items_ptr=(uint64_t)(uintptr_t)&item};errno=0;int rc=drmNmxIoctl(fd,DRM_IOCTL_I915_QUERY,&q);printf("QUERY id=%llu size rc=%d errno=%d length=%d\n",(unsigned long long)ids[i],rc,errno,item.length);
  if(rc==0&&item.length>0&&item.length<1048576) { void *data=calloc(1,item.length);if(!data)return 1;item.data_ptr=(uint64_t)(uintptr_t)data;errno=0;rc=drmNmxIoctl(fd,DRM_IOCTL_I915_QUERY,&q);printf("QUERY id=%llu data rc=%d errno=%d length=%d\n",(unsigned long long)ids[i],rc,errno,item.length);free(data); }
 }
 close(fd);return 0;
}
