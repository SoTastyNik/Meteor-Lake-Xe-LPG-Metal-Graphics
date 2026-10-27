/*
 * latitude-gpu-probe: the smallest i915 submission, without Mesa. A 4 KiB buffer holding MI_BATCH_BUFFER_END is
 * executed on the render and copy engines of the default context and waited on for 5 s each; then the driver state
 * dump (NMX_DRM_IOCTL_DEBUG_DUMP: GT, GuC load/CT/submission state, intel_engine_dump of every engine) is requested,
 * which lands in the kernel log as "i915 dump:" lines. Run as root after the GPU driver has attached.
 * With --dump it only requests the state dump (collect.sh takes one while the Vulkan test is waiting).
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

/*
 * Spinner experiment: a batch that loops on the GPU (MI_ARB_CHECK; MI_BATCH_BUFFER_START back to itself) until the
 * CPU overwrites its first dword with MI_BATCH_BUFFER_END 300 ms later, so the work is certainly still running
 * when the wait starts. Waited on by GEM_WAIT (relative timeout, reference) and by drmSyncobjWait with a deadline
 * of user CLOCK_MONOTONIC + 8 s: ~0.3 s = deadlines and wake-ups work, ~0 s ETIME = the kernel clock still differs
 * from user space's, ~8 s = the fence signals but the syncobj waiter is never woken.
 */
#include <pthread.h>

#define MI_ARB_CHECK (0x05u << 23)
#define MI_BATCH_BUFFER_START_PPGTT ((0x31u << 23) | (1u << 8) | 1u)
#define SPIN_ADDR 0x100000ull

struct spinner { volatile uint32_t *map; uint32_t handle; };

static void *stop_later(void *arg)
{
	struct spinner *s = arg;
	usleep(300000);
	s->map[0] = MI_BATCH_BUFFER_END;
	__sync_synchronize();
	return NULL;
}

static int spinner_start(int fd, struct spinner *s, uint32_t syncobj)
{
	struct drm_i915_gem_create create = { .size = 4096 };
	if (drmNmxIoctl(fd, DRM_IOCTL_I915_GEM_CREATE, &create))
		return -1;
	struct drm_i915_gem_mmap_offset mo = { .handle = create.handle, .flags = I915_MMAP_OFFSET_WC };
	if (drmNmxIoctl(fd, DRM_IOCTL_I915_GEM_MMAP_OFFSET, &mo))
		return -1;
	s->map = drmNmxMmap(4096, PROT_READ | PROT_WRITE, MAP_SHARED, fd, (off_t)mo.offset);
	if (s->map == MAP_FAILED)
		return -1;
	s->handle = create.handle;
	s->map[0] = MI_ARB_CHECK;
	s->map[1] = MI_BATCH_BUFFER_START_PPGTT;
	s->map[2] = (uint32_t)SPIN_ADDR;
	s->map[3] = (uint32_t)(SPIN_ADDR >> 32);
	s->map[4] = MI_BATCH_BUFFER_END;
	__sync_synchronize();
	struct drm_i915_gem_exec_object2 obj = { .handle = create.handle, .offset = SPIN_ADDR,
		.flags = EXEC_OBJECT_PINNED | EXEC_OBJECT_SUPPORTS_48B_ADDRESS };
	struct drm_i915_gem_exec_fence fence = { .handle = syncobj, .flags = I915_EXEC_FENCE_SIGNAL };
	struct drm_i915_gem_execbuffer2 eb = { .buffers_ptr = (uintptr_t)&obj, .buffer_count = 1, .batch_len = 24,
		.flags = I915_EXEC_RENDER | (syncobj ? I915_EXEC_FENCE_ARRAY : 0) };
	if (syncobj) {
		eb.cliprects_ptr = (uintptr_t)&fence;
		eb.num_cliprects = 1;
	}
	int rc = drmNmxIoctl(fd, DRM_IOCTL_I915_GEM_EXECBUFFER2, &eb);
	printf("  spinner execbuf rc=%d errno=%d offset=0x%llx\n", rc, rc ? errno : 0, (unsigned long long)obj.offset);
	return rc;
}

