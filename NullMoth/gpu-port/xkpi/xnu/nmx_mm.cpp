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
#include <sys/proc.h>
#include <kern/task_ref.h>
#include <kern/thread_call.h>
#include <kern/clock.h>
#include <libkern/OSAtomic.h>
#include "nmx_xnu.h"

namespace {
struct MmTask {
    void *mm;
    task_t task;            /* nullptr once the process is gone (nmx_xnu_task_gone) */
    int pid;                /* v74: who, for the census */
    char name[24];
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
            if (task != nullptr)
                task_reference(task);
            break;
        }
    IOLockUnlock(gLock);
    return task;
}
}

static void mm_sweep_start(void);
extern "C" void nmx_xnu_mm_note_task(void *mm)
{
    MmTask *e = IONew(MmTask, 1);
    if (e == nullptr)
        return;     /* the copy helpers then report EFAULT for this process: nothing is written blindly */
    e->mm = mm;
    e->task = current_task();
    e->pid = proc_selfpid();
    proc_selfname(e->name, sizeof(e->name));
    task_reference(e->task);
    IOLockLock(lock());
    e->next = gList;
    gList = e;
    IOLockUnlock(gLock);
    mm_sweep_start();
}

extern "C" void nmx_xnu_mm_forget(void *mm)
{
    IOLockLock(lock());
    for (MmTask **pp = &gList; *pp != nullptr; pp = &(*pp)->next) {
        if ((*pp)->mm == mm) {
            MmTask *e = *pp;
            *pp = e->next;
            IOLockUnlock(gLock);
            if (e->task != nullptr)
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
/*
 * a wired user range: the descriptor, wired by prepare() until complete(). v74_1: no task reference past the wiring
 * (as WTLIntelGfx's xg_vm_x_hold_user): the descriptor's wiring is its UPLs, which need neither the task nor its map
 * to be undone, and a reference held until the buffer went kept an exited process's task, and with it the task's
 * port, alive: launchd tears a process's domain down (a login session's with loginwindow's) only when that port dies.
 * task is kept as the owner's identity for the census only.
 */
struct UserWire {
    IOMemoryDescriptor *md;
    task_t task;
    size_t npages;
    int pid;                /* v74: the census */
    char name[24];
    UserWire *prev, *next;
};
UserWire *gWires;           /* under lock() */
/* live user wirings, to tell a pin leak from a range that went away when xnu refuses one (kIOReturnCannotWire) */
SInt64 g_user_wired_pages, g_user_wired_ranges, g_user_wires_total, g_user_wired_peak;
}

/* v78 (nmx_surfsync.cpp): the IOSurface memory announced for a host import, or nullptr */
extern "C" void *nmx_xnu_surf_expect_take(void *task, uint64_t uaddr, uint64_t len, uint64_t *offset, uint32_t *id);
static SInt64 g_surface_wires, g_surface_wire_us;
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
    /* v78: an IOSurface's mapping the plugin announced: the surface's own memory, no wiring of the user range */
    uint64_t soff = 0;
    uint32_t sid = 0;
    const uint64_t ts = mach_absolute_time();
    IOMemoryDescriptor *md = (IOMemoryDescriptor *)nmx_xnu_surf_expect_take(task, uaddr, npages * PAGE_SIZE, &soff, &sid);
    IOReturn pr = kIOReturnNoMemory;
    if (md != nullptr) {
        pr = md->prepare();
        if (pr != kIOReturnSuccess) {
            IOLog("NullMoth GPU: IOSurface %u's memory refused a prepare (0x%x): its mapping is wired instead\n", sid, pr);
            md->release();
            md = nullptr;
            soff = 0;
        }
    }
    const bool surface = md != nullptr;
    /* the device writes the pages when the mapping is writable (kIODirectionIn), and always reads them */
    if (!surface) {
        md = IOMemoryDescriptor::withAddressRange((mach_vm_address_t)uaddr, npages * PAGE_SIZE,
                                                  write ? kIODirectionOutIn : kIODirectionOut, task);
        pr = md != nullptr ? md->prepare() : kIOReturnNoMemory;
    }
    if (!surface && md != nullptr && pr != kIOReturnSuccess && write) {
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
    for (size_t i = 0; err == 0 && i < npages;) {
        IOByteCount len = 0;
        addr64_t pa = md->getPhysicalSegment(soff + i * PAGE_SIZE, &len, kIOMemoryMapperNone);
        if (pa == 0) {
            md->complete();
            err = EFAULT;
            break;
        }
        /* a physically contiguous run answers for all its pages */
        for (IOByteCount o = 0; i < npages && (o == 0 || o < len); o += PAGE_SIZE)
            phys[i++] = pa + o;
    }
    if (surface && err == 0) {
        uint64_t ns = 0;
        absolutetime_to_nanoseconds(mach_absolute_time() - ts, &ns);
        const SInt64 n = OSAddAtomic64(1, &g_surface_wires) + 1;
        const SInt64 us = OSAddAtomic64((SInt64)(ns / 1000), &g_surface_wire_us) + (SInt64)(ns / 1000);
        if (n <= 8 || (n & 255) == 0)
            IOLog("NullMoth GPU: wiring 0x%llx + %lu pages from IOSurface %u's own memory: %llu us (%lld such, %lld us avg)\n",
                  (unsigned long long)uaddr, (unsigned long)npages, sid, (unsigned long long)(ns / 1000), (long long)n,
                  (long long)(us / n));
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
    w->pid = -1;
    w->name[0] = 0;
    IOLockLock(lock());
    if (mm == nullptr) {
        w->pid = proc_selfpid();
        proc_selfname(w->name, sizeof(w->name));
    } else {
        for (MmTask *e = gList; e != nullptr; e = e->next)
            if (e->mm == mm) { w->pid = e->pid; strlcpy(w->name, e->name, sizeof(w->name)); break; }
    }
    w->prev = nullptr;
    w->next = gWires;
    if (gWires != nullptr)
        gWires->prev = w;
    gWires = w;
    IOLockUnlock(gLock);
    task_deallocate(task);              /* the wiring stands without it; w->task is only a name from here on */
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
/* v84: inside the pin and add phases: 0 the vma pins, 1 the fence slot reservations, 2 request commit, 3 request queue
   (to the GuC), 4 retiring the timeline's finished requests, 5 the timeline unlock; and counts: 0 vma pins that missed
   the quick path, 1 fence slot reservations over 20 us (the list had to grow). v84_1: 6 the GuC doorbell writes (any
   H2G, intel_guc_notify), count 2 those over 20 us (the GT woken first) */
static uint64_t s_sub_ns[7], s_sub_max[7], s_sub_cnt[3];
extern "C" uint64_t nmx_xnu_execbuf_sub(int k, uint64_t *t)
{
    const uint64_t now = mach_absolute_time();
    uint64_t ns = 0;
    absolutetime_to_nanoseconds(now - *t, &ns);
    *t = now;
    __atomic_add_fetch(&s_sub_ns[k], ns, __ATOMIC_RELAXED);
    if (ns > s_sub_max[k])
        s_sub_max[k] = ns;
    return ns;
}
extern "C" void nmx_xnu_execbuf_count(int k)
{
    __atomic_add_fetch(&s_sub_cnt[k], 1, __ATOMIC_RELAXED);
}
static uint64_t s_vma_ns[3], s_vma_max[3], s_vma_bytes, s_vma_binds, s_vma_userptr, s_vma_user_bytes;
static uint64_t s_vma_sizes[6];   /* <64K <256K <1M <4M <16M 16M+ */

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
    const int bucket = bytes < (64ull << 10) ? 0 : bytes < (256ull << 10) ? 1 : bytes < (1ull << 20) ? 2
                     : bytes < (4ull << 20) ? 3 : bytes < (16ull << 20) ? 4 : 5;
    __atomic_add_fetch(&s_vma_sizes[bucket], 1, __ATOMIC_RELAXED);
    const uint64_t n = __atomic_add_fetch(&s_vma_binds, 1, __ATOMIC_RELAXED);
    if (n & 255)
        return;
    uint64_t sizes[6];
    for (int i = 0; i < 6; i++)
        sizes[i] = __atomic_exchange_n(&s_vma_sizes[i], 0, __ATOMIC_RELAXED);
    const uint64_t all = __atomic_exchange_n(&s_vma_bytes, 0, __ATOMIC_RELAXED);
    const uint64_t user = __atomic_exchange_n(&s_vma_userptr, 0, __ATOMIC_RELAXED);
    const uint64_t userBytes = __atomic_exchange_n(&s_vma_user_bytes, 0, __ATOMIC_RELAXED);
    uint64_t avg[3], top[3];
    for (int i = 0; i < 3; i++) {
        avg[i] = __atomic_exchange_n(&s_vma_ns[i], 0, __ATOMIC_RELAXED) / 256000;
        top[i] = __atomic_exchange_n(&s_vma_max[i], 0, __ATOMIC_RELAXED) / 1000;
    }
    IOLog("NullMoth GPU: execbuffer new bindings: 256 of %llu, %llu MB, %llu userptr (%llu MB); us avg/max: pages %llu/%llu tables %llu/%llu bind %llu/%llu; "
          "sizes <64K %llu <256K %llu <1M %llu <4M %llu <16M %llu 16M+ %llu\n",
          (unsigned long long)n, (unsigned long long)(all >> 20), (unsigned long long)user,
          (unsigned long long)(userBytes >> 20), (unsigned long long)avg[0], (unsigned long long)top[0],
          (unsigned long long)avg[1], (unsigned long long)top[1], (unsigned long long)avg[2], (unsigned long long)top[2],
          (unsigned long long)sizes[0], (unsigned long long)sizes[1], (unsigned long long)sizes[2], (unsigned long long)sizes[3],
          (unsigned long long)sizes[4], (unsigned long long)sizes[5]);
}

/*
 * v46: where a large object's first binding goes. Opening a Launchpad folder bound new 16-25 MB objects whose "pages"
 * took up to 64 ms each (285 ms execbuffers). Parts of i915's get_pages, summed until the binding reports: 0 page
 * allocation (shmem) or the page list (userptr), 1 dma mapping, 2 set_pages (the clflush of a new object); a userptr's
 * pinning happens earlier, in execbuffer's lookup, and is logged by itself. Not thread-safe: diagnostics only.
 */
static uint64_t s_pg_part[3];
extern "C" void nmx_xnu_pages_part(int part, uint64_t *t)
{
    const uint64_t now = mach_absolute_time();
    uint64_t ns = 0;
    absolutetime_to_nanoseconds(now - *t, &ns);
    if (part >= 0 && part < 3)
        s_pg_part[part] += ns;
    *t = now;
}
extern "C" void nmx_xnu_pages_reset(void)
{
    s_pg_part[0] = s_pg_part[1] = s_pg_part[2] = 0;
}
extern "C" void nmx_xnu_vma_big(uint64_t bytes, int userptr, uint64_t t0, uint64_t tpages)
{
    static int logs;
    if (bytes < (8ull << 20) || logs >= 400)
        return;
    logs++;
    uint64_t pages = 0, total = 0;
    absolutetime_to_nanoseconds(tpages - t0, &pages);
    absolutetime_to_nanoseconds(mach_absolute_time() - t0, &total);
    IOLog("NullMoth GPU: new binding %llu MB %s: pages %llu us (alloc %llu, dma %llu, set+clflush %llu), total %llu us\n",
          (unsigned long long)(bytes >> 20), userptr ? "userptr" : "shmem", (unsigned long long)(pages / 1000),
          (unsigned long long)(s_pg_part[0] / 1000), (unsigned long long)(s_pg_part[1] / 1000),
          (unsigned long long)(s_pg_part[2] / 1000), (unsigned long long)(total / 1000));
}
/* v50: the phases of the last user pin (nmx_user_pages_pin: wire, page records, pin lists) for the "userptr pin" line */
static uint64_t s_pin_part[3];
static int s_pin_fresh;
static unsigned s_pin_records;
static uint64_t s_pin_reclaimed;
extern "C" void nmx_xnu_pin_parts(uint64_t t0, uint64_t t1, uint64_t t2, uint64_t t3, int fresh, unsigned records,
                                  uint64_t reclaimed)
{
    s_pin_reclaimed = reclaimed;
    absolutetime_to_nanoseconds(t1 - t0, &s_pin_part[0]);
    absolutetime_to_nanoseconds(t2 - t1, &s_pin_part[1]);
    absolutetime_to_nanoseconds(t3 - t2, &s_pin_part[2]);
    s_pin_fresh = fresh;
    s_pin_records = records;
}
extern "C" void nmx_xnu_pin_done(uint64_t bytes, uint64_t t0)
{
    static int logs;
    if (bytes < (8ull << 20) || logs >= 200)
        return;
    logs++;
    uint64_t ns = 0;
    absolutetime_to_nanoseconds(mach_absolute_time() - t0, &ns);
    IOLog("NullMoth GPU: userptr pin %llu MB: %llu us (wire %llu, page records %llu with %d new of %u, %llu freed so far, "
          "pin lists %llu)\n",
          (unsigned long long)(bytes >> 20), (unsigned long long)(ns / 1000), (unsigned long long)(s_pin_part[0] / 1000),
          (unsigned long long)(s_pin_part[1] / 1000), s_pin_fresh, s_pin_records, (unsigned long long)s_pin_reclaimed,
          (unsigned long long)(s_pin_part[2] / 1000));
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
        uint64_t sa[7], st[7], sc[3];
        for (int i = 0; i < 7; i++) {
            sa[i] = __atomic_exchange_n(&s_sub_ns[i], 0, __ATOMIC_RELAXED) / 1024000;
            st[i] = __atomic_exchange_n(&s_sub_max[i], 0, __ATOMIC_RELAXED) / 1000;
        }
        for (int i = 0; i < 3; i++) sc[i] = __atomic_exchange_n(&s_sub_cnt[i], 0, __ATOMIC_RELAXED);
        IOLog("NullMoth GPU: execbuffer detail, us avg/max: vma pins %llu/%llu fence reserve %llu/%llu commit %llu/%llu "
              "queue %llu/%llu retire %llu/%llu unlock %llu/%llu doorbell %llu/%llu; per 1024 calls: slow vma pins %llu, "
              "fence reserves over 20 us %llu, slow doorbells %llu\n",
              (unsigned long long)sa[0], (unsigned long long)st[0], (unsigned long long)sa[1], (unsigned long long)st[1],
              (unsigned long long)sa[2], (unsigned long long)st[2], (unsigned long long)sa[3], (unsigned long long)st[3],
              (unsigned long long)sa[4], (unsigned long long)st[4], (unsigned long long)sa[5], (unsigned long long)st[5],
              (unsigned long long)sa[6], (unsigned long long)st[6],
              (unsigned long long)sc[0], (unsigned long long)sc[1], (unsigned long long)sc[2]);
    }
}

extern "C" void nmx_xnu_user_unwire(void *handle)
{
    UserWire *w = (UserWire *)handle;
    if (w == nullptr)
        return;
    IOLockLock(lock());
    if (w->prev != nullptr)
        w->prev->next = w->next;
    else
        gWires = w->next;
    if (w->next != nullptr)
        w->next->prev = w->prev;
    IOLockUnlock(gLock);
    w->md->complete();
    w->md->release();
    __atomic_sub_fetch(&g_user_wired_pages, (SInt64)w->npages, __ATOMIC_RELAXED);
    __atomic_sub_fetch(&g_user_wired_ranges, 1, __ATOMIC_RELAXED);
    IODelete(w, UserWire, 1);
}

/*
 * v74: tasks a process left behind. xnu destroys a task's port only when the last reference to the task goes, and
 * launchd tears a process's domain down when that port dies; a login session's domain goes with loginwindow's. On
 * accelerated boots the login after a logout waited forever for the previous session (v70..v73): loginwindow had
 * exited (it draws the login window through Metal), launchd never cleaned up after it. The port holds task references
 * here (the mm records, the wirings) and in nmx_devfs.cpp (fixed mappings, opens).
 *
 * nmx_xnu_task_gone: the process is gone (its last DRM open closed after it exited): its mm record lets the task go.
 * The record then answers EFAULT to a worker copying into that process, as for an unknown mm.
 */
extern "C" int nmx_xnu_task_gone(task_t task)
{
    task_t drop[8];
    int n = 0;
    IOLockLock(lock());
    for (MmTask *e = gList; e != nullptr && n < 8; e = e->next)
        if (e->task == task) {
            drop[n++] = e->task;
            e->task = nullptr;
        }
    IOLockUnlock(gLock);
    for (int i = 0; i < n; i++)
        task_deallocate(drop[i]);
    return n;
}

/*
 * v76_1: a process can own an mm record without ever opening a DRM node: the first of its threads to enter the port (an
 * IOKit call into NMXGPU on its behalf) makes its LinuxKPI current and mm (linux_alloc_current), and only the last DRM
 * close of a gone process let the record's task go (nmx_devfs.cpp). loginwindow had such a record and no open (11-22,
 * v76): after the logout its task stayed referenced, so its task port never died, launchd kept the old gui/501 session
 * for it and logging in again spun forever ("Active GUI session already exists for user, pending request"). Opens a
 * process never closed (IOKit clients of processes that died) held their tasks the same way.
 *
 * Every 2 s, records of processes that are gone - their pid not found, or exiting - let their tasks go, here and in
 * the opens (nmx_xnu_devfs_sweep). A live process is always found under its pid, so it never loses its task here; a
 * pid reused meanwhile only delays the release. kernel_task (pid 0) is never swept.
 */
extern "C" int nmx_xnu_devfs_sweep(void);
extern "C" int nmx_xnu_uc_sweep(void);   /* v77, nmx_drmuc.cpp: DRM user clients of gone processes */
static thread_call_t gSweep;
static UInt32 gSweepStop;   /* __atomic: no new kernel import */
static struct { task_t task; int pid; char name[24]; } gSweepRow[128];   /* mm_sweep only: one run at a time */

extern "C" int nmx_xnu_pid_gone(int pid)
{
    if (pid <= 0)
        return 0;
    proc_t p = proc_find(pid);
    if (p == nullptr)
        return 1;
    const int gone = proc_exiting(p) != 0;
    proc_rele(p);
    return gone;
}

static void mm_sweep_arm(void)
{
    if (gSweep == nullptr || __atomic_load_n(&gSweepStop, __ATOMIC_ACQUIRE))
        return;
    uint64_t deadline;
    clock_interval_to_deadline(2, kSecondScale, &deadline);
    thread_call_enter_delayed(gSweep, deadline);
}

static void mm_sweep(thread_call_param_t, thread_call_param_t)
{
    int n = 0;
    IOLockLock(lock());
    for (MmTask *e = gList; e != nullptr && n < 128; e = e->next)
        if (e->task != nullptr && e->pid > 0) {
            gSweepRow[n].task = e->task;
            task_reference(e->task);
            gSweepRow[n].pid = e->pid;
            strlcpy(gSweepRow[n].name, e->name, sizeof(gSweepRow[n].name));
            n++;
        }
    IOLockUnlock(gLock);
    for (int i = 0; i < n; i++) {
        if (nmx_xnu_pid_gone(gSweepRow[i].pid) && nmx_xnu_task_gone(gSweepRow[i].task) > 0) {
            static SInt32 said;
            if (OSIncrementAtomic(&said) < 16)
                IOLog("NullMoth GPU: pid %d (%s) is gone and its mm record still held its task (no last DRM close): "
                      "let go\n", gSweepRow[i].pid, gSweepRow[i].name);
        }
        task_deallocate(gSweepRow[i].task);
        gSweepRow[i].task = nullptr;
    }
    nmx_xnu_uc_sweep();
    nmx_xnu_devfs_sweep();
    mm_sweep_arm();
}

static void mm_sweep_start(void)
{
    if (gSweep != nullptr || __atomic_load_n(&gSweepStop, __ATOMIC_ACQUIRE))
        return;
    thread_call_t tc = thread_call_allocate(mm_sweep, nullptr);
    if (tc == nullptr)
        return;
    if (!OSCompareAndSwapPtr(nullptr, tc, (void * volatile *)&gSweep)) {
        thread_call_free(tc);
        return;
    }
    mm_sweep_arm();
}

/* unload: no sweep runs after this. thread_call_cancel_wait is not exported to kexts (nmx_fb.cpp): cancel and retry
   the free until a run in progress is out; with the stop flag set it arms no next one */
extern "C" void nmx_xnu_mm_fini(void)
{
    __atomic_store_n(&gSweepStop, 1, __ATOMIC_RELEASE);
    thread_call_t tc = gSweep;
    if (tc == nullptr)
        return;
    thread_call_cancel(tc);
    while (!thread_call_free(tc)) { thread_call_cancel(tc); IOSleep(5); }
    gSweep = nullptr;
}

namespace {
struct CensusRow {
    task_t task;
    int pid;
    char name[24];
    unsigned mm, wires, maps, opens;
    uint64_t pages;
};
struct Census {
    CensusRow row[64];
    int n;
    task_t only;            /* one task, or nullptr for all */
};
}

/* one reference of kind 0 mm record, 1 wiring (amount pages), 2 fixed mapping, 3 open */
extern "C" void nmx_xnu_census_add(void *ctx, task_t task, int pid, const char *name, int kind, uint64_t amount)
{
    Census *c = (Census *)ctx;
    if (task == nullptr || (c->only != nullptr && task != c->only))
        return;
    CensusRow *r = nullptr;
    for (int i = 0; i < c->n; i++)
        if (c->row[i].task == task) { r = &c->row[i]; break; }
    if (r == nullptr) {
        if (c->n == 64)
            return;
        r = &c->row[c->n++];
        bzero(r, sizeof(*r));
        r->task = task;
        r->pid = pid;
        strlcpy(r->name, name != nullptr ? name : "?", sizeof(r->name));
    }
    if (kind == 0) r->mm++;
    else if (kind == 1) { r->wires++; r->pages += amount; }
    else if (kind == 2) r->maps++;
    else r->opens++;
}

extern "C" void nmx_xnu_devfs_census(void *ctx);

/* whether pid is still the process that name was recorded for */
static bool census_alive(int pid, const char *name)
{
    if (pid <= 0)
        return false;
    proc_t p = proc_find(pid);
    if (p == nullptr)
        return false;
    char now[24];
    proc_name(pid, now, sizeof(now));
    const bool alive = !proc_exiting(p) && strncmp(now, name, sizeof(now)) == 0;
    proc_rele(p);
    return alive;
}

static void census_fill(Census *c)
{
    IOLockLock(lock());
    for (MmTask *e = gList; e != nullptr; e = e->next)
        nmx_xnu_census_add(c, e->task, e->pid, e->name, 0, 0);
    for (UserWire *w = gWires; w != nullptr; w = w->next)
        nmx_xnu_census_add(c, w->task, w->pid, w->name, 1, w->npages);
    IOLockUnlock(gLock);
    nmx_xnu_devfs_census(c);
}

/* every task the port still references whose process is gone; why: what asked */
extern "C" void nmx_xnu_census(const char *why)
{
    Census *c = IONew(Census, 1);
    if (c == nullptr)
        return;
    bzero(c, sizeof(*c));
    census_fill(c);
    int gone = 0;
    for (int i = 0; i < c->n; i++) {
        CensusRow *r = &c->row[i];
        if (census_alive(r->pid, r->name))
            continue;
        gone++;
        IOLog("NullMoth GPU: census (%s): pid %d (%s) is gone; its task held by %u mm record(s), %u fixed mapping(s), "
              "%u open(s); %u wiring(s) of its memory left (%llu pages)\n", why, r->pid, r->name, r->mm, r->maps,
              r->opens, r->wires, (unsigned long long)r->pages);
    }
    IOLog("NullMoth GPU: census (%s): %d process(es) referenced, %d of them gone\n", why, c->n, gone);
    IODelete(c, Census, 1);
}

/* after a gone process's last close (nmx_devfs.cpp): let its mm record go, then report what still holds the task */
extern "C" void nmx_xnu_task_gone_check(task_t task, int pid, const char *name, int secs)
{
    const int dropped = nmx_xnu_task_gone(task);
    Census *c = IONew(Census, 1);
    if (c == nullptr)
        return;
    bzero(c, sizeof(*c));
    c->only = task;
    census_fill(c);
    if (c->n > 0) {
        CensusRow *r = &c->row[0];
        IOLog("NullMoth GPU: pid %d (%s) closed its last DRM open %d s ago and is gone: %d mm record(s) let its task go; "
              "task still held by %u fixed mapping(s), %u open(s); %u wiring(s) of its memory left (%llu pages)\n", pid,
              name, secs, dropped, r->maps, r->opens, r->wires, (unsigned long long)r->pages);
    } else if (dropped > 0) {
        static SInt32 said;
        if (OSIncrementAtomic(&said) < 8)
            IOLog("NullMoth GPU: pid %d (%s) is gone: its mm record let its task go %d s after its last DRM close\n",
                  pid, name, secs);
    }
    IODelete(c, Census, 1);
}
