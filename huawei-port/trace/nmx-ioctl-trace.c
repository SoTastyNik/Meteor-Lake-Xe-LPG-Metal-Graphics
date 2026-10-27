/*
 * nmx-ioctl-trace.dylib: logs every DRM ioctl a process sends through the port's libdrm (drmNmxIoctl) to stderr,
 * with the arguments that matter for a submission whose fence never signals: EXECBUFFER2 (context, engine flags,
 * fence array / timeline fence extension), SYNCOBJ create/wait/reset/signal/query (handles, flags, deadline against
 * the caller's CLOCK_MONOTONIC), GEM_WAIT and GEM_CONTEXT_CREATE.
 *   sudo bash -c 'DYLD_INSERT_LIBRARIES=/path/nmx-ioctl-trace.dylib exec ./latitude-vulkan-test check.spv'
 * Linked against libdrm's install name (/Library/GPUBundles/nvmtl/libdrm.2.dylib) so dyld can resolve the
 * interposed symbol before the Vulkan loader opens the ICD.
 */
#include <errno.h>
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <time.h>

extern int drmNmxIoctl(int fd, unsigned long request, void *arg);

static uint64_t mono_ns(void)
{
	struct timespec ts;
	clock_gettime(CLOCK_MONOTONIC, &ts);
	return (uint64_t)ts.tv_sec * 1000000000ull + (uint64_t)ts.tv_nsec;
}

struct execbuf2 {   /* struct drm_i915_gem_execbuffer2 */
	uint64_t buffers_ptr;
	uint32_t buffer_count, batch_start_offset, batch_len, DR1, DR4, num_cliprects;
	uint64_t cliprects_ptr, flags, rsvd1, rsvd2;
};
struct exec_fence { uint32_t handle, flags; };   /* I915_EXEC_FENCE_WAIT 1, SIGNAL 2 */
struct user_ext { uint64_t next; uint32_t name, flags, rsvd[4]; };
struct timeline_fences { struct user_ext base; uint64_t fence_count, handles_ptr, values_ptr; };
struct syncobj_wait { uint64_t handles; int64_t timeout_nsec; uint32_t count_handles, flags, first_signaled, pad;
                      uint64_t deadline_nsec; };
struct syncobj_timeline_wait { uint64_t handles, points; int64_t timeout_nsec; uint32_t count_handles, flags,
                               first_signaled, pad; uint64_t deadline_nsec; };
struct syncobj_create { uint32_t handle, flags; };
struct syncobj_array { uint64_t handles; uint32_t count_handles, pad; };
struct gem_wait { uint32_t bo_handle, flags; int64_t timeout_ns; };

#define EXEC_FENCE_ARRAY (1ull << 19)
#define EXEC_USE_EXTENSIONS (1ull << 21)
#define EXEC_FENCE_IN (1ull << 16)
#define EXEC_FENCE_OUT (1ull << 17)

