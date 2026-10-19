#pragma once
#include <stdint.h>
#include <string.h>
static inline int nvmtl_desktop_stall_policy(uint16_t vendor, uint16_t device,
                                            const char *process, const char *existing)
{
    return vendor == 0x8086 && device == 0x7d45 && process &&
           strcmp(process, "WindowServer") == 0 && existing == NULL;
}

static inline int nvmtl_windowserver_serial_policy(uint16_t vendor, uint16_t device, const char *process)
{
    return vendor == 0x8086 && device == 0x7d45 && process && !strcmp(process,"WindowServer");
}

/* Dedicated readback allocation: avoid TLS retention and suballocation/park reuse
   only for the physical Meteor Lake WindowServer candidate. */
static inline int nvmtl_windowserver_fresh_readback(uint16_t vendor,uint16_t device,const char *process)
{
    return nvmtl_windowserver_serial_policy(vendor,device,process);
}
