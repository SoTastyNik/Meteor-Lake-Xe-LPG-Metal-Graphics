// Meteor Lake bring-up: PCI configuration reads only. No GT/display writes.
#include <IOKit/IOService.h>
#include <IOKit/IOLib.h>
#include <IOKit/pci/IOPCIDevice.h>
#include <mach/kmod.h>

class LatitudeMTLProbe : public IOService {
    OSDeclareDefaultStructors(LatitudeMTLProbe)
public:
    bool start(IOService *provider) override;
};
OSDefineMetaClassAndStructors(LatitudeMTLProbe, IOService)

bool LatitudeMTLProbe::start(IOService *provider) {
    IOPCIDevice *pci = OSDynamicCast(IOPCIDevice, provider);
    if (!pci || pci->configRead16(kIOPCIConfigVendorID) != 0x8086 ||
        pci->configRead16(kIOPCIConfigDeviceID) != 0x7D45)
        return false;
    if (!IOService::start(provider)) return false;
    setProperty("PortStage", "PCI diagnostic only; acceleration not implemented");
    setProperty("ActualVendorID", pci->configRead16(kIOPCIConfigVendorID), 16);
    setProperty("ActualDeviceID", pci->configRead16(kIOPCIConfigDeviceID), 16);
    setProperty("ActualRevisionID", pci->configRead8(kIOPCIConfigRevisionID), 8);
    setProperty("PCICommandAtAttach", pci->configRead16(kIOPCIConfigCommand), 16);
    // Raw config dwords, not decoded addresses. Never probe BAR size by writing.
    for (unsigned i = 0; i < 6; ++i) {
        char key[20];
        snprintf(key, sizeof(key), "PCIBAR%uRaw", i);
        setProperty(key, pci->configRead32(0x10 + i * 4), 32);
    }
    setProperty("HardwareWritesEnabled", false);
    IOLog("LatitudeMTLProbe: attached to real 8086:7d45; PCI reads only; no acceleration\n");
    registerService();
    return true;
}
extern "C" {
static kern_return_t moduleStart(kmod_info_t *, void *) { return KERN_SUCCESS; }
static kern_return_t moduleStop(kmod_info_t *, void *) { return KERN_SUCCESS; }
KMOD_EXPLICIT_DECL(com.vedcloud.LatitudeMTLProbe, "0.1.0", moduleStart, moduleStop)
__private_extern__ kmod_start_func_t *_realmain = moduleStart;
__private_extern__ kmod_stop_func_t *_antimain = moduleStop;
__private_extern__ int _kext_apple_cc = __APPLE_CC__;
}
