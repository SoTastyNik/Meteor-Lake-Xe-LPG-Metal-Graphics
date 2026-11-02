/*
 * Reading and writing another process's memory from a driver thread. Compiled with Apple's headers only.
 *
 * Linux drivers do this with kthread_use_mm() followed by copy_to_user(): the worker borrows the process's address
 * space. xnu has no such borrowing for a kext, so the port remembers each mm's Mach task (recorded on the process's
 * own thread when the mm is created) and copies through an IOMemoryDescriptor over the user range in that task,
 * which wires the pages for the duration of the copy. When the caller is already that process, plain copyin/copyout
 * is used.
 *
 * Each record holds a reference on its task. The mm can outlive the process (xe's userptr notifier keeps it), and a
 * worker then wiring through a bare task pointer walked a destroyed vm_map (panic in vm_map_copy_extract: invalid
 * RWLock), or a different process's map once the pointer was reused. With the reference the exited task and its
 * emptied map stay valid, and the wiring fails with EFAULT. Lookups hand out a reference of their own, so a record
 * forgotten meanwhile cannot free the task under the caller.
 */
#include <IOKit/IOMemoryDescriptor.h>
#include <IOKit/IOLib.h>
#include <sys/errno.h>
#include <sys/systm.h>
#include <kern/task_ref.h>
#include "nmx_xnu.h"

namespace {
struct MmTask {
    void *mm;
    task_t task;
    MmTask *next;
};
MmTask *gList;
IOLock *gLock;

IOLock *lock()
{
    if (gLock == nullptr) {
        IOLock *l = IOLockAlloc();
        if (!OSCompareAndSwapPtr(nullptr, l, (void * volatile *)&gLock))
            IOLockFree(l);
    }
    return gLock;
}

/* mm's task with a reference the caller drops with task_deallocate, or nullptr */
task_t find_ref(void *mm)
{
    task_t task = nullptr;
    IOLockLock(lock());
    for (MmTask *e = gList; e != nullptr; e = e->next)
        if (e->mm == mm) {
            task = e->task;
            task_reference(task);
            break;
        }
    IOLockUnlock(gLock);
    return task;
}
}

extern "C" void nmx_xnu_mm_note_task(void *mm)
{
    MmTask *e = IONew(MmTask, 1);
    if (e == nullptr)
        return;     /* the copy helpers then report EFAULT for this process: nothing is written blindly */
    e->mm = mm;
    e->task = current_task();
    task_reference(e->task);
    IOLockLock(lock());
    e->next = gList;
    gList = e;
    IOLockUnlock(gLock);
}

extern "C" void nmx_xnu_mm_forget(void *mm)
{
    IOLockLock(lock());
    for (MmTask **pp = &gList; *pp != nullptr; pp = &(*pp)->next) {
        if ((*pp)->mm == mm) {
            MmTask *e = *pp;
            *pp = e->next;
            IOLockUnlock(gLock);
            task_deallocate(e->task);
            IODelete(e, MmTask, 1);
            return;
        }
    }
    IOLockUnlock(gLock);
}

extern "C" int nmx_xnu_mm_copy(void *mm, uint64_t uaddr, void *kbuf, size_t len, int to_user)
{
    if (len == 0)
        return 0;
    task_t task = find_ref(mm);
    if (task == nullptr)
        return EFAULT;

    int err = EFAULT;
    if (task == current_task()) {
        err = to_user ? copyout(kbuf, (user_addr_t)uaddr, len) : copyin((user_addr_t)uaddr, kbuf, len);
    } else {
        IOMemoryDescriptor *md = IOMemoryDescriptor::withAddressRange((mach_vm_address_t)uaddr, len,
                                                                      kIODirectionOutIn, task);
        if (md == nullptr) {
            err = ENOMEM;
        } else {
            if (md->prepare() == kIOReturnSuccess) {
                IOByteCount done = to_user ? md->writeBytes(0, kbuf, len) : md->readBytes(0, kbuf, len);
                md->complete();
                err = done == len ? 0 : EFAULT;
            }
            md->release();
        }
    }
    task_deallocate(task);
    return err;
}

