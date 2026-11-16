/*
 * Device nodes for the port on xnu devfs. Compiled with Apple's headers only.
 *
 * One xnu cdevsw serves every node. Each node is a clone node (devfs_make_node_clone): every open() of it is given
 * a minor number of its own, and that minor identifies the open in all later calls, which is how per-open state (a
 * Linux struct file) exists although an xnu cdevsw entry point receives only a dev_t. Node minors are 0..255; open
 * minors start at 256.
 *
 * Entry points call into the LinuxKPI side (nmx_cdev_*). mmap is not a cdevsw operation kexts can implement on
 * macOS, so user mappings of GPU memory are made by an ioctl through nmx_xnu_map_user (an IOKit mapping in the
 * calling task).
 */
#include <sys/types.h>
#include <sys/conf.h>
#include <sys/errno.h>
#include <sys/uio.h>
#include <sys/fcntl.h>
#include <sys/proc.h>
#include <sys/vnode.h>
#include <miscfs/devfs/devfs.h>
#include <IOKit/IOLib.h>
#include <IOKit/IOMemoryDescriptor.h>
#include <IOKit/IOLocks.h>
#include <libkern/OSAtomic.h>
#include <kern/thread_call.h>
#include <kern/clock.h>
#include "nmx_xnu.h"

/* exported to kexts (xnu config: Mach.exports task_reference/task_deallocate; Unsupported.exports get_task_map,
   vm_deallocate) but not declared in Kernel.framework's headers */
extern "C" {
void task_reference(task_t task);
void task_deallocate(task_t task);
vm_map_t get_task_map(task_t task);
kern_return_t vm_deallocate(vm_map_t target, vm_offset_t address, vm_size_t size);
}

#define NODE_MINORS 256
#define OPEN_MINOR_MAX 65536

static int g_major = -1;
static IOLock *g_lock;
static void *g_node_cookie[NODE_MINORS];       /* node minor -> LinuxKPI cookie (struct cdev *) */
static void *g_node_handle[NODE_MINORS];       /* devfs node handles */
static char g_node_name[NODE_MINORS][32];      /* devfs path of each node ("dri/renderD128"), for the user client */
static uint16_t g_open_node[OPEN_MINOR_MAX];   /* open minor -> node minor + 1 (0 = free) */
static uint8_t g_open_active[OPEN_MINOR_MAX];  /* 1 while an open() of that minor succeeded and is not closed */

/*
 * v74: who made each open, with a reference on its task until the open is closed. When a process is gone and its
 * last open closes, a check 3 s later lets its mm record release the task and reports what still holds it
 * (nmx_mm.cpp, nmx_xnu_task_gone_check): a task the port keeps alive keeps its port, and launchd waited on it.
 */
struct OpenRec {
    int minor;
    int pid;
    task_t task;
    char name[24];
    OpenRec *next;
};
static OpenRec *g_opens;                       /* under g_lock */
struct GoneRec {
    task_t task;                               /* referenced until the check */
    int pid;
    char name[24];
};
static GoneRec g_gone[16];                     /* under g_lock */
static int g_gone_n;
static thread_call_t g_gone_tc;
extern "C" void nmx_xnu_task_gone_check(task_t task, int pid, const char *name, int secs);
extern "C" void nmx_xnu_census_add(void *ctx, task_t task, int pid, const char *name, int kind, uint64_t amount);

static void gone_fire(thread_call_param_t, thread_call_param_t)
{
    GoneRec now[16];
    IOLockLock(g_lock);
    const int n = g_gone_n;
    memcpy(now, g_gone, sizeof(GoneRec) * (size_t)n);
    g_gone_n = 0;
    IOLockUnlock(g_lock);
    for (int i = 0; i < n; i++) {
        nmx_xnu_task_gone_check(now[i].task, now[i].pid, now[i].name, 3);
        task_deallocate(now[i].task);
    }
}

/* whether the opener of a closing open is gone: closing on its way out (exit closes its files on its own thread), or
   no longer found (an IOKit client closed for a process that died) */
static bool opener_gone(const OpenRec *r, struct proc *closer)
{
    if (closer != nullptr && proc_pid(closer) == r->pid)
        return proc_exiting(closer) != 0;
    proc_t p = proc_find(r->pid);
    if (p == nullptr)
        return true;
    const bool gone = proc_exiting(p) != 0;
    proc_rele(p);
    return gone;
}
static int g_open_next = NODE_MINORS;

