#!/usr/bin/env python3
# gen.py: NMXAGDC's source is NVRMAGDC's (kexts/NVRMAGDC/nvrm-agdc.cpp) with the few changes a VM display needs:
#   - the GPU is the PCI device NMXGPU drives (an SR-IOV VF), and its one framebuffer is NMXVGAFB, which sits under
#     another PCI device (the VM's virtio-vga): NVRMAGDC only reports framebuffers under the GPU's own device
#   - vendor Intel; its own class, kmod and sysctl names (debug.nmxfb_agdc*)
# WindowServer builds one display pipe per framebuffer in this object's 0x980 reply; without one it found no display
# pipe for NMXVGAFB ("Unable to find display pipe for IOFB service") and composited nothing.
import os, sys
here = os.path.dirname(os.path.abspath(__file__))
s = open(os.path.join(here, "../NVRMAGDC/nvrm-agdc.cpp")).read()
def rep(old, new, n=1):
    global s
    assert s.count(old) == n, (old[:60], s.count(old))
    s = s.replace(old, new)
rep('#include "nvrm_off.h"', '#include "../NVRMAGDC/nvrm_off.h"')
rep('#include "AppleGraphicsDeviceControl_re.h"', '#include "../NVRMAGDC/AppleGraphicsDeviceControl_re.h"')
rep('#include "nvrm-agdc-k5.h"', '#include "../NVRMAGDC/nvrm-agdc-k5.h"')
rep('KMOD_EXPLICIT_DECL(com.nullmoth.NVRMAGDC,', 'KMOD_EXPLICIT_DECL(com.nullmoth.NMXAGDC,')
rep('IOLog("NVRM-agdc: "', 'IOLog("NMX-agdc: "')
s = s.replace("NVDADeviceControl", "NMXDeviceControl").replace("NVDAGDCLoader", "NMXAGDCLoader")
s = s.replace("nvrmfb_agdc", "nmxfb_agdc")
rep('strlcpy(v->vendor, "NVIDIA", sizeof v->vendor); v->vendorID = 0x10de;',
    'strlcpy(v->vendor, "Intel", sizeof v->vendor); v->vendorID = 0x8086;')
# targets: the framebuffer is NMXVGAFB, the GPU is the PCI device NMXGPU claimed
rep('''    OSDictionary *m = IOService::serviceMatching("NVRMNVDAFramebuffer"); if (!m) return;
    IOService *f = IOService::copyMatchingService(m); m->release(); if (!f) return;
    IOService *p = f->getProvider(); int hops = 0;
    while (p && !p->metaCast("IOPCIDevice") && hops++ < 8) p = p->getProvider();
    if (!p || !p->metaCast("IOPCIDevice")) { f->release(); return; }''',
    '''    // the framebuffer and GPU NMXAccel handed to nmxAgdcUp: it can arm the display while the framebuffer is still
    // registering, when a matching lookup does not find it yet; the lookups below are the fallback
    IOService *f = gAgdcHintFB, *p = gAgdcHintPCI;
    if (f && p && p->metaCast("IOPCIDevice")) { f->retain(); gAgdcFBRef = f; *fb = f; *pci = p; return; }
    OSDictionary *m = IOService::serviceMatching("NMXVGAFB"); if (!m) return;
    f = IOService::copyMatchingService(m); m->release(); if (!f) return;
    OSDictionary *g = IOService::serviceMatching("NMXGPU"); IOService *gpu = g ? IOService::copyMatchingService(g) : nullptr;
    OSSafeReleaseNULL(g);
    p = gpu ? gpu->getProvider() : nullptr; OSSafeReleaseNULL(gpu);
    if (!p || !p->metaCast("IOPCIDevice")) { f->release(); return; }''')
# the hints live next to the other AGDC state
rep('''static IOService *gAgdcFBRef = nullptr;''', '''static IOService *gAgdcFBRef = nullptr;
static IOService *gAgdcHintFB = nullptr, *gAgdcHintPCI = nullptr;   // from nmxAgdcUp (NMXAccel's framebuffer and GPU)''')
rep('''    OSDictionary *m = IOService::serviceMatching("NVRMNVDAFramebuffer");
    OSIterator *it''', '''    OSDictionary *m = IOService::serviceMatching("NMXVGAFB");
    OSIterator *it''')