namespace {
/* a wired user range: the descriptor and the task reference that keeps its map valid until unwire */
struct UserWire {
    IOMemoryDescriptor *md;
    task_t task;
    size_t npages;
};
/* live user wirings, to tell a pin leak from a range that went away when xnu refuses one (kIOReturnCannotWire) */
SInt64 g_user_wired_pages, g_user_wired_ranges, g_user_wires_total, g_user_wired_peak;
}

extern "C" int nmx_xnu_user_wire(void *mm, uint64_t uaddr, size_t npages, int write, uint64_t *phys, void **handle)
{
    *handle = nullptr;
    if (npages == 0)
        return 0;
    if ((uaddr & PAGE_MASK) != 0)
        return EINVAL;
    task_t task = current_task();
    if (mm != nullptr) {
        task = find_ref(mm);
        if (task == nullptr)
            return EFAULT;
    } else {
        task_reference(task);
    }
    UserWire *w = IONew(UserWire, 1);
    if (w == nullptr) {
        task_deallocate(task);
        return ENOMEM;
    }
    /* the device writes the pages when the mapping is writable (kIODirectionIn), and always reads them */
    IOMemoryDescriptor *md = IOMemoryDescriptor::withAddressRange((mach_vm_address_t)uaddr, npages * PAGE_SIZE,
                                                                  write ? kIODirectionOutIn : kIODirectionOut, task);
    IOReturn pr = md != nullptr ? md->prepare() : kIOReturnNoMemory;
    if (md != nullptr && pr != kIOReturnSuccess && write) {
        /*
         * A range this task may only read (WindowServer's mapping of a full-screen IOSurface another process renders
         * into) cannot be wired for writing; the GPU still needs its pages. Wired for reading, the physical pages are
         * the same ones the surface's owner writes.
         */
        md->release();
        md = IOMemoryDescriptor::withAddressRange((mach_vm_address_t)uaddr, npages * PAGE_SIZE, kIODirectionOut, task);
        IOReturn pr2 = md != nullptr ? md->prepare() : kIOReturnNoMemory;
        IOLog("NullMoth GPU: wiring 0x%llx + %lu pages for writing failed (0x%x); for reading: 0x%x\n",
              (unsigned long long)uaddr, (unsigned long)npages, pr, pr2);
        pr = pr2;
    }
    if (md != nullptr && pr != kIOReturnSuccess)
        IOLog("NullMoth GPU: wiring 0x%llx + %lu pages refused (0x%x) with %lld ranges / %lld pages (%lld MB) wired, "
              "peak %lld pages, %lld wired so far\n", (unsigned long long)uaddr, (unsigned long)npages, pr,
              (long long)g_user_wired_ranges, (long long)g_user_wired_pages, (long long)(g_user_wired_pages >> 8),
              (long long)g_user_wired_peak, (long long)g_user_wires_total);
    int err = md == nullptr ? ENOMEM : pr != kIOReturnSuccess ? EFAULT : 0;
    for (size_t i = 0; err == 0 && i < npages; i++) {
        IOByteCount len = 0;
        addr64_t pa = md->getPhysicalSegment(i * PAGE_SIZE, &len, kIOMemoryMapperNone);
        if (pa == 0) {
            md->complete();
            err = EFAULT;
        }
        phys[i] = pa;
    }
    if (err != 0) {
        if (md != nullptr)
            md->release();
        task_deallocate(task);
        IODelete(w, UserWire, 1);
        return err;
    }
    w->md = md;
    w->task = task;
    w->npages = npages;
    *handle = w;
    SInt64 live = __atomic_add_fetch(&g_user_wired_pages, (SInt64)npages, __ATOMIC_RELAXED);
    __atomic_add_fetch(&g_user_wired_ranges, 1, __ATOMIC_RELAXED);
    if (live > g_user_wired_peak)
        g_user_wired_peak = live;
    if ((__atomic_add_fetch(&g_user_wires_total, 1, __ATOMIC_RELAXED) & 511) == 0)
        IOLog("NullMoth GPU: user wirings: %lld ranges / %lld pages (%lld MB) live, peak %lld pages, %lld so far\n",
              (long long)g_user_wired_ranges, (long long)live, (long long)(live >> 8), (long long)g_user_wired_peak,
              (long long)g_user_wires_total);
    return 0;
}

