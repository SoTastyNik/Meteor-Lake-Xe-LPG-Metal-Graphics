/*
 * IOSurface device caches for the surfaces the GPU writes (NMX_DRM_IOCTL_SURF_SYNC).
 *
 * On a Mac the GPU driver tells IOSurface that it holds a newer copy of a surface (an IOSurfaceDeviceCache made current),
 * and every CPU lock of that surface, in any process, first calls the driver's control function (op 0, in the locking
 * thread with the surface lock dropped), which waits until the GPU's writes have landed in the pages. Here each process
 * imports a surface's pages on its own and nothing orders a reader after the writer: a capture client or an encoder read
 * a 420v frame before the writer's copy-out (a screen share the other side never saw, a Photo Booth photo with no
 * chroma), and v56 tried to cover it by delaying "scheduled", which deadlocked WindowServer.
 *
 * The Metal plugin numbers each write: PENDING when it commits a command buffer that writes the surface (the device cache
 * is made current), DONE once that write is in the pages. The v60 probe found the calls present in macOS 15.8.2 and
 * 1306 of 2035 CPU locks coming before their write landed (OBS read each frame it drew too early; a Photo Booth photo
 * held half a frame). v61: such a lock waits for the writes committed before it, NMX_SS_WAIT_MS at most, unless the
 * plugin asked for the probe only (PENDING's flags) or the locking thread is the one copying that write out (PUBLISH:
 * the plugin's own lock for the copy-out must not wait for itself). IOSurface functions are weak links: a missing one
 * turns the ioctl off, it does not fail the load. Records are found by the cache pointer, not through IOSurface's private
 * layout. Ported in spirit from ArrowWhatever's page-off (patches/0024, Xe-LPG on macOS 26) and Apple's IOAccelerator
 * device-cache model.
 */
#include <sys/types.h>
#include <sys/errno.h>
#include <sys/proc.h>
#include <kern/task.h>
#include <kern/thread.h>
#include <kern/clock.h>
#include <mach/mach_time.h>
#include <string.h>
#include <IOKit/IOLib.h>
#include <IOKit/IOLocks.h>
#include <IOKit/IOService.h>
#include <IOKit/IORegistryEntry.h>
#include <libkern/OSAtomic.h>
#include <libkern/OSKextLib.h>
#include "nmx_xnu.h"

extern "C" {
void *_ZN13IOSurfaceRoot13lookupSurfaceEjP4task(void *root, unsigned int id, task_t task) __attribute__((weak_import));
void *_ZN9IOSurface25deviceCacheForAcceleratorEPvjj(void *surface, void *key, unsigned int accelId, unsigned int plane)
    __attribute__((weak_import));
void _ZN20IOSurfaceDeviceCache14setControlFuncEPvPFvS0_PS_jyyE(
    void *cache, void *ctx, void (*fn)(void *, void *, unsigned int, unsigned long long, unsigned long long)) __attribute__((weak_import));
void _ZN20IOSurfaceDeviceCache10setCurrentEv(void *cache) __attribute__((weak_import));
}

/* a weak function is resolved when its address is not gOSKextUnresolved (OSKextSymbolIsResolved, cast for C++) */
#define NMX_WEAK_OK(fn) ((const void *)(uintptr_t)&(fn) != gOSKextUnresolved)
#define NMX_SS_ACCEL_ID 0x4e4d5853u     /* 'NMXS'; not 0, a CPU lock passes 0 as its own owner */
#define NMX_SS_N 32
#define NMX_SS_WAIT_MS 150              /* a CPU lock waits at most this long for the writes before it */
#define NMX_SS_STALE_NS 2000000000ull   /* a record idle this long may be reused even with a write never marked done */

struct nmx_ss_rec {
    unsigned int id;
    void *surf;             /* not retained by us (the cache retains it) */
    void *cache;            /* +1, ours */
    uint64_t pending, done; /* write numbers: the last PENDING handed out, the highest DONE */
    uint64_t last;          /* mach_absolute_time of the last PENDING or DONE */
    void *publisher;        /* the thread copying a write of this surface out (PUBLISH), whose own lock does not wait */
    uint32_t wait;          /* the last PENDING asked for waits (0: probe only) */
};
static nmx_ss_rec g_ss[NMX_SS_N];
static IOLock *g_ss_lock;
static IORegistryEntry *g_ss_key;   /* the caches' key: an OSObject of ours, not an accelerator (the family keys its own) */
static void *g_ss_root;
static int g_ss_state;              /* 0 not tried, 1 on, -1 off (an IOSurface function is missing) */
static SInt64 g_ss_ops[8], g_ss_pend, g_ss_done, g_ss_attach, g_ss_evict, g_ss_nosurf, g_ss_late, g_ss_inorder, g_ss_foreign;
static SInt64 g_ss_logged;
static SInt64 g_ss_waits, g_ss_timeouts, g_ss_selfpass, g_ss_wait_us_sum, g_ss_wait_us_max, g_ss_wspass;