/* ---- clone minors ------------------------------------------------------------------------------------------------- */

static int clone_minor(dev_t dev, int action)
{
    int node = minor(dev);
    if (action == DEVFS_CLONE_ALLOC) {
        IOLockLock(g_lock);
        for (int tries = 0; tries < OPEN_MINOR_MAX - NODE_MINORS; tries++) {
            int m = g_open_next;
            g_open_next = (g_open_next + 1 < OPEN_MINOR_MAX) ? g_open_next + 1 : NODE_MINORS;
            if (g_open_node[m] == 0) {
                g_open_node[m] = (uint16_t)(node + 1);
                IOLockUnlock(g_lock);
                return m;
            }
        }
        IOLockUnlock(g_lock);
        return -1;
    }
    /*
     * DEVFS_CLONE_FREE: devfs is done with this minor's vnode. Every lookup clones (a stat() of a node allocates a
     * minor without opening it), so a minor that was never opened - or already closed - is released here; otherwise
     * stat()s leaked minors until the table ran out. An open minor is released by close(), which comes first.
     */
    IOLockLock(g_lock);
    if (node >= NODE_MINORS && node < OPEN_MINOR_MAX && !g_open_active[node])
        g_open_node[node] = 0;
    IOLockUnlock(g_lock);
    return 0;
}

static void *cookie_for_open(int m, int *node_out)
{
    void *cookie = nullptr;
    IOLockLock(g_lock);
    if (m >= NODE_MINORS && m < OPEN_MINOR_MAX && g_open_node[m]) {
        int node = g_open_node[m] - 1;
        cookie = g_node_cookie[node];
        if (node_out)
            *node_out = node;
    }
    IOLockUnlock(g_lock);
    return cookie;
}

/* ---- entry points ------------------------------------------------------------------------------------------------- */

/*
 * A driver call must hand the thread back with interrupts enabled. A thread that returned to user space with them
 * off died at exit (workq_exit -> "unsafe thread_call_cancel_wait"). Check RFLAGS.IF after every entry point, name
 * the call that left it clear, and turn interrupts back on.
 */
static inline bool irqs_on(void)
{
    unsigned long fl;
    __asm__ __volatile__("pushfq; popq %0" : "=r"(fl));
    return (fl & 0x200) != 0;
}

extern "C" void nmx_crit_debug(int *nest, int *saved, void **who, void **self);
static void irq_check(const char *what, unsigned long cmd)
{
    if (!irqs_on()) {
        int nest, saved; void *who, *self;
        nmx_crit_debug(&nest, &saved, &who, &self);
        IOLog("NullMoth devfs: IRQ LEAK: %s (cmd 0x%lx) returned with interrupts disabled (crit nest %d saved %d "
              "who %p, nmx_critical_enter at %p); re-enabling\n", what, cmd, nest, saved, who, self);
        __asm__ __volatile__("sti" ::: "memory");
    }
}

static int nmx_open(dev_t dev, int flags, int devtype, struct proc *p)
{
    int m = minor(dev);
    void *cookie = cookie_for_open(m, nullptr);
    if (cookie == nullptr)
        return ENXIO;
    int err = nmx_cdev_open(cookie, m, flags);
    irq_check("open", 0);
    OpenRec *rec = err ? nullptr : IONew(OpenRec, 1);
    if (rec != nullptr) {
        rec->minor = m;
        rec->pid = proc_selfpid();
        proc_selfname(rec->name, sizeof(rec->name));
        rec->task = current_task();
        task_reference(rec->task);
    }
    IOLockLock(g_lock);
    if (err)
        g_open_node[m] = 0;
    else
        g_open_active[m] = 1;
    if (rec != nullptr) {
        rec->next = g_opens;
        g_opens = rec;
    }
    IOLockUnlock(g_lock);
    return err;
}

