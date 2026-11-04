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
 *   /Library/GPUBundles/nvmtl-ws-pipeline        let WindowServer's command buffers be submitted ahead (the queue
 *                                                keeps several in flight) instead of one submit-and-wait at a time.
 *                                                Its main thread spent 27% of a drag waiting to be scheduled behind
 *                                                the previous command buffer's GPU work (v18 sample). Experimental.
 *   /Library/GPUBundles/nvmtl-ws-submit-locked   keep the command buffer class lock across a submit-ahead execbuffer, as
 *                                                before v27. Default (absent): released around it.
 *   /Library/GPUBundles/nvmtl-ws-nowait          with early schedule and the pipeline: WindowServer's commit does not wait
 *                                                to be scheduled at all (NMXAccel's ordered flips hold the surface until
 *                                                it is published). Experimental.
 *   /Library/GPUBundles/nvmtl-ws-split-submit    with the pipeline: execbuffers run on their own serial queue, kicked
 *                                                by every commit; the execution worker only waits for completions
 *                                                (v38, NVMTLEventSync.m nvmtl_kick_submit).
 *   /Library/GPUBundles/nvmtl-ws-tiled           with host import: WindowServer's full-screen render targets are drawn in a
 *                                                tiled private image and copied to the surface's own pages on the GPU
 *                                                once per command buffer (v37, NVMTLDevice.m nvmtl_surface_hybrid).
 *   /Library/GPUBundles/nvmtl-ws-zerocopy        with tiled: those surfaces are drawn in Tile4 straight into their own
 *                                                pages and the panel scans them out tiled (IOSurface value "NMXTile4";
 *                                                NMXVGAFB programs the plane, NMXAccel untiles a frame it has to copy).
 *                                                No copy, no private image (v41). Experimental.
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

static inline int nvmtl_ws_pipeline(void)
{
    static int on = -1;
    return nvmtl_ws_flag("/Library/GPUBundles/nvmtl-ws-pipeline", &on);
}

static inline int nvmtl_ws_submit_unlocked(void)
{
    static int locked = -1;
    return nvmtl_ws_pipeline() && !nvmtl_ws_flag("/Library/GPUBundles/nvmtl-ws-submit-locked", &locked);
}

static inline int nvmtl_ws_nowait(void)
{
    static int on = -1;
    return nvmtl_ws_pipeline() && nvmtl_ws_early_schedule() && nvmtl_ws_flag("/Library/GPUBundles/nvmtl-ws-nowait", &on);
}

static inline int nvmtl_ws_split_submit(void)
{
    static int on = -1;
    return nvmtl_ws_pipeline() && nvmtl_ws_flag("/Library/GPUBundles/nvmtl-ws-split-submit", &on);
}

static inline int nvmtl_ws_tiled(void)
{
    static int on = -1;
    return nvmtl_ws_flag("/Library/GPUBundles/nvmtl-ws-tiled", &on);
}

static inline int nvmtl_ws_zerocopy(void)
{
    static int on = -1;
    return nvmtl_ws_tiled() && nvmtl_ws_flag("/Library/GPUBundles/nvmtl-ws-zerocopy", &on);
}

/* nvmtl_vk_buffer_create's host_visible value for a cached (non-coherent, cache-maintained) readback buffer */
#define NVMTL_HOST_CACHED_READBACK 4