/* What a GPU submission costs: Mesa lists every memory object of the device in each execbuffer, so WindowServer's
   imported surfaces can make the ioctl grow with the number of windows */
extern "C" uint64_t nmx_xnu_execbuf_begin(void)
{
    return mach_absolute_time();
}

static uint64_t s_phase_ns[8], s_phase_max[8];

/* an integer sysctl another kext publishes (NMXAccel's debug.nmxgpu_*), -1 when it is not there */
extern "C" int sysctlbyname(const char *name, void *oldp, size_t *oldlenp, void *newp, size_t newlen);
extern "C" int nmx_xnu_tunable(const char *name)
{
    int v = 0;
    size_t n = sizeof v;
    return sysctlbyname(name, &v, &n, nullptr, 0) == 0 && n == sizeof v ? v : -1;
}
static uint64_t s_vma_ns[3], s_vma_max[3], s_vma_bytes, s_vma_binds, s_vma_userptr, s_vma_user_bytes;

/* A vma's first binding, the slow path of a pin: 0 its pages, 1 page table allocation, 2 the binding */
extern "C" void nmx_xnu_vma_stage(int stage, uint64_t *t)
{
    const uint64_t now = mach_absolute_time();
    uint64_t ns = 0;
    absolutetime_to_nanoseconds(now - *t, &ns);
    *t = now;
    __atomic_add_fetch(&s_vma_ns[stage], ns, __ATOMIC_RELAXED);
    if (ns > s_vma_max[stage])
        s_vma_max[stage] = ns;
}

extern "C" void nmx_xnu_vma_done(uint64_t bytes, int userptr)
{
    __atomic_add_fetch(&s_vma_bytes, bytes, __ATOMIC_RELAXED);
    if (userptr) {
        __atomic_add_fetch(&s_vma_userptr, 1, __ATOMIC_RELAXED);
        __atomic_add_fetch(&s_vma_user_bytes, bytes, __ATOMIC_RELAXED);
    }
    const uint64_t n = __atomic_add_fetch(&s_vma_binds, 1, __ATOMIC_RELAXED);
    if (n & 255)
        return;
    const uint64_t all = __atomic_exchange_n(&s_vma_bytes, 0, __ATOMIC_RELAXED);
    const uint64_t user = __atomic_exchange_n(&s_vma_userptr, 0, __ATOMIC_RELAXED);
    const uint64_t userBytes = __atomic_exchange_n(&s_vma_user_bytes, 0, __ATOMIC_RELAXED);
    uint64_t avg[3], top[3];
    for (int i = 0; i < 3; i++) {
        avg[i] = __atomic_exchange_n(&s_vma_ns[i], 0, __ATOMIC_RELAXED) / 256000;
        top[i] = __atomic_exchange_n(&s_vma_max[i], 0, __ATOMIC_RELAXED) / 1000;
    }
    IOLog("NullMoth GPU: execbuffer new bindings: 256 of %llu, %llu MB, %llu userptr (%llu MB); us avg/max: pages %llu/%llu tables %llu/%llu bind %llu/%llu\n",
          (unsigned long long)n, (unsigned long long)(all >> 20), (unsigned long long)user,
          (unsigned long long)(userBytes >> 20), (unsigned long long)avg[0], (unsigned long long)top[0],
          (unsigned long long)avg[1], (unsigned long long)top[1], (unsigned long long)avg[2], (unsigned long long)top[2]);
}

