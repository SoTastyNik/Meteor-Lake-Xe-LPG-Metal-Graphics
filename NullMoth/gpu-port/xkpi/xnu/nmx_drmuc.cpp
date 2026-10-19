/*
 * IOAccelNMXDRMClient: a DRM node opened through IOKit instead of the device file.
 *
 * WindowServer's sandbox (com.apple.WindowServer.sb) lets it open /dev/dri/renderD128 read-only but denies every ioctl
 * on a device file, while it may open IOKit user clients whose class name starts with "IOAccel" (Apple's GPU drivers
 * are reached that way). So the class name is part of the interface. Each client is one open of the render node; its
 * one external method runs a DRM (or NullMoth node) ioctl on that open, through the same entry point as an ioctl(2) on
 * the device file. It runs on the caller's thread, so the user pointers inside an ioctl's argument (and the mappings
 * NMX_DRM_IOCTL_MMAP makes) belong to the caller, as with the device file. libdrm's Darwin side switches a DRM fd to a
 * client of this kind when an ioctl on it fails with EPERM.
 */
#include <IOKit/IOUserClient.h>
#include <IOKit/IOLib.h>
#include <IOKit/IOMemoryDescriptor.h>
#include <sys/ioccom.h>
#include <sys/errno.h>
#include "nmx_xnu.h"

class IOAccelNMXDRMClient : public IOUserClient {
    OSDeclareDefaultStructors(IOAccelNMXDRMClient)
    int fMinor = -1;
    static constexpr uint32_t kMaxArg = IOCPARM_MAX;    /* 8 KiB: the largest argument an ioctl number can encode */
public:
    bool start(IOService *provider) override;
    IOReturn clientClose() override;
    void stop(IOService *provider) override;
    IOReturn externalMethod(uint32_t selector, IOExternalMethodArguments *args, IOExternalMethodDispatch *dispatch,
                            OSObject *target, void *reference) override;
};
OSDefineMetaClassAndStructors(IOAccelNMXDRMClient, IOUserClient)

bool IOAccelNMXDRMClient::start(IOService *provider)
{
    if (!IOUserClient::start(provider))
        return false;
    int err = nmx_xnu_uc_open("dri/renderD128", &fMinor);
    if (err != 0) {
        IOLog("NullMoth GPU: DRM user client: opening the render node failed (%d)\n", err);
        return false;
    }
    return true;
}

IOReturn IOAccelNMXDRMClient::clientClose()
{
    if (fMinor >= 0) {
        nmx_xnu_uc_close(fMinor);
        fMinor = -1;
    }
    terminate();
    return kIOReturnSuccess;
}

void IOAccelNMXDRMClient::stop(IOService *provider)
{
    if (fMinor >= 0) {
        nmx_xnu_uc_close(fMinor);
        fMinor = -1;
    }
    IOUserClient::stop(provider);
}

/*
 * selector 0: ioctl. scalar in [0] = the ioctl number; structure in = its argument when the number has IOC_IN;
 * structure out = its argument after the call when it has IOC_OUT (inline or by descriptor, as IOKit passes them).
 * scalar out [0] = the errno the ioctl returned (0 on success), so transport failures stay distinct.
 */
IOReturn IOAccelNMXDRMClient::externalMethod(uint32_t selector, IOExternalMethodArguments *args,
                                             IOExternalMethodDispatch *dispatch, OSObject *target, void *reference)
{
    if (selector != 0 || fMinor < 0)
        return kIOReturnBadArgument;
    if (args->scalarInputCount != 1 || args->scalarOutputCount != 1)
        return kIOReturnBadArgument;
    unsigned long cmd = (unsigned long)args->scalarInput[0];
    uint32_t len = IOCPARM_LEN(cmd);
    if (len > kMaxArg)
        return kIOReturnBadArgument;
    uint8_t stackbuf[256];
    uint8_t *buf = len <= sizeof(stackbuf) ? stackbuf : (uint8_t *)IOMalloc(len);
    if (buf == nullptr)
        return kIOReturnNoMemory;
    bzero(buf, len);
    IOReturn ret = kIOReturnSuccess;
    if ((cmd & IOC_IN) && len) {
        if (args->structureInputDescriptor) {
            if (args->structureInputDescriptor->getLength() < len ||
                args->structureInputDescriptor->readBytes(0, buf, len) != len)
                ret = kIOReturnBadArgument;
        } else if (args->structureInputSize >= len && args->structureInput) {
            memcpy(buf, args->structureInput, len);
        } else {
            ret = kIOReturnBadArgument;
        }
    }
    if (ret == kIOReturnSuccess) {
        int err = nmx_xnu_uc_ioctl(fMinor, cmd, buf);
        args->scalarOutput[0] = (uint64_t)err;
        if (err == 0 && (cmd & IOC_OUT) && len) {
            if (args->structureOutputDescriptor) {
                if (args->structureOutputDescriptor->getLength() < len ||
                    args->structureOutputDescriptor->writeBytes(0, buf, len) != len)
                    ret = kIOReturnBadArgument;
                else
                    args->structureOutputDescriptorSize = len;
            } else if (args->structureOutputSize >= len && args->structureOutput) {
                memcpy(args->structureOutput, buf, len);
                args->structureOutputSize = len;
            } else {
                ret = kIOReturnBadArgument;
            }
        } else {
            args->structureOutputSize = 0;
        }
    }
    if (buf != stackbuf)
        IOFree(buf, len);
    return ret;
}

/* NMXGPU::newUserClient's half: type 'NMXD' makes one of these on the GPU's service */
extern "C++" IOUserClient *nmx_drm_user_client(IOService *provider, task_t owningTask, void *securityID, UInt32 type)
{
    IOAccelNMXDRMClient *c = OSTypeAlloc(IOAccelNMXDRMClient);
    if (c == nullptr)
        return nullptr;
    if (!c->initWithTask(owningTask, securityID, type) || !c->attach(provider)) {
        c->release();
        return nullptr;
    }
    if (!c->start(provider)) {
        c->detach(provider);
        c->release();
        return nullptr;
    }
    return c;
}