static bool nmx_ss_init(void)
{
    if (g_ss_state)
        return g_ss_state > 0;
    const bool have = NMX_WEAK_OK(_ZN13IOSurfaceRoot13lookupSurfaceEjP4task) &&
                      NMX_WEAK_OK(_ZN9IOSurface25deviceCacheForAcceleratorEPvjj) &&
                      NMX_WEAK_OK(_ZN20IOSurfaceDeviceCache14setControlFuncEPvPFvS0_PS_jyyE) &&
                      NMX_WEAK_OK(_ZN20IOSurfaceDeviceCache10setCurrentEv);
    if (!have) {
        IOLog("NullMoth GPU: surfsync: OFF - IOSurface lacks%s%s%s%s\n",
              NMX_WEAK_OK(_ZN13IOSurfaceRoot13lookupSurfaceEjP4task) ? "" : " lookupSurface",
              NMX_WEAK_OK(_ZN9IOSurface25deviceCacheForAcceleratorEPvjj) ? "" : " deviceCacheForAccelerator",
              NMX_WEAK_OK(_ZN20IOSurfaceDeviceCache14setControlFuncEPvPFvS0_PS_jyyE) ? "" : " setControlFunc",
              NMX_WEAK_OK(_ZN20IOSurfaceDeviceCache10setCurrentEv) ? "" : " setCurrent");
        g_ss_state = -1;
        return false;
    }
    IOLock *l = IOLockAlloc();
    IORegistryEntry *k = OSTypeAlloc(IORegistryEntry);
    OSDictionary *m = IOService::serviceMatching("IOSurfaceRoot");
    IOService *root = m ? IOService::waitForMatchingService(m, 2ULL * 1000 * 1000 * 1000) : nullptr;
    if (m)
        m->release();
    if (!l || !k || !k->init() || !root) {
        IOLog("NullMoth GPU: surfsync: OFF - %s\n", !root ? "no IOSurfaceRoot" : "out of memory");
        if (l) IOLockFree(l);
        if (k) k->release();
        if (root) root->release();
        g_ss_state = -1;
        return false;
    }
    g_ss_lock = l; g_ss_key = k; g_ss_root = root;   /* kept for the kext's life */
    g_ss_state = 1;
    IOLog("NullMoth GPU: surfsync: ON (a CPU lock waits up to %d ms for the GPU's writes before it, unless the plugin asks for the probe)\n",
          NMX_SS_WAIT_MS);
    return true;
}

static nmx_ss_rec *nmx_ss_find_cache_locked(void *cache)
{
    for (unsigned i = 0; i < NMX_SS_N; i++)
        if (g_ss[i].cache == cache)
            return &g_ss[i];
    return nullptr;
}

/*
 * IOSurface's call for a CPU lock (op 0 sync, 2 wait, 3 end of sync, 4/5 cache life, per ArrowWhatever's notes), in
 * the locking thread with the surface lock dropped. The probe holds nothing: it counts and logs.
 */