static int nmx_close(dev_t dev, int flags, int devtype, struct proc *p)
{
    int m = minor(dev);
    int err = nmx_cdev_close(m, flags);
    irq_check("close", 0);
    OpenRec *rec = nullptr;
    bool last = false;
    IOLockLock(g_lock);
    if (m >= NODE_MINORS && m < OPEN_MINOR_MAX) {
        g_open_node[m] = 0;
        g_open_active[m] = 0;
    }
    for (OpenRec **pp = &g_opens; *pp != nullptr; pp = &(*pp)->next)
        if ((*pp)->minor == m) { rec = *pp; *pp = rec->next; break; }
    if (rec != nullptr) {
        last = true;
        for (OpenRec *o = g_opens; o != nullptr; o = o->next)
            if (o->task == rec->task) { last = false; break; }
    }
    IOLockUnlock(g_lock);
    if (rec != nullptr) {
        bool queued = false;
        if (last && opener_gone(rec, p)) {
            IOLockLock(g_lock);
            if (g_gone_n < 16) {
                GoneRec *g = &g_gone[g_gone_n++];
                g->task = rec->task;            /* the open's reference moves to the check */
                g->pid = rec->pid;
                strlcpy(g->name, rec->name, sizeof(g->name));
                queued = true;
            }
            if (g_gone_tc == nullptr)
                g_gone_tc = thread_call_allocate(gone_fire, nullptr);
            thread_call_t tc = g_gone_tc;
            IOLockUnlock(g_lock);
            if (queued && tc != nullptr) {
                uint64_t deadline;
                clock_interval_to_deadline(3, kSecondScale, &deadline);
                thread_call_enter_delayed(tc, deadline);
            }
        }
        if (!queued)
            task_deallocate(rec->task);
        IODelete(rec, OpenRec, 1);
    }
    return err;
}

static int nmx_ioctl(dev_t dev, u_long cmd, caddr_t data, int fflag, struct proc *p)
{
    int err = nmx_cdev_ioctl(minor(dev), cmd, data, fflag);
    irq_check("ioctl", cmd);
    return err;
}

/*
 * read: the driver's read handler copies straight to the caller's buffer (Linux copy_to_user), so the glue hands
 * it the current user segment of the xnu uio and advances the uio by what was read. Only user-space reads reach a
 * device node from read(2).
 */
static int nmx_read(dev_t dev, struct uio *uio, int ioflag)
{
    if (uio_resid(uio) <= 0)
        return 0;
    if (!uio_isuserspace(uio))
        return EFAULT;
    user_addr_t base = uio_curriovbase(uio);
    user_size_t len = uio_curriovlen(uio);
    size_t done = 0;
    int err = nmx_cdev_read(minor(dev), (uint64_t)base, (size_t)len, &done, (ioflag & IO_NDELAY) ? 1 : 0);
    irq_check("read", 0);
    if (done > 0)
        uio_update(uio, (user_size_t)done);
    return err;
}

/*
 * select/poll: xnu keeps struct selinfo opaque to kexts, so no waiter can be recorded. Readiness is reported from
 * the driver's own poll; a not-ready answer makes poll() fall back to its timeout. The render path does not poll.
 */
static int nmx_select(dev_t dev, int which, void *wql, struct proc *p)
{
    int events = which == FREAD ? 0x0001 /* POLLIN */ : which == FWRITE ? 0x0004 /* POLLOUT */ : 0x0002 /* POLLPRI */;
    return nmx_cdev_poll(minor(dev), events) != 0;
}

static struct cdevsw g_cdevsw = {
    /* d_open */ nmx_open,
    /* d_close */ nmx_close,
    /* d_read */ nmx_read,
    /* d_write */ eno_rdwrt,
    /* d_ioctl */ nmx_ioctl,
    /* d_stop */ eno_stop,
    /* d_reset */ eno_reset,
    /* d_ttys */ nullptr,
    /* d_select */ nmx_select,
    /* d_mmap */ eno_mmap,
    /* d_strategy */ eno_strat,
    /* d_reserved_1 */ eno_getc,
    /* d_reserved_2 */ eno_putc,
    /* d_type */ 0,
};

/* ---- nodes -------------------------------------------------------------------------------------------------------- */

extern "C" int nmx_xnu_devfs_init(void)
{
    g_lock = IOLockAlloc();
    if (g_lock == nullptr)
        return ENOMEM;
    g_major = cdevsw_add(-1, &g_cdevsw);
    if (g_major < 0) {
        IOLockFree(g_lock);
        g_lock = nullptr;
        return ENXIO;
    }
    return 0;
}

