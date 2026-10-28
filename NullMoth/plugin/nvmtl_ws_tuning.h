#pragma once
/*
 * WindowServer presentation switches for the HUAWEI MateBook (2880x1920 panel, 22.1 MB per frame), read once per
 * process from flag files next to the plugin, so a variant can be tried with a reboot instead of a rebuild:
 *
 *   /Library/GPUBundles/nvmtl-ws-staged          publication through the snapshot buffer (the Dell's path): GPU
 *                                                staging -> snapshot -> IOSurface, two CPU copies of every frame.
 *                                                Default (absent): staging -> IOSurface, one copy.
 *   /Library/GPUBundles/nvmtl-ws-early-schedule  report a WindowServer command buffer scheduled at submission instead
 *                                                of after its publication; NMXAccel's ordered flips still hold a
 *                                                surface off the panel until NMXPublished >= NMXPending.
 *                                                (WindowServer crashed under fast window moves with it: keep off.)
 *   /Library/GPUBundles/nvmtl-ws-coherent-readback  retained readback staging in the HOST_COHERENT memory type, which
 *                                                Meteor Lake maps write-combined: the CPU read a 22.1 MB frame at
 *                                                ~1 GB/s (20 ms). Default (absent): the HOST_CACHED type; the leased
 *                                                slots already flush their cache lines before submission and after
 *                                                the fence (nvmtl_cpu_cache_sync).
 */
#include <unistd.h>

static inline int nvmtl_ws_flag(const char *path, int *cache)
{
    if (*cache < 0)
        *cache = access(path, F_OK) == 0;
    return *cache;
}

static inline int nvmtl_ws_staged_publication(void)
{
    static int on = -1;
    return nvmtl_ws_flag("/Library/GPUBundles/nvmtl-ws-staged", &on);
}

static inline int nvmtl_ws_early_schedule(void)
{
    static int on = -1;
    return nvmtl_ws_flag("/Library/GPUBundles/nvmtl-ws-early-schedule", &on);
}

static inline int nvmtl_ws_cached_readback(void)
{
    static int coherent = -1;
    return !nvmtl_ws_flag("/Library/GPUBundles/nvmtl-ws-coherent-readback", &coherent);
}

/* nvmtl_vk_buffer_create's host_visible value for a cached (non-coherent, cache-maintained) readback buffer */
#define NVMTL_HOST_CACHED_READBACK 4
