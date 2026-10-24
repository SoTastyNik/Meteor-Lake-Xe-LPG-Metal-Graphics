#ifndef ANV_LATITUDE_HEAP_H
#define ANV_LATITUDE_HEAP_H
#include <stdint.h>
#include <stdbool.h>
static inline uint64_t
anv_latitude_heap_limit(uint32_t pci_id, bool local_memory, bool darwin,
                        uint64_t normal_size)
{
   if (darwin && pci_id == 0x7d55 && !local_memory) {
      const uint64_t limit = UINT64_C(4) << 30;
      return normal_size < limit ? normal_size : limit;
   }
   return normal_size;
}
#endif
