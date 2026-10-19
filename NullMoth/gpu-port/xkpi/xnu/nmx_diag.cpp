/*
 * The driver state dump: NMX_DRM_IOCTL_DEBUG_DUMP on any DRM node (vm/guest/tools/nmxdump) prints what the xe side
 * registered (override/xe/nmx_xe_debug.c) to the kernel log, so a stuck submission can be looked at in the running
 * system instead of through a rebuild and reboot per question. (Not a sysctl: the port has its own sysctl tree, whose
 * sysctl_register_oid and sysctl__debug_children a kext-side oid would link against.)
 */
#include <IOKit/IOLib.h>
#include "nmx_xnu.h"
#if __has_include("nmx_buildstamp.h")
#include "nmx_buildstamp.h"      /* written by vm/tools/cycle.sh for each test build */
#else
#define NMX_BUILD_STAMP "unstamped"
#endif

static void (*volatile g_dump)(void);

extern "C" void nmx_xnu_set_dump_hook(void (*fn)(void))
{
    g_dump = fn;
}

extern "C" void nmx_xnu_run_dump(void)
{
    void (*fn)(void) = g_dump;
    IOLog("NullMoth GPU: state dump (build %s)%s\n", NMX_BUILD_STAMP, fn ? "" : " - nothing registered");
    if (fn)
        fn();
    IOLog("NullMoth GPU: state dump end\n");
}

extern "C" void nmx_xnu_diag_fini(void)
{
    g_dump = nullptr;
}