static void spinner_end(int fd, struct spinner *s)
{
	drmNmxMunmap((void *)s->map, 4096);
	struct drm_gem_close c = { .handle = s->handle };
	drmNmxIoctl(fd, DRM_IOCTL_GEM_CLOSE, &c);
}

static void spin_gem_wait(int fd)
{
	struct spinner s;
	pthread_t t;
	printf("SPIN + GEM_WAIT (relative 3 s):\n");
	if (spinner_start(fd, &s, 0))
		return;
	double t0 = now();
	pthread_create(&t, NULL, stop_later, &s);
	struct drm_i915_gem_wait w = { .bo_handle = s.handle, .timeout_ns = 3000000000ll };
	int rc = drmNmxIoctl(fd, DRM_IOCTL_I915_GEM_WAIT, &w), saved = errno;
	printf("  GEM_WAIT rc=%d errno=%d after %.3f s (expect ~0.3)\n", rc, rc ? saved : 0, now() - t0);
	pthread_join(t, NULL);
	spinner_end(fd, &s);
}

static void spin_syncobj_wait(int fd, int run)
{
	struct spinner s;
	pthread_t t;
	uint32_t so = 0;
	printf("SPIN + drmSyncobjWait (deadline user CLOCK_MONOTONIC + 8 s), run %d:\n", run);
	if (drmSyncobjCreate(fd, 0, &so)) {
		printf("  drmSyncobjCreate failed errno=%d\n", errno);
		return;
	}
	if (spinner_start(fd, &s, so) == 0) {
		double t0 = now();
		pthread_create(&t, NULL, stop_later, &s);
		struct timespec ts;
		clock_gettime(CLOCK_MONOTONIC, &ts);
		int64_t deadline = (int64_t)ts.tv_sec * 1000000000ll + ts.tv_nsec + 8000000000ll;
		uint32_t first = 0;
		int rc = drmSyncobjWait(fd, &so, 1, deadline, DRM_SYNCOBJ_WAIT_FLAGS_WAIT_ALL, &first), saved = errno;
		printf("  drmSyncobjWait rc=%d errno=%d after %.3f s (0.3 = OK, ~0 + ETIME = clock, ~8 = lost wake-up)\n",
		       rc, rc ? saved : 0, now() - t0);
		pthread_join(t, NULL);
		struct drm_i915_gem_wait w = { .bo_handle = s.handle, .timeout_ns = 3000000000ll };
		drmNmxIoctl(fd, DRM_IOCTL_I915_GEM_WAIT, &w);   /* make sure the spinner is gone before the next run */
		spinner_end(fd, &s);
	}
	drmSyncobjDestroy(fd, so);
}

static int dump(int fd)
{
	struct timespec ts;
	clock_gettime(CLOCK_MONOTONIC, &ts);
	printf("user CLOCK_MONOTONIC just before the dump: %lld ns\n", (long long)ts.tv_sec * 1000000000ll + ts.tv_nsec);
	errno = 0;
	int rc = drmNmxIoctl(fd, NMX_DRM_IOCTL_DEBUG_DUMP, NULL);
	printf("DEBUG_DUMP rc=%d errno=%d (%s): see the kernel log, lines \"i915 dump:\"\n", rc, rc ? errno : 0,
	       rc ? strerror(errno) : "ok");
	return rc;
}

int main(int argc, char **argv)
{
	setbuf(stdout, NULL);
	int fd = drmNmxOpen("/dev/dri/renderD128", O_RDWR | O_CLOEXEC);
	if (fd < 0) {
		printf("DRM open failed: %s\n", strerror(errno));
		return 1;
	}
	/* --dump: only the state dump, taken while another client's submission is stuck */
	if (argc > 1 && !strcmp(argv[1], "--dump")) {
		int rc = dump(fd);
		close(fd);
		return rc ? 1 : 0;
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

	spin_gem_wait(fd);
	spin_syncobj_wait(fd, 1);
	spin_syncobj_wait(fd, 2);

	dump(fd);
	struct drm_gem_close close_bo = { .handle = create.handle };
	drmNmxIoctl(fd, DRM_IOCTL_GEM_CLOSE, &close_bo);
	close(fd);
	return 0;
}