extern "C" int nmx_xnu_devfs_busy(void)
{
    int busy = 0;
    IOLockLock(g_lock);
    for (int m = NODE_MINORS; m < OPEN_MINOR_MAX; m++)
        if (g_open_node[m]) { busy++; }
    IOLockUnlock(g_lock);
    return busy;
}

extern "C" void nmx_xnu_devfs_fini(void)
{
    if (g_major >= 0)
        cdevsw_remove(g_major, &g_cdevsw);
    g_major = -1;
    if (g_lock)
        IOLockFree(g_lock);
    g_lock = nullptr;
}

extern "C" void *nmx_xnu_devfs_make(const char *path, uint32_t uid, uint32_t gid, int mode, void *cookie)
{
    if (g_major < 0)
        return nullptr;
    IOLockLock(g_lock);
    int node = -1;
    for (int i = 0; i < NODE_MINORS; i++)
        if (g_node_cookie[i] == nullptr) { node = i; g_node_cookie[i] = cookie; break; }
    IOLockUnlock(g_lock);
    if (node < 0)
        return nullptr;
    void *h = devfs_make_node_clone(makedev(g_major, node), DEVFS_CHAR, uid, gid, mode, clone_minor, "%s", path);
    IOLockLock(g_lock);
    if (h == nullptr)
        g_node_cookie[node] = nullptr;
    else {
        g_node_handle[node] = h;
        strlcpy(g_node_name[node], path, sizeof(g_node_name[node]));
    }
    IOLockUnlock(g_lock);
    return h;
}

extern "C" void nmx_xnu_devfs_remove(void *handle)
{
    if (handle == nullptr)
        return;
    devfs_remove(handle);
    IOLockLock(g_lock);
    for (int i = 0; i < NODE_MINORS; i++)
        if (g_node_handle[i] == handle) { g_node_handle[i] = nullptr; g_node_cookie[i] = nullptr; break; }
    IOLockUnlock(g_lock);
}

/* ---- user mappings of GPU memory (the mmap ioctl) ------------------------------------------------------------------ */

static IOOptionBits cache_option(int cache)
{
    switch (cache) {
    case NMX_CACHE_UC: return kIOMapInhibitCache;
    case NMX_CACHE_WC: return kIOMapWriteCombineCache;
    case NMX_CACHE_WT: return kIOMapWriteThruCache;
    default: return kIOMapDefaultCache;
    }
}

/*
 * A fixed mapping is entered over the process's own range with kIOMapOverwrite (atomic, like Linux MAP_FIXED). IOKit
 * never deallocates an overwrite mapping's range when the map is released (IOMemoryDescriptor::doUnmap), so the
 * device pages would stay visible to the process after the buffer is freed. The record therefore keeps a reference to
 * the task and removes the range itself before releasing the map.
 */
struct UserMap {
    IOMemoryMap *map;
    task_t task;            /* fixed mappings only: the task whose range is removed at unmap */
    uint64_t addr;
    uint64_t size;
    int pid;                /* v74: the census (fixed mappings, on g_maps under g_lock) */
    char name[24];
    UserMap *prev, *next;
};
static UserMap *g_maps;

