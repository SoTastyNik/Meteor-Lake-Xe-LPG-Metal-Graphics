/*
 * Wired memory and kernel mappings for the port, on IOKit memory descriptors. Compiled with Apple's headers only.
 *
 * Allocations are IOBufferMemoryDescriptors (wired, kernel-mapped); a physically contiguous one is requested with
 * kIOMemoryPhysicallyContiguous and a physical mask derived from the caller's address limit and alignment.
 * Mappings of physical memory (GPU BARs, vmap of scattered pages) are IOMemoryDescriptor mappings into the kernel
 * with the requested cache mode, which is how IOKit drivers get write-combined or uncached views.
 */
#include <IOKit/IOBufferMemoryDescriptor.h>
#include <IOKit/IOMemoryDescriptor.h>
#include <IOKit/IOMultiMemoryDescriptor.h>
#include <IOKit/IOLib.h>
#include <IOKit/IOPlatformExpert.h>
#include <sys/errno.h>
#include <libkern/OSAtomic.h>
#include "nmx_xnu.h"

extern "C" int nmx_xnu_firmware_scanout(uint64_t *base, uint64_t *size)
{
    if (!base || !size) return EINVAL;
    *base = *size = 0;
    PE_Video v = {};
    IOPlatformExpert *pe = IOService::getPlatform();
    if (!pe || pe->getConsoleInfo(&v) != kIOReturnSuccess ||
        !v.v_baseAddr || (v.v_baseAddr & 4095) || v.v_depth != 32 ||
        v.v_width < 640 || v.v_width > 16384 ||
        v.v_height < 480 || v.v_height > 16384 ||
        v.v_rowBytes < v.v_width * 4 ||
        (uint64_t)v.v_rowBytes > UINT64_MAX / v.v_height)
        return EINVAL;
    *base = v.v_baseAddr;
    *size = (uint64_t)v.v_rowBytes * v.v_height;
    return 0;
}

extern "C" {
extern void *kernel_pmap;
extern ppnum_t pmap_find_phys(void *pmap, addr64_t va);
}

static IOOptionBits cache_option(int cache)
{
    switch (cache) {
    case NMX_CACHE_UC: return kIOMapInhibitCache;
    case NMX_CACHE_WC: return kIOMapWriteCombineCache;
    case NMX_CACHE_WT: return kIOMapWriteThruCache;
    default: return kIOMapDefaultCache;
    }
}

extern "C" void *nmx_xnu_mem_alloc(size_t size, int contiguous, uint64_t max_phys, size_t align, void **handle)
{
    IOBufferMemoryDescriptor *md;
    *handle = nullptr;
    if (!size) return nullptr;
    if (contiguous) {
        /* the mask's low bits force alignment, its high bits bound the physical address */
        mach_vm_address_t mask = (max_phys ? (mach_vm_address_t)max_phys : ~0ULL);
        if (align > PAGE_SIZE)
            mask &= ~((mach_vm_address_t)align - 1);
        else
            mask &= ~((mach_vm_address_t)PAGE_SIZE - 1);
        md = IOBufferMemoryDescriptor::inTaskWithPhysicalMask(kernel_task,
                 kIODirectionInOut | kIOMemoryPhysicallyContiguous | kIOMemoryHostPhysicallyContiguous |
                 kIOMemoryMapperNone | kIOMemoryKernelUserShared, size, mask);
    } else {
        md = IOBufferMemoryDescriptor::inTaskWithOptions(kernel_task, kIODirectionInOut | kIOMemoryKernelUserShared,
                                                         size, PAGE_SIZE);
    }
    if (md == nullptr)
        return nullptr;
    if (md->prepare() != kIOReturnSuccess) {
        md->release();
        return nullptr;
    }
    if (contiguous) {
        IOByteCount span=0;
        const addr64_t physical=md->getPhysicalSegment(0,&span,kIOMemoryMapperNone);
        if (!physical || span<size || physical>~(addr64_t)0-(size-1) ||
            (max_phys && (physical>max_phys || size-1>max_phys-physical)) ||
            (align>1 && physical%align)) {
            md->complete(); md->release(); return nullptr;
        }
    }
    *handle = md;
    return md->getBytesNoCopy();
}

