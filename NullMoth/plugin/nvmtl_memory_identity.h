#pragma once

static int nvmtl_memory_properties_valid(const VkPhysicalDeviceMemoryProperties *p)
{
    if (!p || !p->memoryHeapCount || p->memoryHeapCount > VK_MAX_MEMORY_HEAPS ||
        !p->memoryTypeCount || p->memoryTypeCount > VK_MAX_MEMORY_TYPES) return 0;
    for (uint32_t i = 0; i < p->memoryHeapCount; i++)
        if (!p->memoryHeaps[i].size) return 0;
    for (uint32_t i = 0; i < p->memoryTypeCount; i++)
        if (p->memoryTypes[i].heapIndex >= p->memoryHeapCount) return 0;
    return 1;
}

static int nvmtl_mtl_unified_identity(uint32_t vendor, uint32_t device,
                                    VkPhysicalDeviceType type)
{
    return vendor == 0x8086 && device == 0x7d55 &&
           type == VK_PHYSICAL_DEVICE_TYPE_INTEGRATED_GPU;
}

/* The port's i915 builds userptr since the HUAWEI v13 kernel (CONFIG_MMU_NOTIFIER, pin_user_pages through the
   port's IOMemoryDescriptor wiring). Host imports, and with them IOSurface textures rendered in place, are opted into
   with /Library/GPUBundles/nvmtl-host-import until they are proven on the MateBook. */
#include <unistd.h>
static int nvmtl_mtl_userptr_unavailable(uint32_t vendor, uint32_t device)
{
    return vendor == 0x8086 && device == 0x7d55 && access("/Library/GPUBundles/nvmtl-host-import", F_OK) != 0;
}

/* A queried budget is a limit, not dedicated VRAM or a physical reservation. */
static uint64_t nvmtl_shared_working_set(uint64_t heap, uint64_t budget)
{
    return budget < heap ? budget : heap;
}