static void nmx_ss_control(void *key, void *cache, unsigned int op, unsigned long long a, unsigned long long b)
{
    OSIncrementAtomic64(&g_ss_ops[op < 7 ? op : 7]);
    if (!cache || !g_ss_lock)
        return;
    if (key != g_ss_key)
        OSIncrementAtomic64(&g_ss_foreign);
    if (op != 0)
        return;
    const uint64_t t0 = mach_absolute_time();
    unsigned int id = 0;
    uint64_t target = 0, done0 = 0;
    bool found = false, self = false, waited = false, timedout = false, ws = false;
    IOLockLock(g_ss_lock);
    nmx_ss_rec *r = nmx_ss_find_cache_locked(cache);
    if (r) {
        found = true;
        id = r->id; target = r->pending; done0 = r->done;
        self = r->publisher && r->publisher == (void *)current_thread();
        if (done0 < target && r->wait && !self) {
            /* WindowServer's own locks are not held: it composites, and a lock held there is a dropped frame (v62 orders
               its reads another way) */
            char nm[32] = { 0 };
            proc_selfname(nm, sizeof nm);
            ws = strncmp(nm, "WindowServer", sizeof nm) == 0;
        }
        if (done0 < target && r->wait && !self && !ws) {
            uint64_t deadline = 0;
            clock_interval_to_deadline(NMX_SS_WAIT_MS, kMillisecondScale, &deadline);
            waited = true;
            while (r->cache == cache && r->done < target) {
                if (IOLockSleepDeadline(g_ss_lock, &r->done, deadline, THREAD_UNINT) == THREAD_TIMED_OUT) {
                    timedout = r->cache == cache && r->done < target;
                    break;
                }
            }
        }
    }
    IOLockUnlock(g_ss_lock);
    if (!found)
        return;
    const bool late = done0 < target;
    OSIncrementAtomic64(late ? &g_ss_late : &g_ss_inorder);
    if (self && late)
        OSIncrementAtomic64(&g_ss_selfpass);
    if (ws && late)
        OSIncrementAtomic64(&g_ss_wspass);
    SInt64 us = 0;
    if (waited) {
        uint64_t ns = 0;
        absolutetime_to_nanoseconds(mach_absolute_time() - t0, &ns);
        us = (SInt64)(ns / 1000);
        OSIncrementAtomic64(timedout ? &g_ss_timeouts : &g_ss_waits);
        OSAddAtomic64(us, &g_ss_wait_us_sum);
        if (us > g_ss_wait_us_max)
            g_ss_wait_us_max = us;
    }
    if (late && (OSIncrementAtomic64(&g_ss_logged) < 48 || (timedout && g_ss_timeouts <= 16))) {
        char nm[32] = { 0 };
        proc_selfname(nm, sizeof nm);
        IOLog("NullMoth GPU: surfsync: CPU lock of surface %u by %s[%d] came with write %llu of %llu done: %s%lld us (key %s, a 0x%llx b 0x%llx)\n",
              id, nm, proc_selfpid(), (unsigned long long)done0, (unsigned long long)target,
              self ? "its own copy-out, not held " : ws ? "WindowServer, not held " : !waited ? "probe, not held " :
              timedout ? "TIMED OUT after " : "waited ",
              (long long)us, key == g_ss_key ? "ours" : "OTHER", a, b);
    }
}

static void nmx_ss_summary(void)
{
    const SInt64 n = g_ss_pend;
    if (n == 16 || (n > 0 && (n & 4095) == 0))
        IOLog("NullMoth GPU: surfsync: %lld writes, %lld done, %lld caches made, %lld dropped, %lld no surface; CPU locks %lld "
              "before their write landed (%lld waited, %lld timed out, %lld copy-outs and %lld WindowServer locks passed; wait avg %lld us max %lld us), %lld after; "
              "control ops 0:%lld 2:%lld 3:%lld 4:%lld 5:%lld other:%lld, foreign key %lld\n",
              (long long)n, (long long)g_ss_done, (long long)g_ss_attach, (long long)g_ss_evict, (long long)g_ss_nosurf,
              (long long)g_ss_late, (long long)g_ss_waits, (long long)g_ss_timeouts, (long long)g_ss_selfpass, (long long)g_ss_wspass,
              (long long)(g_ss_waits + g_ss_timeouts ? g_ss_wait_us_sum / (g_ss_waits + g_ss_timeouts) : 0), (long long)g_ss_wait_us_max,
              (long long)g_ss_inorder, (long long)g_ss_ops[0], (long long)g_ss_ops[2], (long long)g_ss_ops[3],
              (long long)g_ss_ops[4], (long long)g_ss_ops[5], (long long)(g_ss_ops[1] + g_ss_ops[6] + g_ss_ops[7]),
              (long long)g_ss_foreign);
}

