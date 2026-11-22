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
#include <IOKit/IOLocks.h>
#include <libkern/OSAtomic.h>
#include <sys/ioccom.h>
#include <sys/errno.h>
#include <sys/proc.h>
#include "nmx_xnu.h"

extern "C" int nmx_xnu_pid_gone(int pid);

/*
 * v77: a client of a process that died is closed by the driver. IOKit did not call clientDied / clientClose for the
 * clients of some processes that exited (11-22: NotificationCenter, AXVisualSupportAgent, SafeEjectGPUService - still
 * "active" in the registry minutes later), so their DRM files stayed open: the GPU contexts and memory of a dead
 * process, and a reference on its task. Every client is listed with its process; the sweep (nmx_mm.cpp, every 2 s)
 * closes the DRM file of each client whose process is gone and terminates the client. The minor is taken with an atomic
 * exchange by whichever of clientClose, stop and the sweep comes first, and the sweep closes it only once no external
 * method is running on the client, so an ioctl never runs on a closed (or reused) open.
 */
class IOAccelNMXDRMClient : public IOUserClient {
    OSDeclareDefaultStructors(IOAccelNMXDRMClient)
    int fMinor = -1;
    int fPid = 0;
    char fName[24] = "";
    SInt32 fInflight = 0;                 /* external methods running (__atomic) */
    bool fListed = false;                 /* in gClients, under gClientLock */
    IOAccelNMXDRMClient *fNext = nullptr;
    static constexpr uint32_t kMaxArg = IOCPARM_MAX;    /* 8 KiB: the largest argument an ioctl number can encode */
    void unlist();
    void closeMinor();
public:
    bool start(IOService *provider) override;
    IOReturn clientClose() override;
    void stop(IOService *provider) override;
    void free() override;
    IOReturn externalMethod(uint32_t selector, IOExternalMethodArguments *args, IOExternalMethodDispatch *dispatch,
                            OSObject *target, void *reference) override;
    friend int nmx_uc_sweep_clients(void);
};
OSDefineMetaClassAndStructors(IOAccelNMXDRMClient, IOUserClient)

static IOAccelNMXDRMClient *gClients;
static IOLock *gClientLock;

static IOLock *client_lock(void)
{
    if (gClientLock == nullptr) {
        IOLock *l = IOLockAlloc();
        if (!OSCompareAndSwapPtr(nullptr, l, (void * volatile *)&gClientLock))
            IOLockFree(l);
    }
    return gClientLock;
}

void IOAccelNMXDRMClient::unlist()
{
    IOLockLock(client_lock());
    if (fListed) {
        for (IOAccelNMXDRMClient **pp = &gClients; *pp != nullptr; pp = &(*pp)->fNext)
            if (*pp == this) { *pp = fNext; break; }
        fListed = false;
        fNext = nullptr;
    }
    IOLockUnlock(gClientLock);
}

/* the first caller takes the minor; an external method still running finishes before the open is closed */
void IOAccelNMXDRMClient::closeMinor()
{
    const int m = __atomic_exchange_n(&fMinor, -1, __ATOMIC_SEQ_CST);
    if (m < 0)
        return;
    for (int i = 0; i < 2000 && __atomic_load_n(&fInflight, __ATOMIC_SEQ_CST) > 0; i++)
        IOSleep(1);
    nmx_xnu_uc_close(m);
}

bool IOAccelNMXDRMClient::start(IOService *provider)
{
    if (!IOUserClient::start(provider))
        return false;
    int minor = -1;
    int err = nmx_xnu_uc_open("dri/renderD128", &minor);
    if (err != 0) {
        IOLog("NullMoth GPU: DRM user client: opening the render node failed (%d)\n", err);
        return false;
    }
    fPid = proc_selfpid();
    proc_selfname(fName, sizeof(fName));
    __atomic_store_n(&fMinor, minor, __ATOMIC_SEQ_CST);
    IOLockLock(client_lock());
    fNext = gClients;
    gClients = this;
    fListed = true;
    IOLockUnlock(gClientLock);
    return true;
}

IOReturn IOAccelNMXDRMClient::clientClose()
{
    unlist();
    closeMinor();
    terminate();
    return kIOReturnSuccess;
}

void IOAccelNMXDRMClient::stop(IOService *provider)
{
    unlist();
    closeMinor();
    IOUserClient::stop(provider);
}

void IOAccelNMXDRMClient::free()
{
    unlist();
    IOUserClient::free();
}

/* the sweep's half (nmx_mm.cpp): clients whose process is gone; how many were closed */
int nmx_uc_sweep_clients(void)
{
    IOAccelNMXDRMClient *gone[32];
    int n = 0, closed = 0;
    if (gClientLock == nullptr)
        return 0;
    IOLockLock(gClientLock);
    for (IOAccelNMXDRMClient *c = gClients; c != nullptr && n < 32; c = c->fNext)
        if (c->fPid > 0 && __atomic_load_n(&c->fMinor, __ATOMIC_SEQ_CST) >= 0) {
            c->retain();
            gone[n++] = c;
        }
    IOLockUnlock(gClientLock);
    for (int i = 0; i < n; i++) {
        IOAccelNMXDRMClient *c = gone[i];
        if (nmx_xnu_pid_gone(c->fPid)) {
            c->unlist();
            if (__atomic_load_n(&c->fMinor, __ATOMIC_SEQ_CST) >= 0) {
                c->closeMinor();
                closed++;
                static SInt32 said;
                if (OSIncrementAtomic(&said) < 16)
                    IOLog("NullMoth GPU: pid %d (%s) is gone and IOKit kept its DRM user client: closed by the driver\n",
                          c->fPid, c->fName);
            }
            c->terminate();
        }
        c->release();
    }
    return closed;
}
extern "C" int nmx_xnu_uc_sweep(void) { return nmx_uc_sweep_clients(); }

/*
 * selector 0: ioctl. scalar in [0] = the ioctl number; structure in = its argument when the number has IOC_IN;
 * structure out = its argument after the call when it has IOC_OUT (inline or by descriptor, as IOKit passes them).
 * scalar out [0] = the errno the ioctl returned (0 on success), so transport failures stay distinct.
 */
IOReturn IOAccelNMXDRMClient::externalMethod(uint32_t selector, IOExternalMethodArguments *args,
                                             IOExternalMethodDispatch *dispatch, OSObject *target, void *reference)
{
    if (selector != 0)
        return kIOReturnBadArgument;
    if (args->scalarInputCount != 1 || args->scalarOutputCount != 1)
        return kIOReturnBadArgument;
    /* v77: counted before the minor is read, so the sweep's close waits for this call (closeMinor) */
    struct Inflight { SInt32 *n; ~Inflight() { __atomic_sub_fetch(n, 1, __ATOMIC_SEQ_CST); } } inflight = { &fInflight };
    __atomic_add_fetch(&fInflight, 1, __ATOMIC_SEQ_CST);
    const int minor = __atomic_load_n(&fMinor, __ATOMIC_SEQ_CST);
    if (minor < 0)
        return kIOReturnNotOpen;
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
        int err = nmx_xnu_uc_ioctl(minor, cmd, buf);
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