rep('''        if (p != pci) { other++;''', '''        (void)p;
        if (false) { other++;''')
# no sysctl arming: NMXAccel brings the AGDC object up when it arms the VM display (phase 1, before WindowServer looks
# for displays), with the link-configuration answers (K5) on; the loader publishes itself so NMXAccel can find it
rep('''    virtual void stop(IOService *provider) APPLE_KEXT_OVERRIDE;
};
OSDefineMetaClassAndStructors(NMXAGDCLoader, IOService)''', '''    virtual void stop(IOService *provider) APPLE_KEXT_OVERRIDE;
    virtual IOReturn callPlatformFunction(const OSSymbol *fn, bool wait, void *p1, void *p2, void *p3, void *p4) APPLE_KEXT_OVERRIDE;
};
OSDefineMetaClassAndStructors(NMXAGDCLoader, IOService)
IOReturn NMXAGDCLoader::callPlatformFunction(const OSSymbol *fn, bool wait, void *p1, void *p2, void *p3, void *p4)
{
    if (fn && fn->isEqualTo("nmxAgdcUp")) {
        gAgdcK5 = 1; gAgdcWant = 1;
        gAgdcHintPCI = OSDynamicCast(IOService, (OSObject *)p1); gAgdcHintFB = OSDynamicCast(IOService, (OSObject *)p2);
        OSIncrementAtomic(&gAgdcBusy); nvdaAgdcWorkBody(); OSDecrementAtomic(&gAgdcBusy);
        gAgdcHintPCI = gAgdcHintFB = nullptr;   // not retained: only for this call
        FBLOG("AGDC: brought up for the VM display -> state %d", gAgdcState);
        return gAgdcState == 1 ? kIOReturnSuccess : kIOReturnError;
    }
    return IOService::callPlatformFunction(fn, wait, p1, p2, p3, p4);
}''')
rep('nvdaAgdcInstallSysctl(); FBLOG("loaded; idle until `sysctl debug.nmxfb_agdc=1`"); return true;',
    'nvdaAgdcInstallSysctl(); registerService(); FBLOG("loaded; comes up when NMXAccel arms a VM display"); return true;')