static void before(unsigned nr, void *arg, uint64_t t)
{
	if ((nr == 0x40 + 0x29) && arg) {   /* DRM_I915_GEM_EXECBUFFER2(_WR) */
		const struct execbuf2 *e = arg;
		fprintf(stderr, "  execbuf ctx=%" PRIu64 " engine=%" PRIu64 " flags=0x%" PRIx64 " bos=%u batch_start=%u len=%u\n",
			e->rsvd1 & 0xffffffff, e->flags & 0x3f, e->flags, e->buffer_count, e->batch_start_offset, e->batch_len);
		if ((e->flags & EXEC_FENCE_ARRAY) && !(e->flags & EXEC_USE_EXTENSIONS)) {
			const struct exec_fence *f = (const void *)(uintptr_t)e->cliprects_ptr;
			for (uint32_t i = 0; f && i < e->num_cliprects && i < 16; i++)
				fprintf(stderr, "  fence[%u] syncobj=%u %s%s\n", i, f[i].handle, f[i].flags & 1 ? "WAIT " : "",
					f[i].flags & 2 ? "SIGNAL" : "");
		}
		if (e->flags & EXEC_USE_EXTENSIONS) {
			for (const struct user_ext *x = (const void *)(uintptr_t)e->cliprects_ptr; x;
			     x = (const void *)(uintptr_t)x->next) {
				fprintf(stderr, "  ext name=%u\n", x->name);
				if (x->name == 0) {   /* DRM_I915_GEM_EXECBUFFER_EXT_TIMELINE_FENCES */
					const struct timeline_fences *tf = (const void *)x;
					const struct exec_fence *h = (const void *)(uintptr_t)tf->handles_ptr;
					const uint64_t *v = (const void *)(uintptr_t)tf->values_ptr;
					for (uint64_t i = 0; h && i < tf->fence_count && i < 16; i++)
						fprintf(stderr, "  tfence[%" PRIu64 "] syncobj=%u point=%" PRIu64 " %s%s\n", i, h[i].handle,
							v ? v[i] : 0, h[i].flags & 1 ? "WAIT " : "", h[i].flags & 2 ? "SIGNAL" : "");
				}
			}
		}
		if (e->flags & (EXEC_FENCE_IN | EXEC_FENCE_OUT))
			fprintf(stderr, "  sync_file in=%d out-requested=%d\n", (e->flags & EXEC_FENCE_IN) ? (int)(e->rsvd2 & 0xffffffff) : -1,
				!!(e->flags & EXEC_FENCE_OUT));
	} else if (nr == 0xC3 && arg) {   /* DRM_IOCTL_SYNCOBJ_WAIT */
		const struct syncobj_wait *w = arg;
		const uint32_t *h = (const void *)(uintptr_t)w->handles;
		fprintf(stderr, "  syncobj_wait count=%u flags=0x%x first=%u timeout_abs=%" PRId64 " (now %" PRIu64 ", in %.3f s)\n",
			w->count_handles, w->flags, h && w->count_handles ? h[0] : 0, w->timeout_nsec, t,
			(double)(w->timeout_nsec - (int64_t)t) / 1e9);
	} else if (nr == 0xCA && arg) {   /* DRM_IOCTL_SYNCOBJ_TIMELINE_WAIT */
		const struct syncobj_timeline_wait *w = arg;
		const uint32_t *h = (const void *)(uintptr_t)w->handles;
		const uint64_t *p = (const void *)(uintptr_t)w->points;
		fprintf(stderr, "  timeline_wait count=%u flags=0x%x first=%u point=%" PRIu64 " timeout_abs=%" PRId64 " (in %.3f s)\n",
			w->count_handles, w->flags, h && w->count_handles ? h[0] : 0, p && w->count_handles ? p[0] : 0,
			w->timeout_nsec, (double)(w->timeout_nsec - (int64_t)t) / 1e9);
	} else if ((nr == 0xC4 || nr == 0xC5) && arg) {   /* SYNCOBJ_RESET / SIGNAL */
		const struct syncobj_array *a = arg;
		const uint32_t *h = (const void *)(uintptr_t)a->handles;
		fprintf(stderr, "  syncobj_%s count=%u first=%u\n", nr == 0xC4 ? "reset" : "signal", a->count_handles,
			h && a->count_handles ? h[0] : 0);
	} else if (nr == 0x40 + 0x2c && arg) {   /* DRM_I915_GEM_WAIT */
		const struct gem_wait *w = arg;
		fprintf(stderr, "  gem_wait bo=%u timeout=%" PRId64 "\n", w->bo_handle, w->timeout_ns);
	}
}

static void after(unsigned nr, void *arg)
{
	if (nr == 0xBF && arg) {   /* DRM_IOCTL_SYNCOBJ_CREATE */
		const struct syncobj_create *c = arg;
		fprintf(stderr, "  syncobj_create -> handle=%u flags=0x%x\n", c->handle, c->flags);
	} else if ((nr == 0xC3 || nr == 0xCA) && arg) {
		fprintf(stderr, "  first_signaled=%u\n", nr == 0xC3 ? ((const struct syncobj_wait *)arg)->first_signaled
								 : ((const struct syncobj_timeline_wait *)arg)->first_signaled);
	} else if (nr == 0x40 + 0x29 && arg) {
		const struct execbuf2 *e = arg;
		if (e->flags & EXEC_FENCE_OUT)
			fprintf(stderr, "  sync_file out=%d\n", (int)(e->rsvd2 >> 32));
	}
}

static int trace_ioctl(int fd, unsigned long request, void *arg)
{
	unsigned nr = request & 0xff, type = (request >> 8) & 0xff, size = (request >> 16) & 0x3fff;
	uint64_t t0 = mono_ns();
	fprintf(stderr, "[%.6f] fd=%d ioctl '%c' nr=0x%02x size=%u%s\n", t0 / 1e9, fd, type >= 32 && type < 127 ? type : '?',
		nr, size, type == 'd' ? "" : " (non-DRM)");
	if (type == 'd')
		before(nr, arg, t0);
	int rc = drmNmxIoctl(fd, request, arg), saved = errno;
	if (type == 'd' && rc == 0)
		after(nr, arg);
	fprintf(stderr, "  -> rc=%d errno=%d (%s) %.3f ms\n", rc, rc ? saved : 0, rc ? strerror(saved) : "ok",
		(mono_ns() - t0) / 1e6);
	errno = saved;
	return rc;
}

/* Mesa's vk_drm_syncobj goes through these libdrm helpers, whose ioctls stay inside libdrm and are not interposed */
extern int drmSyncobjCreate(int fd, uint32_t flags, uint32_t *handle);
extern int drmSyncobjWait(int fd, uint32_t *handles, unsigned num, int64_t timeout_nsec, unsigned flags,
			  uint32_t *first_signaled);
extern int drmSyncobjTimelineWait(int fd, uint32_t *handles, uint64_t *points, unsigned num, int64_t timeout_nsec,
				  unsigned flags, uint32_t *first_signaled);
