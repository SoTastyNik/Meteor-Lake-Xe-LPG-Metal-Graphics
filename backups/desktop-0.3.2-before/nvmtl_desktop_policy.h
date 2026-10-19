#pragma once
#include <stdint.h>
#include <string.h>
static inline int nvmtl_desktop_stall_policy(uint16_t vendor, uint16_t device,
                                            const char *process, const char *existing)
{
    return vendor == 0x8086 && device == 0x7d45 && process &&
           strcmp(process, "WindowServer") == 0 && existing == NULL;
}