/* PENDING: a write into surface 'id' (looked up in the caller's task) gets the next number; its cache is made current */
static int nmx_ss_pending(unsigned int id, uint64_t *seq, uint32_t wait)
{
    void *surf = _ZN13IOSurfaceRoot13lookupSurfaceEjP4task(g_ss_root, id, current_task());   /* +1 */
    if (!surf) {
        OSIncrementAtomic64(&g_ss_nosurf);
        return ENOENT;
    }
    void *drop = nullptr, *cache = nullptr;
    const uint64_t now = mach_absolute_time();
    IOLockLock(g_ss_lock);
    nmx_ss_rec *r = nullptr;
    for (unsigned i = 0; i < NMX_SS_N && !r; i++)
        if (g_ss[i].id == id && g_ss[i].surf == surf)
            r = &g_ss[i];
    if (!r) {
        /* a free record, else the one idle longest whose writes have all landed */
        nmx_ss_rec *idle = nullptr;
        for (unsigned i = 0; i < NMX_SS_N && !r; i++) {
            if (!g_ss[i].cache) r = &g_ss[i];
            else {
                uint64_t idle_ns = 0;
                absolutetime_to_nanoseconds(now - g_ss[i].last, &idle_ns);
                const bool reusable = g_ss[i].id == id || g_ss[i].done >= g_ss[i].pending || idle_ns > NMX_SS_STALE_NS;
                if (reusable && (!idle || g_ss[i].last < idle->last)) idle = &g_ss[i];
            }
        }
        if (!r && idle) {
            drop = idle->cache;
            IOLockWakeup(g_ss_lock, &idle->done, false);   /* a lock still waiting on it sees the cache gone */
            bzero(idle, sizeof *idle);
            r = idle;
            OSIncrementAtomic64(&g_ss_evict);
        }
        if (r) {
            void *c = _ZN9IOSurface25deviceCacheForAcceleratorEPvjj(surf, g_ss_key, NMX_SS_ACCEL_ID, 0);   /* +1, ours */
            if (c) {
                r->id = id; r->surf = surf; r->cache = c; r->pending = r->done = 0;
                _ZN20IOSurfaceDeviceCache14setControlFuncEPvPFvS0_PS_jyyE(c, r, nmx_ss_control);
                OSIncrementAtomic64(&g_ss_attach);
            } else {
                r = nullptr;
            }
        }
    }
    if (r) {
        *seq = ++r->pending;
        r->last = now;
        r->wait = wait;
        cache = r->cache;
        ((OSObject *)cache)->retain();
    }
    IOLockUnlock(g_ss_lock);
    if (drop)
        ((OSObject *)drop)->release();
    if (cache) {
        _ZN20IOSurfaceDeviceCache10setCurrentEv(cache);
        ((OSObject *)cache)->release();
    }
    ((OSObject *)surf)->release();
    if (!cache)
        return ENOSPC;
    OSIncrementAtomic64(&g_ss_pend);
    nmx_ss_summary();
    return 0;
}

/* PUBLISH: the calling thread is about to copy a write of surface 'id' out; its own CPU lock must not wait (until DONE) */
static int nmx_ss_publish(unsigned int id)
{
    IOLockLock(g_ss_lock);
    for (unsigned i = 0; i < NMX_SS_N; i++)
        if (g_ss[i].id == id && g_ss[i].cache)
            g_ss[i].publisher = (void *)current_thread();
    IOLockUnlock(g_ss_lock);
    return 0;
}

/* DONE: write 'seq' of surface 'id' is in the pages */
static int nmx_ss_done(unsigned int id, uint64_t seq)
{
    IOLockLock(g_ss_lock);
    for (unsigned i = 0; i < NMX_SS_N; i++) {
        nmx_ss_rec *r = &g_ss[i];
        if (r->id != id || !r->cache)
            continue;
        if (seq > r->done && seq <= r->pending)
            r->done = seq;
        if (r->publisher == (void *)current_thread())
            r->publisher = nullptr;
        r->last = mach_absolute_time();
        IOLockWakeup(g_ss_lock, &r->done, false);
    }
    IOLockUnlock(g_ss_lock);
    OSIncrementAtomic64(&g_ss_done);
    return 0;
}

extern "C" int nmx_xnu_surf_sync(uint32_t surface, uint32_t op, uint64_t *seq, uint64_t *stats, uint32_t nstats)
{
    if (!nmx_ss_init())
        return ENOTSUP;
    switch (op) {
    case 1: {
        const uint32_t wait = nstats ? (uint32_t)(stats[0] & 1) : 0;   /* PENDING's flags: bit 0 = readers wait */
        *seq = 0;
        return nmx_ss_pending(surface, seq, wait);
    }
    case 2:
        return nmx_ss_done(surface, *seq);
    case 4:
        return nmx_ss_publish(surface);
    case 3: {
        const SInt64 v[6] = { g_ss_pend, g_ss_done, g_ss_late, g_ss_inorder, g_ss_waits, g_ss_timeouts };
        for (uint32_t i = 0; i < nstats && i < 6; i++)
            stats[i] = (uint64_t)v[i];
        return 0;
    }
    }
    return EINVAL;
}