/* the time since *t goes to a phase: 0 object lookup, 1 engine pin and ring throttle, 2 object locks, 3 vma pins, 4 reserve and
   parse, 5 request, 6 move to GPU, 7 add to the engine */
extern "C" void nmx_xnu_execbuf_mark(int phase, uint64_t *t)
{
    const uint64_t now = mach_absolute_time();
    uint64_t ns = 0;
    absolutetime_to_nanoseconds(now - *t, &ns);
    *t = now;
    __atomic_add_fetch(&s_phase_ns[phase], ns, __ATOMIC_RELAXED);
    if (ns > s_phase_max[phase])
        s_phase_max[phase] = ns;
}

extern "C" void nmx_xnu_execbuf_end(uint64_t t0, unsigned objects)
{
    static uint64_t s_calls, s_objects, s_ns, s_max;
    uint64_t ns = 0;
    absolutetime_to_nanoseconds(mach_absolute_time() - t0, &ns);
    __atomic_add_fetch(&s_objects, objects, __ATOMIC_RELAXED);
    __atomic_add_fetch(&s_ns, ns, __ATOMIC_RELAXED);
    if (ns > s_max)
        s_max = ns;
    const uint64_t calls = __atomic_add_fetch(&s_calls, 1, __ATOMIC_RELAXED);
    if ((calls & 1023) == 0) {
        const uint64_t objs = __atomic_exchange_n(&s_objects, 0, __ATOMIC_RELAXED);
        const uint64_t total = __atomic_exchange_n(&s_ns, 0, __ATOMIC_RELAXED);
        const uint64_t max = __atomic_exchange_n(&s_max, 0, __ATOMIC_RELAXED);
        IOLog("NullMoth GPU: execbuffer stats: last 1024 of %llu: %llu objects each, %llu us each, %llu us at most\n",
              (unsigned long long)calls, (unsigned long long)(objs / 1024), (unsigned long long)(total / 1024000),
              (unsigned long long)(max / 1000));
        uint64_t avg[8], top[8];
        for (int i = 0; i < 8; i++) {
            avg[i] = __atomic_exchange_n(&s_phase_ns[i], 0, __ATOMIC_RELAXED) / 1024000;
            top[i] = __atomic_exchange_n(&s_phase_max[i], 0, __ATOMIC_RELAXED) / 1000;
        }
        IOLog("NullMoth GPU: execbuffer phases, us avg/max: lookup %llu/%llu throttle %llu/%llu lock %llu/%llu pin %llu/%llu "
              "parse %llu/%llu request %llu/%llu move %llu/%llu add %llu/%llu\n",
              (unsigned long long)avg[0], (unsigned long long)top[0], (unsigned long long)avg[1], (unsigned long long)top[1],
              (unsigned long long)avg[2], (unsigned long long)top[2], (unsigned long long)avg[3], (unsigned long long)top[3],
              (unsigned long long)avg[4], (unsigned long long)top[4], (unsigned long long)avg[5], (unsigned long long)top[5],
              (unsigned long long)avg[6], (unsigned long long)top[6], (unsigned long long)avg[7], (unsigned long long)top[7]);
    }
}

extern "C" void nmx_xnu_user_unwire(void *handle)
{
    UserWire *w = (UserWire *)handle;
    if (w == nullptr)
        return;
    w->md->complete();
    w->md->release();
    task_deallocate(w->task);
    __atomic_sub_fetch(&g_user_wired_pages, (SInt64)w->npages, __ATOMIC_RELAXED);
    __atomic_sub_fetch(&g_user_wired_ranges, 1, __ATOMIC_RELAXED);
    IODelete(w, UserWire, 1);
}
