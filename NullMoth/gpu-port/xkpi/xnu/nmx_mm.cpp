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
};
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
    *handle = w;
    return 0;
}

extern "C" void nmx_xnu_user_unwire(void *handle)
{
    UserWire *w = (UserWire *)handle;
    if (w == nullptr)
        return;
    w->md->complete();
    w->md->release();
    task_deallocate(w->task);
    IODelete(w, UserWire, 1);
}