extern "C" int nmx_xnu_map_user(const uint64_t *pages, size_t npages, int cache, int writable, uint64_t fixed,
                                uint64_t *uaddr, void **handle)
{
    *handle = nullptr;
    *uaddr = 0;
    if (npages == 0 || (fixed & PAGE_MASK) != 0)
        return EINVAL;
    IOAddressRange *ranges = (IOAddressRange *)IOMalloc(sizeof(IOAddressRange) * npages);
    if (ranges == nullptr)
        return ENOMEM;
    size_t n = 0;
    for (size_t i = 0; i < npages; i++) {
        if (n > 0 && ranges[n - 1].address + ranges[n - 1].length == pages[i]) {
            ranges[n - 1].length += PAGE_SIZE;
        } else {
            ranges[n].address = pages[i];
            ranges[n].length = PAGE_SIZE;
            n++;
        }
    }
    IOMemoryDescriptor *md = IOMemoryDescriptor::withAddressRanges(ranges, (UInt32)n,
                                 kIODirectionInOut | kIOMemoryTypePhysical64, nullptr);
    IOFree(ranges, sizeof(IOAddressRange) * npages);
    if (md == nullptr)
        return ENOMEM;
    UserMap *um = IONew(UserMap, 1);
    if (um == nullptr) {
        md->release();
        return ENOMEM;
    }
    IOOptionBits opts = cache_option(cache) | (writable ? 0 : kIOMapReadOnly) | (fixed ? kIOMapOverwrite : kIOMapAnywhere);
    IOMemoryMap *map = md->createMappingInTask(current_task(), fixed, opts);
    md->release();
    if (map == nullptr) {
        IODelete(um, UserMap, 1);
        return fixed ? EINVAL : ENOMEM;
    }
    um->map = map;
    um->addr = map->getAddress();
    um->size = (uint64_t)npages * PAGE_SIZE;
    um->task = nullptr;
    um->prev = um->next = nullptr;
    if (fixed) {
        um->task = current_task();
        task_reference(um->task);
        um->pid = proc_selfpid();
        proc_selfname(um->name, sizeof(um->name));
        IOLockLock(g_lock);
        um->next = g_maps;
        if (g_maps != nullptr)
            g_maps->prev = um;
        g_maps = um;
        IOLockUnlock(g_lock);
    }
    *uaddr = um->addr;
    *handle = um;
    return 0;
}

extern "C" void nmx_xnu_unmap_user(void *handle)
{
    UserMap *um = (UserMap *)handle;
    if (um == nullptr)
        return;
    if (um->task != nullptr) {
        IOLockLock(g_lock);
        if (um->prev != nullptr)
            um->prev->next = um->next;
        else
            g_maps = um->next;
        if (um->next != nullptr)
            um->next->prev = um->prev;
        IOLockUnlock(g_lock);
        /* the range goes first, while the map still holds the pages: the process never sees freed memory */
        vm_deallocate(get_task_map(um->task), (vm_offset_t)um->addr, (vm_size_t)um->size);
        task_deallocate(um->task);
    }
    um->map->release();
    IODelete(um, UserMap, 1);
}

/*
 * The DRM user client (xnu/nmx_drmuc.cpp): sandboxed processes (WindowServer) may open a DRM node read-only but not
 * issue ioctls on it, while IOKit user clients named IOAccel* are allowed. Each client is one open of a node, made and
 * driven through the same entry points as an open of the device file.
 */
extern "C" int nmx_xnu_uc_open(const char *path, int *open_minor)
{
    *open_minor = -1;
    if (g_major < 0)
        return ENXIO;
    int node = -1;
    IOLockLock(g_lock);
    for (int i = 0; i < NODE_MINORS; i++)
        if (g_node_cookie[i] != nullptr && strcmp(g_node_name[i], path) == 0) { node = i; break; }
    IOLockUnlock(g_lock);
    if (node < 0)
        return ENOENT;
    int m = clone_minor(makedev(g_major, node), DEVFS_CLONE_ALLOC);
    if (m < 0)
        return ENFILE;
    int err = nmx_open(makedev(g_major, m), FREAD | FWRITE, 0, nullptr);
    if (err == 0)
        *open_minor = m;
    return err;
}

extern "C" int nmx_xnu_uc_ioctl(int open_minor, unsigned long cmd, void *data)
{
    return nmx_ioctl(makedev(g_major, open_minor), cmd, (caddr_t)data, FREAD | FWRITE, nullptr);
}

extern "C" void nmx_xnu_uc_close(int open_minor)
{
    nmx_close(makedev(g_major, open_minor), FREAD | FWRITE, 0, nullptr);
}

/* v74: the census's devfs half (nmx_mm.cpp): fixed mappings and opens, by task */
extern "C" void nmx_xnu_devfs_census(void *ctx)
{
    if (g_lock == nullptr)
        return;
    IOLockLock(g_lock);
    for (UserMap *um = g_maps; um != nullptr; um = um->next)
        nmx_xnu_census_add(ctx, um->task, um->pid, um->name, 2, 0);
    for (OpenRec *o = g_opens; o != nullptr; o = o->next)
        nmx_xnu_census_add(ctx, o->task, o->pid, o->name, 3, 0);
    IOLockUnlock(g_lock);
}