# Plane 0's gamma (AGDC 0x711, extended capability type 2). IOPresentment builds the plane's GammaArray from it; with
# none, CoreDisplay's DisplayPipe::AreOperationsSupportedInHW fails and every frame runs its software display pipe,
# which rebuilds the colour tables on the CPU (CombineLUTs on all cores, about 60% of WindowServer's time at an idle
# login window). The host (QEMU's GL window, KWin) owns the physical display's colour, so the plane takes the table
# and the VM display does not apply it. Entry layout (0x32c bytes) from IOPresentment's
# IOPresentmentCapabilitiesDisplayPipe::IOPresentmentCreateGammaDictionary: +0 flags, +4 plane mask (u64), +0xc
# non-atomic application period (float), +0x10 type, +0x14 fixed format, +0x18 configuration id (u64), +0x20/+0x24
# minimum/maximum value (float), +0x28 maximum size (u64). Type 0x200 is CoreDisplay's preferred one (a 3-channel
# table of 16-bit entries, IOPCapabilities::GammaChannelTableEntryCountAndType); the flags are the plane scaler's.
rep("""    if (gAgdcK5 && (cmd == NVK5_CMD_LINKCONFIG || cmd == NVK5_CMD_FBCAPEX)) {""", """    if (cmd == NVK5_CMD_FBCAPEX && out && outSize && *outSize == sizeof(struct NVAGDCFBExtCap)) {
        struct NVAGDCFBExtCap *c = (struct NVAGDCFBExtCap *)out;
        const uint32_t type = c->type;
        OSBitOrAtomic(type, (volatile UInt32 *)&gAgdc711Types);
        if ((type == 1 || type == 2 || type == 4) && gAgdcGamma && c->fbIndex == 0) {
            nvk5_zero(c, sizeof *c); c->fbIndex = 0; c->type = type; c->count = 1;
            uint8_t *e = c->entry[0];
            nvk5_put32(e, 0x000, 0x80004);                        // flags; bit 2 is what CoreDisplay checks
            nvk5_put32(e, 0x004, 1); nvk5_put32(e, 0x008, 0);    // plane 0
            if (type == 2) {                                      // gamma: a 1024-entry 3-channel 16-bit table
                nvk5_put32(e, 0x010, 0x200);
                nvk5_put32(e, 0x020, 0x00000000u);                // 0.0f
                nvk5_put32(e, 0x024, 0x3f800000u);                // 1.0f
                nvk5_put32(e, 0x028, 1024); nvk5_put32(e, 0x02c, 0);
            } else if (type == 4) {                               // linearization: sRGB (config 0x10) and linear (0x20)
                c->count = 2;
                nvk5_put32(e, 0x010, 1); nvk5_put32(e, 0x018, 0x10);
                nvk5_put32(e, 0x024, 0x3f800000u);
                uint8_t *e2 = c->entry[1];
                nvk5_put32(e2, 0x000, 0x80004); nvk5_put32(e2, 0x004, 1);
                nvk5_put32(e2, 0x010, 1); nvk5_put32(e2, 0x018, 0x20);
                nvk5_put32(e2, 0x024, 0x3f800000u);
            } else {                                              // CSC: a 3x3 matrix, coefficients -2..2
                nvk5_put32(e, 0x010, 1);
                nvk5_put32(e, 0x024, 0xc0000000u);                // -2.0f
                nvk5_put32(e, 0x028, 0x40000000u);                // 2.0f
            }
            OSAddAtomic64(1, &gAgdcGammaAnswers);
            return kIOReturnSuccess;
        }
    }
    if (gAgdcK5 && (cmd == NVK5_CMD_LINKCONFIG || cmd == NVK5_CMD_FBCAPEX)) {""")
rep("""static int    gAgdcK5 = 0;""", """static int    gAgdcK5 = 0;
static int    gAgdcGamma = 1;          // answer plane 0's gamma capability (0x711 type 2)
static SInt64 gAgdcGammaAnswers = 0;
static int    gAgdc711Types = 0;       // bit t = an extended-capability query of type t (0x711)""")
rep("""static void nvdaAgdcInstallSysctl(void)
{
""", """static void nvdaAgdcInstallSysctl(void)
{
    sysctl_register_oid(&sysctl__debug_nmxfb_agdc_gamma); sysctl_register_oid(&sysctl__debug_nmxfb_agdc_gamma_answers);
    sysctl_register_oid(&sysctl__debug_nmxfb_agdc_711_types);
""")
rep("""static void nvdaAgdcRemoveSysctl(void)
{
""", """SYSCTL_INT (_debug, OID_AUTO, nmxfb_agdc_gamma, CTLFLAG_RW | CTLFLAG_LOCKED, &gAgdcGamma, 0, "1 = report plane 0's colour capabilities: CSC, linearization, gamma (read when WindowServer starts)");
SYSCTL_QUAD(_debug, OID_AUTO, nmxfb_agdc_gamma_answers, CTLFLAG_RD | CTLFLAG_LOCKED, &gAgdcGammaAnswers, "colour capability queries answered (CSC, linearization, gamma)");
SYSCTL_INT (_debug, OID_AUTO, nmxfb_agdc_711_types, CTLFLAG_RD | CTLFLAG_LOCKED, &gAgdc711Types, 0, "the extended capability types (0x711) asked for, ORed");
static void nvdaAgdcRemoveSysctl(void)
{
    sysctl_unregister_oid(&sysctl__debug_nmxfb_agdc_gamma); sysctl_unregister_oid(&sysctl__debug_nmxfb_agdc_gamma_answers);
    sysctl_unregister_oid(&sysctl__debug_nmxfb_agdc_711_types);
""")
open(os.path.join(here, "nmx-agdc.cpp"), "w").write("// GENERATED by gen.py from ../NVRMAGDC/nvrm-agdc.cpp. Do not edit.\n" + s)
print("nmx-agdc.cpp written")
