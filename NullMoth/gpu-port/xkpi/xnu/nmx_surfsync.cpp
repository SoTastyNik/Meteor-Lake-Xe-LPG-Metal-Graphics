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
 * is made current), DONE once that write is in the pages. v60 is the probe: the control function only counts how often a
 * CPU lock came while a write was still pending (what a wait would have covered), and the kernel log says whether the
 * IOSurface functions exist in this macOS at all (weak links: a missing one turns the ioctl off, it does not fail the
 * load). Records are found by the cache pointer, not through IOSurface's private layout. Ported in spirit from
 * ArrowWhatever's page-off (patches/0024, Xe-LPG on macOS 26) and Apple's IOAccelerator device-cache model.
 */
#include <sys/types.h>
#include <sys/errno.h>
#include <sys/proc.h>
#include <kern/task.h>
#include <mach/mach_time.h>
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

struct nmx_ss_rec {
    unsigned int id;
    void *surf;             /* not retained by us (the cache retains it) */
    void *cache;            /* +1, ours */
    uint64_t pending, done; /* write numbers: the last PENDING handed out, the highest DONE */
    uint64_t last;          /* mach_absolute_time of the last PENDING or DONE */
};
static nmx_ss_rec g_ss[NMX_SS_N];
static IOLock *g_ss_lock;
static IORegistryEntry *g_ss_key;   /* the caches' key: an OSObject of ours, not an accelerator (the family keys its own) */
static void *g_ss_root;
static int g_ss_state;              /* 0 not tried, 1 on, -1 off (an IOSurface function is missing) */
static SInt64 g_ss_ops[8], g_ss_pend, g_ss_done, g_ss_attach, g_ss_evict, g_ss_nosurf, g_ss_late, g_ss_inorder, g_ss_foreign;
static SInt64 g_ss_logged;

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
    IOLog("NullMoth GPU: surfsync: ON (probe: CPU locks are counted, not held)\n");
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
    unsigned int id = 0;
    uint64_t pending = 0, done = 0;
    IOLockLock(g_ss_lock);
    nmx_ss_rec *r = nmx_ss_find_cache_locked(cache);
    if (r) { id = r->id; pending = r->pending; done = r->done; }
    IOLockUnlock(g_ss_lock);
    if (!r)
        return;
    const bool late = done < pending;
    OSIncrementAtomic64(late ? &g_ss_late : &g_ss_inorder);
    if (OSIncrementAtomic64(&g_ss_logged) < 48) {
        char nm[32] = { 0 };
        proc_selfname(nm, sizeof nm);
        IOLog("NullMoth GPU: surfsync: CPU lock of surface %u by %s[%d] with write %llu of %llu done%s (key %s, a 0x%llx b 0x%llx)\n",
              id, nm, proc_selfpid(), (unsigned long long)done, (unsigned long long)pending,
              late ? " - WOULD WAIT" : "", key == g_ss_key ? "ours" : "OTHER", a, b);
    }
}

static void nmx_ss_summary(void)
{
    const SInt64 n = g_ss_pend;
    if (n == 16 || (n > 0 && (n & 4095) == 0))
        IOLog("NullMoth GPU: surfsync: %lld writes, %lld done, %lld caches made, %lld dropped, %lld no surface; CPU locks %lld "
              "before their write landed, %lld after; control ops 0:%lld 2:%lld 3:%lld 4:%lld 5:%lld other:%lld, foreign key %lld\n",
              (long long)n, (long long)g_ss_done, (long long)g_ss_attach, (long long)g_ss_evict, (long long)g_ss_nosurf,
              (long long)g_ss_late, (long long)g_ss_inorder, (long long)g_ss_ops[0], (long long)g_ss_ops[2], (long long)g_ss_ops[3],
              (long long)g_ss_ops[4], (long long)g_ss_ops[5], (long long)(g_ss_ops[1] + g_ss_ops[6] + g_ss_ops[7]),
              (long long)g_ss_foreign);
}

/* PENDING: a write into surface 'id' (looked up in the caller's task) gets the next number; its cache is made current */
static int nmx_ss_pending(unsigned int id, uint64_t *seq)
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
            else if (g_ss[i].id == id || (g_ss[i].done >= g_ss[i].pending && (!idle || g_ss[i].last < idle->last))) idle = &g_ss[i];
        }
        if (!r && idle) {
            drop = idle->cache;
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
        r->last = mach_absolute_time();
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
    case 1:
        *seq = 0;
        return nmx_ss_pending(surface, seq);
    case 2:
        return nmx_ss_done(surface, *seq);
    case 3: {
        const SInt64 v[6] = { g_ss_pend, g_ss_done, g_ss_late, g_ss_inorder, g_ss_attach, g_ss_ops[0] };
        for (uint32_t i = 0; i < nstats && i < 6; i++)
            stats[i] = (uint64_t)v[i];
        return 0;
    }
    }
    return EINVAL;
}
