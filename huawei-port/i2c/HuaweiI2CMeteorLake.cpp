// VoodooI2C controller personality for the HUAWEI MateBook 14 (FLMH-XX) Meteor Lake LPSS I2C controllers:
// I2C0 8086:7E78 (touchpad BLTP7853) and I2C1 8086:7E79 (touchscreen FTSC1000), subsystem 19E5:3E71.
// Same approach as the Dell port's LatitudeI2CMeteorLake: bring the controller to D0 before VoodooI2C
// configures it, refusing any device that is not one of these two exact controllers.
#include "VoodooI2CPCIController.hpp"
#include <mach/kmod.h>
extern "C" kern_return_t _start(kmod_info_t*,void*);
extern "C" kern_return_t _stop(kmod_info_t*,void*);
extern "C" { KMOD_EXPLICIT_DECL(com.huawei-mtl.HuaweiI2CMeteorLake,"1.0.0",_start,_stop) }
extern "C" kern_return_t _start(kmod_info_t*,void*) {return KERN_SUCCESS;}
extern "C" kern_return_t _stop(kmod_info_t*,void*) {return KERN_SUCCESS;}

static bool huawei_i2c_identity(IOPCIDevice *pci)
{
    if (!pci) return false;
    uint16_t vendor = pci->configRead16(kIOPCIConfigVendorID), device = pci->configRead16(kIOPCIConfigDeviceID);
    uint16_t sv = pci->configRead16(kIOPCIConfigSubSystemVendorID), sd = pci->configRead16(kIOPCIConfigSubSystemID);
    return vendor == 0x8086 && (device == 0x7e78 || device == 0x7e79) && sv == 0x19e5 && sd == 0x3e71;
}

static bool huawei_i2c_d0(IOPCIDevice *pci)
{
    if (!huawei_i2c_identity(pci)) return false;
    uint8_t cap = 0;
    if (!pci->findPCICapability(1, &cap) || cap < 0x40 || cap > 0xf8 || (cap & 3)) return false;
    uint16_t old = pci->configRead16(cap + 4);
    if (old == 0xffff) return false;
    pci->enablePCIPowerManagement(0);
    if (old & 3) pci->configWrite16(cap + 4, (uint16_t)(old & ~0x8003u));
    for (unsigned i = 0; i < 10; i++) {
        if ((pci->configRead16(cap + 4) & 3) == 0) {
            pci->setBusMasterEnable(true); pci->setMemoryEnable(true); return true;
        }
        IOSleep(1);
    }
    return false;
}

class HuaweiI2CMeteorLakeController : public VoodooI2CPCIController {
    OSDeclareDefaultStructors(HuaweiI2CMeteorLakeController)
public:
    VoodooI2CController *probe(IOService *provider, SInt32 *score) override {
        if (!huawei_i2c_d0(OSDynamicCast(IOPCIDevice, provider))) return nullptr;
        return VoodooI2CPCIController::probe(provider, score);
    }
protected:
    void configurePCI() override {
        bool ok = huawei_i2c_d0(physical_device.pci_device);
        setProperty("HuaweiI2CD0Verified", ok ? kOSBooleanTrue : kOSBooleanFalse);
        IOLog("HuaweiI2CMeteorLake: controller %04x D0 verified=%d\n",
              physical_device.pci_device ? physical_device.pci_device->configRead16(kIOPCIConfigDeviceID) : 0, ok);
    }
};
OSDefineMetaClassAndStructors(HuaweiI2CMeteorLakeController, VoodooI2CPCIController)
