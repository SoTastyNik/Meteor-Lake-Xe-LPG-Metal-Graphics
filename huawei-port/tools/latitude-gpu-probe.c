/*
 * latitude-gpu-probe: the smallest i915 submission, without Mesa. A 4 KiB buffer holding MI_BATCH_BUFFER_END is
 * executed on the render and copy engines of the default context and waited on for 5 s each; then the driver state
 * dump (NMX_DRM_IOCTL_DEBUG_DUMP: GT, GuC load/CT/submission state, intel_engine_dump of every engine) is requested,
 * which lands in the kernel log as "i915 dump:" lines. Run as root after the GPU driver has attached.
 */
#include <xf86drm.h>
#include <i915_drm.h>
#include <errno.h>
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <time.h>
#include <unistd.h>

/* drmNmxOpen and drmNmxIoctl come from the port's xf86drm.h; the map helpers are not declared there */
extern void *drmNmxMmap(size_t, int, int, int, off_t);
extern int drmNmxMunmap(void *, size_t);

#define NMX_DRM_IOCTL_DEBUG_DUMP _IO('N', 0x44)   /* bsdcompat/include/nmx_drm_uapi.h */
#define MI_BATCH_BUFFER_END (0x0Au << 23)

static double now(void)
{
	struct timespec ts;
	clock_gettime(CLOCK_MONOTONIC, &ts);
	return ts.tv_sec + ts.tv_nsec / 1e9;
}

static int submit(int fd, uint32_t handle, uint64_t engine, const char *name)
{
	struct drm_i915_gem_exec_object2 obj = { .handle = handle };
	struct drm_i915_gem_execbuffer2 eb = {
		.buffers_ptr = (uintptr_t)&obj, .buffer_count = 1, .batch_len = 8, .flags = engine,
	};
	errno = 0;
	double t0 = now();
	int rc = drmNmxIoctl(fd, DRM_IOCTL_I915_GEM_EXECBUFFER2, &eb), saved = errno;
	printf("EXECBUFFER2 %s rc=%d errno=%d (%s) bo_offset=0x%llx\n", name, rc, saved, strerror(saved),
	       (unsigned long long)obj.offset);
	if (rc)
		return rc;
	struct drm_i915_gem_wait w = { .bo_handle = handle, .timeout_ns = 5000000000ll };
	errno = 0;
	rc = drmNmxIoctl(fd, DRM_IOCTL_I915_GEM_WAIT, &w);
	saved = errno;
	printf("GEM_WAIT %s rc=%d errno=%d (%s) after %.3f s\n", name, rc, saved, strerror(saved), now() - t0);
	struct drm_i915_gem_busy busy = { .handle = handle };
	rc = drmNmxIoctl(fd, DRM_IOCTL_I915_GEM_BUSY, &busy);
	printf("GEM_BUSY %s rc=%d busy=0x%x\n", name, rc, busy.busy);
	return 0;
}

int main(void)
{
	setbuf(stdout, NULL);
	int fd = drmNmxOpen("/dev/dri/renderD128", O_RDWR | O_CLOEXEC);
	if (fd < 0) {
		printf("DRM open failed: %s\n", strerror(errno));
		return 1;
	}
	struct drm_i915_gem_create create = { .size = 4096 };
	int rc = drmNmxIoctl(fd, DRM_IOCTL_I915_GEM_CREATE, &create);
	printf("GEM_CREATE rc=%d errno=%d handle=%u\n", rc, rc ? errno : 0, create.handle);
	if (rc)
		return 1;
	/* GEM pwrite is gone from Meteor Lake (graphics IP 12.70): write the batch through a write-combined mapping */
	struct drm_i915_gem_mmap_offset mo = { .handle = create.handle, .flags = I915_MMAP_OFFSET_WC };
	rc = drmNmxIoctl(fd, DRM_IOCTL_I915_GEM_MMAP_OFFSET, &mo);
	printf("MMAP_OFFSET WC rc=%d errno=%d offset=0x%llx\n", rc, rc ? errno : 0, (unsigned long long)mo.offset);
	if (rc)
		return 1;
	volatile uint32_t *batch = drmNmxMmap(4096, PROT_READ | PROT_WRITE, MAP_SHARED, fd, (off_t)mo.offset);
	if (batch == MAP_FAILED) {
		printf("NMX_MAP failed: %s\n", strerror(errno));
		return 1;
	}
	batch[0] = MI_BATCH_BUFFER_END;
	batch[1] = 0;   /* MI_NOOP */
	printf("batch written: 0x%08x 0x%08x\n", batch[0], batch[1]);
	drmNmxMunmap((void *)batch, 4096);

	submit(fd, create.handle, I915_EXEC_RENDER, "render");
	submit(fd, create.handle, I915_EXEC_BLT, "copy");

	errno = 0;
	rc = drmNmxIoctl(fd, NMX_DRM_IOCTL_DEBUG_DUMP, NULL);
	printf("DEBUG_DUMP rc=%d errno=%d (%s): see the kernel log, lines \"i915 dump:\"\n", rc, rc ? errno : 0,
	       rc ? strerror(errno) : "ok");
	struct drm_gem_close close_bo = { .handle = create.handle };
	drmNmxIoctl(fd, DRM_IOCTL_GEM_CLOSE, &close_bo);
	close(fd);
	return 0;
}
