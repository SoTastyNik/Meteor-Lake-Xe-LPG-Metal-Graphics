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
