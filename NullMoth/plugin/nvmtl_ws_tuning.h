#pragma once
/*
 * WindowServer presentation switches for the HUAWEI MateBook (2880x1920 panel, 22.1 MB per frame), read once per
 * process from flag files next to the plugin, so a variant can be tried with a reboot instead of a rebuild.
 *
 * v64: the set every MateBook test ran with from v50 to v63 - early schedule, pipeline, split submit, tiled, zero copy
 * (and host import, nvmtl_memory_identity.h) - is built in: each is on unless its nvmtl-ws-no-<name> file is present.
 * The old opt-in files (nvmtl-ws-early-schedule, -pipeline, -split-submit, -tiled, -zerocopy, nvmtl-host-import, and
 * nvmtl-ws-ccs, CCS being the default since v52) are no longer read.
 *
 *   /Library/GPUBundles/nvmtl-ws-staged          publication through the snapshot buffer (the Dell's path): GPU
 *                                                staging -> snapshot -> IOSurface, two CPU copies of every frame.
 *                                                Default (absent): staging -> IOSurface, one copy.
 *   /Library/GPUBundles/nvmtl-ws-no-early-schedule  report a WindowServer command buffer scheduled after its
 *                                                publication. Default: scheduled at submission; NMXAccel's ordered
 *                                                flips still hold a surface off the panel until NMXPublished >=
 *                                                NMXPending. (A v2x build crashed WindowServer under fast window moves
 *                                                with it; v50-v63 ran with it.)
 *   /Library/GPUBundles/nvmtl-ws-coherent-readback  retained readback staging in the HOST_COHERENT memory type, which
 *                                                Meteor Lake maps write-combined: the CPU read a 22.1 MB frame at
 *                                                ~1 GB/s (20 ms). Default (absent): the HOST_CACHED type; the leased
 *                                                slots already flush their cache lines before submission and after
 *                                                the fence (nvmtl_cpu_cache_sync).
 *   /Library/GPUBundles/nvmtl-ws-no-pipeline     one submit-and-wait at a time. Default: WindowServer's command
 *                                                buffers are submitted ahead (the queue keeps several in flight); its
 *                                                main thread spent 27% of a drag waiting to be scheduled behind the
 *                                                previous command buffer's GPU work (v18 sample).
 *   /Library/GPUBundles/nvmtl-ws-submit-locked   keep the command buffer class lock across a submit-ahead execbuffer, as
 *                                                before v27. Default (absent): released around it.
 *   /Library/GPUBundles/nvmtl-ws-no-nowait       WindowServer's commit waits until its command buffer is submitted.
 *                                                Default (v69, with early schedule and the pipeline): it does not wait at
 *                                                all; NMXAccel's ordered flips hold the surface until it is published.
 *                                                v27 measured frames under 17 ms 47% -> 57% with it; ArrowWhatever runs
 *                                                WindowServer this way. (Before v69 opt-in, nvmtl-ws-nowait.)
 *   /Library/GPUBundles/nvmtl-ws-no-split-submit the execution worker submits as well. Default, with the pipeline:
 *                                                execbuffers run on their own serial queue, kicked by every commit;
 *                                                the worker only waits for completions (v38, NVMTLEventSync.m
 *                                                nvmtl_kick_submit).
 *   /Library/GPUBundles/nvmtl-ws-no-tiled        WindowServer draws into linear images. Default, with host import: its
 *                                                full-screen render targets are drawn in a tiled image (v37,
 *                                                NVMTLDevice.m nvmtl_surface_hybrid).
 *   /Library/GPUBundles/nvmtl-ws-no-zerocopy     the tiled image is private and copied to the surface's own pages on
 *                                                the GPU once per command buffer (v37). Default, with tiled: those
 *                                                surfaces are drawn in Tile4 straight into their own pages and the
 *                                                panel scans them out tiled (IOSurface value "NMXTile4"; NMXVGAFB
 *                                                programs the plane, NMXAccel untiles a frame it has to copy). No
 *                                                copy, no private image (v41).
 */
#include <unistd.h>

static inline int nvmtl_ws_flag(const char *path, int *cache)
{
    if (*cache < 0)
        *cache = access(path, F_OK) == 0;
    return *cache;
}

// v64: a built-in switch, on unless its off file is present
static inline int nvmtl_ws_default(const char *off_path, int *cache)
{
    if (*cache < 0)
        *cache = access(off_path, F_OK) != 0;
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
    return nvmtl_ws_default("/Library/GPUBundles/nvmtl-ws-no-early-schedule", &on);
}

static inline int nvmtl_ws_cached_readback(void)
{
    static int coherent = -1;
    return !nvmtl_ws_flag("/Library/GPUBundles/nvmtl-ws-coherent-readback", &coherent);
}

static inline int nvmtl_ws_pipeline(void)
{
    static int on = -1;
    return nvmtl_ws_default("/Library/GPUBundles/nvmtl-ws-no-pipeline", &on);
}

static inline int nvmtl_ws_submit_unlocked(void)
{
    static int locked = -1;
    return nvmtl_ws_pipeline() && !nvmtl_ws_flag("/Library/GPUBundles/nvmtl-ws-submit-locked", &locked);
}

static inline int nvmtl_ws_nowait(void)
{
    static int on = -1;
    return nvmtl_ws_pipeline() && nvmtl_ws_early_schedule() && nvmtl_ws_default("/Library/GPUBundles/nvmtl-ws-no-nowait", &on);
}

static inline int nvmtl_ws_split_submit(void)
{
    static int on = -1;
    return nvmtl_ws_pipeline() && nvmtl_ws_default("/Library/GPUBundles/nvmtl-ws-no-split-submit", &on);
}

static inline int nvmtl_ws_tiled(void)
{
    static int on = -1;
    return nvmtl_ws_default("/Library/GPUBundles/nvmtl-ws-no-tiled", &on);
}

static inline int nvmtl_ws_zerocopy(void)
{
    static int on = -1;
    return nvmtl_ws_tiled() && nvmtl_ws_default("/Library/GPUBundles/nvmtl-ws-no-zerocopy", &on);
}

/* nvmtl_vk_buffer_create's host_visible value for a cached (non-coherent, cache-maintained) readback buffer */
#define NVMTL_HOST_CACHED_READBACK 4