extern "C" void nmx_xnu_mem_free(void *handle)
{
    IOBufferMemoryDescriptor *md = (IOBufferMemoryDescriptor *)handle;
    if (md == nullptr)
        return;
    md->complete();
    md->release();
}

extern "C" uint64_t nmx_xnu_kva_to_phys(const void *va)
{
    ppnum_t pn = pmap_find_phys(kernel_pmap, (addr64_t)(uintptr_t)va);
    if (pn == 0)
        return 0;
    return ((uint64_t)pn << PAGE_SHIFT) | ((uintptr_t)va & PAGE_MASK);
}

extern "C" void *nmx_xnu_map_phys(uint64_t pa, size_t size, int cache, void **handle)
{
    *handle = nullptr;
    uint64_t base = pa & ~(uint64_t)PAGE_MASK;
    size_t len = (size_t)(((pa + size + PAGE_MASK) & ~(uint64_t)PAGE_MASK) - base);
    IOMemoryDescriptor *md = IOMemoryDescriptor::withPhysicalAddress((IOPhysicalAddress)base, len, kIODirectionInOut);
    if (md == nullptr)
        return nullptr;
    IOMemoryMap *map = md->createMappingInTask(kernel_task, 0, kIOMapAnywhere | cache_option(cache));
    md->release();      /* the map keeps the descriptor */
    if (map == nullptr)
        return nullptr;
    *handle = map;
    return (void *)(uintptr_t)(map->getVirtualAddress() + (pa - base));
}

extern "C" void *nmx_xnu_map_pages(const uint64_t *pages, size_t npages, int cache, void **handle)
{
    *handle = nullptr;
    if (npages == 0)
        return nullptr;
    IOAddressRange *ranges = (IOAddressRange *)IOMalloc(sizeof(IOAddressRange) * npages);
    if (ranges == nullptr)
        return nullptr;
    /* coalesce physically adjacent pages into one range each */
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
    /*
     * One physical descriptor per range, mapped back to back by an IOMultiMemoryDescriptor. A single multi-range
     * kIOMemoryTypePhysical64 descriptor mapped only its first range into the kernel: xe's LRC copy (xe_lrc_init)
     * faulted on the first page past the first physically contiguous run of a 9-page BO.
     */
    IOMemoryDescriptor *md = nullptr;
    IOMemoryDescriptor **parts = (IOMemoryDescriptor **)IOMalloc(sizeof(*parts) * n);
    size_t made = 0;
    if (parts != nullptr) {
        for (; made < n; made++) {
            parts[made] = IOMemoryDescriptor::withAddressRanges(&ranges[made], 1,
                              kIODirectionInOut | kIOMemoryTypePhysical64, nullptr);
            if (parts[made] == nullptr)
                break;
        }
        if (made == n)
            md = n == 1 ? parts[0] : IOMultiMemoryDescriptor::withDescriptors(parts, (UInt32)n, kIODirectionInOut, false);
        if (md != nullptr && n == 1)
            md->retain();
        for (size_t i = 0; i < made; i++)
            parts[i]->release();
        IOFree(parts, sizeof(*parts) * n);
    }
    IOFree(ranges, sizeof(IOAddressRange) * npages);
    if (md == nullptr)
        return nullptr;
    IOMemoryMap *map = md->createMappingInTask(kernel_task, 0, kIOMapAnywhere | cache_option(cache));
    md->release();
    if (map == nullptr)
        return nullptr;
    *handle = map;
    return (void *)(uintptr_t)map->getVirtualAddress();
}

extern "C" void nmx_xnu_unmap(void *handle)
{
    IOMemoryMap *map = (IOMemoryMap *)handle;
    if (map)
        map->release();
}