extern int drmSyncobjReset(int fd, const uint32_t *handles, uint32_t count);
extern int drmSyncobjSignal(int fd, const uint32_t *handles, uint32_t count);
extern int drmSyncobjTimelineSignal(int fd, const uint32_t *handles, uint64_t *points, uint32_t count);
extern int drmSyncobjQuery2(int fd, uint32_t *handles, uint64_t *points, uint32_t count, uint32_t flags);

#define RESULT(rc, t0) fprintf(stderr, "  -> rc=%d errno=%d %.3f ms\n", rc, rc ? errno : 0, (mono_ns() - (t0)) / 1e6)

static int t_create(int fd, uint32_t flags, uint32_t *handle)
{
	uint64_t t0 = mono_ns();
	int rc = drmSyncobjCreate(fd, flags, handle), e = errno;
	fprintf(stderr, "[%.6f] drmSyncobjCreate flags=0x%x -> handle=%u\n", t0 / 1e9, flags, handle ? *handle : 0);
	errno = e; RESULT(rc, t0); errno = e;
	return rc;
}

static int t_wait(int fd, uint32_t *h, unsigned n, int64_t timeout, unsigned flags, uint32_t *first)
{
	uint64_t t0 = mono_ns();
	fprintf(stderr, "[%.6f] drmSyncobjWait n=%u first=%u flags=0x%x timeout_abs=%" PRId64 " (in %.3f s)\n", t0 / 1e9, n,
		n ? h[0] : 0, flags, timeout, (double)(timeout - (int64_t)t0) / 1e9);
	int rc = drmSyncobjWait(fd, h, n, timeout, flags, first), e = errno;
	errno = e; RESULT(rc, t0); errno = e;
	return rc;
}

static int t_twait(int fd, uint32_t *h, uint64_t *p, unsigned n, int64_t timeout, unsigned flags, uint32_t *first)
{
	uint64_t t0 = mono_ns();
	fprintf(stderr, "[%.6f] drmSyncobjTimelineWait n=%u first=%u point=%" PRIu64 " flags=0x%x timeout_abs=%" PRId64
		" (in %.3f s)\n", t0 / 1e9, n, n ? h[0] : 0, n && p ? p[0] : 0, flags, timeout,
		(double)(timeout - (int64_t)t0) / 1e9);
	int rc = drmSyncobjTimelineWait(fd, h, p, n, timeout, flags, first), e = errno;
	errno = e; RESULT(rc, t0); errno = e;
	return rc;
}

static int t_reset(int fd, const uint32_t *h, uint32_t n)
{
	uint64_t t0 = mono_ns();
	fprintf(stderr, "[%.6f] drmSyncobjReset n=%u first=%u\n", t0 / 1e9, n, n ? h[0] : 0);
	int rc = drmSyncobjReset(fd, h, n), e = errno;
	errno = e; RESULT(rc, t0); errno = e;
	return rc;
}

static int t_signal(int fd, const uint32_t *h, uint32_t n)
{
	uint64_t t0 = mono_ns();
	fprintf(stderr, "[%.6f] drmSyncobjSignal n=%u first=%u\n", t0 / 1e9, n, n ? h[0] : 0);
	int rc = drmSyncobjSignal(fd, h, n), e = errno;
	errno = e; RESULT(rc, t0); errno = e;
	return rc;
}

static int t_tsignal(int fd, const uint32_t *h, uint64_t *p, uint32_t n)
{
	uint64_t t0 = mono_ns();
	fprintf(stderr, "[%.6f] drmSyncobjTimelineSignal n=%u first=%u point=%" PRIu64 "\n", t0 / 1e9, n, n ? h[0] : 0,
		n && p ? p[0] : 0);
	int rc = drmSyncobjTimelineSignal(fd, h, p, n), e = errno;
	errno = e; RESULT(rc, t0); errno = e;
	return rc;
}

static int t_query2(int fd, uint32_t *h, uint64_t *p, uint32_t n, uint32_t flags)
{
	uint64_t t0 = mono_ns();
	int rc = drmSyncobjQuery2(fd, h, p, n, flags), e = errno;
	fprintf(stderr, "[%.6f] drmSyncobjQuery2 n=%u first=%u flags=0x%x -> point=%" PRIu64 "\n", t0 / 1e9, n, n ? h[0] : 0,
		flags, n && p ? p[0] : 0);
	errno = e; RESULT(rc, t0); errno = e;
	return rc;
}

#define INTERPOSE(rep, orig) { (const void *)(rep), (const void *)(orig) }
__attribute__((used)) static const struct { const void *replacement, *replacee; } interposers[]
	__attribute__((section("__DATA,__interpose"))) = {
	INTERPOSE(trace_ioctl, drmNmxIoctl), INTERPOSE(t_create, drmSyncobjCreate), INTERPOSE(t_wait, drmSyncobjWait),
	INTERPOSE(t_twait, drmSyncobjTimelineWait), INTERPOSE(t_reset, drmSyncobjReset), INTERPOSE(t_signal, drmSyncobjSignal),
	INTERPOSE(t_tsignal, drmSyncobjTimelineSignal), INTERPOSE(t_query2, drmSyncobjQuery2),
};
